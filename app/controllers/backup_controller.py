"""Controller de backup.

Faz a ponte entre a tela Backup (``app.views.backup_view``) e os serviços
de backup e configuração (``app.services.backup_service``,
``app.services.configuracao_service``).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from app.services import backup_service, configuracao_service, nuvem_service
from app.services.auth_service import UsuarioAutenticado
from app.services.backup_service import BackupResultado
from app.services.nuvem_service import StatusNuvem


class BackupController:
    """Controlador da tela de Backup.

    Attributes:
        usuario_logado: Usuário autenticado que está operando a tela
            (as ações desta tela exigem perfil Administrador).
    """

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        self.usuario_logado = usuario_logado

    def obter_pasta_backup(self) -> str:
        """Obtém a pasta configurada para os backups."""
        return configuracao_service.obter_pasta_backup()

    def definir_pasta_backup(self, pasta: str) -> None:
        """Define a pasta onde os backups serão salvos."""
        configuracao_service.definir_pasta_backup(self.usuario_logado, pasta)

    def fazer_backup_manual(self, pasta_destino: Optional[str] = None) -> BackupResultado:
        """Executa um backup manual imediato."""
        return backup_service.fazer_backup_manual(self.usuario_logado, pasta_destino)

    def restaurar_backup(self, caminho_arquivo_zip: str) -> None:
        """Restaura o banco a partir de um arquivo de backup."""
        backup_service.restaurar_backup(self.usuario_logado, caminho_arquivo_zip)

    def status_nuvem(self) -> StatusNuvem:
        """Situação da cópia na nuvem neste computador."""
        return nuvem_service.obter_status()

    def definir_pasta_nuvem(self, pasta: Optional[str]) -> None:
        """Define (ou desativa, com ``None``) a pasta sincronizada com a nuvem deste computador."""
        nuvem_service.definir_pasta(self.usuario_logado, pasta)

    def data_ultimo_backup_agendado(self) -> Optional[date]:
        """Data do último backup feito pelo agendamento do servidor (None se nunca rodou)."""
        return configuracao_service.obter_data_ultimo_backup_agendado()

    def servidor_esta_fazendo_o_backup(self) -> bool:
        """True se o backup agendado do servidor rodou nos últimos dias."""
        return backup_service.servidor_esta_fazendo_o_backup()

