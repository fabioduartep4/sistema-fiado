"""Controller de importação de XML (NF-e venda a prazo).

Faz a ponte entre as telas de importação
(``app.views.xml_importacao_view``) e os serviços
``app.services.xml_importacao_service`` / ``app.services.configuracao_service``.
"""

from __future__ import annotations

from typing import Optional

from app.services import configuracao_service, xml_importacao_service
from app.services.auth_service import UsuarioAutenticado
from app.services.xml_importacao_service import (
    CandidatoImportacao,
    EscolhaImportacao,
    ProgressoCallback,
    ResultadoImportacao,
)
from app.utils.nfe_parser import ProdutoXml


class XmlImportacaoController:
    """Controlador da importação de XMLs de NF-e.

    Attributes:
        usuario_logado: Usuário autenticado que está operando a tela.
    """

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        self.usuario_logado = usuario_logado

    def listar_candidatos(
        self, progresso: Optional[ProgressoCallback] = None
    ) -> list[CandidatoImportacao]:
        """Lista os XMLs de venda a prazo pendentes de importação."""
        return xml_importacao_service.listar_candidatos_importacao(self.usuario_logado, progresso)

    def importar(self, escolhas: list[EscolhaImportacao]) -> list[ResultadoImportacao]:
        """Importa os XMLs escolhidos."""
        return xml_importacao_service.importar_xmls(self.usuario_logado, escolhas)

    def obter_produtos(
        self, chave: str, progresso: Optional[ProgressoCallback] = None
    ) -> list[ProdutoXml]:
        """Obtém os produtos de uma nota já importada (lidos ao vivo do XML)."""
        return xml_importacao_service.obter_produtos(chave, progresso)

    def obter_pasta_xml(self) -> str:
        """Obtém a pasta configurada para os XMLs."""
        return configuracao_service.obter_pasta_xml()

    def definir_pasta_xml(self, pasta: str) -> None:
        """Define a pasta onde os XMLs serão buscados."""
        configuracao_service.definir_pasta_xml(self.usuario_logado, pasta)
