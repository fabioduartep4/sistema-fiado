"""Modelo ORM: XmlIndexado.

Índice permanente (compartilhado via PostgreSQL — o mesmo banco central de
todo o sistema) dos arquivos XML já vistos na pasta de XMLs configurada.

Existe para evitar reler e reinterpretar a pasta inteira a cada operação
("Ver Produtos", "Importar XMLs Agora") em instalações com um volume muito
grande de arquivos acumulados (dezenas ou centenas de milhares) — sem esse
índice, cada operação precisaria abrir e ler todo arquivo da pasta, o que
não escala. Com o índice, uma varredura só precisa processar os arquivos
que ainda não constam aqui (novos desde a última vez que qualquer
computador da rede varreu a pasta) — ver ``app.services.xml_importacao_service``.

Os arquivos XML em si nunca são alterados por este sistema (ver
``app.utils.nfe_parser``); este índice guarda apenas os dados já extraídos
de cada um, para não precisar reabri-los.
"""

from __future__ import annotations

from datetime import date as date_
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, ColunasComunsMixin


class XmlIndexado(Base, ColunasComunsMixin):
    """Representa um arquivo XML já processado ao menos uma vez pelo sistema.

    Attributes:
        caminho_arquivo: Caminho completo do arquivo (único), exatamente
            como aparece dentro da pasta de XMLs configurada.
        nome_arquivo: Nome do arquivo (sem o caminho), só para exibição.
        chave: Chave de acesso da NF-e, ou None se o arquivo não for uma
            NF-e válida (ver ``xml_invalido``).
        natureza_operacao: Natureza da operação extraída do XML (ex.:
            "Venda a prazo"), guardada só para referência/depuração — não
            é suficiente sozinha para saber se é fiado (ver ``eh_fiado``).
        eh_venda_a_prazo: Já calculado a partir de ``natureza_operacao``
            (mesma normalização de ``NotaFiscalXml.eh_venda_a_prazo``) no
            momento da indexação — guardado só para referência/depuração.
        forma_pagamento: Código ``tPag`` (tabela oficial da SEFAZ) da nota
            — ex.: "05" (Crédito Loja/fiado), "03" (Cartão de Crédito),
            "04" (Cartão de Débito) — guardado só para referência/depuração.
        eh_fiado: True só quando a nota é de fato uma venda fiado —
            natureza de operação "Venda a prazo" **e** forma de pagamento
            "Crédito Loja" (``tPag=05``). Confirmado com dados reais que a
            natureza da operação sozinha não basta: vendas no cartão de
            crédito/débito também aparecem como "Venda a prazo" neste
            sistema. É este campo (não ``eh_venda_a_prazo``) que filtra
            candidatos de importação.
        nome_cliente_xml: Nome do destinatário extraído do XML.
        valor_total: Valor total da nota (``<vNF>``) — soma de todas as
            formas de pagamento, guardado só para referência/depuração.
        valor_fiado: Soma só da(s) forma(s) de pagamento "Crédito Loja"
            (``tPag=05``) — é este o valor usado ao importar como compra,
            não ``valor_total``. Confirmado com dado real: o cliente pode
            pagar parte da compra na hora e só o restante ficar na conta —
            nesse caso ``valor_fiado`` é menor que ``valor_total``.
        data_emissao: Data de emissão da nota.
        xml_invalido: True quando o arquivo não pôde ser lido como uma
            NF-e válida — indexado mesmo assim, para não tentar reabri-lo
            (e falhar de novo) a cada varredura futura.
    """

    __tablename__ = "xml_indexados"

    caminho_arquivo: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    chave: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    natureza_operacao: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    eh_venda_a_prazo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    forma_pagamento: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    eh_fiado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    nome_cliente_xml: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    valor_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    valor_fiado: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    data_emissao: Mapped[Optional[date_]] = mapped_column(Date, nullable=True)
    xml_invalido: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<XmlIndexado caminho_arquivo={self.caminho_arquivo!r} chave={self.chave!r}>"
