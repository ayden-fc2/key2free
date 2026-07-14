# NAS Sync Workspace

This directory is reserved for the local cache used by the future NAS data
asset service integration.

Goal:

- Keep the current local backtest and signal runtime fast by reading local
  DuckDB/cache files.
- Let a NAS-hosted microservice own data refresh, Tushare token configuration,
  refresh logs, watermarks, and export generation.
- Let the main system connect to the NAS by IP and port, then synchronize only
  requested date slices into the local repository database.

Planned local layout:

```text
data/nas_sync/
├── incoming/   # downloaded slice archives or parquet files from NAS
├── staging/    # extracted and validated files before import
├── applied/    # manifests for successfully applied slices
└── logs/       # local sync logs, not NAS refresh logs
```

Initial implementation scope:

1. Add NAS connection configuration in the main system.
2. Query NAS health, watermarks, refresh task status, and logs.
3. Request a date-sliced export from NAS.
4. Download the slice into `incoming/`.
5. Validate manifest and schema in `staging/`.
6. Import selected `tushare.*` tables into local DuckDB by date-range
   transaction, without replacing the whole database.

Do not store production DuckDB files, Tushare tokens, or large parquet exports
in git.
