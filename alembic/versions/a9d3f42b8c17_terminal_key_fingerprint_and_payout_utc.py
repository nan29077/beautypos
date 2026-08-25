"""단말기 API 키 지문 컬럼 + 페이아웃 심사시각 UTC 정규화

두 가지를 한 번에 처리한다.

1. terminal_devices.api_key_fingerprint
   단말기 인증이 활성 단말기 전체를 bcrypt 로 순회하던 것을, 지문(HMAC-SHA256)으로
   후보 한 행만 찾아 검증하도록 바꾸면서 필요해진 조회용 컬럼이다.
   기존 행은 평문 키를 알 수 없어 여기서 채울 수 없다 — NULL 로 두고, 첫 인증에
   성공할 때 app/services/terminal_auth.py 가 채워 넣는다(레거시 경로).

2. payout_requests.reviewed_at
   승인/거절 시각만 KST 로 저장되고 나머지 시각 컬럼은 UTC 였다. 저장을 UTC 로
   통일하면서, 이미 KST 로 들어간 기존 값에서 9시간을 뺀다. 값이 없거나 이미
   UTC 인 행은 건드리지 않는다 — 이 리비전 이후 저장분은 전부 UTC 다.

멱등하다: 이미 있는 컬럼은 건너뛰고, 시각 보정은 리비전당 한 번만 돈다.

Revision ID: a9d3f42b8c17
Revises: f7a3c19e5b28
Create Date: 2026-08-25
"""
from datetime import datetime, timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9d3f42b8c17"
down_revision: Union[str, None] = "f7a3c19e5b28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KST_OFFSET_HOURS = 9


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _indexes(conn, table: str) -> set:
    return {i["name"] for i in sa.inspect(conn).get_indexes(table)}


def _parse(value):
    """SQLite 는 DATETIME 을 문자열로 돌려준다. datetime 으로 맞춘다."""
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("terminal_devices"):
        cols = _columns(conn, "terminal_devices")
        if "api_key_fingerprint" not in cols:
            op.add_column(
                "terminal_devices",
                sa.Column("api_key_fingerprint", sa.String(length=64), nullable=True),
            )
        if "ix_terminal_devices_api_key_fingerprint" not in _indexes(conn, "terminal_devices"):
            op.create_index(
                "ix_terminal_devices_api_key_fingerprint",
                "terminal_devices",
                ["api_key_fingerprint"],
            )

    # 기존 reviewed_at(KST 로 저장된 값) → UTC 로 되돌린다.
    if inspector.has_table("payout_requests"):
        rows = conn.execute(sa.text(
            "SELECT id, reviewed_at FROM payout_requests WHERE reviewed_at IS NOT NULL"
        )).fetchall()
        for row in rows:
            value = row[1]
            if value is None:
                continue
            if isinstance(value, str):
                value = _parse(value)  # SQLite 는 문자열로 돌려준다
                if value is None:
                    continue
            conn.execute(
                sa.text("UPDATE payout_requests SET reviewed_at = :v WHERE id = :i"),
                {"v": value - timedelta(hours=KST_OFFSET_HOURS), "i": row[0]},
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("payout_requests"):
        rows = conn.execute(sa.text(
            "SELECT id, reviewed_at FROM payout_requests WHERE reviewed_at IS NOT NULL"
        )).fetchall()
        for row in rows:
            value = row[1]
            if value is None:
                continue
            if isinstance(value, str):
                value = _parse(value)
                if value is None:
                    continue
            conn.execute(
                sa.text("UPDATE payout_requests SET reviewed_at = :v WHERE id = :i"),
                {"v": value + timedelta(hours=KST_OFFSET_HOURS), "i": row[0]},
            )

    if inspector.has_table("terminal_devices"):
        if "ix_terminal_devices_api_key_fingerprint" in _indexes(conn, "terminal_devices"):
            op.drop_index("ix_terminal_devices_api_key_fingerprint", table_name="terminal_devices")
        if "api_key_fingerprint" in _columns(conn, "terminal_devices"):
            op.drop_column("terminal_devices", "api_key_fingerprint")
