# Partner Integration Pipeline

A sync pipeline that pulls orders from a messy partner ERP API and lands them in a clean local store. Built to show the core craft of forward deployed engineering: partner systems are flaky, formats are inconsistent, and the pipeline has to be boringly reliable anyway.

## Why this exists

Every FDE integration meets the same three problems. The partner API has inconsistent field formats, it fails in transient ways, and syncing twice must never corrupt the data. This repo solves all three in about 400 lines, and every design choice is a talking point in an interview.

## How it works

1. **Fetch.** `pipeline/client.py` walks every page of the partner API. Transient failures (500s, 429s, dropped connections) retry with exponential backoff, and the server sent retry delay is honored on rate limits.
2. **Normalize.** `pipeline/normalize.py` maps the mess into one canonical schema: amounts in four formats become floats, dates in five formats become UTC ISO strings, mixed case statuses become lowercase snake case, and the customer id is found under either of its two key names.
3. **Quality gate.** `pipeline/quality.py` runs pass/fail checks on the whole batch before anything is written: no duplicate ids, and null ratios for each field stay under explicit thresholds.
4. **Store.** `pipeline/store.py` writes with `INSERT ... ON CONFLICT DO UPDATE`, so running the sync again after a crash (or by accident) produces identical rows, never duplicates.

## Repo layout

```
mock_partner_api/server.py   Mock ERP API: messy fields, flaky 500s, rate limiting
pipeline/client.py           Paginated HTTP client with retry and backoff
pipeline/normalize.py        Messy records in, one canonical schema out
pipeline/quality.py          Pass/fail batch checks that gate every write
pipeline/store.py            Idempotent SQLite upserts
pipeline/sync.py             Orchestrator plus CLI
tests/test_normalize.py      Every messy format, pinned
tests/test_idempotency.py    Double sync, in place updates, quality gate behavior
scripts/demo.sh              Start the mock API, sync twice, run the tests
dashboard/                 Next.js dashboard: sync run history, quality gates, orders
```

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
bash scripts/demo.sh
```

Or run the pieces by hand:

```bash
.venv/bin/python -m uvicorn mock_partner_api.server:app --port 8000 &
PYTHONPATH=. .venv/bin/python -m pipeline.sync --base-url http://127.0.0.1:8000 --db orders.db
PYTHONPATH=. .venv/bin/python -m pipeline.sync --base-url http://127.0.0.1:8000 --db orders.db --dry-run
PYTHONPATH=. .venv/bin/python -m pytest -q tests/
```

## Dashboard

`dashboard/` is a small Next.js app that reads the same SQLite database the sync writes. It shows three things: sync run history (fetched, new rows, quality verdict per run), the per-check quality gate results behind each run, and a searchable orders table.

Every sync records a row in the `sync_runs` table (timestamp, orders fetched, new rows, quality pass/fail, per-check results as JSON), including dry runs and failed gates, so the dashboard always tells the truth about what happened.

```bash
cd dashboard
npm install
npm run dev
```

Run the pipeline first (`bash scripts/demo.sh` from the repo root) so there is data to look at. The dashboard defaults to `../demo.db`; set `SYNC_DB_PATH` to point it at a different database.

To host it (Vercel plus Turso), the dashboard reads `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` when they are set, and falls back to the local file otherwise. Same SQLite dialect either way, so nothing else changes. `dashboard/seed.sql` is a snapshot of a demo run; the build seeds the hosted database from it automatically on first deploy (skipped when data already exists).

## Design decisions worth explaining

* **Retry lives in the client, not the orchestrator.** Callers iterate orders; they never see pages, 429s, or backoff math.
* **Normalization is pure and total.** Each parser accepts anything and returns a typed value or `None`, never raising. Bad data becomes visible as nulls, not crashes.
* **The quality gate runs before the write, not after.** A bad batch is loud and nothing lands half written.
* **Upserts are idempotent by schema, not by convention.** The primary key plus `ON CONFLICT DO UPDATE` makes double runs safe no matter what.

## What is next

Phase two adds an agent on top of this store: natural language questions over the synced orders, with an eval loop (labeled question set, pass/fail grading, prompt iteration) so every change is measured. The quality checks here are the seed of that loop.
