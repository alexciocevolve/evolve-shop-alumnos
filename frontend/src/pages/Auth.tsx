import { useRef, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import PasswordField from "../components/PasswordField";
import { useSession } from "../session";

const MIN_PASSWORD_LENGTH = 8;

export default function Auth() {
  const [params, setParams] = useSearchParams();
  // Which form is showing is kept in the address, so "Create account" in the menu can
  // land straight on the right one and the back button does what it should.
  const registering = params.get("mode") === "register";

  const { signIn, register } = useSession();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  // The password is the one field NOT kept in state: see PasswordField for why. It is
  // read from the element at the moment it is sent, and wiped straight afterwards.
  const passwordInput = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function clearPassword() {
    if (passwordInput.current) passwordInput.current.value = "";
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const password = passwordInput.current?.value ?? "";
    setBusy(true);
    setError(null);
    const failure = registering
      ? await register(email, password, fullName)
      : await signIn(email, password);
    // Whatever happened, the box is emptied as soon as the answer is in: on success it
    // is not needed any more, and on failure it gets typed again.
    clearPassword();
    setBusy(false);
    if (failure) setError(failure);
    else navigate("/");
  }

  function switchMode(next: boolean) {
    setParams(next ? { mode: "register" } : {}, { replace: true });
    setError(null);
    clearPassword();
  }

  return (
    <div className="auth">
      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          className="chip"
          aria-selected={!registering}
          onClick={() => switchMode(false)}
        >
          Sign in
        </button>
        <button
          type="button"
          role="tab"
          className="chip"
          aria-selected={registering}
          onClick={() => switchMode(true)}
        >
          Create account
        </button>
      </div>

      {/* A real <form>: Enter submits it, and password managers only offer to save when
          they see a form being sent rather than a button calling some function. */}
      <form onSubmit={submit}>
        <h2>{registering ? "Create your account" : "Sign in"}</h2>

        {registering && (
          <div className="field">
            <label htmlFor="full-name">Full name</label>
            <input
              id="full-name"
              name="name"
              autoComplete="name"
              required
              minLength={1}
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </div>
        )}

        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            // autoComplete="username" and not "email": it is what pairs this box with
            // the password box so a manager saves and fills the two together.
            name="username"
            autoComplete="username"
            required
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize="none"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <PasswordField
          id="password"
          label="Password"
          inputRef={passwordInput}
          autoComplete={registering ? "new-password" : "current-password"}
          minLength={registering ? MIN_PASSWORD_LENGTH : undefined}
          hint={
            registering
              ? `At least ${MIN_PASSWORD_LENGTH} characters. A long phrase you can remember beats a short one full of symbols.`
              : undefined
          }
        />

        {/* One message for a wrong password and for an email nobody has registered: the
            server answers the same on purpose, and the screen must not add to it. */}
        {error && (
          <p className="status error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Working…" : registering ? "Create account" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
