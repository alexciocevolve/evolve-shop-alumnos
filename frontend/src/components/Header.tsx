import { Link } from "react-router-dom";
import { useCart } from "../cart";

export default function Header() {
  const { itemCount } = useCart();

  return (
    <header className="site-header">
      <h1>
        <Link to="/">Evolve Shop</Link>
      </h1>
      <Link to="/cart">Cart ({itemCount})</Link>
    </header>
  );
}
