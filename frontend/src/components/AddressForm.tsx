import { useEffect, useState, type FormEvent } from "react";
import type { Address, AddressInput, AddressKind } from "../api";

const EMPTY: AddressInput = {
  recipient_name: "",
  street: "",
  city: "",
  postal_code: "",
  country: "ES",
};

// One component for both addresses: they hold the same fields, and the only difference is
// which slot on the server they are saved into.
export default function AddressForm({
  kind,
  title,
  address,
  onSave,
  onDelete,
  onCopyFromShipping,
}: {
  kind: AddressKind;
  title: string;
  address: Address | null;
  onSave: (kind: AddressKind, values: AddressInput) => Promise<string | null>;
  onDelete: (kind: AddressKind) => Promise<string | null>;
  onCopyFromShipping?: () => AddressInput | null;
}) {
  const [values, setValues] = useState<AddressInput>(EMPTY);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // When the saved address arrives (or changes), the boxes show it. Editing one of them
  // only changes what is on screen: nothing is stored until Save is pressed.
  useEffect(() => {
    setValues(
      address
        ? {
            recipient_name: address.recipient_name,
            street: address.street,
            city: address.city,
            postal_code: address.postal_code,
            country: address.country,
          }
        : EMPTY,
    );
  }, [address]);

  function set(field: keyof AddressInput, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setStatus(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const failure = await onSave(kind, { ...values, country: values.country.toUpperCase() });
    setBusy(false);
    if (failure) setError(failure);
    else setStatus("Saved");
  }

  return (
    <form className="address-form" onSubmit={submit}>
      <div className="address-head">
        <h3>{title}</h3>
        {onCopyFromShipping && (
          <button
            type="button"
            className="chip"
            onClick={() => {
              const copied = onCopyFromShipping();
              if (copied) {
                setValues(copied);
                // Deliberately not saved straight away: it fills the boxes so the lines
                // can still be changed - a company name, a different recipient - before
                // this becomes a second row in the table.
                setStatus("Copied. Press Save to keep it.");
              } else {
                setStatus("There is no shipping address to copy yet.");
              }
            }}
          >
            Copy from shipping
          </button>
        )}
      </div>

      <div className="field">
        <label htmlFor={`${kind}-recipient`}>Recipient name</label>
        <input
          id={`${kind}-recipient`}
          autoComplete={kind === "billing" ? "billing name" : "shipping name"}
          required
          value={values.recipient_name}
          onChange={(event) => set("recipient_name", event.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor={`${kind}-street`}>Street</label>
        {/* autoComplete tells the browser which address this is, so it can offer the
            right saved one instead of putting the home address into both forms. */}
        <input
          id={`${kind}-street`}
          autoComplete={kind === "billing" ? "billing street-address" : "shipping street-address"}
          required
          value={values.street}
          onChange={(event) => set("street", event.target.value)}
        />
      </div>

      <div className="address-row">
        <div className="field">
          <label htmlFor={`${kind}-postal`}>Postal code</label>
          <input
            id={`${kind}-postal`}
            autoComplete={kind === "billing" ? "billing postal-code" : "shipping postal-code"}
            required
            value={values.postal_code}
            onChange={(event) => set("postal_code", event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={`${kind}-city`}>City</label>
          <input
            id={`${kind}-city`}
            autoComplete={kind === "billing" ? "billing address-level2" : "shipping address-level2"}
            required
            value={values.city}
            onChange={(event) => set("city", event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={`${kind}-country`}>Country</label>
          <input
            id={`${kind}-country`}
            autoComplete={kind === "billing" ? "billing country" : "shipping country"}
            required
            minLength={2}
            maxLength={2}
            size={2}
            spellCheck={false}
            autoCapitalize="characters"
            value={values.country}
            onChange={(event) => set("country", event.target.value)}
          />
        </div>
      </div>
      <p className="field-hint">Country as two letters: ES, PT, FR…</p>

      {error && (
        <p className="status error" role="alert">
          {error}
        </p>
      )}

      <div className="address-actions">
        {/* A live region: "Saved" is announced, not only shown. */}
        <span className="field-hint" role="status">
          {status ?? ""}
        </span>
        {address && (
          <button
            type="button"
            className="link-button"
            onClick={async () => {
              setError(await onDelete(kind));
              setStatus(null);
            }}
          >
            Delete
          </button>
        )}
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Saving…" : address ? "Save changes" : "Save address"}
        </button>
      </div>
    </form>
  );
}
