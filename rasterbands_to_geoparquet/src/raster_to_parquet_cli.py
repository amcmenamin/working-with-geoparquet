from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from src.raster_to_parquet import (
    DEFAULT_DATA_PATH,
    RasterToParquet,
    build_raster_path,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert every cell in a TIFF raster to a GeoParquet polygon.",
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
    parser.add_argument("--export-path", required=True, type=Path)
    parser.add_argument("--row-group-size", default=100_000, type=int)
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
    converter = RasterToParquet(row_group_size=args.row_group_size)
    result = converter.convert(
        source,
        args.export_path,
    )
    print(f"Band count: {result.band_count}")
    print(f"Cell polygons written: {result.cell_count}")
    print(f"GeoParquet: {result.export_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
