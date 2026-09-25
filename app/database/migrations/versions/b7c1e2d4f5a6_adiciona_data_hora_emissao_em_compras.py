"""adiciona data_hora_emissao em compras

Revision ID: b7c1e2d4f5a6
Revises: 94e8ed403220
Create Date: 2026-09-25 21:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c1e2d4f5a6'
down_revision: Union[str, None] = '94e8ed403220'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'compras',
        sa.Column('data_hora_emissao', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('compras', 'data_hora_emissao')
