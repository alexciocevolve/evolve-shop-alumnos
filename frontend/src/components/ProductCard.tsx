import type { Product } from "../api";
import { formatPrice } from "../format";

export default function ProductCard({ product }: { product: Product }) {
  return (
    <article className="card">
      {/* loading="lazy": the browser downloads this image only when it is about to be
          seen. width/height reserve its space so the page does not jump when it arrives. */}
      <img src={product.image_url} alt={product.name} loading="lazy" width="400" height="300" />
      <div className="card-body">
        <h3>{product.name}</h3>
        <span className="price">{formatPrice(product.price_cents)}</span>
        {product.stock === 0 && <span className="badge">Out of stock</span>}
      </div>
    </article>
  );
}
