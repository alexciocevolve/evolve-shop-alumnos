import { useEffect, useRef, useState } from "react";
import { listProducts, type ApiError, type Product } from "../api";
import ProductCard from "../components/ProductCard";

// The API has no endpoint that lists the categories, so they are fixed here.
const CATEGORIES = ["laptops", "monitors", "peripherals", "storage", "networking"];

export default function Catalog() {
  const [category, setCategory] = useState<string | undefined>();
  const [items, setItems] = useState<Product[]>([]);
  // Cursor of the next page to ask for. 0 means "from the start", so the first page goes
  // through exactly the same code as every other one. null means "there are no more".
  const [nextCursor, setNextCursor] = useState<number | null>(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sentinel = useRef<HTMLDivElement>(null);
  // Bumped on every category change, so an answer that arrives late for the previous
  // category can be recognised and thrown away instead of polluting the new list.
  const generation = useRef(0);

  function loadPage(cursor: number) {
    const mine = generation.current;
    setLoading(true);
    listProducts({ category, cursor }).then(
      (page) => {
        if (mine !== generation.current) return;
        setItems((current) => [...current, ...page.items]); // concatenate, never replace
        setNextCursor(page.next_cursor);
        setLoading(false);
      },
      (e: ApiError) => {
        if (mine !== generation.current) return;
        setError(e.detail);
        setLoading(false);
      },
    );
  }

  function selectCategory(next: string | undefined) {
    if (next === category) return;
    generation.current += 1;
    setCategory(next);
    setItems([]); // changing category empties the list and starts again from the top
    setNextCursor(0);
    setLoading(false);
    setError(null);
  }

  // Lazy loading of the NEXT PAGE (not of the images: that is loading="lazy" in ProductCard).
  // An empty <div> sits after the grid; when it scrolls into view, we ask for the next page.
  // The observer is re-created after every page, because observe() reports the current
  // state right away: if the sentinel is still visible (a tall screen), we keep loading.
  useEffect(() => {
    const element = sentinel.current;
    if (!element || nextCursor === null || loading || error) return;

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) loadPage(nextCursor);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [category, nextCursor, loading, error]);

  return (
    <>
      <div className="filters">
        <button className="chip" aria-pressed={category === undefined} onClick={() => selectCategory(undefined)}>
          All
        </button>
        {CATEGORIES.map((c) => (
          <button key={c} className="chip" aria-pressed={category === c} onClick={() => selectCategory(c)}>
            {c}
          </button>
        ))}
      </div>

      <div className="grid">
        {items.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>

      <div ref={sentinel} className="sentinel" />

      {loading && <p className="status">Loading…</p>}
      {error && (
        <p className="status error">
          {error}{" "}
          <button className="chip" onClick={() => setError(null)}>
            Try again
          </button>
        </p>
      )}
      {!loading && !error && nextCursor === null && items.length === 0 && (
        <p className="status">No products in this category.</p>
      )}
    </>
  );
}
