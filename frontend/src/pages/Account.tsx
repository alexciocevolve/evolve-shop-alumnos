import { Navigate } from "react-router-dom";
import type { AddressKind } from "../api";
import AddressForm from "../components/AddressForm";
import { formatDate } from "../format";
import { useSession } from "../session";

export default function Account() {
  // The addresses live in the session, not here: the cart needs them too, and two copies
  // would drift apart the moment one screen saved and the other did not notice.
  const { user, loading, addresses, saveAddress, removeAddress } = useSession();

  // Wait for the stored token to be checked before deciding; otherwise a reload of this
  // page would bounce a signed-in person to the sign-in form for a moment.
  if (loading) return <p className="status">Loading…</p>;
  if (!user) return <Navigate to="/auth" replace />;

  const find = (kind: AddressKind) => addresses?.find((a) => a.kind === kind) ?? null;

  return (
    <div className="account-page">
      <h2>My account</h2>
      <p className="status">
        {user.full_name} · {user.email} · joined {formatDate(user.created_at)}
      </p>

      {addresses === null ? (
        <p className="status">Loading addresses…</p>
      ) : (
        <div className="addresses">
          <AddressForm
            kind="shipping"
            title="Shipping address"
            address={find("shipping")}
            onSave={saveAddress}
            onDelete={removeAddress}
          />
          <AddressForm
            kind="billing"
            title="Billing address"
            address={find("billing")}
            onSave={saveAddress}
            onDelete={removeAddress}
            // The two addresses are separate rows, so using the same one for both means
            // storing the same lines twice. This makes that one click instead of
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

      <p className="field-hint account-note">
        Changing an address does not overwrite the old one: it is kept, retired, so that
        orders already placed still show the address they were actually sent to.
      </p>
    </div>
  );
}
