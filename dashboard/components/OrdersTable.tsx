"use client";

import { useMemo, useState } from "react";
import type { OrderRow } from "@/lib/db";

function formatAmount(o: OrderRow): string {
  if (o.amount == null) return "–";
  const cur = o.currency ?? "";
  return `${o.amount.toFixed(2)} ${cur}`.trim();
}

function formatDate(iso: string | null): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function OrdersTable({ orders, statuses }: { orders: OrderRow[]; statuses: string[] }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return orders.filter((o) => {
      if (status !== "all" && o.status !== status) return false;
      if (!q) return true;
      return (
        o.order_id.toLowerCase().includes(q) ||
        (o.customer_id ?? "").toLowerCase().includes(q)
      );
    });
  }, [orders, query, status]);

  return (
    <>
      <div className="filters">
        <input
          type="search"
          placeholder="Search by order id or customer id…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search orders"
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="all">All statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <p className="count-note">
        Showing <strong>{filtered.length}</strong> of {orders.length} orders
      </p>

      <div className="card" style={{ padding: "6px 14px" }}>
        <table className="data">
          <thead>
            <tr>
              <th>Order</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Customer</th>
              <th>Ordered</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((o) => (
              <tr key={o.order_id}>
                <td className="mono">{o.order_id}</td>
                <td>{formatAmount(o)}</td>
                <td>
                  {o.status ? <span className="badge neutral">{o.status}</span> : <span className="muted">–</span>}
                </td>
                <td className="mono">{o.customer_id ?? <span className="muted">–</span>}</td>
                <td>{formatDate(o.ordered_at)}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="muted" style={{ textAlign: "center", padding: "30px" }}>
                  No orders match this search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
