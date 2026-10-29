"""Export New Zealand GeoParquet examples for airport and building-point layers."""

import argparse
import logging
from pathlib import Path

try:
	from src.configuration import Config
	from src.extract_geoparquet_layer import GeoParquetLayer
except ModuleNotFoundError:
	from configuration import Config
	from extract_geoparquet_layer import GeoParquetLayer


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
		help="Export all layers in the layer configuration with this theme.",
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
		help="Folder for GeoParquet files and extract_geoparquet.log (default: %(default)s).",
	)
	parser.add_argument(
		"--split-geometry-types",
		action="store_true",
		help="Split each exported file into one additional file per geometry type.",
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
	return parser.parse_args()


def main() -> None:
	"""Export the selected layers using the requested or default bbox coverage."""
	arguments = parse_arguments()
	if arguments.layer_names is not None and arguments.theme is not None:
		raise ValueError("--layer-names and --theme cannot be used together")
	export_folder = (
		arguments.export_folder / arguments.bbox_name.lower()
		if arguments.bbox_name is not None
		else arguments.export_folder
	)
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
	for layer_name in selected_layers:
		bbox = arguments.bbox_name or (
			arguments.extent if arguments.extent is not None else "NZ_MAINLAND"
		)
		layer = GeoParquetLayer(
			url_config.url_path,
			layer_name,
			bbox=bbox,
			export_folder=export_folder,
			data_path=url_config.data_path,
			date=arguments.release_date,
			theme=url_config.get_layer_theme(layer_name),
			url_data_path=url_config.url_data_path,
		)
		if arguments.bbox_name is not None or arguments.extent is not None:
			output_path, copy_query = layer.export_bbox()
		else:
			output_path, copy_query = layer.export_new_zealand()
		print(f"Exported {layer_name} to {output_path}")
		logger.info("COPY SQL for %s:\n%s", layer_name, copy_query)
		if arguments.split_geometry_types:
			for split_output_path in layer.split_geometry_types(output_path):
				print(f"Exported {layer_name} geometry type to {split_output_path}")
				logger.info(
					"Split %s by geometry type to %s",
					layer_name,
					split_output_path,
				)


if __name__ == "__main__":
	main()