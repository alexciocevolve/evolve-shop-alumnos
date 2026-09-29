import { useEffect, useRef } from "react";
import type { Product } from "../api";
import { useCart } from "../cart";
import { formatPrice } from "../format";

// A native <dialog>, not a <div> pretending to be one. The browser already gives us,
// for free and correctly: the dark backdrop, closing with Escape, keeping the keyboard
// inside the dialog while it is open, and returning the focus to the card that opened it.
// Writing all of that by hand is where hand-made modals usually get accessibility wrong.
export default function ProductModal({
  product,
  onClose,
}: {
  product: Product;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const { cart, setQuantity } = useCart();
  const inCart = cart?.items.find((item) => item.product_id === product.id)?.quantity ?? 0;

  // showModal() is what makes it a MODAL dialog (backdrop + focus trap); simply rendering
  // the element, or setting the `open` attribute, would not. It has to happen after the
  // first render, when the element already exists in the page.
  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  return (
    <dialog
      ref={dialog}
      className="modal"
      aria-labelledby="product-modal-title"
      // Every way out - Escape, the close button, a click outside - ends in close(), which
      // fires this one event. One way back to the shop instead of three copies of it.
      onClose={onClose}
      // The backdrop is part of the <dialog> element itself, so a click that lands on the
      // element and not on the content inside it IS the click outside.
      onClick={(event) => {
        if (event.target === dialog.current) dialog.current?.close();
      }}
    >
      <div className="modal-body">
        <img
          className="modal-image"
          src={product.image_url}
          alt={product.name}
          width="400"
          height="300"
        />
        <div className="modal-text">
          <h2 id="product-modal-title">{product.name}</h2>
          <p className="modal-price">{formatPrice(product.price_cents)}</p>
          {product.stock > 0 ? (
            <span className="badge badge-ok">In stock</span>
          ) : (
            <span className="badge">Out of stock</span>
          )}
          <p className="modal-description">{product.description}</p>
          <button
            type="button"
            className="primary"
            disabled={product.stock === 0}
            onClick={() => setQuantity(product.id, inCart + 1)}
          >
            {inCart > 0 ? `Add to cart (${inCart})` : "Add to cart"}
          </button>
        </div>
      </div>

      <button
        type="button"
        className="modal-close"
        aria-label="Close"
        onClick={() => dialog.current?.close()}
      >
        &times;
      </button>
    </dialog>
  );
}
