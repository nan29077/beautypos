"""거래 중복 적재 방지: (terminal_id, approval_code) 복합 unique

Revision ID: f1c4d8b62a10
Revises: e4b7a92d61c3
Create Date: 2026-08-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1c4d8b62a10"
down_revision: Union[str, None] = "e4b7a92d61c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "transactions"
CONSTRAINT = "uq_terminal_approval"


def _has_constraint(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in set(inspector.get_table_names()):
        return False
    existing = {uc["name"] for uc in inspector.get_unique_constraints(TABLE)}
    existing |= {ix["name"] for ix in inspector.get_indexes(TABLE) if ix.get("unique")}
    return name in existing


def upgrade() -> None:
    if TABLE not in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    if _has_constraint(CONSTRAINT):
        return
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.create_unique_constraint(CONSTRAINT, ["terminal_id", "approval_code"])


def downgrade() -> None:
    if not _has_constraint(CONSTRAINT):
        return
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="unique")
