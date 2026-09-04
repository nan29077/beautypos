"""폐지된 기능(월세결제·명품·LANDLORD)의 잔재를 일괄 정리한다

기존에는 이 정리를 앱 기동 시점(app/init_db.py 의 _remove_retired_features)에서
DROP TABLE / DELETE / ALTER 로 매번 실행했다. 운영 DB 에 대해 애플리케이션이
DDL 을 직접 돌리는 구조라, 기동 순서나 실수 하나로 데이터가 사라질 수 있었다.
정리는 한 번만 하면 되는 일이므로 마이그레이션으로 옮긴다.

멱등하다: 이미 정리된 DB 에서도 안전하게 다시 돌릴 수 있다.

Revision ID: c4e9b71fa2d5
Revises: a2f7c4e18b93
Create Date: 2026-09-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e9b71fa2d5"
down_revision: Union[str, None] = "a2f7c4e18b93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 폐지된 기능이 쓰던 테이블 (자식 → 부모 순서)
RETIRED_TABLES = (
    "luxury_product_orders",
    "luxury_products",
    "rent_payments",
    "landlord_sales_assignments",
    "tenants",
    "landlord_profiles",
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    for table in RETIRED_TABLES:
        if table in tables:
            op.drop_table(table)

    # 구 ONGI PG 연동 레코드 정리 (현재 ONGI 는 PG 가 아니라 별도 연동으로 동작한다)
    if {"pg_providers", "merchant_pg_configs"} <= tables:
        conn.execute(sa.text(
            "DELETE FROM merchant_pg_configs WHERE provider_id IN "
            "(SELECT id FROM pg_providers WHERE code = 'ongi')"
        ))
    if "pg_providers" in tables:
        conn.execute(sa.text("DELETE FROM pg_providers WHERE code = 'ongi'"))

    if "users" in tables:
        conn.execute(sa.text("DELETE FROM users WHERE role IN ('LANDLORD', 'landlord')"))
        if conn.dialect.name in {"mysql", "mariadb"}:
            conn.execute(sa.text(
                "ALTER TABLE users MODIFY role "
                "ENUM('ADMIN','SALES','OWNER','DESIGNER') NOT NULL"
            ))

    # 단말기 평문 키 컬럼 제거 (해시/지문만 남긴다)
    if "terminal_devices" in tables:
        columns = {c["name"] for c in inspector.get_columns("terminal_devices")}
        if "api_key_plain" in columns:
            conn.execute(sa.text("UPDATE terminal_devices SET api_key_plain = NULL"))
            op.drop_column("terminal_devices", "api_key_plain")


def downgrade() -> None:
    # 폐지된 기능의 테이블과 데이터는 복구하지 않는다 (되돌릴 원본이 없다).
    pass
