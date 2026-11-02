"""Upgrade an existing v0.2 SQLite database without discarding wardrobe data.

Run from backend/: python migrate_v02_to_v03.py
Existing v0.2 records are assigned to a temporary legacy account. Sign up with
your intended email after migration; then use the documented transfer script
or re-add records. New installs do not need this script.
"""
import os, sqlite3
from pathlib import Path

db_url = os.getenv("DATABASE_URL", "sqlite:///./clothed.db")
if not db_url.startswith("sqlite:///"):
    raise SystemExit("This helper only supports SQLite. Use a reviewed Alembic migration for PostgreSQL.")
db_path = Path(db_url.replace("sqlite:///", "", 1))
if not db_path.exists():
    print("No existing database found; a fresh v0.3 database will be created on API startup.")
    raise SystemExit(0)

con = sqlite3.connect(db_path)
con.execute("PRAGMA foreign_keys=ON")
tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if "users" not in tables:
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, created_at DATETIME)")
    con.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('legacy-local@clothed.invalid','disabled',CURRENT_TIMESTAMP)")
legacy_id = con.execute("SELECT id FROM users WHERE email='legacy-local@clothed.invalid'").fetchone()
legacy_id = legacy_id[0] if legacy_id else None

for table in ("clothing_items","outfits","wear_logs"):
    if table not in tables: continue
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    if "owner_id" not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN owner_id INTEGER REFERENCES users(id)")
        con.execute(f"UPDATE {table} SET owner_id=? WHERE owner_id IS NULL",(legacy_id,))
con.commit()
con.close()
print("Schema columns upgraded. Existing records are safely retained under the disabled legacy account.")
print("Note: create a fresh account and contact your app maintainer to transfer legacy data; do not expose the legacy account.")
