"""
loader.py — Load cleaned CSV data into SQL Server tables.

HOW IT WORKS
------------
1. Reads connection settings from .env (server, database, auth mode, driver).
2. Connects to SQL Server via SQLAlchemy + pyodbc.
3. Creates the database if it doesn't exist (using a raw pyodbc connection
   because CREATE DATABASE can't run inside a transaction).
4. Executes schema.sql to create/recreate the 3 tables.
5. Reads data/processed/customers_features.csv.
6. Inserts rows into customers, campaign_assignments, and outcomes
   using pandas .to_sql() with fast_executemany for speed.

USAGE (from the project root in cmd)
-----
    python -m src.db.loader

Or from a notebook:
    from src.db.loader import load_all
    load_all()

PREREQUISITES
-------------
- SQL Server running (check: services.msc → SQL Server)
- pyodbc installed (pip install pyodbc)
- .env file configured (copy from .env.example)
- data/processed/customers_features.csv exists (from Phase 2)
"""

import os
import sys
import pyodbc
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, event

# ── Load .env from project root ──────────────────────
# Walk up from this file's location to find .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_connection_string() -> str:
    """
    Build a SQLAlchemy connection URL for SQL Server.

    SQLAlchemy uses this format for SQL Server via pyodbc:
        mssql+pyodbc://[user:password@]server/database?driver=...

    For Windows Authentication (most common on local dev):
        mssql+pyodbc://@server/database?driver=...&Trusted_Connection=yes

    For SQL Server Authentication:
        mssql+pyodbc://user:password@server/database?driver=...
    """
    server = os.getenv("DB_SERVER", r"localhost\SQLEXPRESS")
    database = os.getenv("DB_NAME", "hillstrom_uplift")
    auth_mode = os.getenv("DB_AUTH_MODE", "windows").lower()
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

    # URL-encode the driver name (spaces → +)
    driver_encoded = driver.replace(" ", "+")

    if auth_mode == "windows":
        # Windows Authentication — no user/password needed
        conn_str = (
            f"mssql+pyodbc://@{server}/{database}"
            f"?driver={driver_encoded}&Trusted_Connection=yes"
        )
    else:
        # SQL Server Authentication
        user = os.getenv("DB_USER", "sa")
        password = os.getenv("DB_PASSWORD", "")
        conn_str = (
            f"mssql+pyodbc://{user}:{password}@{server}/{database}"
            f"?driver={driver_encoded}"
        )

    return conn_str


def get_raw_pyodbc_string() -> str:
    """
    Build a raw pyodbc connection string (not SQLAlchemy).
    Needed for CREATE DATABASE which can't run inside SQLAlchemy's
    transaction management.
    """
    server = os.getenv("DB_SERVER", r"localhost\SQLEXPRESS")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    auth_mode = os.getenv("DB_AUTH_MODE", "windows").lower()

    if auth_mode == "windows":
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE=master;"
            f"Trusted_Connection=yes;"
        )
    else:
        user = os.getenv("DB_USER", "sa")
        password = os.getenv("DB_PASSWORD", "")
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE=master;"
            f"UID={user};"
            f"PWD={password};"
        )


def create_database_if_not_exists():
    """
    Create the target database if it doesn't already exist.

    WHY RAW PYODBC?
    CREATE DATABASE is a DDL statement that SQL Server won't allow
    inside a multi-statement transaction. SQLAlchemy wraps everything
    in transactions by default. So we use a raw pyodbc connection
    with autocommit=True to sidestep that.
    """
    db_name = os.getenv("DB_NAME", "hillstrom_uplift")
    conn_str = get_raw_pyodbc_string()

    print(f"[loader] Connecting to SQL Server (master database)...")
    conn = pyodbc.connect(conn_str, autocommit=True)
    cursor = conn.cursor()

    # Check if database exists
    cursor.execute(
        "SELECT database_id FROM sys.databases WHERE name = ?", db_name
    )
    exists = cursor.fetchone()

    if not exists:
        print(f"[loader] Creating database '{db_name}'...")
        cursor.execute(f"CREATE DATABASE [{db_name}]")
        print(f"[loader] Database '{db_name}' created.")
    else:
        print(f"[loader] Database '{db_name}' already exists.")

    cursor.close()
    conn.close()


def run_schema(engine):
    """
    Execute schema.sql to create (or recreate) the 3 tables.

    Reads the .sql file, splits on 'GO' (T-SQL batch separator),
    and executes each batch. GO is NOT a SQL statement — it's a
    signal to SSMS/sqlcmd to send the preceding batch. SQLAlchemy
    doesn't understand GO, so we split manually.
    """
    schema_path = Path(__file__).parent / "schema.sql"
    print(f"[loader] Running schema from {schema_path}...")

    sql_text = schema_path.read_text(encoding="utf-8")

    # Split on GO (case-insensitive, on its own line)
    import re
    batches = re.split(r"^\s*GO\s*$", sql_text, flags=re.MULTILINE | re.IGNORECASE)

    with engine.connect() as conn:
        for batch in batches:
            batch = batch.strip()
            if batch and not batch.startswith("--"):
                conn.execute(text(batch))
        conn.commit()

    print("[loader] Schema created successfully.")


