"""add scanner tables

Adds every table introduced by the daily NIFTY 500 hybrid signal scanner:
scan_runs, signal_events, notification_deliveries, scan_locks,
universe_membership_events, strategy_config_versions. Safe to apply to a
fresh database (after 0001_baseline) or to an existing one that was
`alembic stamp`-ed at 0001_baseline.

Revision ID: 0002_scanner_tables
Revises: 0001_baseline
Create Date: 2026-10-23 10:28:29.881015

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_scanner_tables"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trigger", sa.String(length=16), nullable=False, server_default="scheduled"),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("universe_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_stale", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buy_signals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sell_signals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    op.create_table(
        "signal_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "stock_id", sa.Integer(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "scan_run_id",
            sa.Integer(),
            sa.ForeignKey("scan_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("signal_type", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("indicators_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("data_quality_status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column(
            "notification_status",
            sa.String(length=16),
            nullable=False,
            server_default="not_applicable",
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "stock_id",
            "strategy_name",
            "strategy_version",
            "session_date",
            "signal_type",
            name="uq_signal_events_identity",
        ),
    )
    op.create_index("ix_signal_events_stock_id", "signal_events", ["stock_id"])
    op.create_index(
        "ix_signal_events_stock_strategy_session",
        "signal_events",
        ["stock_id", "strategy_name", "session_date"],
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "signal_event_id",
            sa.Integer(),
            sa.ForeignKey("signal_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="telegram"),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_deliveries_signal_event_id", "notification_deliveries", ["signal_event_id"]
    )

    op.create_table(
        "scan_locks",
        sa.Column("name", sa.String(length=64), primary_key=True),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_by", sa.String(length=128), nullable=False),
    )

    op.create_table(
        "universe_membership_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "stock_id", sa.Integer(), sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("universe", sa.String(length=32), nullable=False, server_default="NIFTY500"),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_universe_membership_events_stock_id", "universe_membership_events", ["stock_id"]
    )
    op.create_index(
        "ix_universe_membership_stock_universe",
        "universe_membership_events",
        ["stock_id", "universe"],
    )

    op.create_table(
        "strategy_config_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("strategy_config_versions")
    op.drop_table("universe_membership_events")
    op.drop_table("scan_locks")
    op.drop_table("notification_deliveries")
    op.drop_table("signal_events")
    op.drop_table("scan_runs")
