"""ad_dispatches 에 리워드팝 실측 컬럼 추가

requested_count 는 "우리가 요청한 수"만 담고 있어서, 리워드팝이 실제로 몇 건을
소화했는지(reqCount / rewardCount)와 어떤 키워드가 실제로 등록됐는지를 알 수 없었다.
상태 갱신 때 채울 컬럼을 추가한다.

멱등하다: 이미 있는 컬럼은 건너뛴다.

Revision ID: a2f7c4e18b93
Revises: b9e4f61a2d73
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2f7c4e18b93"
down_revision: Union[str, None] = "b9e4f61a2d73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "ad_dispatches"

NEW_COLUMNS = (
    ("delivered_count", sa.Column("delivered_count", sa.Integer(), nullable=True)),
    ("reward_count", sa.Column("reward_count", sa.Integer(), nullable=True)),
    ("keyword_count", sa.Column("keyword_count", sa.Integer(), nullable=True)),
    ("keywords_json", sa.Column("keywords_json", sa.Text(), nullable=True)),
    ("external_status", sa.Column("external_status", sa.String(length=40), nullable=True)),
)


def _existing(conn) -> set:
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE):
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _existing(conn)
    if not present:
        # 테이블 자체가 없으면 create_all 이 새 정의로 만들어 준다.
        return
    for name, column in NEW_COLUMNS:
        if name not in present:
            op.add_column(TABLE, column)


def downgrade() -> None:
    conn = op.get_bind()
    present = _existing(conn)
    for name, _ in reversed(NEW_COLUMNS):
        if name in present:
            op.drop_column(TABLE, name)
