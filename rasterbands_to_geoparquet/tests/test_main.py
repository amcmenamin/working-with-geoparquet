import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyarrow.parquet as pq
import rasterio
from pytest import MonkeyPatch
from rasterio.transform import from_origin

from src import (
    RasterToParquet,
    build_raster_path,
    normalize_raster_source,
    raster_to_geoparquet,
)


def test_build_raster_path_for_url() -> None:
    path = build_raster_path(
        "https://data.source.coop/epoch/forest-typology-2020/",
        "v2_beta",
        2025,
        "60G",
        "raster_60G_20_16_3.tif",
    )

    assert path == (
        "https://data.source.coop/epoch/forest-typology-2020/"
        "v2_beta/2025/60G/raster_60G_20_16_3.tif"
    )


def test_normalize_raster_source_for_catalogue_url() -> None:
    source = (
        "https://source.coop/epoch/forest-typology-2020/"
        "v2_beta/2025/60G/raster_60G_20_16_3.tif"
    )

    assert normalize_raster_source(source) == source.replace(
        "https://source.coop/",
        "https://data.source.coop/",
    )


def test_build_raster_path_for_local_directory(tmp_path: Path) -> None:
    path = build_raster_path(
        tmp_path,
        "v1",
        2024,
        "tile-set",
        "tile.tif",
    )

    assert Path(path) == tmp_path / "v1" / "2024" / "tile-set" / "tile.tif"


def test_raster_to_geoparquet_writes_cell_polygons_and_bands(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("PROJ_LIB", raising=False)
    source = tmp_path / "source.tif"
    output = tmp_path / "cells.parquet"
    transform = from_origin(100, 200, 10, 5)
    values = np.array(
        [
            [[1, 2], [3, 4]],
            [[10, 20], [30, 40]],
        ],
        dtype=np.uint8,
    )
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=2,
        dtype=values.dtype,
        crs="EPSG:2193",
        transform=transform,
    ) as dataset:
        dataset.write(values)

    monkeypatch.setenv("PROJ_LIB", str(tmp_path / "invalid-proj"))
    result = RasterToParquet(row_group_size=2).convert(source, output)

    assert result.band_count == 2
    assert result.cell_count == 4
    frame = gpd.read_parquet(output)
    assert frame["band_1"].tolist() == [1, 2, 3, 4]
    assert frame["band_2"].tolist() == [10, 20, 30, 40]
    assert frame.crs.to_epsg() == 2193
    assert frame.geometry.iloc[0].bounds == (100.0, 195.0, 110.0, 200.0)
    assert frame.geometry.iloc[3].bounds == (110.0, 190.0, 120.0, 195.0)

    parquet = pq.ParquetFile(output)
    metadata = parquet.schema_arrow.metadata
    assert metadata is not None
    geo = json.loads(metadata[b"geo"])
    assert geo["columns"]["geometry"]["bbox"] == [100.0, 190.0, 120.0, 200.0]
    assert "bbox" in parquet.schema_arrow.names
    assert parquet.num_row_groups == 2


def test_raster_to_geoparquet_rejects_invalid_row_group_size(
    tmp_path: Path,
) -> None:
    try:
        raster_to_geoparquet("unused.tif", tmp_path / "output.parquet", row_group_size=0)
    except ValueError as error:
        assert str(error) == "row_group_size must be at least 1"
    else:
        raise AssertionError("Expected ValueError")
