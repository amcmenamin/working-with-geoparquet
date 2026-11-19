from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from src.raster_polygonize import RasterPolygonizer
from src.raster_to_parquet import DEFAULT_DATA_PATH, build_raster_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Merge connected equal-value raster cells and write one "
            "GeoParquet file per band."
        ),
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
    parser.add_argument("--row-group-size", default=100_000, type=int)
    parser.add_argument(
        "--connectivity",
        choices=(4, 8),
        default=4,
        type=int,
        help="Merge cells sharing edges (4) or edges and corners (8).",
    )
    parser.add_argument(
        "--include-nodata",
        action="store_true",
        help="Include nodata regions; excluded by default.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing per-band GeoParquet files.",
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
    result = RasterPolygonizer(
        output_folder=args.output_folder,
        connectivity=args.connectivity,
        row_group_size=args.row_group_size,
        include_nodata=args.include_nodata,
        overwrite=args.overwrite,
    ).polygonize(source)
    print(f"Band count: {result.band_count}")
    for output_path in result.output_paths:
        print(f"GeoParquet: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
