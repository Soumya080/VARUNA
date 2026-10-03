"""initial_schema

Revision ID: 8cd5bdc2d07b
Revises: 
Create Date: 2026-08-25 20:46:17.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = '8cd5bdc2d07b'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Ensure PostGIS is enabled
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis')

    # cases
    op.create_table('cases',
    sa.Column('case_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('bbox', geoalchemy2.types.Geometry(geometry_type='POLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('event_sequence_current', sa.Integer(), nullable=False, server_default='0'),
    sa.PrimaryKeyConstraint('case_id')
    )
    op.create_index('ix_cases_status', 'cases', ['status'], unique=False)
    op.create_index('ix_cases_created_at', 'cases', ['created_at'], unique=False)

    # artifacts
    op.create_table('artifacts',
    sa.Column('artifact_id', sa.String(length=128), nullable=False),
    sa.Column('case_id', sa.String(length=64), nullable=False),
    sa.Column('artifact_type', sa.String(length=64), nullable=False),
    sa.Column('produced_by', sa.String(length=64), nullable=False),
    sa.Column('content_hash', sa.String(length=128), nullable=True),
    sa.Column('storage_key', sa.String(length=512), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.case_id'], ),
    sa.PrimaryKeyConstraint('artifact_id')
    )
    op.create_index('ix_artifacts_case_id', 'artifacts', ['case_id'], unique=False)
    op.create_index('ix_artifacts_type', 'artifacts', ['artifact_type'], unique=False)
    op.create_index('ix_artifacts_created_at', 'artifacts', ['created_at'], unique=False)

    # case_events
    op.create_table('case_events',
    sa.Column('event_id', sa.String(length=64), nullable=False),
    sa.Column('case_id', sa.String(length=64), nullable=False),
    sa.Column('event_type', sa.String(length=128), nullable=False),
    sa.Column('actor', sa.String(length=128), nullable=False),
    sa.Column('correlation_id', sa.String(length=128), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('idempotency_key', sa.String(length=256), nullable=True),
    sa.ForeignKeyConstraint(['case_id'], ['cases.case_id'], ),
    sa.PrimaryKeyConstraint('event_id'),
    sa.UniqueConstraint('case_id', 'idempotency_key', name='uq_case_event_idempotency')
    )
    op.create_index('ix_case_events_case_seq', 'case_events', ['case_id', 'sequence'], unique=False)
    op.create_index('ix_case_events_type', 'case_events', ['event_type'], unique=False)
    op.create_index('ix_case_events_ts', 'case_events', ['timestamp'], unique=False)

    # vessels
    op.create_table('vessels',
    sa.Column('mmsi', sa.String(length=16), nullable=False),
    sa.Column('vessel_name', sa.String(length=256), nullable=True),
    sa.Column('vessel_type', sa.String(length=32), nullable=True),
    sa.Column('flag_state', sa.String(length=8), nullable=True),
    sa.Column('imo', sa.String(length=16), nullable=True),
    sa.PrimaryKeyConstraint('mmsi')
    )

    # ais_tracks
    op.create_table('ais_tracks',
    sa.Column('id', postgresql.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('mmsi', sa.String(length=16), nullable=True),
    sa.Column('case_id', sa.String(length=64), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('position', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, from_text='ST_GeomFromEWKT', name='geometry'), nullable=False),
    sa.Column('sog_knots', sa.Float(), nullable=True),
    sa.Column('heading_deg', sa.Float(), nullable=True),
    sa.Column('gap_flag', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['cases.case_id'], ),
    sa.ForeignKeyConstraint(['mmsi'], ['vessels.mmsi'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ais_tracks_mmsi_ts', 'ais_tracks', ['mmsi', 'timestamp'], unique=False)
    op.create_index('ix_ais_tracks_case_mmsi', 'ais_tracks', ['case_id', 'mmsi'], unique=False)

    # recommendations
    op.create_table('recommendations',
    sa.Column('recommendation_id', sa.String(length=64), nullable=False),
    sa.Column('case_id', sa.String(length=64), nullable=True),
    sa.Column('decision_state', sa.String(length=32), nullable=True),
    sa.Column('latent_probability', sa.Float(), nullable=True),
    sa.Column('top_posterior', sa.Float(), nullable=True),
    sa.Column('distinguishability', sa.Float(), nullable=True),
    sa.Column('candidates', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('envelope', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['case_id'], ['cases.case_id'], ),
    sa.PrimaryKeyConstraint('recommendation_id')
    )

    # decisions
    op.create_table('decisions',
    sa.Column('decision_id', sa.String(length=64), nullable=False),
    sa.Column('case_id', sa.String(length=64), nullable=True),
    sa.Column('recommendation_id', sa.String(length=64), nullable=True),
    sa.Column('human_officer_id', sa.String(length=64), nullable=True),
    sa.Column('human_decision', sa.String(length=32), nullable=True),
    sa.Column('override_reason', sa.Text(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['case_id'], ['cases.case_id'], ),
    sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.recommendation_id'], ),
    sa.PrimaryKeyConstraint('decision_id')
    )

def downgrade() -> None:
    op.drop_table('decisions')
    op.drop_table('recommendations')
    op.drop_index('ix_ais_tracks_case_mmsi', table_name='ais_tracks')
    op.drop_index('ix_ais_tracks_mmsi_ts', table_name='ais_tracks')
    op.drop_table('ais_tracks')
    op.drop_table('vessels')
    op.drop_index('ix_case_events_ts', table_name='case_events')
    op.drop_index('ix_case_events_type', table_name='case_events')
    op.drop_index('ix_case_events_case_seq', table_name='case_events')
    op.drop_table('case_events')
    op.drop_index('ix_artifacts_created_at', table_name='artifacts')
    op.drop_index('ix_artifacts_type', table_name='artifacts')
    op.drop_index('ix_artifacts_case_id', table_name='artifacts')
    op.drop_table('artifacts')
    op.drop_index('ix_cases_created_at', table_name='cases')
    op.drop_index('ix_cases_status', table_name='cases')
    op.drop_table('cases')
