"""Testes de app.services.nuvem_service — não tocam no banco nem em Qt.

A "nuvem" aqui é só uma pasta temporária: o sistema copia os backups para
uma pasta sincronizada, e quem envia de verdade é o aplicativo do Google.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.models.usuario import PerfilUsuario
from app.services import nuvem_service
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import PermissaoNegadaError

_ADMIN = UsuarioAutenticado(id="1", nome="Admin", login="admin", perfil=PerfilUsuario.ADMINISTRADOR)
_FUNCIONARIO = UsuarioAutenticado(id="2", nome="Func", login="func", perfil=PerfilUsuario.FUNCIONARIO)


@pytest.fixture(autouse=True)
def _config_local_temporaria(tmp_path, monkeypatch):
    """Cada teste usa o próprio arquivo de configuração local (nunca o do computador)."""
    monkeypatch.setattr(nuvem_service, "_ARQUIVO_CONFIG", tmp_path / "config" / "config_local.json")


def _criar_backup(pasta, nome: str):
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    arquivo.write_bytes(b"conteudo do backup " + nome.encode())
    return arquivo


def _nome_de_hoje(hora: str = "101500") -> str:
    return f"backup_fiado_{date.today().strftime('%Y%m%d')}_{hora}.zip"


def test_sem_pasta_configurada_nao_copia_nada(tmp_path) -> None:
    backup = _criar_backup(tmp_path / "local", _nome_de_hoje())

    assert nuvem_service.copiar_para_nuvem(backup) is False
    assert nuvem_service.falta_copia_de_hoje() is False
    status = nuvem_service.obter_status()
    assert (status.pasta, status.ultima_copia, status.ultimo_erro) == (None, None, None)


def test_copia_o_backup_para_a_pasta_e_registra_quando(tmp_path) -> None:
    nuvem = tmp_path / "drive"
    nuvem.mkdir()
    nuvem_service.definir_pasta(_ADMIN, str(nuvem))
    assert nuvem_service.falta_copia_de_hoje() is True
    backup = _criar_backup(tmp_path / "local", _nome_de_hoje())

    assert nuvem_service.copiar_para_nuvem(backup) is True

    assert (nuvem / backup.name).read_bytes() == backup.read_bytes()
    assert not list(nuvem.glob("*.copiando"))  # nada pela metade para o Drive enviar
    assert nuvem_service.falta_copia_de_hoje() is False
    status = nuvem_service.obter_status()
    assert status.pasta == str(nuvem)
    assert status.ultima_copia is not None and status.ultimo_erro is None


def test_so_administrador_configura_e_a_pasta_precisa_existir(tmp_path) -> None:
    with pytest.raises(PermissaoNegadaError):
        nuvem_service.definir_pasta(_FUNCIONARIO, str(tmp_path))
    with pytest.raises(ValueError):
        nuvem_service.definir_pasta(_ADMIN, str(tmp_path / "nao_existe"))
    assert nuvem_service.obter_status().pasta is None


def test_mantem_so_os_30_backups_mais_recentes_na_nuvem(tmp_path) -> None:
    nuvem = tmp_path / "drive"
    nuvem.mkdir()
    nuvem_service.definir_pasta(_ADMIN, str(nuvem))
    for dia in range(1, 36):  # 35 backups antigos já na nuvem
        _criar_backup(nuvem, f"backup_fiado_202601{dia:02d}_080000.zip" if dia <= 31 else f"backup_fiado_202602{dia - 31:02d}_080000.zip")
    outro_arquivo = _criar_backup(nuvem, "planilha_do_dono.xlsx")
    backup = _criar_backup(tmp_path / "local", _nome_de_hoje())

    assert nuvem_service.copiar_para_nuvem(backup) is True

    restantes = sorted(a.name for a in nuvem.glob("backup_fiado_*.zip"))
    assert len(restantes) == nuvem_service.QUANTIDADE_MANTIDA_NA_NUVEM == 30
    assert restantes[-1] == backup.name  # o novo ficou
    assert "backup_fiado_20260101_080000.zip" not in restantes  # os mais antigos saíram
    assert outro_arquivo.exists()  # só mexe nos backups do sistema


def test_falha_na_copia_nao_levanta_erro_e_fica_registrada(tmp_path) -> None:
    nuvem = tmp_path / "drive"
    nuvem.mkdir()
    nuvem_service.definir_pasta(_ADMIN, str(nuvem))
    backup = _criar_backup(tmp_path / "local", _nome_de_hoje())
    assert nuvem_service.copiar_para_nuvem(backup) is True
    nuvem.joinpath(backup.name).unlink()
    nuvem.rmdir()  # o Google Drive foi fechado / a pasta sumiu

    assert nuvem_service.copiar_para_nuvem(backup) is False

    status = nuvem_service.obter_status()
    assert status.ultimo_erro and "não está acessível" in status.ultimo_erro
    assert status.ultima_copia is not None  # a última que deu certo continua registrada
    assert nuvem_service.falta_copia_de_hoje() is True  # vai tentar de novo

    nuvem.mkdir()  # voltou
    assert nuvem_service.copiar_para_nuvem(backup) is True
    assert nuvem_service.obter_status().ultimo_erro is None


def test_desativar_para_de_copiar(tmp_path) -> None:
    nuvem = tmp_path / "drive"
    nuvem.mkdir()
    nuvem_service.definir_pasta(_ADMIN, str(nuvem))
    nuvem_service.definir_pasta(_ADMIN, None)
    backup = _criar_backup(tmp_path / "local", _nome_de_hoje())

    assert nuvem_service.copiar_para_nuvem(backup) is False
    assert not list(nuvem.iterdir())
    assert nuvem_service.falta_copia_de_hoje() is False


def test_backup_salvo_direto_na_pasta_da_nuvem_nao_e_copiado_sobre_si_mesmo(tmp_path) -> None:
    nuvem = tmp_path / "drive"
    nuvem.mkdir()
    nuvem_service.definir_pasta(_ADMIN, str(nuvem))
    backup = _criar_backup(nuvem, _nome_de_hoje())

    assert nuvem_service.copiar_para_nuvem(backup) is True
    assert backup.read_bytes().startswith(b"conteudo do backup")
