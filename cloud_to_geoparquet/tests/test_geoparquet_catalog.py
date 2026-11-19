from pathlib import Path

import duckdb

from src.extract_geoparquet_layer import GeoParquetLayer
from src.geoparquet_catalog import CatalogExtent, GeoParquetCatalog


def _write_parquet(path: Path, rows: tuple[tuple[int, str], ...]) -> None:
	with duckdb.connect() as connection:
		connection.execute("INSTALL spatial")
		connection.execute("LOAD spatial")
		connection.execute(
			"CREATE TABLE source (id INTEGER, name VARCHAR, geometry GEOMETRY)"
		)
		connection.executemany(
			"INSERT INTO source VALUES (?, ?, ST_Point(?, ?))",
			[(identifier, name, identifier, identifier) for identifier, name in rows],
		)
		connection.execute(
			"COPY source TO ? (FORMAT PARQUET)",
			[str(path)],
		)


def test_catalog_registers_and_replaces_views_with_metadata(tmp_path: Path) -> None:
	roads_path = tmp_path / "roads.parquet"
	rivers_path = tmp_path / "rivers.parquet"
	catalog_path = tmp_path / "catalog.duckdb"
	_write_parquet(roads_path, ((1, "first"),))
	_write_parquet(rivers_path, ((2, "river"),))
	catalog = GeoParquetCatalog(catalog_path)

	catalog.register(
		roads_path,
		"roads",
		"roads",
		"https://example.test/roads/*.parquet",
		(CatalogExtent("ROADS_EXTENT", (170.0, -46.0, 171.0, -45.0)),),
	)
	catalog.register(
		rivers_path,
		"rivers",
		"rivers",
		"https://example.test/rivers/*.parquet",
		(CatalogExtent("RIVERS_EXTENT", (172.0, -44.0, 173.0, -43.0)),),
	)

	with duckdb.connect(str(catalog_path)) as connection:
		connection.execute("LOAD spatial")
		assert connection.execute(
			"SELECT id, name FROM roads"
		).fetchall() == [(1, "first")]
		assert connection.execute(
			"SELECT id, name FROM rivers"
		).fetchall() == [(2, "river")]
		assert connection.execute(
			"SELECT view_name FROM datasets ORDER BY view_name"
		).fetchall() == [("rivers",), ("roads",)]
		assert connection.execute(
			"SELECT view_name, extent_name, west, south, east, north "
			"FROM extents ORDER BY view_name"
		).fetchall() == [
			("rivers", "RIVERS_EXTENT", 172.0, -44.0, 173.0, -43.0),
			("roads", "ROADS_EXTENT", 170.0, -46.0, 171.0, -45.0),
		]

	roads_path.unlink()
	_write_parquet(roads_path, ((3, "replacement"), (4, "second")))
	catalog.register(
		roads_path,
		"roads",
		"roads",
		"https://example.test/roads/*.parquet",
		(CatalogExtent("UPDATED_EXTENT", (174.0, -42.0, 175.0, -41.0)),),
	)

	with duckdb.connect(str(catalog_path)) as connection:
		connection.execute("LOAD spatial")
		assert connection.execute(
			"SELECT id, name FROM roads ORDER BY id"
		).fetchall() == [
			(3, "replacement"),
			(4, "second"),
		]
		assert connection.execute(
			"SELECT count(*) FROM downloads WHERE view_name = 'roads'"
		).fetchone() == (2,)
		assert connection.execute(
			"SELECT extent_name, west, south, east, north FROM extents "
			"WHERE view_name = 'roads'"
		).fetchone() == (
			"UPDATED_EXTENT",
			174.0,
			-42.0,
			175.0,
			-41.0,
		)


def test_catalog_registers_filtered_remote_view_without_download(
	tmp_path: Path,
) -> None:
	source_path = tmp_path / "remote-source.parquet"
	catalog_path = tmp_path / "catalog.duckdb"
	_write_parquet(source_path, ((1, "excluded"), (2, "included")))
	escaped_source_path = str(source_path).replace("'", "''")
	catalog = GeoParquetCatalog(catalog_path)

	catalog.register_remote(
		f"SELECT * FROM read_parquet('{escaped_source_path}') WHERE id = 2",
		"remote_roads",
		"roads",
		"https://example.test/roads/*.parquet",
		(CatalogExtent("REMOTE_EXTENT", (170.0, -46.0, 171.0, -45.0)),),
	)

	with duckdb.connect(str(catalog_path)) as connection:
		connection.execute("LOAD spatial")
		assert connection.execute(
			"SELECT id, name FROM remote_roads"
		).fetchall() == [(2, "included")]
		assert connection.execute(
			"SELECT source_kind, parquet_path FROM datasets "
			"WHERE view_name = 'remote_roads'"
		).fetchone() == (
			"remote",
			"https://example.test/roads/*.parquet",
		)
		assert connection.execute(
			"SELECT count(*) FROM downloads WHERE view_name = 'remote_roads'"
		).fetchone() == (0,)


def test_remote_select_query_keeps_bbox_and_attribute_filters() -> None:
	layer = GeoParquetLayer(
		"https://example.test",
		"roads",
		bbox=(170.0, -46.0, 171.0, -45.0),
		query=(("class", "primary"),),
	)

	select_query = layer.build_select_query([layer.bbox])

	assert "read_parquet('https://example.test/roads/latest/*.parquet')" in select_query
	assert "ST_MakeEnvelope(170.0, -46.0, 171.0, -45.0)" in select_query
	assert "class = 'primary'" in select_query


def test_catalog_adds_extent_name_to_existing_metadata_table(
	tmp_path: Path,
) -> None:
	source_path = tmp_path / "roads.parquet"
	catalog_path = tmp_path / "catalog.duckdb"
	_write_parquet(source_path, ((1, "road"),))
	with duckdb.connect(str(catalog_path)) as connection:
		connection.execute(
			"""
			CREATE TABLE extents (
				view_name VARCHAR NOT NULL,
				extent_index INTEGER NOT NULL,
				west DOUBLE NOT NULL,
				south DOUBLE NOT NULL,
				east DOUBLE NOT NULL,
				north DOUBLE NOT NULL,
				PRIMARY KEY (view_name, extent_index)
			)
			"""
		)

	GeoParquetCatalog(catalog_path).register(
		source_path,
		"roads",
		"roads",
		"https://example.test/roads/*.parquet",
		(CatalogExtent("HAMILTON_URBAN_AREA", (175.1, -37.9, 175.4, -37.6)),),
	)

	with duckdb.connect(str(catalog_path)) as connection:
		assert connection.execute(
			"SELECT extent_name FROM extents WHERE view_name = 'roads'"
		).fetchone() == ("HAMILTON_URBAN_AREA",)
