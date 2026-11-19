# Raster Bands to GeoParquet

Convert every cell in a local or cloud-hosted TIFF into a polygon row. Each
raster band is written as a separate `band_N` column, and the raster CRS is
preserved in the GeoParquet output.

The `RasterToParquet` conversion class is in `src/raster_to_parquet.py`, and
command-line handling is in `src/raster_to_parquet_cli.py`.

## Install

```powershell
uv sync
```

## Cloud example

The source path is composed as:

```text
{data_path}/{version}/{year}/{location}/{tile_name}
```

For the defaults, this produces:

```text
https://data.source.coop/epoch/forest-typology-2020/v2_beta/2025/60G/raster_60G_20_16_3.tif
```

Run the conversion:

### Windows Command Prompt

```cmd
uv run rasterbands-to-geoparquet --export-path exports\forest_typology.parquet
```

Override any path component when needed:

```cmd
uv run rasterbands-to-geoparquet ^
  --data-path https://data.source.coop/epoch/forest-typology-2020/ ^
  --version v2_beta ^
  --year 2025 ^
  --location 60G ^
  --tile-name raster_60G_20_16_3.tif ^
  --export-path exports\forest_typology.parquet
```

### Linux

```bash
uv run rasterbands-to-geoparquet \
  --export-path exports/forest_typology.parquet
```

Override any path component when needed:

```bash
uv run rasterbands-to-geoparquet \
  --data-path https://data.source.coop/epoch/forest-typology-2020/ \
  --version v2_beta \
  --year 2025 \
  --location 60G \
  --tile-name raster_60G_20_16_3.tif \
  --export-path exports/forest_typology.parquet
```

## Local or direct URL input

Use `--input-path` to bypass path composition:

```powershell
uv run rasterbands-to-geoparquet `
  --input-path C:\data\source.tif `
  --export-path exports\source.parquet
```

The converter works in row batches rather than constructing the whole raster
in memory. `--row-group-size` controls the target number of rows per batch and
Parquet row group; its default is `100000`. All cells are retained, including
cells whose values equal a band's nodata value.

Source Cooperative catalogue URLs using `source.coop` are automatically changed
to the equivalent `data.source.coop` download endpoint. The example TIFF has 7
bands and 11,695,104 cells, so its output contains that many polygon rows.

## Split a raster into individual bands

`raster-to-bands` reads the raster in windows and writes one single-band
GeoTIFF per source band. For example, `raster_60G_20_16_3.tif` produces files
named `raster_60G_20_16_3_band_1.tif`, `raster_60G_20_16_3_band_2.tif`, and so
on.

Use the default cloud raster from Windows Command Prompt:

```cmd
uv run raster-to-bands --output-folder exports\bands
```

Use the default cloud raster from Linux:

```bash
uv run raster-to-bands --output-folder exports/bands
```

Split a local raster on Windows:

```cmd
uv run raster-to-bands ^
  --input-path C:\data\source.tif ^
  --output-folder exports\bands
```

Split a local raster on Linux:

```bash
uv run raster-to-bands \
  --input-path /data/source.tif \
  --output-folder exports/bands
```

Existing output files are protected by default. Pass `--overwrite` to replace
them.

## Test

```powershell
uv run pytest
```