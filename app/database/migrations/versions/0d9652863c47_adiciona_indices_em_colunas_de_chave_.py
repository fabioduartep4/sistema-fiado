"""adiciona indices em colunas de chave estrangeira

Revision ID: 0d9652863c47
Revises: a3a381d60d20
Create Date: 2026-08-15 11:28:00.912857
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0d9652863c47'
down_revision: Union[str, None] = 'a3a381d60d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_compradores_cliente_id', 'compradores', ['cliente_id'], unique=False)
    op.create_index('ix_historico_alteracoes_usuario_id', 'historico_alteracoes', ['usuario_id'], unique=False)
    op.create_index('ix_nomes_alternativos_cliente_id', 'nomes_alternativos', ['cliente_id'], unique=False)
    op.create_index('ix_pagamentos_cliente_id', 'pagamentos', ['cliente_id'], unique=False)
    op.create_index('ix_pagamentos_recebido_por_usuario_id', 'pagamentos', ['recebido_por_usuario_id'], unique=False)
    op.create_index('ix_telefones_cliente_id', 'telefones', ['cliente_id'], unique=False)
    op.create_index('ix_compras_cliente_id', 'compras', ['cliente_id'], unique=False)
    op.create_index('ix_compras_comprador_id', 'compras', ['comprador_id'], unique=False)
    op.create_index('ix_compras_compra_origem_id', 'compras', ['compra_origem_id'], unique=False)
    op.create_index('ix_pagamento_compra_pagamento_id', 'pagamento_compra', ['pagamento_id'], unique=False)
    op.create_index('ix_pagamento_compra_compra_id', 'pagamento_compra', ['compra_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_pagamento_compra_compra_id', table_name='pagamento_compra')
    op.drop_index('ix_pagamento_compra_pagamento_id', table_name='pagamento_compra')
    op.drop_index('ix_compras_compra_origem_id', table_name='compras')
    op.drop_index('ix_compras_comprador_id', table_name='compras')
    op.drop_index('ix_compras_cliente_id', table_name='compras')
    op.drop_index('ix_telefones_cliente_id', table_name='telefones')
    op.drop_index('ix_pagamentos_recebido_por_usuario_id', table_name='pagamentos')
    op.drop_index('ix_pagamentos_cliente_id', table_name='pagamentos')
    op.drop_index('ix_nomes_alternativos_cliente_id', table_name='nomes_alternativos')
    op.drop_index('ix_historico_alteracoes_usuario_id', table_name='historico_alteracoes')
    op.drop_index('ix_compradores_cliente_id', table_name='compradores')
