# GeoParquet Extractor Runtime

This folder contains the packaged Windows executable copied from
`dist/geoparquet-extract`.

## Files

Keep the executable and `config` folder together:

```text
exe_runtime/
  geoparquet-extract.exe
  config/
    nztopo_layers.yml
    nz_names_bboxes.yml
    url_data_paths.yml
```

The YAML files in `config` can be edited without rebuilding the executable.

## Run

Open PowerShell in this folder and view the available options:

```powershell
.\geoparquet-extract.exe --help
```

Run an airport export for the Chatham Islands using the default NZ source:

```powershell
.\geoparquet-extract.exe `
  --layer-names airport `
  --url-data-path nztopodev `
  --bbox-name CHATHAM_ISLANDS
```

Export all layers configured with the `landcover` theme:

```powershell
.\geoparquet-extract.exe `
  --layer-config config\nztopo_layers.yml `
  --theme landcover `
  --url-data-path nztopodev `
  --bbox-name HAMILTON_URBAN_AREA
```

Run an Overture buildings export for the Hamilton urban area:

```powershell
.\geoparquet-extract.exe `
  --layer-names building `
  --url-data-path overture `
  --release-date 2026-09-23.1 `
  --bbox-name HAMILTON_URBAN_AREA
```

Use `--export-folder` to choose another output location:

```powershell
.\geoparquet-extract.exe `
  --layer-names airport `
  --bbox-name CHATHAM_ISLANDS `
  --export-folder C:\temp\geoparquet-exports
```

By default, output is written below an `exports` folder in the current
working directory. The selected URL configuration name is included in the
output path, for example:

```text
exports/nztopodev/airport.parquet
```

## Requirements

The executable needs network access to the selected GeoParquet source and to
DuckDB's spatial extension repository on its first spatial query or export.

Distribute the complete runtime folder, including the executable, `config`,
and all other files copied from `dist/geoparquet-extract`.
