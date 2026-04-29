from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote


# Force-load `.env` from this folder so running via uvicorn from repo root still works.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(BASE_DIR, ".env")
load_dotenv(env_path)


def build_database_url() -> str:
    db_type = (os.getenv("DB_TYPE", "sqlserver") or "sqlserver").strip().lower()
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "")
    name = os.getenv("DB_NAME", "")
    port = os.getenv("DB_PORT", "")

    if db_type == "postgres":
        # Uses a synchronous SQLAlchemy engine, so a sync PostgreSQL driver is required.
        # Recommended: `psycopg2-binary`.
        port = port or "5432"
        sslmode = os.getenv("DB_SSLMODE", "").strip()
        search_path = os.getenv("DB_SEARCH_PATH", "").strip()

        base = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
        params: list[str] = []
        if sslmode:
            params.append(f"sslmode={quote(sslmode)}")
        if search_path:
            # psycopg2 supports server options; this sets the session search_path.
            params.append(f"options={quote('-csearch_path=' + search_path)}")

        return f"{base}?{'&'.join(params)}" if params else base

    # Default: SQL Server via ODBC.
    port = port or "1433"
    driver = os.getenv("DB_SQLSERVER_DRIVER", "ODBC Driver 17 for SQL Server")
    mars = os.getenv("DB_MARS", "Yes")
    return (
        f"mssql+pyodbc://{user}:{password}@{host}:{port}/{name}"
        f"?driver={driver}&MARS_Connection={mars}"
    )


DATABASE_URL = build_database_url()
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


if __name__ == "__main__":
    try:
        db = SessionLocal()
        _ = db.execute(text("SELECT 1")).fetchall()
        print("DB CONNECTED")
    except Exception as exc:
        print("DB ERROR", str(exc))
