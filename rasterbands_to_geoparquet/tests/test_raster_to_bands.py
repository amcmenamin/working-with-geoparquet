from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src import RasterToBands


def _write_source(path: Path) -> np.ndarray:
    values = np.array(
        [
            [[1, 2], [3, 4]],
            [[10, 20], [30, 40]],
        ],
        dtype=np.uint8,
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=2,
        dtype=values.dtype,
        crs="EPSG:2193",
        transform=from_origin(100, 200, 10, 5),
    ) as dataset:
        dataset.write(values)
        dataset.set_band_description(1, "first band")
        dataset.update_tags(2, category="second")
    return values


def test_raster_to_bands_writes_one_tiff_per_band(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    values = _write_source(source)

    result = RasterToBands(tmp_path / "bands").split(source)

    assert result.band_count == 2
    assert [path.name for path in result.output_paths] == [
        "source_band_1.tif",
        "source_band_2.tif",
    ]
    for band_number, output_path in enumerate(result.output_paths, start=1):
        with rasterio.open(output_path) as dataset:
            assert dataset.count == 1
            assert dataset.crs.to_epsg() == 2193
            assert dataset.transform == from_origin(100, 200, 10, 5)
            np.testing.assert_array_equal(dataset.read(1), values[band_number - 1])

    with rasterio.open(result.output_paths[0]) as first:
        assert first.descriptions == ("first band",)
    with rasterio.open(result.output_paths[1]) as second:
        assert second.tags(1)["category"] == "second"


def test_raster_to_bands_requires_overwrite_for_existing_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.tif"
    _write_source(source)
    splitter = RasterToBands(tmp_path / "bands")
    splitter.split(source)

    with pytest.raises(FileExistsError, match="Output file already exists"):
        splitter.split(source)

    overwritten = RasterToBands(tmp_path / "bands", overwrite=True).split(source)
    assert overwritten.band_count == 2
