import os

import psycopg2


def _get_database_url():
    return os.getenv("DATABASE_URL", "").strip()


def get_db_connection():
    database_url = _get_database_url()
    sslmode = os.getenv("DB_SSLMODE", "require").strip() or "require"

    if database_url:
        return psycopg2.connect(database_url, sslmode=sslmode)

    db_name = os.getenv("DB_NAME", "ids_db")
    db_user = os.getenv("DB_USER", "aya")
    db_password = os.getenv("DB_PASSWORD", "aya")
    db_host = os.getenv("DB_HOST", "192.168.1.2")
    db_port = int(os.getenv("DB_PORT", "5432"))

    return psycopg2.connect(
        dbname=db_name,
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port,
        sslmode=sslmode,
    )
