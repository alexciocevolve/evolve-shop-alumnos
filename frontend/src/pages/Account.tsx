import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  deleteAddress,
  listAddresses,
  saveAddress,
  type Address,
  type AddressInput,
  type AddressKind,
  type ApiError,
} from "../api";
import AddressForm from "../components/AddressForm";
import { formatDate } from "../format";
import { useSession } from "../session";

export default function Account() {
  const { user, loading } = useSession();
  const [addresses, setAddresses] = useState<Address[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    listAddresses().then(setAddresses, (e: ApiError) => setLoadError(e.detail));
  }, [user]);

  // Wait for the stored token to be checked before deciding; otherwise a reload of this
  // page would bounce a signed-in person to the sign-in form for a moment.
  if (loading) return <p className="status">Loading…</p>;
  if (!user) return <Navigate to="/auth" replace />;

  const find = (kind: AddressKind) => addresses?.find((a) => a.kind === kind) ?? null;

  // Both actions end by storing what the server replied, never a guess made here: the
  // same rule the cart follows.
  async function save(kind: AddressKind, values: AddressInput): Promise<string | null> {
    try {
      const saved = await saveAddress(kind, values);
      setAddresses((current) => [...(current ?? []).filter((a) => a.kind !== kind), saved]);
      return null;
    } catch (e) {
      return (e as ApiError).detail;
    }
  }

  async function remove(kind: AddressKind): Promise<string | null> {
    try {
      await deleteAddress(kind);
      setAddresses((current) => (current ?? []).filter((a) => a.kind !== kind));
      return null;
    } catch (e) {
      return (e as ApiError).detail;
    }
  }

  return (
    <div className="account-page">
      <h2>My account</h2>
      <p className="status">
        {user.full_name} · {user.email} · joined {formatDate(user.created_at)}
      </p>

      {loadError && <p className="status error">{loadError}</p>}

      {addresses === null && !loadError ? (
        <p className="status">Loading addresses…</p>
      ) : (
        <div className="addresses">
          <AddressForm
            kind="shipping"
            title="Shipping address"
            address={find("shipping")}
            onSave={save}
            onDelete={remove}
          />
          <AddressForm
            kind="billing"
            title="Billing address"
            address={find("billing")}
            onSave={save}
            onDelete={remove}
            // The two addresses are separate rows, so using the same one for both means
            // storing the same lines twice. This button makes that one click instead of
            // retyping, and it is the price of keeping the kind on the row itself.
            onCopyFromShipping={() => {
              const shipping = find("shipping");
              if (!shipping) return null;
              return {
                recipient_name: shipping.recipient_name,
                street: shipping.street,
                city: shipping.city,
                postal_code: shipping.postal_code,
                country: shipping.country,
              };
            }}
          />
        </div>
      )}
    </div>
  );
}
