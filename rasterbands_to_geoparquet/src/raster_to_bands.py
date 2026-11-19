from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import rasterio

from src.raster_to_parquet import (
    DEFAULT_DATA_PATH,
    build_raster_path,
    normalize_raster_source,
)


@dataclass(frozen=True)
class BandSplitResult:
    source: str
    output_paths: tuple[Path, ...]

    @property
    def band_count(self) -> int:
        return len(self.output_paths)


@dataclass(frozen=True)
class RasterToBands:
    output_folder: Path
    overwrite: bool = False

    def split(self, source: str | Path) -> BandSplitResult:
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
                    self.output_folder / f"{source_name}_band_{band_number}.tif"
                    for band_number in range(1, dataset.count + 1)
                )
                existing = [path for path in output_paths if path.exists()]
                if existing and not self.overwrite:
                    paths = ", ".join(str(path) for path in existing)
                    raise FileExistsError(f"Output file already exists: {paths}")

                with TemporaryDirectory(
                    prefix="raster-bands-",
                    dir=self.output_folder,
                ) as temporary_directory:
                    temporary_paths = self._write_bands(
                        dataset,
                        Path(temporary_directory),
                        output_paths,
                    )
                    for temporary_path, output_path in zip(
                        temporary_paths,
                        output_paths,
                        strict=True,
                    ):
                        os.replace(temporary_path, output_path)

        return BandSplitResult(source=source_string, output_paths=output_paths)

    @staticmethod
    def _write_bands(
        dataset: rasterio.io.DatasetReader,
        temporary_folder: Path,
        output_paths: tuple[Path, ...],
    ) -> tuple[Path, ...]:
        profile = dataset.profile.copy()
        profile.update(driver="GTiff", count=1)
        temporary_paths: list[Path] = []

        for band_number, output_path in enumerate(output_paths, start=1):
            temporary_path = temporary_folder / output_path.name
            with rasterio.open(temporary_path, "w", **profile) as destination:
                for _, window in dataset.block_windows(band_number):
                    values = dataset.read(band_number, window=window)
                    destination.write(values, 1, window=window)
                destination.update_tags(**dataset.tags())
                destination.update_tags(1, **dataset.tags(band_number))
                description = dataset.descriptions[band_number - 1]
                if description:
                    destination.set_band_description(1, description)
            temporary_paths.append(temporary_path)

        return tuple(temporary_paths)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split a multiband TIFF into one GeoTIFF per band.",
    )
    parser.add_argument("--data-path", default=DEFAULT_DATA_PATH)
    parser.add_argument("--version", default="v2_beta")
    parser.add_argument("--year", default="2025")
    parser.add_argument("--location", default="60G")
    parser.add_argument("--tile-name", default="raster_60G_20_16_3.tif")
    parser.add_argument(
        "--input-path",
        help="Direct local path or HTTP(S) TIFF URL; overrides the composed path.",
    )
    parser.add_argument("--output-folder", required=True, type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing band TIFFs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = args.input_path or build_raster_path(
        args.data_path,
        args.version,
        args.year,
        args.location,
        args.tile_name,
    )
    print(f"Source: {source}")
    result = RasterToBands(
        output_folder=args.output_folder,
        overwrite=args.overwrite,
    ).split(source)
    print(f"Band count: {result.band_count}")
    for output_path in result.output_paths:
        print(f"GeoTIFF: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
