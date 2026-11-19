from __future__ import annotations

import json
import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
from rasterio.io import DatasetReader
from rasterio.windows import Window
from shapely import polygons

DEFAULT_DATA_PATH = "https://data.source.coop/epoch/forest-typology-2020/"


@dataclass(frozen=True)
class ConversionResult:
    source: str
    export_path: Path
    band_count: int
    cell_count: int


@dataclass(frozen=True)
class RasterToParquet:
    row_group_size: int = 100_000

    def __post_init__(self) -> None:
        if self.row_group_size < 1:
            raise ValueError("row_group_size must be at least 1")

    def convert(
        self,
        source: str | Path,
        export_path: str | Path,
    ) -> ConversionResult:
        return raster_to_geoparquet(
            source,
            export_path,
            row_group_size=self.row_group_size,
        )


def build_raster_path(
    data_path: str | Path,
    version: str,
    year: str | int,
    location: str,
    tile_name: str,
) -> str:
    parts = (version, str(year), location, tile_name)
    base = str(data_path)
    if urlparse(base).scheme in {"http", "https"}:
        return "/".join((base.rstrip("/"), *(part.strip("/") for part in parts)))
    return str(Path(base).joinpath(*parts))


def normalize_raster_source(source: str | Path) -> str:
    source_string = str(source)
    parsed = urlparse(source_string)
    if parsed.hostname == "source.coop":
        return parsed._replace(netloc="data.source.coop").geturl()
    return source_string


def _windows(dataset: DatasetReader, row_group_size: int) -> Iterator[Window]:
    rows_per_window = max(1, row_group_size // dataset.width)
    for row_offset in range(0, dataset.height, rows_per_window):
        height = min(rows_per_window, dataset.height - row_offset)
        yield Window(0, row_offset, dataset.width, height)


def _cell_polygons(dataset: DatasetReader, window: Window) -> np.ndarray:
    row_start = int(window.row_off)
    row_stop = row_start + int(window.height)
    col_start = int(window.col_off)
    col_stop = col_start + int(window.width)
    rows, cols = np.meshgrid(
        np.arange(row_start, row_stop),
        np.arange(col_start, col_stop),
        indexing="ij",
    )
    rows = rows.ravel()
    cols = cols.ravel()
    transform = dataset.transform

    corner_cols = np.column_stack((cols, cols + 1, cols + 1, cols))
    corner_rows = np.column_stack((rows, rows, rows + 1, rows + 1))
    x = transform.a * corner_cols + transform.b * corner_rows + transform.c
    y = transform.d * corner_cols + transform.e * corner_rows + transform.f
    return polygons(np.stack((x, y), axis=-1))


def _window_geodataframe(dataset: DatasetReader, window: Window) -> gpd.GeoDataFrame:
    raster_values = dataset.read(window=window)
    columns = {
        f"band_{band_number}": raster_values[band_number - 1].ravel()
        for band_number in range(1, dataset.count + 1)
    }
    frame = pd.DataFrame(columns)
    return gpd.GeoDataFrame(
        frame,
        geometry=_cell_polygons(dataset, window),
        crs=dataset.crs,
    )


def _set_dataset_bbox(schema: pa.Schema, bounds: Sequence[float]) -> pa.Schema:
    metadata = dict(schema.metadata or {})
    geo = json.loads(metadata[b"geo"])
    primary_column = geo["primary_column"]
    geo["columns"][primary_column]["bbox"] = list(bounds)
    metadata[b"geo"] = json.dumps(geo).encode("utf-8")
    return schema.with_metadata(metadata)


def raster_to_geoparquet(
    source: str | Path,
    export_path: str | Path,
    *,
    row_group_size: int = 100_000,
) -> ConversionResult:
    if row_group_size < 1:
        raise ValueError("row_group_size must be at least 1")

    source_string = normalize_raster_source(source)
    destination = Path(export_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_destination = destination.with_name(f".{destination.name}.tmp")
    temporary_destination.unlink(missing_ok=True)

    writer: pq.ParquetWriter | None = None
    try:
        rasterio_options = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR"}
        bundled_proj_data = Path(rasterio.__file__).parent / "proj_data"
        if bundled_proj_data.is_dir():
            rasterio_options["PROJ_DATA"] = str(bundled_proj_data)
        with rasterio.Env(**rasterio_options):
            with rasterio.open(source_string) as dataset:
                if dataset.count < 1:
                    raise ValueError(f"Raster has no bands: {source_string}")

                with TemporaryDirectory(
                    prefix="rasterbands-",
                    dir=destination.parent,
                ) as temporary_directory:
                    batch_path = Path(temporary_directory) / "batch.parquet"
                    for window in _windows(dataset, row_group_size):
                        frame = _window_geodataframe(dataset, window)
                        frame.to_parquet(
                            batch_path,
                            engine="pyarrow",
                            compression="zstd",
                            write_covering_bbox=True,
                            row_group_size=row_group_size,
                            index=False,
                        )
                        table = pq.read_table(batch_path)
                        if writer is None:
                            bounds = (
                                dataset.bounds.left,
                                dataset.bounds.bottom,
                                dataset.bounds.right,
                                dataset.bounds.top,
                            )
                            schema = _set_dataset_bbox(table.schema, bounds)
                            table = table.cast(schema)
                            writer = pq.ParquetWriter(
                                temporary_destination,
                                schema,
                                compression="zstd",
                            )
                        writer.write_table(table, row_group_size=row_group_size)

                band_count = dataset.count
                cell_count = dataset.width * dataset.height
    except Exception:
        if writer is not None:
            writer.close()
        temporary_destination.unlink(missing_ok=True)
        raise
    else:
        if writer is None:
            raise RuntimeError(f"Raster contains no cells: {source_string}")
        writer.close()
        os.replace(temporary_destination, destination)

    return ConversionResult(
        source=source_string,
        export_path=destination,
        band_count=band_count,
        cell_count=cell_count,
    )


