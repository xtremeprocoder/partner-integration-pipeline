import RunCard from "@/components/RunCard";
import { dbPath, getRuns } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function Home() {
  const runs = await getRuns();
  const latest = runs[0];

  if (runs.length === 0) {
    return (
      <div className="empty">
        <h2>No sync runs yet</h2>
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
      <h1>Sync runs</h1>
      <p className="lede">
        Every pipeline run, with its quality gate verdict. Click a run to see the per-check
        results that gated the write.
      </p>

      <div className="stats">
        <div className="stat">
          <div className="label">Total runs</div>
          <div className="value">{runs.length}</div>
        </div>
        <div className="stat">
          <div className="label">Latest run fetched</div>
          <div className="value">{latest.orders_fetched}</div>
        </div>
        <div className="stat">
          <div className="label">New rows (latest)</div>
          <div className="value accent">{latest.new_rows}</div>
        </div>
        <div className="stat">
          <div className="label">Orders in store</div>
          <div className="value">{latest.total_rows ?? "–"}</div>
        </div>
      </div>

      <div className="card">
        <h2>Run history</h2>
        <p className="sub">Newest first. Dry runs are marked and write nothing.</p>
        {runs.map((run) => (
          <RunCard key={run.id} run={run} />
        ))}
      </div>
    </>
  );
}
