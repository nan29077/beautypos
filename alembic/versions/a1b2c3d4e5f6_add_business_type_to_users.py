"""add business_type to users

Revision ID: a1b2c3d4e5f6
Revises: f2d5e9c73b21
Create Date: 2026-08-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f2d5e9c73b21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUSINESS_TYPE_ENUM = sa.Enum("beauty", "general", name="businesstype")


def upgrade() -> None:
    # 1) SQLite는 ADD COLUMN 후 server_default 없이 nullable=True 로 추가한 뒤,
    #    기존 행을 'beauty' 로 업데이트하고, NOT NULL을 별도로 강제할 수 없으므로
    #    server_default 를 붙여 ADD COLUMN 한다 (Alembic은 이를 자동 처리).
    BUSINESS_TYPE_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "business_type",
            BUSINESS_TYPE_ENUM,
            nullable=False,
            server_default="beauty",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "business_type")
    BUSINESS_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
