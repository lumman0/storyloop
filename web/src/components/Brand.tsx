import { Link } from "react-router-dom";
import { Feather } from "lucide-react";

export function Brand({ light = false }: { light?: boolean }) {
  return (
    <Link
      to="/"
      className={`brand ${light ? "brand-light" : ""}`}
      aria-label="Storyloop 首页"
    >
      <span className="brand-mark">
        <Feather size={18} strokeWidth={1.8} />
      </span>
      <span>
        storyloop<span className="brand-dot">.</span>
      </span>
    </Link>
  );
}
