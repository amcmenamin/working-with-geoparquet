# GeoParquet Catalog Options

## Purpose

The catalog features make GeoParquet datasets discoverable and queryable
through DuckDB without requiring users to manage individual file paths.

The application supports three catalog workflows:

1. Export GeoParquet files and catalog the local outputs.
2. Create filtered views over remote GeoParquet without downloading files.
3. Catalog GeoParquet files that already exist in a local folder.

A fourth option copies data into physical DuckDB tables rather than creating
Parquet-backed views.

---

## Option 1: Export And Create A Catalog

Use `--create-catalog` when the application should download filtered
GeoParquet files and register them in `catalog.duckdb`.

```powershell
uv run python -m src.run_extract_geoparquet `
  --layer-names airport,building_point `
  --bbox-name HAMILTON_URBAN_AREA `
  --create-catalog `
  --export-folder C:\Data\exports
```

Example output:

```text
C:\Data\exports\nztopodev\
├── airport.parquet
├── building_point.parquet
└── catalog.duckdb
```

### Characteristics

- Creates local GeoParquet files.
- Creates one DuckDB view per file.
- Works offline after the export completes.
- Records dataset, download, and extent metadata.
- Replaces matching view definitions when rerun.
- Can catalog files created by `--split-geometry-types`.

### Best For

- Repeatable local analysis.
- Sharing a self-contained dataset folder.
- Reducing repeated remote reads.
- Workflows that require local GeoParquet files.

---

## Option 2: Remote Catalog Without Downloads

Use `--catalog-only` when DuckDB should query the configured HTTP or S3
GeoParquet source directly.

```powershell
uv run python -m src.run_extract_geoparquet `
  --layer-names airport,building_point `
  --bbox-name HAMILTON_URBAN_AREA `
  --catalog-only `
  --export-folder C:\Data\remote-catalog
```

Example output:

```text
C:\Data\remote-catalog\nztopodev\
└── catalog.duckdb
```

### Characteristics

- Does not create local GeoParquet files.
- Views retain bbox and `--query` filters.
- Requires network access when views are queried.
- Records remote dataset and extent metadata.
- Does not add `downloads` records.
- Cannot be combined with geometry-type splitting.

### Best For

- Exploring large remote datasets.
- Avoiding local storage costs.
- Creating lightweight catalogs.
- Accessing frequently updated remote sources.

### Query Setup

Remote views require DuckDB HTTPFS and Spatial:

```sql
INSTALL httpfs;
LOAD httpfs;
INSTALL spatial;
LOAD spatial;
SET allow_asterisks_in_http_paths = true;

SELECT * FROM airport;
```

---

## Option 3: Catalog An Existing Local Folder

Use `--catalog-folder` when GeoParquet files already exist locally.

```powershell
uv run python -m src.run_extract_geoparquet `
  --catalog-folder C:\Data\temp\topographic-data-dev-67-full
```

Example output:

```text
C:\Data\temp\topographic-data-dev-67-full\
├── airport.parquet
├── building.parquet
├── road_line.parquet
├── ...
└── catalog.duckdb
```

### Characteristics

- Scans top-level files with the lowercase `.parquet` suffix.
- Uses each file stem as its view name.
- Reads extents from GeoParquet metadata.
- Falls back to calculating the geometry extent when required.
- Stores absolute file paths.
- Does not add `downloads` records.
- Refreshes existing matching views.
- Does not automatically remove views for deleted files.

### Best For

- Existing GeoParquet collections.
- Retrofitting discoverability onto exported datasets.
- Creating a single SQL entry point for many files.

---

## Option 4: Physical DuckDB Tables

Use `--export-format duckdb` when data should be copied into DuckDB rather than
referenced through views.

```powershell
uv run python -m src.run_extract_geoparquet `
  --layer-names airport,building_point `
  --bbox-name HAMILTON_URBAN_AREA `
  --export-format duckdb `
  --database-path C:\Data\exports\topographic.duckdb
```

### Characteristics

- Copies rows into physical DuckDB tables.
- Does not retain separate GeoParquet files.
- Stops if the target table already exists.
- Uses more database storage than view-only catalogs.
- Can provide predictable local query performance.

---

## Comparison

| Option | Local Parquet | Data In DuckDB | Network To Query | Metadata |
|---|---:|---:|---:|---|
| `--create-catalog` | Yes | Views | No | Datasets, downloads, extents |
| `--catalog-only` | No | Remote views | Yes | Datasets and extents |
| `--catalog-folder` | Already exists | Local views | No | Datasets and extents |
| `--export-format duckdb` | No | Physical tables | No | Not catalog metadata |

---

## Catalog Structure

```text
catalog.duckdb
├── datasets
├── downloads
├── extents
├── airport                 (view)
├── building_point          (view)
└── road_line               (view)
```

### `datasets`

One current record per view:

- View name
- Layer name
- Original source URL
- Local or remote Parquet path
- Source kind: `local` or `remote`
- Created and updated timestamps

### `downloads`

Append-only history for files exported by the application:

- View name
- Download timestamp
- Local file path
- File size
- Row count

Existing files registered with `--catalog-folder` and remote views created with
`--catalog-only` do not create download records.

### `extents`

One or more spatial extents per view:

- View name
- Extent index
- Extent name
- West, south, east, and north coordinates

Configured names such as `NZ_MAINLAND` and `HAMILTON_URBAN_AREA` are retained.
Direct coordinate inputs use `EXPLICIT_EXTENT`.

---

## Example Queries

List catalog datasets:

```sql
SELECT
  view_name,
  layer_name,
  source_kind,
  parquet_path,
  updated_at
FROM datasets
ORDER BY view_name;
```

Review extents:

```sql
SELECT
  view_name,
  extent_name,
  west,
  south,
  east,
  north
FROM extents
ORDER BY view_name, extent_index;
```

Review export history:

```sql
SELECT
  view_name,
  downloaded_at,
  file_size_bytes,
  row_count
FROM downloads
ORDER BY downloaded_at DESC;
```

Query a cataloged layer:

```sql
SELECT *
FROM airport
LIMIT 10;
```

---

## Decision Guide

Choose `--create-catalog` when:

- Local files are required.
- The same data will be queried repeatedly.
- The dataset folder must work offline.

Choose `--catalog-only` when:

- Avoiding downloads is the priority.
- Network access is available.
- A lightweight filtered catalog is sufficient.

Choose `--catalog-folder` when:

- GeoParquet files already exist.
- A DuckDB catalog needs to be added without recreating data.

Choose `--export-format duckdb` when:

- Physical DuckDB tables are preferred.
- Separate GeoParquet files are unnecessary.

---

## Key Message

The catalog provides a consistent SQL interface while allowing the data to
remain in the location best suited to the workflow:

- Downloaded GeoParquet
- Remote GeoParquet
- Existing local GeoParquet
- Physical DuckDB tables
