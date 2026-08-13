"""
Database initialization: create all tables and run seed data.
Run: python -m app.init_db
"""
import time
import sys
from sqlalchemy import inspect, text
from app.database import engine, Base, SessionLocal
from app.models import *  # noqa: F401, F403 — import all models to register them
from app.seed import run_seed, seed_crm_demo, seed_plans, seed_general_owner
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
    (개발: SQLite / 운영: MariaDB 모두 ADD COLUMN 지원)

    [LEGACY] 이 목록은 alembic 도입 전에 반영된 컬럼의 구버전 DB 보정용으로만 유지한다.
    새 스키마 변경은 여기에 추가하지 말고 alembic 마이그레이션으로 작성할 것:
      alembic revision --autogenerate -m "..."  → 배포 시 deploy.sh 가 upgrade head 실행.
    운영 DB(beautypos)는 2026-08-13 에 head(a1b2c3d4e5f6)로 stamp 되어 alembic 이 관리한다."""
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
        # 커미션 구조 개편 (2026-07)
        ("fee_policies", "merchant_fee_rate", "NUMERIC(5,4)", "0.05"),
        ("settlements", "merchant_fee_amount", "NUMERIC(14,2)", "0"),
        ("settlements", "company_profit_amount", "NUMERIC(14,2)", "0"),
        ("settlements", "sales_manager_user_id", "INTEGER", "NULL"),
        ("users", "referral_code", "VARCHAR(50)", "NULL"),
        ("users", "business_type", "VARCHAR(20)", "'beauty'"),
        # 거래 취소 기능
        ("transactions", "status", "VARCHAR(9)", "'APPROVED'"),
        ("transactions", "cancelled_at", "DATETIME", "NULL"),
        ("transactions", "cancel_reason", "VARCHAR(255)", "NULL"),
        # 광고 주문 수량·단가 스냅샷
        ("ad_order_blog_details", "order_count", "INTEGER", "1"),
        ("ad_order_blog_details", "unit_price", "NUMERIC(12,2)", "0"),
        ("ad_order_blog_details", "est_total_cost", "NUMERIC(14,2)", "0"),
        ("ad_order_place_traffic_details", "order_count", "INTEGER", "1"),
        ("ad_order_place_traffic_details", "unit_price", "NUMERIC(12,2)", "0"),
        ("ad_order_place_traffic_details", "est_total_cost", "NUMERIC(14,2)", "0"),
    ]
    with engine.connect() as conn:
        for table, column, ddl_type, default in pending:
            try:
                cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))} \
                    if engine.dialect.name == "sqlite" else None
                if cols is None:
                    # 비-SQLite: information_schema 로 존재 여부 확인
                    # table_schema 를 현재 DB로 한정하지 않으면 같은 RDS 인스턴스의
                    # 다른 데이터베이스에 있는 동명 컬럼을 보고 ALTER 를 건너뛴다.
                    res = conn.execute(text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() "
                        "AND table_name = :t AND column_name = :c"
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

    # SQLite 전용: fee_policies.merchant_id 를 nullable 로 재구성 (전역 기본값 지원)
    _rebuild_fee_policies_for_nullable_merchant(engine)


def _rebuild_fee_policies_for_nullable_merchant(engine_):
    """fee_policies.merchant_id 를 nullable 로 변경.

    SQLite: 테이블 재생성으로 처리.
    MariaDB/MySQL: ALTER TABLE MODIFY COLUMN 으로 처리.
    """
    with engine_.begin() as conn:
        try:
            if engine_.dialect.name == "sqlite":
                pragma = list(conn.execute(text("PRAGMA table_info(fee_policies)")))
                if not pragma:
                    return
                merchant_id_col = next((r for r in pragma if r[1] == "merchant_id"), None)
                if merchant_id_col is None or merchant_id_col[3] == 0:
                    return  # 이미 nullable
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS _fee_policies_new (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        merchant_id INTEGER REFERENCES merchants(id),
                        merchant_fee_rate NUMERIC(5,4) DEFAULT 0.05,
                        pg_fee_rate NUMERIC(5,4) DEFAULT 0.03,
                        vat_inclusive_rate NUMERIC(5,4),
                        updated_at DATETIME
                    )
                """))
                conn.execute(text(
                    "INSERT OR IGNORE INTO _fee_policies_new "
                    "(id, merchant_id, merchant_fee_rate, pg_fee_rate, vat_inclusive_rate, updated_at) "
                    "SELECT id, merchant_id, "
                    "COALESCE(merchant_fee_rate, 0.05), pg_fee_rate, vat_inclusive_rate, updated_at "
                    "FROM fee_policies"
                ))
                conn.execute(text("DROP TABLE fee_policies"))
                conn.execute(text("ALTER TABLE _fee_policies_new RENAME TO fee_policies"))
                print("   ♻️  Rebuilt fee_policies with nullable merchant_id (SQLite)")
            elif engine_.dialect.name in ("mysql", "mariadb"):
                # MODIFY COLUMN is idempotent — safe to run even if already nullable
                conn.execute(text(
                    "ALTER TABLE fee_policies MODIFY COLUMN merchant_id INT NULL"
                ))
                print("   ♻️  Ensured fee_policies.merchant_id is nullable (MariaDB)")
        except Exception as e:
            print(f"   ⚠️ Could not make fee_policies.merchant_id nullable: {e}")


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


