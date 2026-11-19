# GeoParquet Layer Query

Query a remote GeoParquet 1.1 layer with DuckDB and its `spatial` extension.
The included example retrieves airport features that intersect the approximate
mainland New Zealand bounding box.

See the `USER_GUIDE.md` file for instructions / examples on running the application and under `runtime-release\README.md` on using the release executable.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Network access to the GeoParquet URL and DuckDB extension repository

## Run

```powershell
uv sync
uv run python src/extract_geoparquet_layer.py
```

## Docker

Build the image, then mount a host folder for the exported files and logs:

```powershell
docker build -t geoparquet-export .
docker run --rm -v "${PWD}/exports:/app/exports" geoparquet-export --layer-names airport --bbox-name CHATHAM_ISLANDS
```

All runner arguments can follow the image name. Run `docker run --rm
geoparquet-export --help` to view them.

On Windows with WSL containers, build the image with:

```powershell
wslc build -t gp-extract .
```

## Use As A Class

```python
from src.extract_geoparquet_layer import GeoParquetLayer

airports = GeoParquetLayer(
	"https://d1jzh93b1t1cv.cloudfront.net/data",
	"airport",
	"CHATHAM_ISLANDS",
)
rows = airports.query_bbox()
```

The constructor's `bbox` property defaults to `"NZ_MAINLAND"`. It accepts a
defined region name such as `"CHATHAM_ISLANDS"`, or an explicit tuple in
`(west, south, east, north)` order:

```python
custom_area = GeoParquetLayer(
	"https://d1jzh93b1t1cv.cloudfront.net/data",
	"airport",
	(174.7, -41.4, 174.9, -41.2),
)
rows = custom_area.query_bbox()
```

`query_bbox()` first filters the GeoParquet 1.1 `bbox` covering using overlap
comparisons, then uses `ST_Intersects` for an exact geometry test. The source
layer must provide root-level `geometry` and `bbox` columns; `bbox` must contain
`xmin`, `ymin`, `xmax`, and `ymax` fields.

## Export GeoParquet

Set `export_folder` to choose where DuckDB writes the extracted file. The output
is named `<layer_name>.parquet` and is produced by DuckDB `COPY` with Zstandard
compression.

```python
output, copy_sql = airports.export_bbox()
print(output)  # exports/airport.parquet
print(copy_sql)  # full DuckDB COPY command
```

Use `export_new_zealand()` to export all configured mainland and offshore
regions into one file.

## Export To DuckDB

Use `--export-format duckdb` with `--database-path` to write each selected
layer to a table instead of creating a GeoParquet file:

```powershell
uv run python -m src.run_extract_geoparquet `
	--layer-names airport,building_point `
	--bbox-name CHATHAM_ISLANDS `
	--export-format duckdb `
	--database-path exports\nztopo.duckdb
```

An existing database is retained and each new layer is added as a separate
table, such as `airport` or `building_point`. The export stops with an error if
the target table already exists. `--split-geometry-types` is available only
for Parquet exports.

## Create A Local GeoParquet Catalog

Use `--create-catalog` to keep the normal GeoParquet exports and create a
`catalog.duckdb` beside them. Each exported file is registered as a DuckDB view
that reads the Parquet file:

```powershell
uv run python -m src.run_extract_geoparquet `
	--layer-names airport,building_point `
	--bbox-name CHATHAM_ISLANDS `
	--create-catalog
