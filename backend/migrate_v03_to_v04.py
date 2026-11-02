"""Add AI-recognition attributes to an existing v0.3 SQLite database.

Back up clothed.db first, then run from backend/:
    python migrate_v03_to_v04.py
Fresh databases do not need this script.
"""
import os, sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

url = os.getenv("DATABASE_URL", "sqlite:///./clothed.db")
if not url.startswith("sqlite:///"):
    raise SystemExit("This helper supports SQLite only. Use Alembic for PostgreSQL.")
path = Path(url.replace("sqlite:///", "", 1))
if not path.exists():
    print("No existing database found. A fresh v0.4 database will be created on API startup.")
    raise SystemExit(0)

con = sqlite3.connect(path)
tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if "clothing_items" not in tables:
    print("No clothing_items table found; nothing to migrate.")
    con.close()
    raise SystemExit(0)
existing = {row[1] for row in con.execute("PRAGMA table_info(clothing_items)")}
columns = {
    "subcategory": "VARCHAR(60)",
    "secondary_colour": "VARCHAR(60)",
    "pattern": "VARCHAR(60)",
    "material": "VARCHAR(80)",
    "occasion": "VARCHAR(80)",
    "ai_confidence": "FLOAT",
}
for name, sql_type in columns.items():
    if name not in existing:
        con.execute(f"ALTER TABLE clothing_items ADD COLUMN {name} {sql_type}")
con.commit()
con.close()
print("v0.3 → v0.4 migration complete. Existing wardrobe items are preserved.")
