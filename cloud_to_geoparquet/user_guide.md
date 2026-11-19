# User Guide

This guide covers the configuration and export options for the GeoParquet layer
extractor. Run the Python commands from the `src` folder.

Note: This is similar to the QGIS Plugin that supports downloading geoparquet via QGIS extent. See: https://github.com/cholmes/qgis_plugin_gpq_downloader/

Note: ArcGIS Pro addin (current OVERTURE) also now available that support downloading geoparquet via ArcGIS Pro extent. Also additional tools.
https://cofgisonline.maps.arcgis.com/home/item.html?id=8293d1220b7848848ce316b4fa3263b5#overview

Note: Overture also has its own download tools and library: See: https://github.com/OvertureMaps/overturemaps-py/blob/main/README.md

## Default Configuration

When no configuration options are supplied, the runner uses:

- Layer configuration: `nztopo`
- URL data path: `nztopodev`
- Layer file: `config/nztopo_layers.yml`
- URL file: `config/url_data_paths.yml`
- Export folder: `exports`
- Default bbox: `NZ_MAINLAND`

The current `nztopodev` URL is stored in `url_data_paths.yml`, rather than in
the Python source.

## Install And Run

Install the locked dependencies and view the runner options:

```powershell
uv sync
Set-Location src
uv run python -m run_extract_geoparquet --help
```

Run the default export:

```powershell
uv run python -m run_extract_geoparquet
```

The runner writes GeoParquet files and an `extract_geoparquet.log` file under
`exports`.

For manual runs and PyInstaller executable builds, see
[PYINSTALLER.md](PYINSTALLER.md). Its commands run from the project root;
the source-module commands in this guide continue to run from `src`.

## Export To DuckDB

To write layers into a DuckDB database instead, select the DuckDB format and
provide a database path:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names airport,building_point `
  --bbox-name CHATHAM_ISLANDS `
  --export-format duckdb `
  --database-path C:\Temp\exports\nztopo.duckdb
```

This creates `airport` and `building_point` tables. Inspect the database with
the DuckDB Python API:

```powershell
uv run python -c "import duckdb; connection = duckdb.connect(r'C:\Temp\exports\nztopo.duckdb'); print(connection.execute('SHOW TABLES').fetchall())"
```

Add another layer to the same database by reusing the database path:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names coastline `
  --bbox-name CHATHAM_ISLANDS `
  --export-format duckdb `
  --database-path C:\Temp\exports\nztopo.duckdb
```

Each layer is created as a table named after the layer. If the database already
exists, new layer tables are added without removing existing tables. Exporting
a layer whose table already exists stops with an error. Geometry-type splitting
is supported only for Parquet exports.

## Create A GeoParquet Catalog

Use `--create-catalog` to export GeoParquet normally and create a
`catalog.duckdb` database in the same folder as the exported files:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names airport,building_point `
  --bbox-name CHATHAM_ISLANDS `
  --create-catalog
```

The database contains a view for each file. Conceptually, an `airport` view is:

```sql
CREATE VIEW airport AS
SELECT *
FROM read_parquet('airport.parquet');
```

The actual catalog stores an absolute Parquet path so the view continues to
work regardless of the process working directory. Query the view and metadata
with DuckDB:

```sql
INSTALL spatial;
LOAD spatial;
SELECT * FROM airport;
SELECT * FROM datasets ORDER BY view_name;
SELECT * FROM downloads ORDER BY downloaded_at DESC;
SELECT * FROM extents ORDER BY view_name, extent_index;
```

The catalog includes:

- `datasets`: one current row per view with its layer, source URL, and file.
- `downloads`: append-only export history with file size and row count.
- `extents`: the named bounding boxes used to create each export.

The `extent_name` column retains configured names such as `NZ_MAINLAND`,
`CHATHAM_ISLANDS`, or `HAMILTON_URBAN_AREA`. Direct `--extent` values use
`EXPLICIT_EXTENT`. GeoPackage features use `<layer>_<index>`, for example
`study_areas_1`. Existing catalogs receive the column automatically the next
time they are updated; previously stored rows remain null until their view is
registered again.

If the catalog already exists, new views are added. Re-exporting an existing
view replaces its definition and current metadata while retaining its download
history. `--split-geometry-types` also registers every split output as a view.

This differs from `--export-format duckdb`, which copies rows into physical
DuckDB tables instead of retaining Parquet-backed views.

### Catalog Remote GeoParquet Without Downloading

Use `--catalog-only` when the catalog should point directly at the configured
HTTP or S3 GeoParquet source and no local Parquet export is required:

```powershell
uv run python -m run_extract_geoparquet `
  --catalog-only `
  --export-folder C:\Temp\geoparquet-catalog
