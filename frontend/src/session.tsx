import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  AUTH_TOKEN_KEY,
  getMe,
  registerUser,
  signIn,
  signOut,
  type ApiError,
  type User,
} from "./api";

type SessionValue = {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<string | null>;
  register: (email: string, password: string, fullName: string) => Promise<string | null>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) throw new Error("useSession used outside SessionProvider");
  return value;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // True until we know whether the stored token is still good, so the header does not
  // flash "Sign in" for a moment at every page load for somebody who is signed in.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!localStorage.getItem(AUTH_TOKEN_KEY)) {
      setLoading(false);
      return;
    }
    // Who the token belongs to is asked of the server, never read out of the token in
    // the browser: only the server can say whether it is still valid.
    getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // These two return the error message to show, or null when it worked. The password is
  // an argument and nothing more: it is never put into state, so it cannot end up in a
  // re-render, in the React developer tools, or in a component that logs its props.
  async function doSignIn(email: string, password: string): Promise<string | null> {
    try {
      const { token } = await signIn(email, password);
      localStorage.setItem(AUTH_TOKEN_KEY, token);
      setUser(await getMe());
      return null;
    } catch (e) {
      return (e as ApiError).detail;
    }
  }

  async function doRegister(
    email: string,
    password: string,
    fullName: string,
  ): Promise<string | null> {
    try {
      await registerUser(email, password, fullName);
      // Registering signs you in: asking for the same password twice in a row would be
      // one more chance to mistype it and no more secure.
      return doSignIn(email, password);
    } catch (e) {
      return (e as ApiError).detail;
    }
  }

  async function doSignOut() {
    // Tell the server first, so the token stops working for anyone who copied it, and
    // then forget it here. Even if the call fails, this browser must let go of it.
    await signOut().catch(() => undefined);
    localStorage.removeItem(AUTH_TOKEN_KEY);
    setUser(null);
  }

  return (
    <SessionContext.Provider
      value={{ user, loading, signIn: doSignIn, register: doRegister, signOut: doSignOut }}
    >
      {children}
    </SessionContext.Provider>
  );
}
