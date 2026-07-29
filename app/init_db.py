"""
Database initialization: create all tables and run seed data.
Run: python -m app.init_db
"""
import time
import sys
from sqlalchemy import inspect, text
from app.database import engine, Base, SessionLocal
from app.models import *  # noqa: F401, F403 — import all models to register them
from app.seed import run_seed, seed_crm_demo
from app.config import get_settings


def _make_console_lenient():
    """콘솔이 못 그리는 글자 때문에 기동이 막히지 않게 한다.

    한글 Windows 콘솔(cp949)에서는 아래 로그의 이모지가 UnicodeEncodeError 를 일으켜
    lifespan(init_db) 이 그대로 죽고 서버가 뜨지 않는다. 인코딩은 그대로 두고
    표현 못 하는 문자만 대체하도록 바꾼다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001 — 콘솔 설정 실패가 기동을 막으면 안 된다
            pass


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
        ("ad_place_profiles", "analysis_keyword", "VARCHAR(200)", "NULL"),
        ("ad_metrics", "search_keyword", "VARCHAR(200)", "NULL"),
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


def _remove_retired_features():
    """Permanently remove storage for the retired rent-payment and luxury features."""
    retired_tables = [
        "luxury_product_orders",
        "luxury_products",
        "rent_payments",
        "landlord_sales_assignments",
        "tenants",
        "landlord_profiles",
    ]
    with engine.begin() as conn:
        for table in retired_tables:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        conn.execute(text(
            "DELETE FROM merchant_pg_configs WHERE provider_id IN "
            "(SELECT id FROM pg_providers WHERE code = 'ongi')"
        ))
        conn.execute(text("DELETE FROM pg_providers WHERE code = 'ongi'"))
        conn.execute(text("DELETE FROM users WHERE role IN ('LANDLORD', 'landlord')"))
        terminal_columns = {column["name"] for column in inspect(conn).get_columns("terminal_devices")}
        if "api_key_plain" in terminal_columns:
            conn.execute(text("UPDATE terminal_devices SET api_key_plain = NULL"))
            conn.execute(text("ALTER TABLE terminal_devices DROP COLUMN api_key_plain"))
        if engine.dialect.name in {"mysql", "mariadb"}:
            conn.execute(text(
                "ALTER TABLE users MODIFY role "
                "ENUM('ADMIN','SALES','OWNER','DESIGNER') NOT NULL"
            ))


def init_db():
    _make_console_lenient()
    if not wait_for_db():
        sys.exit(1)

    print("🔧 Creating tables...")
    Base.metadata.create_all(bind=engine)
    _remove_retired_features()
    _ensure_columns()
    print("✅ Tables created")

    settings = get_settings()
    if not settings.DEV_MODE:
        print("ℹ️ Demo seed skipped (DEV_MODE is disabled)")
        return

    print("🌱 Running development seed data...")
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