def load_data(engine):
    """
    Read customers_features.csv and insert into the 3 normalized tables.

    STRATEGY:
    We use pandas .to_sql() with the default row-by-row insert method.
    SQLAlchemy's fast_executemany event (set on the engine) makes pyodbc
    batch the inserts efficiently under the hood — this avoids the
    SQL Server 2,100-parameter limit that method='multi' hits.

    COLUMN MAPPING:
    The CSV has 17 columns. We split them across 3 tables:

      customers (13 cols):
        recency, history, mens, womens, zip_code, newbie,
        channel_multichannel, channel_phone, channel_web,
        history_segment_code, category_count, recency_bin, history_bin

      campaign_assignments (2 cols):
        segment, treatment
        + customer_id (the row number, since CSV rows and DB rows align 1:1)

      outcomes (3 cols):
        visit, conversion, spend
        + customer_id
    """
    csv_path = PROJECT_ROOT / "data" / "processed" / "customers_features.csv"
    print(f"[loader] Reading {csv_path}...")

    df = pd.read_csv(csv_path)
    print(f"[loader] Loaded {len(df)} rows x {len(df.columns)} columns.")

    # The processed CSV doesn't have 'segment' (it was dropped during
    # feature engineering because it's redundant with 'treatment' for ML).
    # But the campaign_assignments table needs the original segment labels
    # ('Mens E-Mail', 'Womens E-Mail', 'No E-Mail') for richer SQL analytics.
    # So we read just that column from the raw CSV.
    raw_path = PROJECT_ROOT / "data" / "raw" / "hillstrom.csv"
    print(f"[loader] Reading segment column from {raw_path}...")
    df_raw = pd.read_csv(raw_path, usecols=["segment"])

    # ── Split into 3 DataFrames ─────────────────────

    # Customer attributes (everything except segment, treatment, visit, conversion, spend)
    customer_cols = [
        "recency", "history", "mens", "womens", "zip_code", "newbie",
        "channel_multichannel", "channel_phone", "channel_web",
        "history_segment_code", "category_count", "recency_bin", "history_bin",
    ]
    df_customers = df[customer_cols].copy()

    # Phase 2 used .fillna(-1) for some columns, but SQL Server's TINYINT
    # only holds 0-255 (unsigned). Replace any negative fill values with 0
    # so they don't overflow. This affects zip_code mainly.
    for col in df_customers.columns:
        if df_customers[col].dtype in ["int8", "int16", "int32", "int64"]:
            df_customers[col] = df_customers[col].clip(lower=0)

    # Campaign assignments — segment from raw CSV, treatment from processed CSV
    df_assignments = pd.DataFrame({
        "segment": df_raw["segment"],
        "treatment": df["treatment"]
    })

    # Outcomes
    df_outcomes = df[["visit", "conversion", "spend"]].copy()

    # ── Insert customers first (to get auto-generated IDs) ──
    print("[loader] Inserting into 'customers'... (this may take a minute)")
    df_customers.to_sql(
        "customers", engine, schema="dbo",
        if_exists="append", index=False,
        chunksize=500
    )

    # ── Read back the customer_ids ──────────────────
    # IDENTITY values are 1, 2, 3, ... in insertion order
    # Since we inserted 64k rows in order, customer_id = row_index + 1
    print("[loader] Reading back customer IDs...")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT customer_id FROM dbo.customers ORDER BY customer_id"))
        customer_ids = [row[0] for row in result]

    print(f"[loader] Got {len(customer_ids)} customer IDs.")

    # ── Add customer_id to assignments and outcomes ──
    df_assignments["customer_id"] = customer_ids
    df_outcomes["customer_id"] = customer_ids

    # ── Insert assignments ──────────────────────────
    print("[loader] Inserting into 'campaign_assignments'...")
    df_assignments.to_sql(
        "campaign_assignments", engine, schema="dbo",
        if_exists="append", index=False,
        chunksize=500
    )

    # ── Insert outcomes ─────────────────────────────
    print("[loader] Inserting into 'outcomes'...")
    df_outcomes.to_sql(
        "outcomes", engine, schema="dbo",
        if_exists="append", index=False,
        chunksize=500
    )

    print(f"[loader] Done! Loaded {len(df)} rows into 3 tables.")


def load_all():
    """Run the full loading pipeline."""
    print("=" * 55)
    print("  Phase 3: SQL Server Data Loading")
    print("=" * 55)

    # Step 1: Create database
    create_database_if_not_exists()

    # Step 2: Connect via SQLAlchemy
    conn_str = get_connection_string()
    print(f"\n[loader] Connecting via SQLAlchemy...")
    engine = create_engine(conn_str)

    # Enable fast_executemany for pyodbc — this makes row-by-row
    # .to_sql() inserts much faster by batching them at the ODBC level,
    # without hitting SQL Server's 2,100-parameter limit.
    @event.listens_for(engine, "before_cursor_execute")
    def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if executemany:
            cursor.fast_executemany = True

    # Quick connection test
    with engine.connect() as conn:
        result = conn.execute(text("SELECT @@VERSION"))
        version = result.fetchone()[0]
        print(f"[loader] Connected! Server version:\n  {version[:80]}...")

    # Step 3: Create tables
    run_schema(engine)

    # Step 4: Load data
    load_data(engine)

    # Step 5: Verify counts
    print("\n[loader] Verification:")
    with engine.connect() as conn:
        for table in ["customers", "campaign_assignments", "outcomes"]:
            result = conn.execute(text(f"SELECT COUNT(*) FROM dbo.{table}"))
            count = result.fetchone()[0]
            print(f"  {table}: {count:,} rows")

    print("\n Phase 3 loading complete!")
    engine.dispose()


# ── Run as script ────────────────────────────────────
if __name__ == "__main__":
    load_all()