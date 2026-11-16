"""add tournament sync ledger

Revision ID: 34b5a8c98be6
Revises: ed8bc3869b03
Create Date: 2026-11-03 19:43:51.050587

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '34b5a8c98be6'
down_revision = 'ed8bc3869b03'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tournament_sync_state",
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_tournament_sync_state_revision"),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tournament_id"),
    )

    op.create_table(
        "tournament_sync_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_tournament_sync_request_revision"),
        sa.CheckConstraint("origin IN ('online', 'offline')", name="ck_tournament_sync_request_origin"),
        sa.CheckConstraint("length(payload_sha256) = 64", name="ck_tournament_sync_request_hash_length"),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tournament_id", "request_id", name="uq_tournament_sync_request_identity"),
    )
    op.create_index(
        "ix_tournament_sync_requests_tournament_revision",
        "tournament_sync_requests",
        ["tournament_id", "revision"],
    )


def downgrade():
    op.drop_index("ix_tournament_sync_requests_tournament_revision", table_name="tournament_sync_requests")
    op.drop_table("tournament_sync_requests")
    op.drop_table("tournament_sync_state")
