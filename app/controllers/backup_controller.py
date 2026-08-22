"""Controller de backup.

Faz a ponte entre a tela Backup (``app.views.backup_view``) e os serviços
de backup e configuração (``app.services.backup_service``,
``app.services.configuracao_service``).
"""

from __future__ import annotations

from typing import Optional

from app.services import backup_service, configuracao_service
from app.services.auth_service import UsuarioAutenticado
from app.services.backup_service import BackupResultado


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
