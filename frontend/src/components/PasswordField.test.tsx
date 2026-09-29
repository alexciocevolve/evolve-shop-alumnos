import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import PasswordField from "./PasswordField";

function renderField(autoComplete: "current-password" | "new-password" = "current-password") {
  const ref = createRef<HTMLInputElement>();
  render(
    <PasswordField id="password" label="Password" inputRef={ref} autoComplete={autoComplete} />,
  );
  return { ref, input: screen.getByLabelText("Password") };
}

describe("PasswordField", () => {
  // This test exists because the bug was real: with a controlled <input value={...}>,
  // React writes the text into the element's value ATTRIBUTE, so the password ends up in
  // the page's HTML and anything that serialises the DOM - a session recorder, a crash
  // reporter, an extension - carries it away in plain text.
  it("never writes what is typed into the page's HTML", async () => {
    const { input } = renderField();

    await userEvent.type(input, "a-long-test-passphrase");

    expect(input).toHaveValue("a-long-test-passphrase"); // the live property, as it must be
    expect(input.getAttribute("value")).toBeNull(); // the attribute, which must stay empty
    expect(document.body.innerHTML).not.toContain("a-long-test-passphrase");
    expect(input.outerHTML).not.toContain("a-long-test-passphrase");
  });

  it("hands the field back through the ref, because nothing keeps it in state", async () => {
    const { ref, input } = renderField();

    await userEvent.type(input, "read-me-on-submit");

    // How the form reads it when it is sent: from the element, once, at that moment.
    expect(ref.current?.value).toBe("read-me-on-submit");
  });

  it("is masked until asked otherwise, and goes back to masked", async () => {
    const { input } = renderField();

    expect(input).toHaveAttribute("type", "password");

    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(input).toHaveAttribute("type", "text");

    await userEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(input).toHaveAttribute("type", "password");
  });

  it("tells a screen reader whether the password is showing", async () => {
    renderField();
    const toggle = screen.getByRole("button", { name: "Show password" });

    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("does not submit the form when the reveal button is pressed", () => {
    renderField();

    // Without type="button" a button inside a form submits it, so revealing the password
    // would try to sign in with whatever had been typed so far.
    expect(screen.getByRole("button", { name: "Show password" })).toHaveAttribute(
      "type",
      "button",
    );
  });

  it("asks a password manager for the saved password when signing in", () => {
    const { input } = renderField("current-password");

    expect(input).toHaveAttribute("autocomplete", "current-password");
    expect(input).toHaveAttribute("name", "password");
  });

  it("asks for a new one when registering, so the old one is not filled in", () => {
    const { input } = renderField("new-password");

    expect(input).toHaveAttribute("autocomplete", "new-password");
    expect(input).toHaveAttribute("name", "new-password");
  });

  it("keeps spellcheckers and autocorrect away from it", () => {
    const { input } = renderField();

    // Both would send what is typed here somewhere else to be checked, and autocorrect
    // would "helpfully" change it.
    expect(input).toHaveAttribute("spellcheck", "false");
    expect(input).toHaveAttribute("autocorrect", "off");
    expect(input).toHaveAttribute("autocapitalize", "none");
  });

  it("warns when Caps Lock is on, which is why a correct password gets refused", async () => {
    const { input } = renderField();

    expect(screen.queryByText("Caps Lock is on")).not.toBeInTheDocument();

    input.focus();
    await userEvent.keyboard("{CapsLock}a");

    expect(screen.getByText("Caps Lock is on")).toBeInTheDocument();
  });
});
