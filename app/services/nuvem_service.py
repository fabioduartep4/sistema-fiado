"""Cópia dos backups para a nuvem, por meio de uma pasta sincronizada.

O sistema não fala com o Google: ele só copia cada backup para uma pasta
que o aplicativo "Google Drive para computador" (ou equivalente) mantém
sincronizada — quem envia para a nuvem é esse aplicativo. Por isso não há
senha nem chave de acesso guardada aqui.

A pasta é uma configuração **deste computador**, não do sistema: fica num
arquivo local (``app/config_local.json``, ao lado dos backups e dos logs),
não no banco compartilhado. Só a máquina que tem o Google Drive instalado
tem essa pasta; as outras simplesmente não copiam nada.

Nada aqui interrompe um backup: se a cópia falhar (pasta sumiu, Drive
fechado, disco cheio), o backup local continua valendo e o erro fica
registrado para aparecer na tela Backups.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.config.logging_config import logger
from app.config.settings import settings
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import PermissaoNegadaError

# Quantos backups ficam na pasta da nuvem; os mais antigos são apagados dela.
QUANTIDADE_MANTIDA_NA_NUVEM = 30

_PADRAO_ARQUIVOS = "backup_fiado_*.zip"
_ARQUIVO_CONFIG: Path = settings.base_dir / "app" / "config_local.json"


@dataclass(frozen=True)
class StatusNuvem:
    """Situação da cópia na nuvem neste computador, para a tela Backups.

    Attributes:
        pasta: Pasta sincronizada configurada, ou ``None`` se desativada.
        ultima_copia: Quando um backup foi copiado para ela pela última vez.
        ultimo_erro: Motivo da última falha de cópia; ``None`` se a última deu certo.
    """

    pasta: Optional[str]
    ultima_copia: Optional[datetime]
    ultimo_erro: Optional[str]


def _ler() -> dict:
    try:
        return json.loads(_ARQUIVO_CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.exception("Não foi possível ler %s; a cópia na nuvem fica desativada.", _ARQUIVO_CONFIG)
        return {}


def _gravar(dados: dict) -> None:
    _ARQUIVO_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _ARQUIVO_CONFIG.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def obter_status() -> StatusNuvem:
    """Lê a configuração e o resultado da última cópia neste computador."""
    dados = _ler()
    ultima = dados.get("ultima_copia")
    return StatusNuvem(
        pasta=dados.get("pasta") or None,
        ultima_copia=datetime.fromisoformat(ultima) if ultima else None,
        ultimo_erro=dados.get("ultimo_erro") or None,
    )


def definir_pasta(usuario_logado: UsuarioAutenticado, pasta: Optional[str]) -> None:
    """Define (ou desativa, com ``None``) a pasta sincronizada deste computador.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se a pasta informada não existir.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem alterar configurações do sistema.")

    pasta = (pasta or "").strip() or None
    if pasta is not None and not Path(pasta).is_dir():
        raise ValueError(f"A pasta não existe: {pasta}")

    # Troca de pasta zera o histórico: a última cópia/erro eram da pasta anterior.
    _gravar({"pasta": pasta} if pasta else {})


def falta_copia_de_hoje() -> bool:
    """True se este computador copia para a nuvem e ainda não há backup de hoje lá.

    Com a pasta inacessível (Drive fechado, pendrive fora) também é True:
    a próxima tentativa registra o erro, que aparece na tela Backups.
    """
    pasta = obter_status().pasta
    if pasta is None:
        return False
    prefixo_de_hoje = f"backup_fiado_{date.today().strftime('%Y%m%d')}_"
    try:
        return not any(Path(pasta).glob(f"{prefixo_de_hoje}*.zip"))
    except OSError:
        return True


def copiar_para_nuvem(caminho_backup: str | Path) -> bool:
    """Copia um backup para a pasta sincronizada e apaga dela os mais antigos.

    Nunca levanta exceção: devolve se copiou, e registra o resultado para a
    tela Backups. Sem pasta configurada neste computador, não faz nada.

    Args:
        caminho_backup: Arquivo ``.zip`` de backup já gerado.

    Returns:
        True se o arquivo foi copiado.
    """
    dados = _ler()
    pasta = dados.get("pasta")
    if not pasta:
        return False

    origem, destino = Path(caminho_backup), Path(pasta)
    try:
        if not destino.is_dir():
            raise OSError(f"a pasta não está acessível: {pasta}")
        if origem.resolve().parent != destino.resolve():
            # Copia com outro nome e só renomeia no fim: o aplicativo de
            # sincronização nunca enxerga (e envia) um arquivo pela metade.
            temporario = destino / f"{origem.name}.copiando"
            shutil.copy2(origem, temporario)
            temporario.replace(destino / origem.name)
        _apagar_antigos(destino)
    except OSError as exc:
        logger.exception("Falha ao copiar o backup %s para a nuvem (%s).", origem.name, pasta)
        dados["ultimo_erro"] = str(exc)
        _gravar_sem_falhar(dados)
        return False

    dados["ultima_copia"] = datetime.now().isoformat(timespec="seconds")
    dados.pop("ultimo_erro", None)
    _gravar_sem_falhar(dados)
    return True


def _gravar_sem_falhar(dados: dict) -> None:
    try:
        _gravar(dados)
    except OSError:
        logger.exception("Não foi possível gravar %s.", _ARQUIVO_CONFIG)


def _apagar_antigos(pasta: Path) -> None:
    """Mantém na pasta só os ``QUANTIDADE_MANTIDA_NA_NUVEM`` backups mais recentes.

    O nome do arquivo traz a data e a hora, então a ordem alfabética é a
    cronológica. Só mexe em arquivos de backup do sistema (``backup_fiado_*.zip``).
    """
    arquivos = sorted(pasta.glob(_PADRAO_ARQUIVOS), key=lambda arquivo: arquivo.name)
    for antigo in arquivos[:-QUANTIDADE_MANTIDA_NA_NUVEM]:
        antigo.unlink()
