"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type State = "idle" | "running" | "done" | "error";

export default function ExecuteButton() {
  const router = useRouter();
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState("");

  async function run() {
    setState("running");
    setMessage("");
    try {
      const res = await fetch("/api/execute", { method: "POST" });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || `Sync failed (HTTP ${res.status})`);
      }
      setState("done");
      setMessage(
        `Fetched ${data.fetched}, ${data.new_rows} new, ${data.total_rows} total. ` +
          `Quality ${data.quality_passed ? "passed" : "FAILED"}.`
      );
      router.refresh();
    } catch (e) {
      setState("error");
      setMessage(e instanceof Error ? e.message : "Sync failed.");
    }
  }

  return (
    <div className="execute-wrap">
      <button className="btn-execute" onClick={run} disabled={state === "running"}>
        {state === "running" ? "Running…" : "Execute sync"}
      </button>
      {message && <span className={`run-status ${state}`}>{message}</span>}
    </div>
  );
}