```

The default command creates:

```text
C:\Temp\geoparquet-catalog\nztopodev\catalog.duckdb
```

It creates filtered `airport` and `building_point` views using the configured
remote paths and the default New Zealand extents. Named bboxes, explicit
extents, GeoPackage extents, and `--query` filters are retained in each view
definition.

The `datasets` table records `source_kind = 'remote'` and stores the remote
GeoParquet path. Because no local file is produced, no row is added to
`downloads`. Creating and querying the view can still make HTTP range and
metadata requests to the remote source.

Before querying remote catalog views in a new DuckDB connection, configure the
required extensions and HTTP wildcard support:

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

### Catalog Existing Local GeoParquet Files

Use `--catalog-folder` to create a catalog for GeoParquet files that already
exist locally:

```powershell
uv run python -m run_extract_geoparquet `
  --catalog-folder C:\Data\temp\topographic-data-dev-67-full
```

This creates:

```text
C:\Data\temp\topographic-data-dev-67-full\catalog.duckdb
```

Every top-level `*.parquet` file becomes a view named from its file stem. For
example:

```text
airport.parquet       -> airport
building_point.parquet -> building_point
road_line.parquet     -> road_line
```

The `datasets` table records each absolute file path with
`source_kind = 'local'`. Existing local files are not downloads, so no
`downloads` rows are added. The extent is read from the GeoParquet file-level
bbox metadata; files without that metadata fall back to calculating their
geometry extent.

Rerunning the command refreshes matching views and preserves unrelated catalog
entries. Only top-level files with a lowercase `.parquet` suffix are scanned.
Deleted files are not removed from the catalog automatically. Because views
use absolute paths, rerun the command after moving the folder.

## Select Layers

Use `--layer-names` with a comma-separated list:

```powershell
uv run python -m run_extract_geoparquet --layer-names airport,building_point
```

Or use `--layer-config` with a YAML file whose keys are layer names:

```powershell
uv run python -m run_extract_geoparquet --layer-config config/nztopo_layers.yml
```

The layer names and themes are defined in `config/nztopo_layers.yml`. Use
`--theme` with `--layer-config` to export every layer whose theme matches the
specified value:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-config config/nztopo_layers.yml `
  --theme landcover `
  --bbox-name HAMILTON_URBAN_AREA
```

This selects layers such as `coastline`, `landcover`, and `marine`, which are
configured with the `landcover` theme. Theme matching is case-sensitive.

When `--layer-names` is also provided, it supplies the source type and
`--theme` overrides that type's configured source theme. This supports source
paths where theme and type differ, such as Overture `theme=base` with
`type=land_cover`.

## Query Filters

Use `--query` to filter exported rows with a `field=value` condition. Quote
string values when needed, and repeat the option for multiple conditions:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names marine `
  --query "service='slipway'"
```

## URL Data Paths

URL bases and relative data path templates are defined in
`config/url_data_paths.yml`:

```yaml
nztopodev:
  url: https://d1jzh93b1t1cv.cloudfront.net/data
  data_path: "{layer_name}/latest/"
overture:
  url: s3://overturemaps-us-west-2
  data_path: "release/{date}/theme={theme}/type={layer_name}/*"
```

The extractor combines `url` and `data_path` to form the full remote path. The
default is `nztopodev`. Select the configured source with
`--url-data-path`:

```powershell
# nztopodev
uv run python -m run_extract_geoparquet `
  --layer-names airport `
  --url-data-path nztopodev

# overture S3
uv run python -m run_extract_geoparquet `
  --layer-names building `
  --url-data-path overture `
  --release-date 2026-09-23.1 `
  --bbox-name HAMILTON_URBAN_AREA

