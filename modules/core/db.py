"""
SQLite-backed store for scan list and metadata items.

Schema: flat columns — no JSON blob. Each piece of metadata has its own column.
Auto-migrates from:
  - Old blob schema (data TEXT column) → flat columns
  - JSON files (metadata_progress.json / scan_list.json) → SQLite
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path


# Columns that map 1-to-1 between the item dict and the DB row.
# 'genres' is stored as a JSON string since it's a list.
_ITEM_COLS = (
    'name', 'year', 'rating', 'description', 'cover_url',
    'genre', 'genres', 'provider_url', 'website_url', 'slug',
    'provider_source', 'full_path',
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata_items (
    original_name   TEXT PRIMARY KEY,
    name            TEXT,
    year            TEXT,
    rating          TEXT,
    description     TEXT,
    cover_url       TEXT,
    genre           TEXT,
    genres          TEXT,
    provider_url    TEXT,
    website_url     TEXT,
    slug            TEXT,
    provider_source TEXT,
    full_path       TEXT,
    found           INTEGER DEFAULT 0,
    manual          INTEGER DEFAULT 0,
    last_updated    TEXT
);
CREATE INDEX IF NOT EXISTS idx_meta_genre ON metadata_items(genre);
CREATE INDEX IF NOT EXISTS idx_meta_found  ON metadata_items(found);

CREATE TABLE IF NOT EXISTS scan_list (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    clean_name  TEXT NOT NULL,
    folder_path TEXT NOT NULL
);
"""


