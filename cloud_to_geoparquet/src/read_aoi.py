"""Read area-of-interest extents from GeoPackage layers."""

from pathlib import Path

import duckdb


BBox = tuple[float, float, float, float]


class ReadAoi:
	"""Read WGS84 extents from a GeoPackage area-of-interest layer."""

	def __init__(self, path: Path, layer_name: str) -> None:
		self.path = path
		self.layer_name = layer_name

	def read_geopackage_extents(self) -> tuple[BBox, ...]:
		"""Return one WGS84 bbox per non-null feature in the configured layer."""
		if not self.path.is_file():
			raise FileNotFoundError(f"GeoPackage not found: {self.path}")

		connection = duckdb.connect()
		try:
			connection.execute("INSTALL spatial")
			connection.execute("LOAD spatial")
			metadata = connection.execute(
				"SELECT layers FROM ST_Read_Meta(?)", [str(self.path)]
			).fetchone()
			layers = metadata[0] if metadata is not None else []
			layer = next(
				(item for item in layers if item["name"] == self.layer_name), None
			)
			if layer is None:
				available_layers = ", ".join(item["name"] for item in layers)
				raise ValueError(
					f"Layer {self.layer_name!r} not found in {self.path}. "
					f"Available layers: {available_layers or 'none'}"
				)
			geometry_fields = layer["geometry_fields"]
			if not geometry_fields:
				raise ValueError(f"Layer {self.layer_name!r} has no geometry column")
			geometry_field = geometry_fields[0]
			crs = geometry_field["crs"]
			if crs is None:
				raise ValueError(
					f"Layer {self.layer_name!r} has no coordinate reference system"
				)
			source_crs = (
				f"{crs['auth_name']}:{crs['auth_code']}"
				if crs["auth_name"] and crs["auth_code"]
				else crs["wkt"] or crs["proj4"]
			)
			if not source_crs:
				raise ValueError(
					f"Layer {self.layer_name!r} has no usable coordinate reference system"
				)

			geometry_column = '"' + geometry_field["name"].replace('"', '""') + '"'
			rows = connection.execute(
				f"""
				SELECT
					ST_XMin(feature_extent),
					ST_YMin(feature_extent),
					ST_XMax(feature_extent),
					ST_YMax(feature_extent)
				FROM (
					SELECT ST_Extent(
						ST_Transform({geometry_column}, ?, 'EPSG:4326', true)
					) AS feature_extent
					FROM ST_Read(?, layer = ?)
					WHERE {geometry_column} IS NOT NULL
				)
				""",
				[source_crs, str(self.path), self.layer_name],
			).fetchall()
			return tuple(tuple(float(value) for value in row) for row in rows)  # type: ignore[return-value]
		finally:
			connection.close()