# User Guide

This guide covers the configuration and export options for the GeoParquet layer
extractor. Run the Python commands from the `src` folder.

Note: This is similar to the QGIS Plugin that supports downloading geoparquet via QGIS extent. See: https://github.com/cholmes/qgis_plugin_gpq_downloader/

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
wslc build -t geoparquet-export .
```

Run the image and pass runner options:

```powershell
wslc run --rm -v "${PWD}/exports:/app/src/exports" geoparquet-export --layer-names airport,water --bbox-name CHATHAM_ISLANDS
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
folder. Explicit extents use the export folder directly.

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
