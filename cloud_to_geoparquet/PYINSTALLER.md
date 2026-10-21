# PyInstaller Builds

This project supports both a normal Python run and a PyInstaller onedir
build. Run the commands below from the project root, the directory containing
`pyproject.toml`.

## Manual Run

Install the normal project dependencies and run the CLI with uv:

```powershell
uv sync
uv run python -m src.run_extract_geoparquet `
  --layer-names building `
  --url-data-path overture `
  --release-date 2026-09-23.1 `
  --bbox-name HAMILTON_URBAN_AREA
```

The source files can also be run from the `src` directory:

```powershell
Set-Location src
uv run python -m run_extract_geoparquet --help
```

## Build The Executable

Install the PyInstaller dependency group:

```powershell
uv sync --group binary
```

Build from the checked-in spec file:

```powershell
uv run pyinstaller --clean --noconfirm geoparquet-extract.spec
```

The executable is created at:

```text
dist/geoparquet-extract/geoparquet-extract.exe
```

The spec file copies the YAML files to `config` beside the executable:

```text
dist/geoparquet-extract/
  geoparquet-extract.exe
  config/
    nztopo_layers.yml
    nz_names_bboxes.yml
    url_data_paths.yml
```

The executable reads this external `config` folder first, so users can edit
the YAML configuration without rebuilding the executable. Keep the folder
beside the executable when distributing the application.

## Run The Executable

Run the executable from the project root so exported files are written under
the expected relative `exports` directory:

```powershell
.\dist\geoparquet-extract\geoparquet-extract.exe `
  --layer-names building `
  --url-data-path overture `
  --release-date 2026-09-23.1 `
  --bbox-name HAMILTON_URBAN_AREA
```

View all available options:

```powershell
.\dist\geoparquet-extract\geoparquet-extract.exe --help
```

The executable still needs network access. DuckDB downloads and loads its
`spatial` extension when the extraction starts, and the selected remote
GeoParquet source must also be reachable.

## Clean Build

Remove previous PyInstaller output before a clean rebuild:

```powershell
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
uv run pyinstaller --clean --noconfirm geoparquet-extract.spec
```