```

The Overture examples use the `building` layer, whose configured theme is
`buildings`. Replace `2024-08-20.0` with a release available from the selected
source.

Use `--url-path-config` when the URL keys are stored in another YAML file:

```powershell
uv run python -m run_extract_geoparquet `
  --url-path-config config/url_data_paths.yml `
  --url-data-path overture
```

## Split Geometry Types

Some sources, including Overture and OpenStreetMap Layercake, can contain
multiple geometry types in one layer. Use `--split-geometry-types` to reload
each completed export and create one additional parquet file per type:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names buildings `
  --url-data-path openstreetmap-layerlake `
  --split-geometry-types
```

For an export named `buildings.parquet`, the additional files use names such
as `buildings_point.parquet` and `buildings_polygon.parquet`. Null geometries
are retained in `buildings_null.parquet`, and the original mixed export is not
removed.

## Named Bboxes

Named bboxes are defined in `config/nz_names_bboxes.yml`.

Use a named bbox from the runner:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names airport `
  --bbox-name CHATHAM_ISLANDS
```

When `--bbox-name` is used, output is placed in a lowercase subfolder such as
`exports/chatham_islands`.

To add another set of named bboxes, create a file following the
`<name>_names_bboxes.yml` naming pattern in `config`.

## Explicit Extents

Use `--extent` when the bbox is not already named. Coordinates must be in
`west,south,east,north` order:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names airport `
  --extent 174.7,-41.4,174.9,-41.2
```

## GeoPackage Extents

Use `--extent-geopackage` with `--extent-layer` to run one export for every
non-null geometry in a GeoPackage layer:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names airport `
  --extent-geopackage C:\Temp\exports\study_areas\study_areas.gpkg `
  --extent-layer study_area
```

The layer must have a declared coordinate reference system. Each geometry is
transformed to EPSG:4326 and its bbox becomes the export extent. Numbered files
prevent features from overwriting one another, for example
`airport_1.parquet`, `airport_2.parquet`, and `airport_3.parquet`.

Export the Overture land-cover layer once for each study-area feature:

```powershell
uv run python run_extract_geoparquet.py `
  --layer-names land_cover `
  --theme base `
  --url-data-path overture `
  --release-date 2026-09-23.1 `
  --extent-geopackage C:\Temp\exports\study_areas\study_areas.gpkg `
  --extent-layer study_areas `
  --export-folder C:\Temp\exports\overture_land_cover
```

This writes numbered outputs such as
`C:\Temp\exports\overture_land_cover\overture\land_cover_1.parquet`.
The remote source resolves to
`release/2026-09-23.1/theme=base/type=land_cover/*`.

## Python Export API

Query one bbox:

```python
from extract_geoparquet_layer import GeoParquetLayer

layer = GeoParquetLayer(
  "https://d1jzh93b1t1cv.cloudfront.net/data",
  "airport",
  bbox="NZ_MAINLAND",
)
rows = layer.query_bbox()
```

Export one bbox:

```python
output_path, copy_sql = layer.export_bbox()
```

Export the configured New Zealand mainland and offshore regions:

```python
output_path, copy_sql = layer.export_new_zealand()
```

Split an existing export by geometry type:

```python
split_paths = layer.split_geometry_types(output_path)
```

Set a different output folder with `export_folder`:

```python
layer = GeoParquetLayer(
  "https://d1jzh93b1t1cv.cloudfront.net/data",
    "airport",
    export_folder="data/exports",
)
```

## Docker

Build the image:

```powershell
docker build -t geoparquet-export .
```

Run the default export with a host output folder:

```powershell
docker run --rm `
  -v "${PWD}/exports:/app/src/exports" `
  geoparquet-export
```

Pass runner options after the image name:

```powershell
docker run --rm `
  -v "${PWD}/exports:/app/src/exports" `
  geoparquet-export `
  --layer-names airport,water `
  --bbox-name CHATHAM_ISLANDS
```

## Windows WSL Containers

WSL 2.9.3 or later includes `wslc.exe`, a container CLI that does not require
Docker. Update WSL and verify the installation from PowerShell:

```powershell
wsl --update
wsl --version
wslc version
```

From the project root, build the image with `wslc`:

