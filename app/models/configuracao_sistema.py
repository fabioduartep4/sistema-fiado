"""Modelo ORM: ConfiguracaoSistema.

Tabela de configurações globais do sistema, no formato chave/valor. Por
morar no PostgreSQL central (e não em um arquivo local), o valor é o
mesmo para todos os computadores da rede — é o caso do modo de data
padrão usado em Adicionar Compra e Receber Conta ("dia atual" ou "dia
anterior"), e será reaproveitada pela futura tela de Configurações
(pasta de backup, tema, etc.).
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, ColunasComunsMixin


class ConfiguracaoSistema(Base, ColunasComunsMixin):
    """Representa uma configuração global do sistema (chave/valor).

    Attributes:
        chave: Identificador único da configuração (ex.: "modo_data_padrao").
        valor: Valor da configuração, armazenado como texto.
    """

    __tablename__ = "configuracoes"

    chave: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    valor: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConfiguracaoSistema chave={self.chave!r} valor={self.valor!r}>"
