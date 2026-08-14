import os
import sqlite3
from contextlib import closing
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
        "PRAGMA busy_timeout=30000"
    )

    return connection


def initialise_database():

    print("[DATABASE] Initialising database")

    with closing(get_connection()) as connection, connection:

        connection.execute(
            "PRAGMA journal_mode=WAL"
        )

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

        entity_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(entities)"
            ).fetchall()
        }

        for column_name, column_type in {
            "integration": "TEXT",
            "device_id": "TEXT",
            "area_id": "TEXT",
            "platform": "TEXT",
            "entity_category": "TEXT"
        }.items():

            if column_name not in entity_columns:
                connection.execute(
                    "ALTER TABLE entities "
                    f"ADD COLUMN {column_name} "
                    f"{column_type}"
                )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS floors
            (
                floor_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                level INTEGER
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS areas
            (
                area_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                floor_id TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS devices
            (
                device_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                area_id TEXT,
                manufacturer TEXT,
                model TEXT,
                config_entries TEXT NOT NULL,
                via_device_id TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_states
            (
                entity_id TEXT PRIMARY KEY,
                state TEXT,
                attributes TEXT NOT NULL,
                available INTEGER NOT NULL,
                last_updated TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoint_assignments
            (
                endpoint_id TEXT PRIMARY KEY,
                area_id TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoint_credentials
            (
                endpoint_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoint_pairing_codes
            (
                token_hash TEXT PRIMARY KEY,
                device_name TEXT NOT NULL,
                area_id TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoint_profiles
            (
                endpoint_id TEXT PRIMARY KEY,
                device_name TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoint_credentials
            (
                endpoint_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoint_pairing_codes
            (
                token_hash TEXT PRIMARY KEY,
                device_name TEXT NOT NULL,
                area_id TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoint_profiles
            (
                endpoint_id TEXT PRIMARY KEY,
                device_name TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoint_entity_exclusions
            (
                endpoint_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                PRIMARY KEY (endpoint_id, entity_id)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoint_entity_preferences
            (
                endpoint_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (endpoint_id, entity_id)
            )
            """
        )

        connection.commit()