```

The resulting folder contains the Parquet files and catalog:

```text
catalog.duckdb
airport.parquet
building_point.parquet
```

The catalog contains `airport` and `building_point` views plus metadata tables:

- `datasets`: current view, layer, source URL, and local Parquet path.
- `downloads`: append-only export time, file size, and row count history.
- `extents`: named bounding boxes associated with each view.

Configured bboxes retain names such as `NZ_MAINLAND` or
`HAMILTON_URBAN_AREA`. Direct `--extent` values use `EXPLICIT_EXTENT`, and
GeoPackage features use `<layer>_<index>`. Existing catalogs are migrated with
the new `extent_name` column when next updated.

Rerunning an export replaces its view definition and current metadata while
adding another `downloads` row. Existing unrelated views remain in the
database. When `--split-geometry-types` is also supplied, each split Parquet
file is registered as another view.

Catalog mode differs from `--export-format duckdb`: catalog mode retains
Parquet files and creates views over them, while DuckDB export copies the data
into physical database tables.

### Remote Catalog Without Downloads

Use `--catalog-only` to create `catalog.duckdb` without writing local Parquet
files. Each view reads the configured remote GeoParquet source and retains the
requested bbox and `--query` filters:

```powershell
uv run python -m src.run_extract_geoparquet `
	--catalog-only `
	--export-folder C:\Temp\geoparquet-catalog
```

With the default source, the database is created at
`C:\Temp\geoparquet-catalog\nztopodev\catalog.duckdb`. Its `datasets` rows use
`source_kind = 'remote'` and store the remote path. No `downloads` rows or
local Parquet files are created.

Remote views require network access. Load DuckDB HTTPFS and Spatial before
querying them:

```sql
INSTALL httpfs;
LOAD httpfs;
INSTALL spatial;
LOAD spatial;
SET allow_asterisks_in_http_paths = true;
SELECT * FROM airport;
```

`--catalog-only` cannot be combined with `--create-catalog`,
`--split-geometry-types`, or `--export-format duckdb`.

### Catalog An Existing Local Folder

Use `--catalog-folder` to scan the top-level `*.parquet` files in an existing
folder and create `catalog.duckdb` in that folder:

```powershell
uv run python -m src.run_extract_geoparquet `
	--catalog-folder C:\Data\temp\topographic-data-dev-67-full
```

Each file stem becomes its view name, such as `airport.parquet` becoming
`airport`. Existing view definitions are refreshed and unrelated catalog views
remain. Local files use `source_kind = 'local'` and do not add `downloads`
rows.

The catalog derives each extent from the GeoParquet file-level bbox metadata.
If that bbox is absent, it calculates the geometry extent. Views store absolute
file paths, so moving the folder requires rerunning the command. Only
top-level files with the lowercase `.parquet` suffix are scanned; files removed
from the folder are not automatically removed from an existing catalog.

## Runner

Run the default airport and building-point exports for all configured New
Zealand regions:

```powershell
uv run python -m src.run_extract_geoparquet
```

Use `--help` to view the available options. Layer names are positional; use
`--bbox-name` for a named region or `--extent` for four explicit coordinates:

```powershell
uv run python -m src.run_extract_geoparquet --help
uv run python -m src.run_extract_geoparquet --layer-names airport --bbox-name CHATHAM_ISLANDS
uv run python -m src.run_extract_geoparquet --layer-names airport,building_point
uv run python -m src.run_extract_geoparquet --layer-names building_point --extent 174.7,-41.4,174.9,-41.2
uv run python -m src.run_extract_geoparquet --layer-names building_point --extent-geopackage C:\Temp\exports\study_areas\study_areas.gpkg --extent-layer study_area
uv run python -m src.run_extract_geoparquet --layer-config src/config/nztopo_layers.yml --export-folder data/exports
uv run python -m src.run_extract_geoparquet --layer-config src/config/nztopo_layers.yml --theme landcover
uv run python -m src.run_extract_geoparquet --layer-names land_cover --theme base --url-data-path overture --release-date 2026-09-23.1 --extent-geopackage C:\Temp\exports\study_areas\study_areas.gpkg --extent-layer study_areas
uv run python -m src.run_extract_geoparquet --layer-names buildings --url-data-path openstreetmap-layerlake --split-geometry-types
```

Without `--layer-names`, `--theme` selects every configured layer whose theme
matches the supplied value. With `--layer-names`, it overrides the source theme
for those explicit layer types. For example, `--layer-names land_cover --theme
base` reads Overture's `theme=base/type=land_cover` path.

`--split-geometry-types` reloads each completed export and writes an additional
file for every geometry type. For example, `buildings.parquet` can produce
`buildings_point.parquet` and `buildings_polygon.parquet`. Rows with a null
geometry are written to `buildings_null.parquet`. The original mixed file is
retained.

