// Seeds the hosted database on first deploy. Runs as part of `npm run build`
// (see package.json). Skips silently without TURSO_DATABASE_URL (local dev)
// and skips if the database already has sync runs (idempotent).
import { createClient } from "@libsql/client";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const url = process.env.TURSO_DATABASE_URL;
if (!url) {
  console.log("[seed] no TURSO_DATABASE_URL, skipping");
  process.exit(0);
}

const client = createClient({ url, authToken: process.env.TURSO_AUTH_TOKEN });

const existing = await client.execute("SELECT COUNT(*) AS n FROM sync_runs").catch(() => null);
if (existing && Number(existing.rows[0]?.n ?? 0) > 0) {
  console.log("[seed] database already has sync runs, skipping");
  process.exit(0);
}

const dir = dirname(fileURLToPath(import.meta.url));
const sql = readFileSync(join(dir, "..", "seed.sql"), "utf8");
await client.executeMultiple(sql);
const check = await client.execute("SELECT COUNT(*) AS n FROM orders");
console.log(`[seed] seeded ${check.rows[0]?.n ?? "?"} orders`);
