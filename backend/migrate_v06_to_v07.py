"""Add v0.7 wardrobe price and favourite fields to an existing v0.6 database.

Run from the backend directory:
    python migrate_v06_to_v07.py

Back up your database first. Supports SQLite and PostgreSQL.
"""
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import inspect, text
from app.database import engine

ADDITIONS = {
    "clothing_items": {
        "purchase_price": "FLOAT",
        "is_favorite": "BOOLEAN NOT NULL DEFAULT FALSE",
    },
    "outfits": {
        "is_favorite": "BOOLEAN NOT NULL DEFAULT FALSE",
    },
}

def main():
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in ADDITIONS.items():
            existing = {column["name"] for column in inspect(conn).get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                    print(f"Added {table}.{name}")
                else:
                    print(f"Already exists: {table}.{name}")
    print("v0.7 database migration complete.")

if __name__ == "__main__":
    main()