```powershell
wslc build -t gp-extract .
```

Run the image interactively and pass runner options:

```powershell
wslc run --rm -it gp-extract args...
```

See Microsoft's [Get started with containers on WSL](https://learn.microsoft.com/en-us/windows/wsl/tutorials/wsl-containers)
guide for installation and troubleshooting details.

## Output And Logging

Each exported layer is written below a folder named for the selected
`url_data_path`, as `<export-folder>/<url_data_path>/<layer_name>.parquet`.
The runner also logs the generated DuckDB `COPY` SQL to:

```text
<export-folder>/extract_geoparquet.log
```

Named bbox runs use a lowercase bbox subfolder below the selected export
folder. Explicit and GeoPackage extents use the export folder directly.

## Example Runs

Run one layer for the Chatham Islands using the default NZ URL configuration:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names island `
  --bbox-name CHATHAM_ISLANDS `
  --url-data-path nztopodev `
  --export-folder C:\temp\exports
```

Run all layers from the NZ layer configuration for the Chatham Islands:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-config config/nztopo_layers.yml `
  --bbox-name CHATHAM_ISLANDS `
  --url-data-path nztopodev `
  --export-folder C:\temp\exports
```

Run all configured layers using the default NZ regional coverage and URL:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-config config/nztopo_layers.yml `
  --url-data-path nztopodev `
  --export-folder C:\temp\exports
```

Run the Overture buildings layer for the Hamilton urban area from S3:

```powershell
uv run python -m run_extract_geoparquet `
  --layer-names building `
  --bbox-name HAMILTON_URBAN_AREA `
  --url-data-path overture `
  --release-date 2026-09-23.1 `
  --export-folder C:\temp\exports
```

The `building` layer resolves to the Overture `buildings` theme. Replace the
release date with one available from the selected Overture source.

The same example runs from Windows Command Prompt use `^` for line
continuation:

Run one layer for the Chatham Islands:

```cmd
uv run python -m run_extract_geoparquet ^
  --layer-names island ^
  --bbox-name CHATHAM_ISLANDS ^
  --url-data-path nztopodev ^
  --export-folder C:\temp\exports
```

Run all configured layers for the Chatham Islands:

```cmd
uv run python -m run_extract_geoparquet ^
  --layer-config config/nztopo_layers.yml ^
  --bbox-name CHATHAM_ISLANDS ^
  --url-data-path nztopodev ^
  --export-folder C:\temp\exports
```

Run all configured layers using the default NZ regional coverage:

```cmd
uv run python -m run_extract_geoparquet ^
  --layer-config config/nztopo_layers.yml ^
  --url-data-path nztopodev ^
  --export-folder C:\temp\exports
```

Run the Overture buildings layer for the Hamilton urban area from S3:

```cmd
uv run python -m run_extract_geoparquet ^
  --layer-names building ^
  --bbox-name HAMILTON_URBAN_AREA ^
  --url-data-path overture ^
  --release-date 2026-09-23.1 ^
  --export-folder C:\temp\exports
```

The same commands can be run from Linux or macOS shells. Bash uses `\` for
line continuation and Linux paths use `/`:

Run all configured layers for the Chatham Islands:

```bash
uv run python -m run_extract_geoparquet \
  --layer-config config/nztopo_layers.yml \
  --bbox-name CHATHAM_ISLANDS \
  --url-data-path nztopodev \
  --export-folder /tmp/geoparquet-exports
```

Run all configured layers using the default NZ regional coverage:

```bash
uv run python -m run_extract_geoparquet \
  --layer-config config/nztopo_layers.yml \
  --url-data-path nztopodev \
  --export-folder /tmp/geoparquet-exports
```

When no `--bbox-name` or `--extent` is supplied, the runner uses the NZ
regional coverage set:

- `NZ_MAINLAND`
- `CHATHAM_ISLANDS`
- `SNARES_ISLANDS`
- `AUCKLAND_ISLANDS`
- `CAMPBELL_ISLAND`
- `ANTIPODES_ISLANDS`
- `BOUNTY_ISLANDS`
- `RAOUL_ISLAND`
- `MACAULEY_CURTIS_ISLANDS`

Use `--bbox-name` or `--extent` when only one area should be exported.
