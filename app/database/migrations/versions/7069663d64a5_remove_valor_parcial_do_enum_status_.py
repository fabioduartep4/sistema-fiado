"""remove valor parcial do enum status_compra

Revision ID: 7069663d64a5
Revises: 0d9652863c47
Create Date: 2026-08-15 11:40:19.655920
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7069663d64a5'
down_revision: Union[str, None] = '0d9652863c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 'PARCIAL' nunca é atribuído pelo código (uma compra em aberto é sempre
    # integralmente devida) — mas confere antes de remover o valor do enum,
    # para nunca apagar dado real silenciosamente.
    # Nota: os rótulos armazenados no Postgres são o *nome* dos membros do
    # enum Python (ABERTA/PARCIAL/QUITADA), não o `.value` (aberta/.../...),
    # já que o modelo usa `Enum(StatusCompra, ...)` sem `values_callable`.
    conexao = op.get_bind()
    em_uso = conexao.execute(
        sa.text("SELECT COUNT(*) FROM compras WHERE status = 'PARCIAL'")
    ).scalar()
    if em_uso:
        raise RuntimeError(
            f"Migração abortada: {em_uso} compra(s) com status='PARCIAL' encontradas. "
            "Essa migração remove esse valor do enum e apagaria essas linhas."
        )

    # Postgres não suporta remover um valor de um ENUM diretamente — é
    # preciso recriar o tipo.
    op.execute("ALTER TYPE status_compra RENAME TO status_compra_old")
    op.execute("CREATE TYPE status_compra AS ENUM ('ABERTA', 'QUITADA')")
    op.execute(
        "ALTER TABLE compras ALTER COLUMN status TYPE status_compra "
        "USING status::text::status_compra"
    )
    op.execute("DROP TYPE status_compra_old")


def downgrade() -> None:
    op.execute("ALTER TYPE status_compra RENAME TO status_compra_new")
    op.execute("CREATE TYPE status_compra AS ENUM ('ABERTA', 'PARCIAL', 'QUITADA')")
    op.execute(
        "ALTER TABLE compras ALTER COLUMN status TYPE status_compra "
        "USING status::text::status_compra"
    )
    op.execute("DROP TYPE status_compra_new")
