"use client";

import { useState } from "react";
import type { SyncRun } from "@/lib/db";

function formatRunTime(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function RunCard({ run }: { run: SyncRun }) {
  const [open, setOpen] = useState(false);
  const passed = run.quality_passed === 1;

  return (
    <div className="run">
      <div className="run-head" onClick={() => setOpen((v) => !v)} role="button" tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setOpen((v) => !v); }}>
        <div className="meta">
          <span className="time">{formatRunTime(run.run_at)}</span>
          <span className={`badge ${passed ? "pass" : "fail"}`}>
            {passed ? "Quality passed" : "Quality failed"}
          </span>
          {run.dry_run === 1 && <span className="badge neutral">Dry run</span>}
        </div>
        <div className="muted">
          <span className="mono">{run.orders_fetched}</span> fetched ·{" "}
          <span className="mono">{run.new_rows}</span> new ·{" "}
          <span className="mono">{run.total_rows ?? "–"}</span> total
        </div>
      </div>
      {open && (
        <div className="run-checks">
          {run.checks.map((c) => (
            <div className="check" key={c.name}>
              <span className={`dot ${c.passed ? "pass" : "fail"}`} aria-hidden />
              <span className="name">{c.name}</span>
              <span className="detail">{c.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
