import os
import sqlite3
from pathlib import Path


DEFAULT_DATABASE = (
    Path(__file__).resolve().parents[2]
    / "roomhub.db"
)

DATABASE = Path(
    os.getenv(
        "ROOMHUB_DATABASE_PATH",
        str(DEFAULT_DATABASE)
    )
)


def get_connection():

    DATABASE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    connection.execute(
        "PRAGMA journal_mode=WAL"
    )

    connection.execute(
        "PRAGMA busy_timeout=30000"
    )

    return connection


def initialise_database():

    print("[DATABASE] Initialising database")

    with get_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS entities
            (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL
            )
            """
        )

        connection.commit()