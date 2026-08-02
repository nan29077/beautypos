"""결제 취소/환불: transactions.status / cancelled_at / cancel_reason 추가

Revision ID: f2d5e9c73b21
Revises: f1c4d8b62a10
Create Date: 2026-08-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2d5e9c73b21"
down_revision: Union[str, None] = "f1c4d8b62a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "transactions"
STATUS_ENUM = sa.Enum("APPROVED", "CANCELLED", name="transaction_status")


def _columns() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _indexes() -> set:
    return {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    STATUS_ENUM.create(bind, checkfirst=True)

    columns = _columns()
    with op.batch_alter_table(TABLE) as batch_op:
        if "status" not in columns:
            batch_op.add_column(
                sa.Column(
                    "status",
                    STATUS_ENUM,
                    nullable=False,
                    server_default="APPROVED",
                )
            )
        if "cancelled_at" not in columns:
            batch_op.add_column(sa.Column("cancelled_at", sa.DateTime(), nullable=True))
        if "cancel_reason" not in columns:
            batch_op.add_column(sa.Column("cancel_reason", sa.String(255), nullable=True))

    if "ix_transactions_status" not in _indexes():
        op.create_index("ix_transactions_status", TABLE, ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    if "ix_transactions_status" in _indexes():
        op.drop_index("ix_transactions_status", table_name=TABLE)

    columns = _columns()
    with op.batch_alter_table(TABLE) as batch_op:
        for column_name in ("cancel_reason", "cancelled_at", "status"):
            if column_name in columns:
                batch_op.drop_column(column_name)

    STATUS_ENUM.drop(bind, checkfirst=True)
