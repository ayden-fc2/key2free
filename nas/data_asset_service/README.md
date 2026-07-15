# Key2Free NAS Data Asset Service

This service owns the nightly Tushare refresh lifecycle on the NAS while the
main trading system continues to read its local DuckDB database for backtests
and signals.

## Runtime

- NAS source path: `/volume2/docker/ayden/key2free-data-asset`
- LAN endpoint: `http://192.168.1.62:18080`
- Container: `key2free-data-asset-service`
- Restart policy: `unless-stopped`
- DuckDB path: `runtime/data/data.duckdb`
- Service config: `runtime/data/config/service_config.json`
- Export cache: `runtime/data/exports`
- Operation log: `runtime/logs/operations.jsonl`

The container imports the existing asset implementation from `backend/app`.
Watermark rules, table definitions, 5-minute refresh behavior, retries, and the
daily technical table rebuild therefore stay identical to the main repository.

## Database Readiness

The service does not bootstrap a multi-year database automatically. Copy the
existing DuckDB file to:

```text
/volume2/docker/ayden/key2free-data-asset/runtime/data/data.duckdb
```

Stop the container before replacing the database file, then start it again.
Until the file contains initialized Tushare tables and a non-empty trade
calendar, `/health` reports `database.ready=false` and the nightly job writes a
`skipped` operation log instead of starting a historical rebuild.

## Refresh Schedule

The internal scheduler runs every day at `02:30` Asia/Shanghai by default and
refreshes through the previous calendar day. The full refresh includes:

- trade calendar;
- maintained index metadata, daily bars, and daily indicators;
- stock backup basics, adjustment factors, daily bars, and daily basics;
- `tushare.stk_mins_5min`, using Baostock with the existing Tushare fallback;
- `tushare.stock_daily_technical` rebuild after base watermarks are ready.

The technical table is rebuilt in batches of ten symbols with two calculation
workers. Each batch is written to a temporary Parquet shard under
`runtime/data/rebuild/stock_daily_technical`; only a fully validated snapshot is
installed into the live table, inside one DuckDB transaction. A failed build
therefore leaves the live table unchanged. The two latest successful snapshots
are retained for recovery.

Base data is loaded for 80 symbols per SQL query, then split into the smaller
calculation batches. This reduces repeated scans without increasing the number
of indicator frames calculated concurrently.

The container limits DuckDB to two threads and 1500 MB by default. These values,
the technical calculation worker count, and batch size can be overridden in the
Compose `.env` file.

Schedule time, Tushare proxy URL, token, timeout, and advertised NAS address can
be hot-updated through `PUT /api/v1/config`. The token is never returned in
plain text.

## APIs

```text
GET  /health
GET  /api/v1/status
GET  /api/v1/config
PUT  /api/v1/config
GET  /api/v1/database
GET  /api/v1/watermarks
POST /api/v1/refresh
GET  /api/v1/refresh-task
GET  /api/v1/logs
POST /api/v1/exports
GET  /api/v1/exports/{export_id}/download
GET  /docs
```

Refresh lifecycle details remain in the shared DuckDB task table for
compatibility. NAS-level starts, completions, failures, configuration changes,
and exports are additionally written to the standalone JSONL operation log.

Exports are restricted to the known Tushare asset table allowlist. Dated tables
are exported as Zstandard-compressed Parquet slices with row count, schema, file
size, and SHA-256 metadata. Five-minute slices are limited to seven calendar
days; other dated assets are limited to 120 days per request.

## Deployment

The Compose build context is the repository root because the image reuses
`backend/app`:

```bash
cd nas/data_asset_service
cp .env.example .env
sudo docker compose up -d --build
sudo docker compose ps
```

When Docker Hub is not reachable, override `PYTHON_IMAGE` only in the untracked
NAS `.env`. No NAS password, Tushare token, DuckDB database, or exported market
data belongs in Git.

This NAS stores Docker data under `/volume2/@docker`. Install the tracked
systemd drop-in and enable Docker so the daemon waits for `/volume2` during boot:

```bash
sudo install -D -m 0644 deploy/docker.service.d/key2free-volume2.conf \
  /etc/systemd/system/docker.service.d/key2free-volume2.conf
sudo systemctl daemon-reload
sudo systemctl enable docker.service
```

After Docker starts, the `unless-stopped` policy restores the service. A
container explicitly stopped by an operator remains stopped until started
again.
