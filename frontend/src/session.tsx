import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  AUTH_TOKEN_KEY,
  deleteAddress,
  getMe,
  listAddresses,
  registerUser,
  saveAddress,
  signIn,
  signOut,
  type Address,
  type AddressInput,
  type AddressKind,
  type ApiError,
  type User,
} from "./api";

type SessionValue = {
  user: User | null;
  loading: boolean;
  // The addresses in use, kept here rather than fetched by each screen: the account page
  // and the cart both need them, and two copies would drift apart.
  addresses: Address[] | null;
  shippingAddress: Address | null;
  signIn: (email: string, password: string) => Promise<string | null>;
  register: (email: string, password: string, fullName: string) => Promise<string | null>;
  signOut: () => Promise<void>;
  saveAddress: (kind: AddressKind, values: AddressInput) => Promise<string | null>;
  removeAddress: (kind: AddressKind) => Promise<string | null>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) throw new Error("useSession used outside SessionProvider");
  return value;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [addresses, setAddresses] = useState<Address[] | null>(null);
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

  // Whenever we know who this is, load their addresses; when they sign out, forget them
  // rather than leaving the previous person's on screen.
  useEffect(() => {
    if (!user) {
      setAddresses(null);
      return;
    }
    listAddresses().then(setAddresses, () => setAddresses([]));
  }, [user]);

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

  // Both of these end by storing what the server replied. Saving an address does not
  // change a row, it creates one, so the id that comes back is a new id - which is
  // exactly why the answer has to replace what was there instead of being patched.
  async function doSaveAddress(
    kind: AddressKind,
    values: AddressInput,
  ): Promise<string | null> {
    try {
      const saved = await saveAddress(kind, values);
      setAddresses((current) => [...(current ?? []).filter((a) => a.kind !== kind), saved]);
      return null;
    } catch (e) {
      return (e as ApiError).detail;
    }
  }

  async function doRemoveAddress(kind: AddressKind): Promise<string | null> {
    try {
      await deleteAddress(kind);
      setAddresses((current) => (current ?? []).filter((a) => a.kind !== kind));
      return null;
    } catch (e) {
      return (e as ApiError).detail;
    }
  }

  return (
    <SessionContext.Provider
      value={{
        user,
        loading,
        addresses,
        shippingAddress: addresses?.find((a) => a.kind === "shipping") ?? null,
        signIn: doSignIn,
        register: doRegister,
        signOut: doSignOut,
        saveAddress: doSaveAddress,
        removeAddress: doRemoveAddress,
      }}
    >
      {children}
    </SessionContext.Provider>
  );
}
