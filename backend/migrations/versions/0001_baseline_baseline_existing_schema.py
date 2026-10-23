"""baseline existing schema

Recreates the three tables that already existed before Alembic was
introduced into this project (they were previously created ad hoc via
`Base.metadata.create_all()`). For any database that already has these
tables, run `alembic stamp 0001_baseline` instead of `upgrade` for this
one revision, then `alembic upgrade head` to apply only what's new -
see README.md "Database migrations".

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-23 10:28:29.481682

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_stocks_symbol", "stocks", ["symbol"], unique=True)

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "stock_id", sa.Integer(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False, server_default="1d"),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("adjusted_close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "stock_id", "date", "interval", name="uq_price_history_stock_id_date_interval"
        ),
    )
    op.create_index("ix_price_history_stock_id", "price_history", ["stock_id"])
    op.create_index("ix_price_history_date", "price_history", ["date"])

    op.create_table(
        "stock_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "stock_id", sa.Integer(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="other"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(length=16),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_stock_events_provider_event_id"
        ),
    )
    op.create_index("ix_stock_events_stock_id", "stock_events", ["stock_id"])
    op.create_index(
        "ix_stock_events_stock_id_published_at", "stock_events", ["stock_id", "published_at"]
    )


def downgrade() -> None:
    op.drop_table("stock_events")
    op.drop_table("price_history")
    op.drop_table("stocks")
