"""
Database initialization: create all tables and run seed data.
Run: python -m app.init_db
"""
import time
import sys
from sqlalchemy import text
from app.database import engine, Base, SessionLocal
from app.models import *  # noqa: F401, F403 — import all models to register them
from app.seed import run_seed, seed_crm_demo


def wait_for_db(max_retries=30, delay=2):
    """Wait for the database to be ready."""
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ Database connection established")
            return True
        except Exception as e:
            print(f"⏳ Waiting for database... ({i+1}/{max_retries}) — {e}")
            time.sleep(delay)
    print("❌ Could not connect to database")
    return False


def _ensure_columns():
    """create_all 은 기존 테이블에 컬럼을 추가하지 않으므로, 신규 컬럼을 멱등하게 보강한다.
    (개발: SQLite / 운영: MariaDB 모두 ADD COLUMN 지원)"""
    # (table, column, DDL type, default)
    pending = [
        ("staff", "share_rate", "NUMERIC(5,4)", "0.5"),
        ("crm_customers", "anniversary", "DATE", "NULL"),
        ("crm_customers", "allergy_memo", "TEXT", "NULL"),
        ("crm_customers", "hair_memo", "TEXT", "NULL"),
        ("crm_customers", "photo_url", "VARCHAR(500)", "NULL"),
        ("crm_customers", "preferred_staff_id", "INTEGER", "NULL"),
        ("crm_customers", "preferred_service", "VARCHAR(200)", "NULL"),
        ("crm_customers", "last_message_at", "DATETIME", "NULL"),
        ("crm_services", "category", "VARCHAR(50)", "NULL"),
        ("crm_reservations", "end_at", "DATETIME", "NULL"),
        ("crm_reservations", "duration_min", "INTEGER", "NULL"),
        ("crm_reservations", "reminder_sent_at", "DATETIME", "NULL"),
    ]
    with engine.connect() as conn:
        for table, column, ddl_type, default in pending:
            try:
                cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))} \
                    if engine.dialect.name == "sqlite" else None
                if cols is None:
                    # 비-SQLite: information_schema 로 존재 여부 확인
                    res = conn.execute(text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :t AND column_name = :c"
                    ), {"t": table, "c": column})
                    exists = res.first() is not None
                else:
                    exists = column in cols
                if not exists:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type} DEFAULT {default}"
                    ))
                    conn.commit()
                    print(f"   ➕ Added column {table}.{column}")
            except Exception as e:
                print(f"   ⚠️ Could not ensure {table}.{column}: {e}")


def init_db():
    if not wait_for_db():
        sys.exit(1)

    print("🔧 Creating tables...")
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    print("✅ Tables created")

    print("🌱 Running seed data...")
    db = SessionLocal()
    try:
        run_seed(db)
        # 기존(이미 시드된) DB에도 CRM 데모 데이터를 멱등하게 1회 보강
        try:
            seed_crm_demo(db)
        except Exception as e:
            print(f"   ⚠️ CRM demo seed skipped: {e}")
        print("✅ Seed data loaded")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
