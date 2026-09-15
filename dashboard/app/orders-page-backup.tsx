import OrdersTable from "@/components/OrdersTable";
import { dbPath, getOrders, getStatuses } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function OrdersPage() {
  const orders = await getOrders();

  if (orders.length === 0) {
    return (
      <div className="empty">
        <h2>No orders yet</h2>
        <p>
          Run the pipeline first to generate data:
          <br />
          <code>bash scripts/demo.sh</code> from the repo root.
        </p>
        <p className="muted">
          The dashboard reads <span className="mono">{dbPath()}</span> by default; override with{" "}
          <span className="mono">SYNC_DB_PATH</span>.
        </p>
      </div>
    );
  }

  return (
    <>
      <h1>Orders</h1>
      <p className="lede">
        The normalized orders in the store: one canonical schema, messy partner formats resolved.
      </p>
      <OrdersTable orders={orders} statuses={await getStatuses()} />
    </>
  );
}
