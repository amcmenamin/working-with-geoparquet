"""Export New Zealand GeoParquet examples for airport and building-point layers."""

import argparse
import ast
import logging
from pathlib import Path

try:
	from src.configuration import Config
	from src.extract_geoparquet_layer import GeoParquetLayer
	from src.geoparquet_catalog import CatalogExtent, GeoParquetCatalog
	from src.read_aoi import ReadAoi
except ModuleNotFoundError:
	from configuration import Config
	from extract_geoparquet_layer import GeoParquetLayer
	from geoparquet_catalog import CatalogExtent, GeoParquetCatalog
	from read_aoi import ReadAoi


CONFIG = Config()
LAYER_NAMES = ("airport", "building_point")
EXPORT_FOLDER = Path("exports")
logger = logging.getLogger(__name__)


def parse_layer_names(value: str) -> tuple[str, ...]:
	"""Parse a comma-separated list of layer names."""
	layer_names = tuple(name.strip() for name in value.split(",") if name.strip())
	if not layer_names:
		raise argparse.ArgumentTypeError("provide at least one layer name")
	return layer_names


def parse_extent(value: str) -> tuple[float, float, float, float]:
	"""Parse ``west,south,east,north`` bbox coordinates."""
	coordinates = [coordinate.strip() for coordinate in value.split(",")]
	if len(coordinates) != 4:
		raise argparse.ArgumentTypeError(
			"extent must contain west,south,east,north"
		)
	try:
		return tuple(float(coordinate) for coordinate in coordinates)  # type: ignore[return-value]
	except ValueError as error:
		raise argparse.ArgumentTypeError(
			"extent coordinates must be numbers"
		) from error


def parse_query(value: str) -> tuple[str, object]:
	"""Parse a ``field=value`` filter for the DuckDB query."""
	field, separator, raw_value = value.partition("=")
	field = field.strip()
	if not separator or not field or not raw_value.strip():
		raise argparse.ArgumentTypeError("query must use field=value")
	try:
		parsed_value = ast.literal_eval(raw_value.strip())
	except (ValueError, SyntaxError):
		parsed_value = raw_value.strip()
	return field, parsed_value


