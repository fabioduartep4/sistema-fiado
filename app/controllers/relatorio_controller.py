"""Controller de histórico e relatórios.

Faz a ponte entre a tela Histórico e Relatórios (``app.views.relatorio_view``)
e a regra de negócio (``app.services.relatorio_service``).
"""

from __future__ import annotations

from typing import Optional

from app.services import relatorio_service
from app.services.auth_service import UsuarioAutenticado
from app.services.relatorio_service import (
    HistoricoResumo,
    LogErroResumo,
    SaldoAtrasoResumo,
    SaldoClienteResumo,
)


class RelatorioController:
    """Controlador da tela de Histórico e Relatórios.

    Attributes:
        usuario_logado: Usuário autenticado que está operando a tela
            (as consultas exigem perfil Administrador).
    """

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        self.usuario_logado = usuario_logado

    def listar_historico(self, entidade: Optional[str] = None, limite: int = 200) -> list[HistoricoResumo]:
        """Lista o histórico de alterações do sistema."""
        return relatorio_service.listar_historico(self.usuario_logado, entidade, limite)

    def listar_log_erros(self, limite: int = 200) -> list[LogErroResumo]:
        """Lista os erros registrados pelo sistema."""
        return relatorio_service.listar_log_erros(self.usuario_logado, limite)

    def listar_saldos_em_aberto(self) -> list[SaldoClienteResumo]:
        """Lista os clientes com saldo em aberto."""
        return relatorio_service.listar_saldos_em_aberto(self.usuario_logado)

    def exportar_saldos_em_aberto_csv(self, caminho_arquivo: str) -> None:
        """Exporta o relatório de saldo em aberto para CSV."""
        relatorio_service.exportar_saldos_em_aberto_csv(self.usuario_logado, caminho_arquivo)

    def exportar_saldos_em_aberto_xlsx(self, caminho_arquivo: str) -> None:
        """Exporta o relatório de saldo em aberto para uma planilha Excel formatada."""
        relatorio_service.exportar_saldos_em_aberto_xlsx(self.usuario_logado, caminho_arquivo)

    def listar_saldos_em_atraso(self, dias_atraso: int = 30) -> list[SaldoAtrasoResumo]:
        """Lista os clientes com saldo em aberto há mais de ``dias_atraso`` dias."""
        return relatorio_service.listar_saldos_em_atraso(self.usuario_logado, dias_atraso)