class LibraryDB:

    def __init__(self, db_path: Path):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._migrate_blob_schema_if_needed()
        self._migrate_from_json_if_needed()

    # ── Internal helpers ──────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def _ensure_schema(self):
        with self._conn() as conn:
            for stmt in _SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)

    def _migrate_blob_schema_if_needed(self):
        """If the old data-blob column exists, extract it into flat columns."""
        with self._conn() as conn:
            cols = {r[1] for r in conn.execute('PRAGMA table_info(metadata_items)').fetchall()}
            if 'data' not in cols:
                return

            rows = conn.execute(
                'SELECT original_name, data, last_updated FROM metadata_items'
            ).fetchall()

            conn.execute('ALTER TABLE metadata_items RENAME TO _metadata_items_old')
            for stmt in _SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)

            for row in rows:
                try:
                    item = json.loads(row['data'])
                    self._insert_or_replace(conn, row['original_name'], item, row['last_updated'])
                except Exception as e:
                    print(f'[DB] Migration warning for {row["original_name"]}: {e}')

            conn.execute('DROP TABLE _metadata_items_old')
        print('[DB] Migrated blob schema → flat columns')

    def _migrate_from_json_if_needed(self):
        """One-time import from JSON files if they exist and DB is empty."""
        data_dir = self._path.parent
        meta_json = data_dir / 'metadata_progress.json'
        scan_json = data_dir / 'scan_list.json'

        with self._conn() as conn:
            has_meta = conn.execute('SELECT COUNT(*) FROM metadata_items').fetchone()[0] > 0
            has_scan = conn.execute('SELECT COUNT(*) FROM scan_list').fetchone()[0] > 0

        migrated = False

        if not has_meta and meta_json.exists():
            try:
                with open(meta_json, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                items = raw.get('processed_items', raw.get('processed_games', {}))
                self.save_metadata({'processed_items': items})
                meta_json.rename(meta_json.with_suffix('.json.bak'))
                print(f'[DB] Migrated {len(items)} metadata items from JSON → SQLite')
                migrated = True
            except Exception as e:
                print(f'[DB] Migration warning (metadata): {e}')

        if not has_scan and scan_json.exists():
            try:
                with open(scan_json, 'r', encoding='utf-8') as f:
                    items = json.load(f)
                self.save_scan_list(items)
                scan_json.rename(scan_json.with_suffix('.json.bak'))
                print(f'[DB] Migrated {len(items)} scan list items from JSON → SQLite')
                migrated = True
            except Exception as e:
                print(f'[DB] Migration warning (scan list): {e}')

        if migrated:
            print('[DB] Migration complete.')

    @staticmethod
    def _insert_or_replace(conn, original_name: str, item: dict, last_updated: str = None):
        ts = last_updated or datetime.now().isoformat(timespec='seconds')
        genres_raw = item.get('genres')
        genres_str = json.dumps(genres_raw, ensure_ascii=False) if isinstance(genres_raw, list) else (genres_raw or None)
        conn.execute(
            f'''INSERT INTO metadata_items
                    (original_name, {", ".join(_ITEM_COLS)}, found, manual, last_updated)
                VALUES
                    (?, {", ".join("?" * len(_ITEM_COLS))}, ?, ?, ?)
                ON CONFLICT(original_name) DO UPDATE SET
                    {", ".join(f"{c} = excluded.{c}" for c in _ITEM_COLS)},
                    found        = excluded.found,
                    manual       = excluded.manual,
                    last_updated = excluded.last_updated''',
            (
                original_name,
                item.get('name') or None,
                item.get('year') or None,
                item.get('rating') or None,
                item.get('description') or None,
                item.get('cover_url') or None,
                item.get('genre') or None,
                genres_str,
                item.get('provider_url') or None,
                item.get('website_url') or None,
                item.get('slug') or None,
                item.get('provider_source') or None,
                item.get('full_path') or item.get('folder_path') or None,
                1 if (item.get('found') or item.get('igdb_found')) else 0,
                1 if item.get('manual') else 0,
                ts,
            ),
        )

    @staticmethod
    def _row_to_item(row) -> dict:
        """Convert a DB row to the item dict format the rest of the app expects."""
        genres_raw = row['genres']
        try:
            genres = json.loads(genres_raw) if genres_raw else []
        except Exception:
            genres = []

        found = bool(row['found'])
        return {
            'original_name':   row['original_name'],
            'name':            row['name'] or '',
            'year':            row['year'] or '',
            'rating':          row['rating'] or '',
            'description':     row['description'] or '',
            'cover_url':       row['cover_url'] or '',
            'genre':           row['genre'] or '',
            'genres':          genres,
            'provider_url':    row['provider_url'] or '',
            'website_url':     row['website_url'] or '',
            'slug':            row['slug'] or '',
            'provider_source': row['provider_source'] or '',
            'full_path':       row['full_path'] or '',
            'found':           found,
            'igdb_found':      found,   # legacy alias — some callers still check this
            'manual':          bool(row['manual']),
            'last_updated':    row['last_updated'] or '',
        }

    # ── Scan list ─────────────────────────────────────────────────────

    def load_scan_list(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT name, clean_name, folder_path FROM scan_list ORDER BY id'
            ).fetchall()
        return [dict(r) for r in rows]

    def save_scan_list(self, items: list):
        with self._conn() as conn:
            conn.execute('DELETE FROM scan_list')
            conn.executemany(
                'INSERT INTO scan_list (name, clean_name, folder_path) VALUES (?, ?, ?)',
                [(i.get('name', ''), i.get('clean_name', ''), i.get('folder_path', '')) for i in items],
            )

    # ── Metadata — single item ────────────────────────────────────────

    def get_item(self, original_name: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                'SELECT * FROM metadata_items WHERE original_name = ?', (original_name,)
            ).fetchone()
        return self._row_to_item(row) if row else None

    def set_item(self, original_name: str, item: dict):
        with self._conn() as conn:
            self._insert_or_replace(conn, original_name, item)

    def delete_item(self, original_name: str):
        with self._conn() as conn:
            conn.execute('DELETE FROM metadata_items WHERE original_name = ?', (original_name,))

    def rename_item(self, old_name: str, new_name: str, updates: dict | None = None):
        item = self.get_item(old_name)
        if item is None:
            raise KeyError(f'Item {old_name!r} not found in DB')
        if updates:
            item.update(updates)
        item['original_name'] = new_name
        self.delete_item(old_name)
        self.set_item(new_name, item)

    def item_exists(self, original_name: str) -> bool:
        with self._conn() as conn:
            return conn.execute(
                'SELECT 1 FROM metadata_items WHERE original_name = ?', (original_name,)
            ).fetchone() is not None

    # ── Metadata — bulk ───────────────────────────────────────────────

    def get_all_items(self) -> dict:
        """Returns {original_name: item_dict}."""
        with self._conn() as conn:
            rows = conn.execute('SELECT * FROM metadata_items').fetchall()
        return {row['original_name']: self._row_to_item(row) for row in rows}

    def get_failed_items(self) -> dict:
        """Returns {original_name: item_dict} for items where found=0."""
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT * FROM metadata_items WHERE found = 0'
            ).fetchall()
        return {row['original_name']: self._row_to_item(row) for row in rows}

    def load_metadata(self) -> dict:
        """Returns {'schema_version': 2, 'processed_items': {original_name: dict}}."""
        return {'schema_version': 2, 'processed_items': self.get_all_items()}

    def save_metadata(self, data: dict):
        """Accepts {'processed_items': {original_name: dict}}."""
        items = data.get('processed_items', data.get('processed_games', {}))
        with self._conn() as conn:
            for original_name, item in items.items():
                self._insert_or_replace(conn, original_name, item)

    # ── Counts ────────────────────────────────────────────────────────

    def count_scan_list(self) -> int:
        with self._conn() as conn:
            return conn.execute('SELECT COUNT(*) FROM scan_list').fetchone()[0]

    def count_items(self) -> int:
        with self._conn() as conn:
            return conn.execute('SELECT COUNT(*) FROM metadata_items').fetchone()[0]

    def count_found(self) -> int:
        with self._conn() as conn:
            return conn.execute('SELECT COUNT(*) FROM metadata_items WHERE found = 1').fetchone()[0]

    def count_failed(self) -> int:
        with self._conn() as conn:
            return conn.execute('SELECT COUNT(*) FROM metadata_items WHERE found = 0').fetchone()[0]

    def delete_failed_items(self) -> int:
        with self._conn() as conn:
            count = conn.execute(
                'SELECT COUNT(*) FROM metadata_items WHERE found = 0'
            ).fetchone()[0]
            conn.execute('DELETE FROM metadata_items WHERE found = 0')
        return count

    def count_organized(self) -> int:
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM metadata_items WHERE found = 1 AND genre IS NOT NULL AND genre != ''"
            ).fetchone()[0]

    def genre_counts(self) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT genre, COUNT(*) as cnt FROM metadata_items "
                "WHERE genre IS NOT NULL AND genre != '' GROUP BY genre"
            ).fetchall()
        return {row['genre']: row['cnt'] for row in rows}

    def delete_items_by_genres(self, genres: list) -> int:
        if not genres:
            return 0
        from modules.core.utils import is_path_skipped
        with self._conn() as conn:
            rows = conn.execute('SELECT original_name, full_path FROM metadata_items').fetchall()
            to_delete = [
                r['original_name'] for r in rows
                if r['full_path'] and is_path_skipped(Path(r['full_path']).parent, genres)
            ]
            if to_delete:
                conn.executemany(
                    'DELETE FROM metadata_items WHERE original_name = ?',
                    [(k,) for k in to_delete],
                )
        return len(to_delete)

    # ── Wipe ─────────────────────────────────────────────────────────

    def wipe(self):
        with self._conn() as conn:
            conn.execute('DELETE FROM metadata_items')
            conn.execute('DELETE FROM scan_list')
