"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Sync runs" },
  { href: "/orders", label: "Orders" },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <Link href="/" className="brand">
        <span className="brand-mark" aria-hidden />
        <span>
          Partner
          <br />
          Integration
        </span>
      </Link>
      <nav>
        {links.map((l) => {
          const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
          return (
            <Link key={l.href} href={l.href} className={active ? "active" : ""}>
              {l.label}
            </Link>
          );
        })}
      </nav>
      <p className="sidebar-note">
        Reads the same SQLite database the sync pipeline writes.
      </p>
    </aside>
  );
}
