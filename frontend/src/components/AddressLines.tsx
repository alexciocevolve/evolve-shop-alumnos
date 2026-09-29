import type { Address } from "../api";

// One way of writing an address on screen, used by the cart and by the order.
export default function AddressLines({ address }: { address: Address }) {
  return (
    <address className="address-lines">
      <strong>{address.recipient_name}</strong>
      {address.street}
      <span>
        {address.postal_code} {address.city} ({address.country})
      </span>
    </address>
  );
}
