import { createClient, type Client } from "@libsql/client";
import { existsSync } from "node:fs";
import path from "node:path";

/**
 * Data source for the dashboard.
 *
 * - Remote (hosted): set TURSO_DATABASE_URL (and TURSO_AUTH_TOKEN). The sync
 *   pipeline writes to the same database, so the hosted dashboard stays live.
 * - Local (dev): defaults to the SQLite file the sync writes, overridable
 *   with SYNC_DB_PATH.
 */
function databaseUrl(): string {
  const remote = process.env.TURSO_DATABASE_URL;
  if (remote) return remote;
  const p = path.resolve(process.cwd(), process.env.SYNC_DB_PATH ?? "../demo.db");
  return "file:" + p;
}

/** Human-readable description of the data source, for the empty-state UI. */
export function dbPath(): string {
  const remote = process.env.TURSO_DATABASE_URL;
  if (remote) {
    try {
      return new URL(remote).host;
    } catch {
      return "Turso";
    }
  }
  return path.resolve(process.cwd(), process.env.SYNC_DB_PATH ?? "../demo.db");
}

let client: Client | null = null;

function getClient(): Client | null {
  if (client) return client;
  const url = databaseUrl();
  if (url.startsWith("file:") && !existsSync(url.slice("file:".length))) return null;
  client = createClient({ url, authToken: process.env.TURSO_AUTH_TOKEN });
  return client;
}

export interface CheckPayload {
  name: string;
  passed: boolean;
  detail: string;
}

export interface SyncRun {
  id: number;
  run_at: string;
  orders_fetched: number;
  new_rows: number;
  total_rows: number | null;
  quality_passed: number;
  dry_run: number;
  checks: CheckPayload[];
}

export interface OrderRow {
  order_id: string;
  amount: number | null;
  currency: string | null;
  status: string | null;
  customer_id: string | null;
  ordered_at: string | null;
  synced_at: string | null;
}

type Row = Record<string, number | string | bigint | Uint8Array | null>;

const num = (v: number | string | bigint | Uint8Array | null): number | null =>
  typeof v === "bigint" ? Number(v) : typeof v === "number" ? v : null;
const str = (v: number | string | bigint | Uint8Array | null): string | null =>
  typeof v === "string" ? v : v === null ? null : String(v);

export async function getRuns(): Promise<SyncRun[]> {
  const conn = getClient();
  if (!conn) return [];
  try {
    const rs = await conn.execute("SELECT * FROM sync_runs ORDER BY id DESC");
    return (rs.rows as Row[]).map((r) => ({
      id: Number(r.id ?? 0),
      run_at: str(r.run_at) ?? "",
      orders_fetched: Number(r.orders_fetched ?? 0),
      new_rows: Number(r.new_rows ?? 0),
      total_rows: num(r.total_rows),
      quality_passed: Number(r.quality_passed ?? 0),
      dry_run: Number(r.dry_run ?? 0),
      checks: safeParseChecks(str(r.checks_json) ?? ""),
    }));
  } catch {
    return [];
  }
}

export async function getOrders(): Promise<OrderRow[]> {
  const conn = getClient();
  if (!conn) return [];
  try {
    const rs = await conn.execute(
      "SELECT order_id, amount, currency, status, customer_id, ordered_at, synced_at FROM orders ORDER BY ordered_at DESC, order_id"
    );
    return (rs.rows as Row[]).map((r) => ({
      order_id: str(r.order_id) ?? "",
      amount: num(r.amount),
      currency: str(r.currency),
      status: str(r.status),
      customer_id: str(r.customer_id),
      ordered_at: str(r.ordered_at),
      synced_at: str(r.synced_at),
    }));
  } catch {
    return [];
  }
}

export async function getStatuses(): Promise<string[]> {
  const conn = getClient();
  if (!conn) return [];
  try {
    const rs = await conn.execute(
      "SELECT DISTINCT status FROM orders WHERE status IS NOT NULL ORDER BY status"
    );
    return (rs.rows as Row[]).map((r) => str(r.status) ?? "").filter(Boolean);
  } catch {
    return [];
  }
}

function safeParseChecks(json: string): CheckPayload[] {
  try {
    const parsed = JSON.parse(json);
    if (Array.isArray(parsed)) {
      return parsed.map((c) => ({
        name: String(c.name ?? "check"),
        passed: Boolean(c.passed),
        detail: String(c.detail ?? ""),
      }));
    }
  } catch {
    // fall through
  }
  return [];
}
