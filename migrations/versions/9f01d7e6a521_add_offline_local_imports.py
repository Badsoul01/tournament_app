"""Add offline local import identity ledger for production.

Revision ID: 9f01d7e6a521
Revises: 34b5a8c98be6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '9f01d7e6a521'
down_revision = '34b5a8c98be6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if not sa.inspect(conn).has_table('offline_local_imports'):
        op.create_table(
            'offline_local_imports',
            sa.Column('local_uuid', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('tournament_id', sa.Integer(), sa.ForeignKey('tournaments.id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('organizer_id', sa.Integer(), sa.ForeignKey('organizers.id'), nullable=True),
            sa.Column('payload_sha256', sa.CHAR(64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade():
    # Do not automatically drop an import ledger that may contain confirmed tournaments.
    raise RuntimeError('Manual downgrade required: preserve offline_local_imports data')
