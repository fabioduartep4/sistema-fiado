"""Pacote de modelos ORM (SQLAlchemy).

Importar todos os modelos aqui garante que o Alembic (autogenerate) e o
``Base.metadata`` enxerguem todas as tabelas do sistema.
"""

from app.models.cliente import Cliente
from app.models.comprador import Comprador
from app.models.compra import Compra, StatusCompra
from app.models.configuracao_sistema import ConfiguracaoSistema
from app.models.historico_alteracao import HistoricoAlteracao
from app.models.log_erro import LogErro
from app.models.nome_alternativo import NomeAlternativo
from app.models.pagamento import Pagamento
from app.models.pagamento_compra import PagamentoCompra
from app.models.telefone import Telefone
from app.models.usuario import PerfilUsuario, Usuario
from app.models.xml_indexado import XmlIndexado

__all__ = [
    "Cliente",
    "Comprador",
    "Compra",
    "StatusCompra",
    "ConfiguracaoSistema",
    "HistoricoAlteracao",
    "LogErro",
    "NomeAlternativo",
    "Pagamento",
    "PagamentoCompra",
    "Telefone",
    "Usuario",
    "PerfilUsuario",
    "XmlIndexado",
]
