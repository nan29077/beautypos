"""플레이스 저장(place_save) 목표 건수를 플레이스 방문(place_traffic)으로 합산 이관

두 광고 종류를 화면에서 '플레이스 방문' 하나로 통합하기로 하면서,
플랜에 나뉘어 있던 목표 건수를 place_traffic 쪽으로 더해 옮긴다.
place_save 컬럼과 ad_executions 의 기존 기록은 그대로 둔다 — 되돌릴 수 있게 하기 위함이다.

멱등하다: 이관 후 place_save 목표가 0 이 되므로 두 번 실행해도 값이 변하지 않는다.

Revision ID: c8a1f0d54e39
Revises: a1b2c3d4e5f6
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8a1f0d54e39"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(conn, name: str) -> bool:
    return sa.inspect(conn).has_table(name)


def _columns(conn, table: str) -> set:
    return {col["name"] for col in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn, "plans"):
        return
    cols = _columns(conn, "plans")
    required = {
        "place_traffic_daily", "place_traffic_monthly",
        "place_save_daily", "place_save_monthly",
    }
    if not required.issubset(cols):
        return

    conn.execute(sa.text(
        "UPDATE plans SET "
        "  place_traffic_daily = COALESCE(place_traffic_daily, 0) + COALESCE(place_save_daily, 0), "
        "  place_traffic_monthly = COALESCE(place_traffic_monthly, 0) + COALESCE(place_save_monthly, 0), "
        "  place_save_daily = 0, "
        "  place_save_monthly = 0"
    ))


def downgrade() -> None:
    # 합산 이관은 원래 배분을 알 수 없어 되돌릴 수 없다.
    # 분리가 필요하면 plan.py 의 HIDDEN_AD_EXECUTION_TYPES 를 비우고
    # 관리자 화면에서 목표 건수를 다시 입력한다.
    pass
