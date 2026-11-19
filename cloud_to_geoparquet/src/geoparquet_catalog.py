"""Maintain a local DuckDB catalog of GeoParquet-backed views."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb


BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class CatalogEntry:
	catalog_path: Path
	view_name: str


@dataclass(frozen=True)
class CatalogExtent:
	extent_name: str
	bbox: BBox


class GeoParquetCatalog:
	"""Register local GeoParquet files as DuckDB views with export metadata."""

	def __init__(self, catalog_path: str | Path) -> None:
		self.catalog_path = Path(catalog_path)

	def register(
		self,
		parquet_path: str | Path,
		view_name: str,
		layer_name: str,
		source_url: str,
		extents: Iterable[CatalogExtent],
	) -> CatalogEntry:
		"""Create or replace a view and record metadata for a Parquet export."""
		source_path = Path(parquet_path).resolve()
		if not source_path.is_file():
			raise FileNotFoundError(f"GeoParquet export not found: {source_path}")
		escaped_source_path = str(source_path).replace("'", "''")
		select_query = (
			f"SELECT * FROM read_parquet('{escaped_source_path}')"
		)
		return self._register(
			select_query,
			view_name,
			layer_name,
			source_url,
			str(source_path),
			"local",
			extents,
			record_download=True,
			file_size_bytes=source_path.stat().st_size,
		)

	def register_remote(
		self,
		select_query: str,
		view_name: str,
		layer_name: str,
		source_url: str,
		extents: Iterable[CatalogExtent],
	) -> CatalogEntry:
		"""Register a filtered remote GeoParquet query without downloading it."""
		return self._register(
			select_query,
			view_name,
			layer_name,
			source_url,
			source_url,
			"remote",
			extents,
			record_download=False,
		)

	def _register(
		self,
		select_query: str,
		view_name: str,
		layer_name: str,
		source_url: str,
		source_location: str,
		source_kind: str,
		extents: Iterable[CatalogExtent],
		*,
		record_download: bool,
		file_size_bytes: int | None = None,
	) -> CatalogEntry:
		if not view_name:
			raise ValueError("view_name must not be empty")
		if record_download and file_size_bytes is None:
			raise ValueError("file_size_bytes is required for download metadata")
		normalized_extents = tuple(extents)
		if not normalized_extents:
			raise ValueError("at least one extent is required")
		for extent in normalized_extents:
			if not extent.extent_name:
				raise ValueError("extent_name must not be empty")
			west, south, east, north = extent.bbox
			if west > east or south > north:
				raise ValueError(
					"extent must be ordered as (west, south, east, north)"
				)

		self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
		connection = duckdb.connect(str(self.catalog_path))
		try:
			connection.execute("SET allow_asterisks_in_http_paths = true")
			if source_kind == "remote":
				connection.execute("INSTALL httpfs")
				connection.execute("LOAD httpfs")
			connection.execute("INSTALL spatial")
			connection.execute("LOAD spatial")
			connection.execute("BEGIN TRANSACTION")
			self._create_metadata_tables(connection)
			self._create_view(connection, select_query, view_name)
			self._upsert_dataset(
				connection,
				view_name,
				layer_name,
				source_url,
				source_location,
				source_kind,
			)
			if record_download:
				quoted_view_name = self._quote_identifier(view_name)
				row_count = connection.execute(
					f"SELECT count(*) FROM {quoted_view_name}"
				).fetchone()[0]
				connection.execute(
					"""
					INSERT INTO downloads (
						view_name,
						parquet_path,
						file_size_bytes,
						row_count
					)
					VALUES (?, ?, ?, ?)
					""",
					[
						view_name,
						source_location,
						file_size_bytes,
						row_count,
					],
				)
			connection.execute(
				"DELETE FROM extents WHERE view_name = ?",
				[view_name],
			)
			connection.executemany(
				"""
				INSERT INTO extents (
					view_name,
					extent_index,
					extent_name,
					west,
					south,
					east,
					north
				)
				VALUES (?, ?, ?, ?, ?, ?, ?)
				""",
				[
					[
						view_name,
						index,
						extent.extent_name,
						*extent.bbox,
					]
					for index, extent in enumerate(
						normalized_extents,
						start=1,
					)
				],
			)
			connection.execute("COMMIT")
		finally:
			connection.close()

		return CatalogEntry(self.catalog_path, view_name)

	@staticmethod
	def _create_metadata_tables(connection: duckdb.DuckDBPyConnection) -> None:
		connection.execute(
			"""
			CREATE TABLE IF NOT EXISTS datasets (
				view_name VARCHAR PRIMARY KEY,
				layer_name VARCHAR NOT NULL,
				source_url VARCHAR NOT NULL,
				parquet_path VARCHAR NOT NULL,
				source_kind VARCHAR NOT NULL DEFAULT 'local',
				created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
				updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
			)
			"""
		)
		connection.execute(
			"""
			ALTER TABLE datasets
			ADD COLUMN IF NOT EXISTS source_kind VARCHAR DEFAULT 'local'
			"""
		)
		connection.execute(
			"""
			CREATE TABLE IF NOT EXISTS downloads (
				view_name VARCHAR NOT NULL,
				downloaded_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
				parquet_path VARCHAR NOT NULL,
				file_size_bytes BIGINT NOT NULL,
				row_count BIGINT NOT NULL
			)
			"""
		)
		connection.execute(
			"""
			CREATE TABLE IF NOT EXISTS extents (
				view_name VARCHAR NOT NULL,
				extent_index INTEGER NOT NULL,
				extent_name VARCHAR NOT NULL,
				west DOUBLE NOT NULL,
				south DOUBLE NOT NULL,
				east DOUBLE NOT NULL,
				north DOUBLE NOT NULL,
				PRIMARY KEY (view_name, extent_index)
			)
			"""
		)
		connection.execute(
			"""
			ALTER TABLE extents
			ADD COLUMN IF NOT EXISTS extent_name VARCHAR
			"""
		)

	@staticmethod
	def _create_view(
		connection: duckdb.DuckDBPyConnection,
		select_query: str,
		view_name: str,
	) -> None:
		quoted_view_name = GeoParquetCatalog._quote_identifier(view_name)
		connection.execute(
			f"CREATE OR REPLACE VIEW {quoted_view_name} AS {select_query}"
		)

	@staticmethod
	def _quote_identifier(identifier: str) -> str:
		return '"' + identifier.replace('"', '""') + '"'

	@staticmethod
	def _upsert_dataset(
		connection: duckdb.DuckDBPyConnection,
		view_name: str,
		layer_name: str,
		source_url: str,
		source_location: str,
		source_kind: str,
	) -> None:
		connection.execute(
			"""
			INSERT INTO datasets (
				view_name,
				layer_name,
				source_url,
				parquet_path,
				source_kind
			)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT (view_name) DO UPDATE SET
				layer_name = excluded.layer_name,
				source_url = excluded.source_url,
				parquet_path = excluded.parquet_path,
				source_kind = excluded.source_kind,
				updated_at = now()
			""",
			[
				view_name,
				layer_name,
				source_url,
				source_location,
				source_kind,
			],
		)
