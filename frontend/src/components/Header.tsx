import { Link } from "react-router-dom";
import { useCart } from "../cart";
import AccountMenu from "./AccountMenu";

export default function Header() {
  const { itemCount } = useCart();

  return (
    <header className="site-header">
      <h1>
        <Link to="/">Evolve Shop</Link>
      </h1>
      <nav className="site-nav">
        <Link to="/cart">Cart ({itemCount})</Link>
        <AccountMenu />
      </nav>
    </header>
  );
}
