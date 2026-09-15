import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Partner Integration Dashboard",
  description: "Sync run history, quality gates, and synced orders for the partner integration pipeline.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <Sidebar />
          <div className="content">
            <main className="wrap page">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
