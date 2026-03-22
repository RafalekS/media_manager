"""
SQLite-backed store for scan list and metadata items.

Replaces scan_list.json + metadata_progress.json with a single library.db.
Auto-migrates from JSON files on first open (renames them to .json.bak).
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path


class LibraryDB:

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS metadata_items (
        original_name TEXT PRIMARY KEY,
        data          TEXT NOT NULL,
        genre         TEXT,
        found         INTEGER DEFAULT 0,
        last_updated  TEXT
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

    def __init__(self, db_path: Path):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._migrate_from_json_if_needed()

    # ── Internal helpers ──────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def _ensure_schema(self):
        with self._conn() as conn:
            for stmt in self._SCHEMA.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)

    def _migrate_from_json_if_needed(self):
        """One-time import from JSON files if they exist and DB is empty."""
        data_dir = self._path.parent
        meta_json = data_dir / 'metadata_progress.json'
        scan_json = data_dir / 'scan_list.json'

        # Check if DB already has data
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
            print('[DB] Migration complete. JSON files renamed to .json.bak')

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
                [
                    (i.get('name', ''), i.get('clean_name', ''), i.get('folder_path', ''))
                    for i in items
                ],
            )

    # ── Metadata — single item ────────────────────────────────────────

    def get_item(self, original_name: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                'SELECT data FROM metadata_items WHERE original_name = ?',
                (original_name,),
            ).fetchone()
        if row:
            try:
                return json.loads(row['data'])
            except Exception:
                return None
        return None

    def set_item(self, original_name: str, item: dict):
        now = datetime.now().isoformat(timespec='seconds')
        item_copy = dict(item)
        item_copy.setdefault('original_name', original_name)
        with self._conn() as conn:
            conn.execute(
                '''INSERT INTO metadata_items
                       (original_name, data, genre, found, last_updated)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(original_name) DO UPDATE SET
                       data         = excluded.data,
                       genre        = excluded.genre,
                       found        = excluded.found,
                       last_updated = excluded.last_updated''',
                (
                    original_name,
                    json.dumps(item_copy, ensure_ascii=False),
                    item_copy.get('genre') or None,
                    1 if (item_copy.get('igdb_found') or item_copy.get('found')) else 0,
                    now,
                ),
            )

    def delete_item(self, original_name: str):
        with self._conn() as conn:
            conn.execute(
                'DELETE FROM metadata_items WHERE original_name = ?', (original_name,)
            )

    def rename_item(self, old_name: str, new_name: str, updates: dict | None = None):
        """Rename the primary key (folder rename) and optionally apply field updates."""
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
            row = conn.execute(
                'SELECT 1 FROM metadata_items WHERE original_name = ?', (original_name,)
            ).fetchone()
        return row is not None

    # ── Metadata — bulk ───────────────────────────────────────────────

    def get_all_items(self) -> dict:
        """Returns {original_name: item_dict}."""
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT original_name, data FROM metadata_items'
            ).fetchall()
        result = {}
        for row in rows:
            try:
                result[row['original_name']] = json.loads(row['data'])
            except Exception:
                pass
        return result

    def get_failed_items(self) -> dict:
        """Returns {original_name: item_dict} for items where found=0."""
        with self._conn() as conn:
            rows = conn.execute(
                'SELECT original_name, data FROM metadata_items WHERE found = 0'
            ).fetchall()
        result = {}
        for row in rows:
            try:
                result[row['original_name']] = json.loads(row['data'])
            except Exception:
                pass
        return result

    def load_metadata(self) -> dict:
        """Returns {'schema_version': 2, 'processed_items': {original_name: dict}}."""
        return {'schema_version': 2, 'processed_items': self.get_all_items()}

    def save_metadata(self, data: dict):
        """Accepts {'processed_items': {original_name: dict}} (same format as JSON)."""
        items = data.get('processed_items', data.get('processed_games', {}))
        now = datetime.now().isoformat(timespec='seconds')
        with self._conn() as conn:
            for original_name, item in items.items():
                item_copy = dict(item)
                item_copy.setdefault('original_name', original_name)
                conn.execute(
                    '''INSERT INTO metadata_items
                           (original_name, data, genre, found, last_updated)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(original_name) DO UPDATE SET
                           data         = excluded.data,
                           genre        = excluded.genre,
                           found        = excluded.found,
                           last_updated = excluded.last_updated''',
                    (
                        original_name,
                        json.dumps(item_copy, ensure_ascii=False),
                        item_copy.get('genre') or None,
                        1 if (item_copy.get('igdb_found') or item_copy.get('found')) else 0,
                        now,
                    ),
                )

    # ── Counts ────────────────────────────────────────────────────────

    def count_scan_list(self) -> int:
        with self._conn() as conn:
            return conn.execute('SELECT COUNT(*) FROM scan_list').fetchone()[0]

    def count_items(self) -> int:
        with self._conn() as conn:
            return conn.execute('SELECT COUNT(*) FROM metadata_items').fetchone()[0]

    def count_found(self) -> int:
        with self._conn() as conn:
            return conn.execute(
                'SELECT COUNT(*) FROM metadata_items WHERE found = 1'
            ).fetchone()[0]

    def count_failed(self) -> int:
        with self._conn() as conn:
            return conn.execute(
                'SELECT COUNT(*) FROM metadata_items WHERE found = 0'
            ).fetchone()[0]

    def count_organized(self) -> int:
        """Items that are found AND have a genre assigned."""
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM metadata_items WHERE found = 1 AND genre IS NOT NULL AND genre != ''"
            ).fetchone()[0]

    def genre_counts(self) -> dict:
        """Returns {genre: count} for all items with a genre."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT genre, COUNT(*) as cnt FROM metadata_items "
                "WHERE genre IS NOT NULL AND genre != '' GROUP BY genre"
            ).fetchall()
        return {row['genre']: row['cnt'] for row in rows}

    # ── Wipe ─────────────────────────────────────────────────────────

    def wipe(self):
        """Delete all data from both tables."""
        with self._conn() as conn:
            conn.execute('DELETE FROM metadata_items')
            conn.execute('DELETE FROM scan_list')