def parse_arguments() -> argparse.Namespace:
	"""Parse command-line options for GeoParquet exports."""
	parser = argparse.ArgumentParser(
		description="Export remote GeoParquet layers with DuckDB Spatial."
	)
	layer_group = parser.add_mutually_exclusive_group()
	layer_group.add_argument(
		"--layer-names",
		type=parse_layer_names,
		metavar="LAYER[,LAYER...]",
		help="Comma-separated layer names (default: airport,building_point).",
	)
	layer_group.add_argument(
		"--layer-config",
		type=Path,
		metavar="PATH",
		help="Path to a YAML layer configuration file.",
	)
	parser.add_argument(
		"--url-data-path",
		default=CONFIG.url_data_path,
		metavar="NAME",
		help="URL data path key from the URL config (default: %(default)s).",
	)
	parser.add_argument(
		"--theme",
		metavar="THEME",
		help=(
			"Source theme for --layer-names, or export all configured layers "
			"with this theme when --layer-names is omitted."
		),
	)
	parser.add_argument(
		"--url-path-config",
		type=Path,
		default=CONFIG.url_path_config,
		metavar="PATH",
		help="Path to the URL data path YAML file.",
	)
	parser.add_argument(
		"--release-date",
		metavar="DATE",
		help="Release date used by data paths containing {date}, such as Overture.",
	)
	parser.add_argument(
		"--export-folder",
		type=Path,
		default=EXPORT_FOLDER,
		help="Folder for exports and extract_geoparquet.log (default: %(default)s).",
	)
	parser.add_argument(
		"--export-format",
		choices=("parquet", "duckdb"),
		default="parquet",
		help="Export each layer to GeoParquet or a DuckDB table (default: %(default)s).",
	)
	parser.add_argument(
		"--database-path",
		type=Path,
		metavar="PATH",
		help="DuckDB database path; required with --export-format duckdb.",
	)
	parser.add_argument(
		"--split-geometry-types",
		action="store_true",
		help="Split each exported file into one additional file per geometry type.",
	)
	parser.add_argument(
		"--create-catalog",
		"--catalog",
		action="store_true",
		dest="create_catalog",
		help="Create or update catalog.duckdb beside each GeoParquet export.",
	)
	parser.add_argument(
		"--catalog-only",
		action="store_true",
		help="Create filtered remote-backed catalog views without exporting files.",
	)
	parser.add_argument(
		"--query",
		dest="query",
		type=parse_query,
		action="append",
		metavar="FIELD=VALUE",
		help="Filter rows with a field=value condition; may be repeated.",
	)
	bbox_group = parser.add_mutually_exclusive_group()
	bbox_group.add_argument(
		"--bbox-name",
		choices=sorted(GeoParquetLayer.NAMED_BBOXES),
		help="Named bbox to export instead of all configured New Zealand regions.",
	)
	bbox_group.add_argument(
		"--extent",
		type=parse_extent,
		metavar="WEST,SOUTH,EAST,NORTH",
		help="Comma-separated bbox to export instead of all configured New Zealand regions.",
	)
	bbox_group.add_argument(
		"--extent-geopackage",
		"--extent-gpkg",
		dest="extent_geopackage",
		type=Path,
		metavar="PATH",
		help="GeoPackage containing one export geometry per feature.",
	)
	parser.add_argument(
		"--extent-layer",
		metavar="LAYER",
		help="Layer to read from --extent-geopackage.",
	)
	arguments = parser.parse_args()
	if (arguments.extent_geopackage is None) != (arguments.extent_layer is None):
		parser.error("--extent-geopackage and --extent-layer must be used together")
	if arguments.export_format == "duckdb" and arguments.database_path is None:
		parser.error("--database-path is required with --export-format duckdb")
	if arguments.export_format == "parquet" and arguments.database_path is not None:
		parser.error("--database-path requires --export-format duckdb")
	if arguments.export_format == "duckdb" and arguments.split_geometry_types:
		parser.error("--split-geometry-types requires --export-format parquet")
	if arguments.export_format == "duckdb" and arguments.create_catalog:
		parser.error("--create-catalog requires --export-format parquet")
	if arguments.export_format == "duckdb" and arguments.catalog_only:
		parser.error("--catalog-only requires --export-format parquet")
	if arguments.catalog_only and arguments.create_catalog:
		parser.error("--catalog-only cannot be combined with --create-catalog")
	if arguments.catalog_only and arguments.split_geometry_types:
		parser.error("--catalog-only cannot be combined with --split-geometry-types")
	return arguments


