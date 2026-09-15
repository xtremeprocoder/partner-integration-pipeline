import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Partner Integration Dashboard",
  description: "Sync run history, quality gates, and synced orders for the partner integration pipeline.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="wrap header-inner">
            <Link href="/" className="brand">
              <span className="brand-mark" aria-hidden />
              Partner Integration
            </Link>
            <nav>
              <Link href="/">Sync runs</Link>
              <Link href="/orders">Orders</Link>
            </nav>
          </div>
        </header>
        <main className="wrap page">{children}</main>
        <footer className="wrap site-footer">
          Reads the same SQLite database the sync pipeline writes. Set <span className="mono">SYNC_DB_PATH</span> to
          point it at a different database.
        </footer>
      </body>
    </html>
  );
}
