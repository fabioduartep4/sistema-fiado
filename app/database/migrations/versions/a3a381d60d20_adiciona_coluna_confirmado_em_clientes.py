"""adiciona coluna confirmado em clientes

Revision ID: a3a381d60d20
Revises: 775425f06865
Create Date: 2026-08-11 08:52:06.019194
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3a381d60d20'
down_revision: Union[str, None] = '775425f06865'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adding server_default ensures existing rows get 'False' instead of NULL
    op.add_column(
        'clientes',
        sa.Column(
            'confirmado',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),  # Or 'true'
        ),
    )


def downgrade() -> None:
    op.drop_column('clientes', 'confirmado')