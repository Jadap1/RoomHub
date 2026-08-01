import sqlite3


DATABASE = "roomhub.db"


def get_connection():

    return sqlite3.connect(
        DATABASE
    )


def initialise_database():

    print("[DATABASE] Initialising database")
    connection = get_connection()

    cursor = connection.cursor()


    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS entities (

            entity_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            state TEXT NOT NULL

        )
        """
    )


    connection.commit()

    connection.close()