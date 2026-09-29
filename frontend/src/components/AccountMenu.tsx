import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../session";

export default function AccountMenu() {
  const { user, loading, signOut } = useSession();
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // The three ways out of an open menu that people expect. Unlike the product detail,
  // this one is not a <dialog>, so they have to be wired by hand: a menu must not trap
  // the keyboard or block the page behind it the way a modal does.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function go(to: string) {
    setOpen(false);
    navigate(to);
  }

  return (
    <div className="account" ref={container}>
      <button
        type="button"
        className="account-button"
        // These two are what make a dropdown announce itself as one, instead of as a
        // button that mysteriously changes the page when pressed.
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((shown) => !shown)}
      >
        {/* While the stored token is still being checked, say nothing rather than
            flashing "Sign in" at somebody who turns out to be signed in. */}
        {loading ? "…" : user ? user.full_name : "Account"}
        <span aria-hidden="true" className="caret">
          ▾
        </span>
      </button>

      {open && (
        <div className="account-menu" role="menu">
          {user ? (
            <>
              <p className="account-who">
                Signed in as
                <strong>{user.email}</strong>
              </p>
              <button type="button" role="menuitem" onClick={() => go("/account")}>
                My account
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={async () => {
                  setOpen(false);
                  await signOut();
                  navigate("/");
                }}
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <button type="button" role="menuitem" onClick={() => go("/auth")}>
                Sign in
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => go("/auth?mode=register")}
              >
                Create account
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
