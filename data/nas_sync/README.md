# NAS Sync Workspace

This directory is the main system's local workspace for the NAS data asset
integration. Backtests and signals continue to use the local `data/data.duckdb`
database; they never query the NAS across the network.

```text
data/nas_sync/
|-- incoming/   # temporary Parquet downloads
|-- staging/    # reserved for additional validation or extraction
|-- applied/    # immutable JSON manifests for imported slices
`-- logs/       # reserved for local synchronization logs
```

The main backend stores its NAS host and port in the ignored
`nas_connection.json`. The NAS token and proxy URL are stored only in the NAS
service's persistent runtime configuration.

Incremental synchronization works as follows:

1. Query NAS and local asset watermarks.
2. Request allowlisted Parquet slices only for the missing date range.
3. Verify SHA-256 and require the remote schema to exactly match the local
   target table.
4. Replace the slice in a local DuckDB transaction using column names.
5. Advance the local watermark to the maximum imported date.
6. Write an applied manifest and remove the downloaded Parquet file.

The deployable NAS service lives in `nas/data_asset_service/`.