### Overture Sources

The URL configuration keeps the remote base in `url` and the relative source
template in `data_path`. The extractor combines them into the full remote
path. Overture templates also use the layer theme from `nztopo_layers.yml`
and require a release date.

For example, extract Overture buildings intersecting the Hamilton urban area
from the Overture S3 source:

```powershell
# Overture S3
uv run python -m src.run_extract_geoparquet `
	--layer-names building `
	--url-data-path overture `
	--release-date 2024-08-20.0 `
	--bbox-name HAMILTON_URBAN_AREA

```

The resulting source path for the S3 example is
`s3://overturemaps-us-west-2/release/2024-08-20.0/theme=buildings/type=building/*`.
Use a release date present in the selected Overture source.

Supported `--bbox-name` values:

```text
NZ_MAINLAND
NORTHLAND_REGION
AUCKLAND_REGION
WAIKATO_REGION
BAY_OF_PLENTY_REGION
GISBORNE_REGION
HAWKES_BAY_REGION
TARANAKI_REGION
MANAWATU_WHANGANUI_REGION
GREATER_WELLINGTON_REGION
WEST_COAST_REGION
CANTERBURY_REGION
OTAGO_REGION
SOUTHLAND_REGION
TASMAN_REGION
NELSON_REGION
MARLBOROUGH_REGION
CHATHAM_ISLANDS
SNARES_ISLANDS
AUCKLAND_ISLANDS
CAMPBELL_ISLAND
ANTIPODES_ISLANDS
BOUNTY_ISLANDS
RAOUL_ISLAND
MACAULEY_CURTIS_ISLANDS
AUCKLAND_URBAN_AREA
GREATER_WELLINGTON_URBAN_AREA
CHRISTCHURCH_URBAN_AREA
KAITAIA_URBAN_AREA
WHANGAREI_URBAN_AREA
HAMILTON_URBAN_AREA
TAURANGA_URBAN_AREA
ROTORUA_URBAN_AREA
GISBORNE_URBAN_AREA
NAPIER_HASTINGS_URBAN_AREA
TAUPO_URBAN_AREA
NEW_PLYMOUTH_URBAN_AREA
WHANGANUI_URBAN_AREA
PALMERSTON_NORTH_URBAN_AREA
PARAPARAUMU_URBAN_AREA
WELLINGTON_URBAN_AREA
NELSON_URBAN_AREA
BLENHEIM_URBAN_AREA
GREYMOUTH_URBAN_AREA
TIMARU_URBAN_AREA
DUNEDIN_URBAN_AREA
QUEENSTOWN_URBAN_AREA
INVERCARGILL_URBAN_AREA
```

`--extent-geopackage` reads every non-null geometry in the selected
`--extent-layer`, transforms it from the GeoPackage layer's declared CRS to
EPSG:4326, and runs one export using each geometry's bbox. Outputs are numbered
per feature, such as `building_point_1.parquet` and
`building_point_2.parquet`.

Without `--bbox-name`, `--extent`, or `--extent-geopackage`, the runner
preserves the default all-regions New Zealand export. Each run logs its `COPY` SQL to
`<export-folder>/extract_geoparquet.log`.

When `--bbox-name` is used, the runner appends its lowercase name to the export
folder. For example, `--export-folder exports --bbox-name CHATHAM_ISLANDS` writes to
`exports/chatham_islands/`.

Regional bboxes are calculated from NZ Stats regional boundary data. City names
align with Stats NZ Urban Area labels; their mapped bboxes are intended for
coarse extraction, while the GeoParquet geometry predicate performs the exact
spatial test.

`query_new_zealand()` uses the class's `NZ_BBOXES` set. It includes the
mainland extent plus Chatham, Snares, Auckland, Campbell, Antipodes, Bounty,
and Kermadec Islands (Raoul, Macauley, and Curtis). Separate bboxes avoid
turning the widely dispersed islands into one large ocean-sized query area.
