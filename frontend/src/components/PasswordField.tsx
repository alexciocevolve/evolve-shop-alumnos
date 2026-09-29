import { useState, type RefObject } from "react";

// Everything that is standard today for handling a password in a browser, in one place.
//
// This field is UNCONTROLLED - it has no value in React state, and the form reads it from
// the element when it is submitted. That is not laziness, it is the point. A controlled
// <input value={...}> makes React write the text into the element's `value` ATTRIBUTE, and
// an attribute is part of the page's HTML: anything that serialises the DOM (a session
// recorder, a crash reporter, an extension, someone copying outerHTML) would carry the
// password away in plain text. Uncontrolled, it lives only in the live value property,
// which is where the browser keeps what you type and which is not serialised.
export default function PasswordField({
  id,
  label,
  inputRef,
  autoComplete,
  minLength,
  hint,
}: {
  id: string;
  label: string;
  inputRef: RefObject<HTMLInputElement>;
  // "current-password" when signing in, "new-password" when registering. This is what
  // tells a password manager whether to offer the saved one or to offer to make a new
  // one, and it is what stops the browser filling a new-password box with the old one.
  autoComplete: "current-password" | "new-password";
  minLength?: number;
  hint?: string;
}) {
  const [visible, setVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="password-input">
        <input
          id={id}
          ref={inputRef}
          // The whole point: masked by default, and back to masked on every visit,
          // because `visible` starts false and is never remembered anywhere.
          type={visible ? "text" : "password"}
          // A name, so a password manager recognises the field and can save it.
          name={autoComplete === "new-password" ? "new-password" : "password"}
          autoComplete={autoComplete}
          minLength={minLength}
          required
          // Caps Lock on while typing blind is the commonest reason a correct password
          // is refused, so say it instead of letting them guess.
          onKeyUp={(event) => setCapsLock(event.getModifierState("CapsLock"))}
          onKeyDown={(event) => setCapsLock(event.getModifierState("CapsLock"))}
          onBlur={() => setCapsLock(false)}
          // No spellchecker and no autocorrect: they would send what is typed here off to
          // be checked somewhere else, and would "helpfully" change it.
          spellCheck={false}
          autoCorrect="off"
          autoCapitalize="none"
        />
        {/* type="button", or pressing it would submit the form. aria-pressed tells a
            screen reader whether the password is showing right now. */}
        <button
          type="button"
          className="reveal"
          aria-pressed={visible}
          aria-controls={id}
          aria-label={visible ? "Hide password" : "Show password"}
          title={visible ? "Hide password" : "Show password"}
          onClick={() => setVisible((shown) => !shown)}
        >
          {visible ? "Hide" : "Show"}
        </button>
      </div>
      {hint && <p className="field-hint">{hint}</p>}
      {/* A live region, so the warning is announced when it appears and not only seen. */}
      <p className="field-warning" role="status">
        {capsLock ? "Caps Lock is on" : ""}
      </p>
    </div>
  );
}
