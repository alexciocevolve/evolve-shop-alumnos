import type { Product } from "../api";
import { useCart } from "../cart";
import { formatPrice } from "../format";

export default function ProductCard({
  product,
  onOpen,
}: {
  product: Product;
  onOpen: () => void;
}) {
  const { cart, setQuantity } = useCart();
  // How many of this product are already in the cart, so "Add" means "one more".
  const inCart =
    cart?.items.find((item) => item.product_id === product.id)?.quantity ?? 0;

  return (
    <article className="card">
      {/* loading="lazy": the browser downloads this image only when it is about to be
          seen. width/height reserve its space so the page does not jump when it arrives. */}
      <img src={product.image_url} alt={product.name} loading="lazy" width="400" height="300" />
      <div className="card-body">
        <h3>
          {/* Only the name is a button, and CSS stretches it over the whole card, so
              clicking anywhere opens the detail. Done the other way round - a <button>
              wrapped around the card - the heading would end up inside a button, which
              HTML does not allow, and the keyboard would stop at every card twice. */}
          <button type="button" className="card-open" onClick={onOpen}>
            {product.name}
          </button>
        </h3>
        <span className="price">{formatPrice(product.price_cents)}</span>
        {product.stock === 0 && <span className="badge">Out of stock</span>}
        {/* This button sits ON TOP of the stretched card button (z-index in the
            stylesheet), so clicking it adds to the cart instead of opening the detail. */}
        <button
          type="button"
          className="add"
          disabled={product.stock === 0}
          onClick={() => setQuantity(product.id, inCart + 1)}
        >
          {inCart > 0 ? `Add to cart (${inCart})` : "Add to cart"}
        </button>
      </div>
    </article>
  );
}
