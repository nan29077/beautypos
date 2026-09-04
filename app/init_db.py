"""
Database initialization: create all tables and run seed data.
Run: python -m app.init_db
"""
import time
import sys
from sqlalchemy import text
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
    """[REMOVED] 기동 시점의 레거시 컬럼 보정은 더 이상 하지 않는다.

    예전에는 alembic 도입 전 DB 를 맞추려고 여기에서 ALTER TABLE 을 돌렸지만,
    앱이 운영 DB 에 DDL 을 직접 실행하는 구조 자체가 위험하다.
    스키마 변경은 전부 alembic 마이그레이션으로만 반영한다:
      alembic revision --autogenerate -m "..."  → 배포 시 deploy.sh 가 upgrade head 실행.
    운영 DB(beautypos)는 2026-08-13 에 alembic 으로 편입되었고,
    과거 pending 목록의 컬럼은 모두 마이그레이션에 포함되어 있다.

    호출부 호환을 위해 함수만 남긴 no-op 이다.
    """
    return


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


def _warn_if_remote_db():
    """개발 모드인데 원격 DB 에 붙어 있으면 눈에 띄게 알린다.

    로컬에서 서버를 띄웠는데 실제로는 원격 DB 를 건드리고 있으면 실험한 결과가
    그대로 남고, 기동 시 create_all 이 그 DB 에 테이블을 만든다.
    비밀번호는 출력하지 않고 호스트와 DB 이름만 보여준다.
    """
    settings = get_settings()
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        return
    if settings.APP_ENV.lower() in {"production", "prod"}:
        return
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        name = (parsed.path or "").lstrip("/")
    except Exception:  # noqa: BLE001 — 경고가 기동을 막으면 안 된다
        return
    if not host or host in {"localhost", "127.0.0.1", "::1", "db"}:
        return

    print("")
    print("=" * 72)
    print("[주의] 개발 모드인데 원격 DB 에 접속합니다")
    print(f"   호스트   : {host}")
    print(f"   데이터베이스: {name}")
    print("   이 서버의 모든 변경이 원격 DB 에 그대로 남고,")
    print("   기동할 때마다 create_all 이 그 DB 에 테이블을 만듭니다.")
    print("   로컬에서만 돌리려면 .env 에 아래를 넣으세요:")
    print("       DATABASE_URL_OVERRIDE=sqlite:///./adpay.db")
    print("=" * 72)
    print("")


def init_db():
    _make_console_lenient()
    _warn_if_remote_db()
    if not wait_for_db():
        sys.exit(1)

    print("🔧 Creating tables...")
    Base.metadata.create_all(bind=engine)
    # 폐지 기능 정리(DROP/DELETE)는 alembic c4e9b71fa2d5 로 옮겼다. 여기서는 하지 않는다.
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
        # 데모 가맹점은 이 시점에 만들어지므로 플랜 배정을 한 번 더 보강한다.
        # 위쪽 seed_plans 는 가맹점이 없는 상태에서 돌아 배정할 대상이 없다.
        try:
            seed_plans(db)
        except Exception as e:
            print(f"   ⚠️ Plan assign skipped: {e}")
        print("✅ Seed data loaded")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