def _ensure_shorts_ad_support():
    """쇼츠 배포 주문에 필요한 스키마/기본 설정을 멱등하게 보강한다.

    - MariaDB/MySQL: ad_orders.type 네이티브 ENUM 에 'SHORTS' 추가
      (SQLite 는 VARCHAR 이라 보강할 것이 없다)
    - 쇼츠 기능 스위치는 기본 ON 으로 넣어, 광고 주문이 켜진 환경에서 바로 노출된다.
    """
    try:
        with engine.begin() as conn:
            if engine.dialect.name in {"mysql", "mariadb"}:
                conn.execute(text(
                    "ALTER TABLE ad_orders MODIFY COLUMN type "
                    "ENUM('BLOG','PLACE_TRAFFIC','SHORTS') NOT NULL"
                ))
            exists = conn.execute(text(
                "SELECT 1 FROM system_configs WHERE config_key = :key"
            ), {"key": "ad_shorts_enabled"}).first()
            if not exists:
                conn.execute(text(
                    "INSERT INTO system_configs (config_key, is_enabled, description) "
                    "VALUES (:key, :enabled, :description)"
                ), {
                    "key": "ad_shorts_enabled",
                    "enabled": True,
                    "description": "쇼츠(숏폼) 배포 광고 ON/OFF",
                })
                print("   ➕ Enabled ad_shorts_enabled feature flag")
    except Exception as e:  # noqa: BLE001 — 보강 실패가 기동을 막으면 안 된다
        print(f"   ⚠️ Could not ensure shorts ad support: {e}")


def init_db():
    _make_console_lenient()
    if not wait_for_db():
        sys.exit(1)

    print("🔧 Creating tables...")
    Base.metadata.create_all(bind=engine)
    _remove_retired_features()
    _ensure_columns()
    _ensure_shorts_ad_support()
    print("✅ Tables created")

    # 플랜은 데모 데이터가 아니라 운영에도 필요한 기준 데이터이므로 DEV_MODE 와 무관하게 보강한다.
    db = SessionLocal()
    try:
        seed_plans(db)
    except Exception as e:
        print(f"   ⚠️ Plan seed skipped: {e}")
    finally:
        db.close()

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
        # 일반 업종 테스트 원장 계정 보강 (기존 DB에도 1회 안전하게 추가)
        try:
            seed_general_owner(db)
        except Exception as e:
            print(f"   ⚠️ General owner seed skipped: {e}")
        print("✅ Seed data loaded")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