def main() -> None:
	"""Export the selected layers using the requested or default bbox coverage."""
	arguments = parse_arguments()
	export_folder = (
		arguments.export_folder / arguments.bbox_name.lower()
		if arguments.bbox_name is not None
		else arguments.export_folder
	)
	if not arguments.catalog_only:
		export_folder.mkdir(parents=True, exist_ok=True)
		logging.basicConfig(
			filename=export_folder / "extract_geoparquet.log",
			level=logging.INFO,
			format="%(asctime)s %(levelname)s %(message)s",
		)
	layer_config = (
		Config(layer_file=arguments.layer_config)
		if arguments.layer_config is not None
		else CONFIG
	)
	if arguments.layer_names is not None:
		selected_layers = arguments.layer_names
	elif arguments.theme is not None:
		selected_layers = tuple(
			layer_name
			for layer_name, layer_theme in layer_config.layers.items()
			if layer_theme == arguments.theme
		)
		if not selected_layers:
			raise ValueError(
				f"No layers found with theme {arguments.theme!r}"
			)
	elif arguments.layer_config is not None:
		selected_layers = tuple(layer_config.layers)
	else:
		selected_layers = LAYER_NAMES
	url_config = Config(
		url_data_path=arguments.url_data_path,
		url_path_config=arguments.url_path_config,
		layer_file=arguments.layer_config,
	)
	use_new_zealand = (
		arguments.bbox_name is None
		and arguments.extent is None
		and arguments.extent_geopackage is None
	)
	if arguments.extent_geopackage is not None:
		geopackage_extents = ReadAoi(
			arguments.extent_geopackage, arguments.extent_layer
		).read_geopackage_extents()
		if not geopackage_extents:
			raise ValueError(
				f"Layer {arguments.extent_layer!r} contains no non-null geometries"
			)
		extent_exports = tuple(
			(bbox, f"_{index}")
			for index, bbox in enumerate(geopackage_extents, start=1)
		)
	else:
		bbox = arguments.bbox_name or (
			arguments.extent if arguments.extent is not None else "NZ_MAINLAND"
		)
		extent_exports = ((bbox, ""),)
	for layer_name in selected_layers:
		for bbox, output_suffix in extent_exports:
			layer_theme = (
				arguments.theme
				if arguments.layer_names is not None and arguments.theme is not None
				else url_config.get_layer_theme(layer_name)
			)
			layer = GeoParquetLayer(
				url_config.url_path,
				layer_name,
				bbox=bbox,
				export_folder=export_folder,
				data_path=url_config.data_path,
				date=arguments.release_date,
				theme=layer_theme,
				url_data_path=url_config.url_data_path,
				query=tuple(arguments.query or ()),
				output_suffix=output_suffix,
				export_format=arguments.export_format,
				database_path=arguments.database_path,
			)
			if use_new_zealand:
				catalog_extents = tuple(
					CatalogExtent(name, layer.NAMED_BBOXES[name])
					for name in layer.NZ_BBOX_NAMES
				)
			elif isinstance(bbox, str):
				catalog_extents = (CatalogExtent(bbox, layer.bbox),)
			elif arguments.extent_geopackage is not None:
				extent_index = output_suffix.removeprefix("_")
				catalog_extents = (
					CatalogExtent(
						f"{arguments.extent_layer}_{extent_index}",
						layer.bbox,
					),
				)
			else:
				catalog_extents = (
					CatalogExtent("EXPLICIT_EXTENT", layer.bbox),
				)
			export_bboxes = [extent.bbox for extent in catalog_extents]
			if arguments.catalog_only:
				catalog = GeoParquetCatalog(
					layer.output_path.parent / "catalog.duckdb"
				)
				entry = catalog.register_remote(
					layer.build_select_query(export_bboxes),
					layer.output_table_name,
					layer.layer_name,
					layer.parquet_url,
					catalog_extents,
				)
				print(
					f"Cataloged remote {layer_name} as {entry.view_name} "
					f"in {entry.catalog_path}"
				)
				continue
			if use_new_zealand:
				output_path, copy_query = layer.export_new_zealand()
			else:
				output_path, copy_query = layer.export_bbox()
			if arguments.export_format == "duckdb":
				print(
					f"Exported {layer_name} to table "
					f"{layer.output_table_name} in {output_path}"
				)
			else:
				print(f"Exported {layer_name} to {output_path}")
			logger.info("Export SQL for %s:\n%s", layer_name, copy_query)
			catalog = (
				GeoParquetCatalog(output_path.parent / "catalog.duckdb")
				if arguments.create_catalog
				else None
			)
			if catalog is not None:
				entry = catalog.register(
					output_path,
					layer.output_table_name,
					layer.layer_name,
					layer.parquet_url,
					catalog_extents,
				)
				print(
					f"Cataloged {output_path.name} as {entry.view_name} "
					f"in {entry.catalog_path}"
				)
			if arguments.split_geometry_types:
				for split_output_path in layer.split_geometry_types(output_path):
					print(f"Exported {layer_name} geometry type to {split_output_path}")
					logger.info(
						"Split %s by geometry type to %s",
						layer_name,
						split_output_path,
					)
					if catalog is not None:
						entry = catalog.register(
							split_output_path,
							split_output_path.stem,
							layer.layer_name,
							layer.parquet_url,
							catalog_extents,
						)
						print(
							f"Cataloged {split_output_path.name} as "
							f"{entry.view_name} in {entry.catalog_path}"
						)


if __name__ == "__main__":
	main()