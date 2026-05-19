from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker


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

        query: dict[str, str] = {}
        if sslmode:
            query["sslmode"] = sslmode
        if search_path:
            # psycopg2 supports server options; this sets the session search_path.
            query["options"] = "-csearch_path=" + search_path

        url = URL.create(
            drivername="postgresql+psycopg2",
            username=user or None,
            password=password or None,
            host=host or None,
            port=int(port),
            database=name or None,
            query=query or None,
        )
        return str(url)

    # Default: SQL Server via ODBC.
    port = port or "1433"
    driver = os.getenv("DB_SQLSERVER_DRIVER", "ODBC Driver 17 for SQL Server")
    mars = os.getenv("DB_MARS", "Yes")
    url = URL.create(
        drivername="mssql+pyodbc",
        username=user or None,
        password=password or None,
        host=host or None,
        port=int(port),
        database=name or None,
        query={"driver": driver, "MARS_Connection": mars},
    )
    return str(url)


DATABASE_URL = build_database_url()

# ---------------------------------------------------------------------------
# Connection pool — all values are tunable via environment variables.
#
#   DB_POOL_SIZE          persistent connections per process  (default 5)
#   DB_POOL_MAX_OVERFLOW  extra connections allowed on burst  (default 10)
#   DB_POOL_TIMEOUT       seconds to wait for a free slot     (default 30)
#   DB_POOL_RECYCLE       seconds before recycling a conn     (default 3600)
#   DB_ECHO               set to "1" to log all SQL          (default off)
#
# For serverless / PaaS deployments set DB_POOL_SIZE=1, DB_POOL_MAX_OVERFLOW=0
# and consider NullPool to avoid idle-connection costs.
# ---------------------------------------------------------------------------

_echo = os.getenv("DB_ECHO", "").strip().lower() in ("1", "true", "yes")

engine = create_engine(
    DATABASE_URL,
    echo=_echo,
    pool_pre_ping=True,           # validate connections before use (avoids stale-conn errors)
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_POOL_MAX_OVERFLOW", "10")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
    pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


if __name__ == "__main__":
    try:
        db = SessionLocal()
        _ = db.execute(text("SELECT 1")).fetchall()
        print("DB CONNECTED")
    except Exception as exc:
        print("DB ERROR", str(exc))
