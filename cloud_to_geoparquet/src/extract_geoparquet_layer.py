import duckdb
import logging
from datetime import datetime
from pathlib import Path

try:
	from src.configuration import Config
	from src.named_bboxes import NamedBBoxes
except ModuleNotFoundError:
	from configuration import Config
	from named_bboxes import NamedBBoxes


config = Config()
url_path = config.url_path
data_path = config.data_path
layer_name = "airport"
export_folder = Path("exports")

NZ_BBOX_NAMES = (
	"NZ_MAINLAND",
	"CHATHAM_ISLANDS",
	"SNARES_ISLANDS",
	"AUCKLAND_ISLANDS",
	"CAMPBELL_ISLAND",
	"ANTIPODES_ISLANDS",
	"BOUNTY_ISLANDS",
	"RAOUL_ISLAND",
	"MACAULEY_CURTIS_ISLANDS",
)
NAMED_BBOX_CONFIG = NamedBBoxes()


class GeoParquetLayer:
	"""Query a remote GeoParquet 1.1 layer with DuckDB Spatial.

	The layer must expose a native ``geometry`` column and a per-row ``bbox``
	covering with ``xmin``, ``ymin``, ``xmax``, and ``ymax`` fields.
	"""

	BBOXES = NAMED_BBOX_CONFIG
	NZ_BBOXES = {NAMED_BBOX_CONFIG.get_bbox(name) for name in NZ_BBOX_NAMES}
	NAMED_BBOXES = NAMED_BBOX_CONFIG.as_mapping()

	def __init__(
		self,
		url_path: str,
		layer_name: str,
		bbox: str | tuple[float, float, float, float] = "NZ_MAINLAND",
		export_folder: str | Path = export_folder,
		data_path: str = "{layer_name}/latest/",
		date: str | None = None,
		theme: str | None = None,
		url_data_path: str = "nztopodev",
	) -> None:
		self.url_path = url_path.rstrip("/")
		self.layer_name = layer_name
		self.data_path = data_path
		self.date = date
		self.theme = theme
		self.url_data_path = url_data_path
		self.bbox = bbox
		self.export_folder = Path(export_folder)

	@property
	def bbox(self) -> tuple[float, float, float, float]:
		"""Return the default bbox used when ``query_bbox()`` has no argument."""
		return self._bbox

	@bbox.setter
	def bbox(self, value: str | tuple[float, float, float, float]) -> None:
		"""Set a named bbox or explicit ``(west, south, east, north)`` extent."""
		if isinstance(value, str):
			self._bbox = self.BBOXES.get_bbox(value)
			return

		west, south, east, north = value
		if west > east or south > north:
			raise ValueError("bbox must be ordered as (west, south, east, north)")
		self._bbox = value

	@property
	def parquet_url(self) -> str:
		"""Return the configured remote GeoParquet path for this layer."""
		try:
			path = self.data_path.format(
				layer_name=self.layer_name,
				date=self.date,
				theme=self.theme,
			)
		except KeyError as error:
			raise ValueError(
				f"Unsupported placeholder {error.args[0]!r} in data_path"
			) from error
		if "{date}" in self.data_path and self.date is None:
			raise ValueError("date is required by data_path")
		if "{theme}" in self.data_path and self.theme is None:
			raise ValueError("theme is required by data_path")
		if path.endswith("/"):
			path += "*.parquet"
		return f"{self.url_path}/{path.lstrip('/')}"

	@property
	def output_path(self) -> Path:
		"""Return the GeoParquet export path for this layer."""
		return self.export_folder / self.url_data_path / f"{self.layer_name}.parquet"

	def query_bbox(
		self, bbox: tuple[float, float, float, float] | None = None
	) -> list[tuple[object, ...]]:
		"""Return rows that intersect an explicit or configured default bbox."""
		return self.query_bboxes((self.bbox if bbox is None else bbox,))

	def query_new_zealand(self) -> list[tuple[object, ...]]:
		"""Return rows from mainland New Zealand and selected offshore islands."""
		return self.query_bboxes(self.NZ_BBOXES)

	def query_bboxes(
		self, bboxes: set[tuple[float, float, float, float]]
		| tuple[tuple[float, float, float, float], ...],
	) -> list[tuple[object, ...]]:
		"""Return rows that intersect one or more ``(west, south, east, north)`` bboxes.

		The bbox covering predicate is evaluated before the exact geometry
		intersection, allowing DuckDB to prune non-overlapping data.
		"""
		if not bboxes:
			return []

		conditions = []
		query_parameters: list[object] = [self.parquet_url]
		for west, south, east, north in bboxes:
			conditions.append("""
				(bbox.xmax >= ?
					AND bbox.xmin <= ?
					AND bbox.ymax >= ?
					AND bbox.ymin <= ?
					AND ST_Intersects(
						geometry,
						ST_MakeEnvelope(?, ?, ?, ?)
					)
				)
			""")
			query_parameters.extend(
				[west, east, south, north, west, south, east, north]
			)

		query = "SELECT * FROM read_parquet(?) WHERE " + " OR ".join(conditions)
		connection = duckdb.connect()
		connection.execute("SET allow_asterisks_in_http_paths = true")
		connection.execute("INSTALL spatial")
		connection.execute("LOAD spatial")
		return connection.execute(query, query_parameters).fetchall()

	def export_bbox(
		self, bbox: tuple[float, float, float, float] | None = None
	) -> tuple[Path, str]:
		"""Export the configured or explicit bbox and return its path and SQL."""
		return self.export_bboxes((self.bbox if bbox is None else bbox,))

	def export_new_zealand(self) -> tuple[Path, str]:
		"""Export mainland New Zealand and selected offshore islands with COPY."""
		return self.export_bboxes(self.NZ_BBOXES)

	def export_bboxes(
		self, bboxes: set[tuple[float, float, float, float]]
		| tuple[tuple[float, float, float, float], ...],
	) -> tuple[Path, str]:
		"""Export rows and return the GeoParquet path and executed COPY SQL."""
		if not bboxes:
			raise ValueError("at least one bbox is required for export")

		conditions = []
		query_parameters: list[object] = [self.parquet_url]
		for west, south, east, north in bboxes:
			conditions.append("""
				(bbox.xmax >= ?
					AND bbox.xmin <= ?
					AND bbox.ymax >= ?
					AND bbox.ymin <= ?
					AND ST_Intersects(
						geometry,
						ST_MakeEnvelope(?, ?, ?, ?)
					)
				)
			""")
			query_parameters.extend(
				[west, east, south, north, west, south, east, north]
			)

		select_query = "SELECT * FROM read_parquet(?) WHERE " + " OR ".join(conditions)
		for query_parameter in query_parameters:
			if isinstance(query_parameter, str):
				literal = "'" + query_parameter.replace("'", "''") + "'"
			else:
				literal = str(query_parameter)
			select_query = select_query.replace("?", literal, 1)

		self.output_path.parent.mkdir(parents=True, exist_ok=True)
		escaped_output_path = str(self.output_path).replace("'", "''")
		copy_query = (
			f"COPY ({select_query}) TO '{escaped_output_path}' "
			"(FORMAT PARQUET, COMPRESSION ZSTD)"
		)
		connection = duckdb.connect()
		connection.execute("SET allow_asterisks_in_http_paths = true")
		connection.execute("INSTALL spatial")
		connection.execute("LOAD spatial")
		connection.execute(copy_query)
		return self.output_path, copy_query


def main() -> None:
	"""Export airports in mainland New Zealand and selected offshore islands."""
	starttime = datetime.now()
	print(f"Running Process: {starttime}")
	geoparquet_layer = GeoParquetLayer(
		url_path,
		layer_name,
		export_folder=export_folder,
		data_path=data_path,
		url_data_path=config.url_data_path,
	)
	geoparquet_layer.export_folder.mkdir(parents=True, exist_ok=True)
	logging.basicConfig(
		filename=geoparquet_layer.export_folder / "extract_geoparquet.log",
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(message)s",
	)
	output_path, copy_query = geoparquet_layer.export_new_zealand()
	endtime = datetime.now()
	delta = endtime - starttime
	print(f"Exported airports to {output_path}")
	print(f"Start time: {starttime}")
	print(f"End time: {endtime}")
	print(f"Elapsed time: {delta}")
	logging.info("COPY SQL for %s:\n%s", layer_name, copy_query)
	logging.info("Start time: %s", starttime)
	logging.info("End time: %s", endtime)
	logging.info("Elapsed time: %s", delta)


if __name__ == "__main__":
	main()

