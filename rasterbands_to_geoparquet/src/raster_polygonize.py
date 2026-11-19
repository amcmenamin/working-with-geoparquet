from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape

from src.raster_to_parquet import normalize_raster_source, set_dataset_bbox


@dataclass(frozen=True)
class PolygonizeResult:
    source: str
    output_paths: tuple[Path, ...]

    @property
    def band_count(self) -> int:
        return len(self.output_paths)


@dataclass(frozen=True)
class RasterPolygonizer:
    output_folder: Path
    connectivity: int = 4
    row_group_size: int = 100_000
    include_nodata: bool = False
    overwrite: bool = False

    def __post_init__(self) -> None:
        if self.connectivity not in {4, 8}:
            raise ValueError("connectivity must be 4 or 8")
        if self.row_group_size < 1:
            raise ValueError("row_group_size must be at least 1")

    def polygonize(self, source: str | Path) -> PolygonizeResult:
        source_string = normalize_raster_source(source)
        self.output_folder.mkdir(parents=True, exist_ok=True)
        source_name = Path(urlparse(source_string).path).stem or "raster"

        rasterio_options = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR"}
        bundled_proj_data = Path(rasterio.__file__).parent / "proj_data"
        if bundled_proj_data.is_dir():
            rasterio_options["PROJ_DATA"] = str(bundled_proj_data)

        with rasterio.Env(**rasterio_options):
            with rasterio.open(source_string) as dataset:
                output_paths = tuple(
                    self.output_folder
                    / f"{source_name}_band_{band_number}.parquet"
                    for band_number in range(1, dataset.count + 1)
                )
                existing = [path for path in output_paths if path.exists()]
                if existing and not self.overwrite:
                    paths = ", ".join(str(path) for path in existing)
                    raise FileExistsError(f"Output file already exists: {paths}")

                with TemporaryDirectory(
                    prefix="raster-polygonize-",
                    dir=self.output_folder,
                ) as temporary_directory:
                    temporary_folder = Path(temporary_directory)
                    for band_number, output_path in enumerate(
                        output_paths,
                        start=1,
                    ):
                        self._polygonize_band(
                            dataset,
                            band_number,
                            temporary_folder / output_path.name,
                        )
                    for output_path in output_paths:
                        os.replace(
                            temporary_folder / output_path.name,
                            output_path,
                        )

        return PolygonizeResult(
            source=source_string,
            output_paths=output_paths,
        )

    def _polygonize_band(
        self,
        dataset: rasterio.io.DatasetReader,
        band_number: int,
        output_path: Path,
    ) -> None:
        band = dataset.read(band_number, masked=not self.include_nodata)
        source_values = np.asarray(band.data if np.ma.isMaskedArray(band) else band)
        valid_mask = (
            None
            if self.include_nodata
            else ~np.ma.getmaskarray(band)
        )
        feature_iterator = shapes(
            source_values,
            mask=valid_mask,
            connectivity=self.connectivity,
            transform=dataset.transform,
        )
        frames = self._frames(
            feature_iterator,
            band_number,
            dataset.dtypes[band_number - 1],
            dataset.crs,
        )
        self._write_frames(frames, output_path, dataset.bounds)

    def _frames(
        self,
        features: Iterator[tuple[dict[str, object], float]],
        band_number: int,
        dtype: str,
        crs: object,
    ) -> Iterator[gpd.GeoDataFrame]:
        values: list[object] = []
        geometries = []
        yielded_frame = False
        for geometry, value in features:
            values.append(np.asarray(value).astype(dtype).item())
            geometries.append(shape(geometry))
            if len(values) == self.row_group_size:
                yield self._frame(values, geometries, band_number, dtype, crs)
                yielded_frame = True
                values = []
                geometries = []
        if values:
            yield self._frame(values, geometries, band_number, dtype, crs)
        elif not yielded_frame:
            yield self._frame([], [], band_number, dtype, crs)

    @staticmethod
    def _frame(
        values: list[object],
        geometries: list[object],
        band_number: int,
        dtype: str,
        crs: object,
    ) -> gpd.GeoDataFrame:
        frame = pd.DataFrame(
            {
                "band": np.full(len(values), band_number, dtype=np.int32),
                "value": np.asarray(values, dtype=dtype),
            }
        )
        return gpd.GeoDataFrame(frame, geometry=geometries, crs=crs)

    def _write_frames(
        self,
        frames: Iterator[gpd.GeoDataFrame],
        output_path: Path,
        bounds: rasterio.coords.BoundingBox,
    ) -> None:
        writer: pq.ParquetWriter | None = None
        try:
            with TemporaryDirectory(
                prefix="polygon-batches-",
                dir=output_path.parent,
            ) as temporary_directory:
                batch_path = Path(temporary_directory) / "batch.parquet"
                for frame in frames:
                    frame.to_parquet(
                        batch_path,
                        engine="pyarrow",
                        compression="zstd",
                        write_covering_bbox=True,
                        row_group_size=self.row_group_size,
                        index=False,
                    )
                    table = pq.read_table(batch_path)
                    if writer is None:
                        schema = set_dataset_bbox(
                            table.schema,
                            (bounds.left, bounds.bottom, bounds.right, bounds.top),
                        )
                        table = table.cast(schema)
                        writer = pq.ParquetWriter(
                            output_path,
                            schema,
                            compression="zstd",
                        )
                    writer.write_table(
                        table,
                        row_group_size=self.row_group_size,
                    )
            if writer is None:
                raise RuntimeError("Polygonization produced no output schema")
        finally:
            if writer is not None:
                writer.close()
