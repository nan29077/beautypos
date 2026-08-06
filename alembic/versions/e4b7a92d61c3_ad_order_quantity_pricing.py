"""광고 주문 수량·단가 스냅샷 추가

Revision ID: e4b7a92d61c3
Revises: b7e2d4a91c85
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b7a92d61c3"
down_revision: Union[str, None] = "b7e2d4a91c85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DETAIL_TABLES = (
    "ad_order_blog_details",
    "ad_order_place_traffic_details",
)


def _columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in DETAIL_TABLES:
        if table_name not in tables:
            continue
        columns = _columns(table_name)
        with op.batch_alter_table(table_name) as batch_op:
            if "order_count" not in columns:
                batch_op.add_column(
                    sa.Column(
                        "order_count",
                        sa.Integer(),
                        nullable=False,
                        server_default="1",
                    )
                )
            if "unit_price" not in columns:
                batch_op.add_column(
                    sa.Column(
                        "unit_price",
                        sa.Numeric(12, 2),
                        nullable=False,
                        server_default="0",
                    )
                )
            if "est_total_cost" not in columns:
                batch_op.add_column(
                    sa.Column(
                        "est_total_cost",
                        sa.Numeric(14, 2),
                        nullable=False,
                        server_default="0",
                    )
                )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in reversed(DETAIL_TABLES):
        if table_name not in tables:
            continue
        columns = _columns(table_name)
        with op.batch_alter_table(table_name) as batch_op:
            for column_name in ("est_total_cost", "unit_price", "order_count"):
                if column_name in columns:
                    batch_op.drop_column(column_name)
