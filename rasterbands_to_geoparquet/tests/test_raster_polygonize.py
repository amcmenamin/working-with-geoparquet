from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src import RasterPolygonizer


def _write_source(path: Path) -> None:
    values = np.array(
        [
            [[1, 1, 2], [1, 2, 2], [3, 3, 3]],
            [[5, 0, 5], [0, 5, 0], [5, 0, 5]],
            [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        ],
        dtype=np.uint8,
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=3,
        width=3,
        count=3,
        dtype=values.dtype,
        nodata=0,
        crs="EPSG:2193",
        transform=from_origin(100, 200, 10, 10),
    ) as dataset:
        dataset.write(values)


def test_polygonizer_writes_merged_per_band_geoparquet(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)

    result = RasterPolygonizer(
        tmp_path / "polygons",
        row_group_size=2,
    ).polygonize(source)

    assert [path.name for path in result.output_paths] == [
        "source_band_1.parquet",
        "source_band_2.parquet",
        "source_band_3.parquet",
    ]
    first_band = gpd.read_parquet(result.output_paths[0])
    assert first_band["band"].tolist() == [1, 1, 1]
    assert sorted(first_band["value"].tolist()) == [1, 2, 3]
    assert sorted(first_band.geometry.area.tolist()) == [300.0, 300.0, 300.0]
    assert first_band.crs.to_epsg() == 2193

    second_band = gpd.read_parquet(result.output_paths[1])
    assert second_band["band"].tolist() == [2, 2, 2, 2, 2]
    assert second_band["value"].tolist() == [5, 5, 5, 5, 5]
    assert second_band.geometry.area.tolist() == [100.0] * 5

    third_band = gpd.read_parquet(result.output_paths[2])
    assert third_band.empty
    assert third_band.crs.to_epsg() == 2193


def test_polygonizer_requires_overwrite_for_existing_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)
    polygonizer = RasterPolygonizer(tmp_path / "polygons")
    polygonizer.polygonize(source)

    with pytest.raises(FileExistsError, match="Output file already exists"):
        polygonizer.polygonize(source)
