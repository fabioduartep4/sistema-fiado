"""Testes de integração do serviço de backup/restauração.

Gravam de verdade no banco configurado em ``.env`` (fazem backup real via
``pg_dump``). Só rodam com ``RODAR_TESTES_INTEGRACAO=1`` (ver
``tests/conftest.py``).

**Importante**: o caminho de sucesso de ``restaurar_backup`` apaga o schema
``public`` inteiro (``DROP SCHEMA public CASCADE``) antes de restaurar —
por isso, propositalmente, este arquivo testa apenas as validações que
falham *antes* dessa etapa (permissão, arquivo inexistente, zip sem
``.sql``). Executar a restauração de verdade destruiria os dados do banco
configurado, o que não é seguro fazer num teste automatizado.
"""

from __future__ import annotations

import uuid
import zipfile
from pathlib import Path

import pytest

from app.services import backup_service, usuario_service
from app.services.usuario_service import PermissaoNegadaError

pytestmark = pytest.mark.integration


def _criar_funcionario_teste(usuario_admin_teste):
    from app.models.usuario import PerfilUsuario
    from app.services import auth_service

    login = f"teste_func_backup_{uuid.uuid4().hex[:10]}"
    funcionario = usuario_service.criar_usuario(
        usuario_admin_teste, "Funcionário de Teste Backup", login, "senha-func-123",
        PerfilUsuario.FUNCIONARIO,
    )
    usuario_funcionario = auth_service.autenticar(login, "senha-func-123")
    return funcionario, usuario_funcionario


def test_fazer_backup_manual_funcionario_e_rejeitado(usuario_admin_teste, tmp_path):
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        backup_service.fazer_backup_manual(usuario_funcionario, str(tmp_path))

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_fazer_backup_manual_gera_arquivo_zip(usuario_admin_teste, tmp_path):
    resultado = backup_service.fazer_backup_manual(usuario_admin_teste, str(tmp_path))

    caminho = Path(resultado.caminho_arquivo)
    assert caminho.exists()
    assert caminho.suffix == ".zip"
    assert caminho.parent == tmp_path

    with zipfile.ZipFile(caminho) as arquivo_zip:
        nomes = arquivo_zip.namelist()
        assert any(nome.endswith(".sql") for nome in nomes)


def test_restaurar_backup_funcionario_e_rejeitado(usuario_admin_teste, tmp_path):
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        backup_service.restaurar_backup(usuario_funcionario, str(tmp_path / "inexistente.zip"))

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_restaurar_backup_arquivo_inexistente_e_rejeitado(usuario_admin_teste, tmp_path):
    with pytest.raises(ValueError):
        backup_service.restaurar_backup(usuario_admin_teste, str(tmp_path / "nao_existe.zip"))


def test_restaurar_backup_zip_sem_sql_e_rejeitado(usuario_admin_teste, tmp_path):
    caminho_zip = tmp_path / "backup_vazio.zip"
    with zipfile.ZipFile(caminho_zip, "w") as arquivo_zip:
        arquivo_zip.writestr("leia_me.txt", "não é um dump de banco")

    with pytest.raises(ValueError):
        backup_service.restaurar_backup(usuario_admin_teste, str(caminho_zip))


def test_verificar_backup_automatico_nao_roda_duas_vezes_no_mesmo_dia(usuario_admin_teste):
    from datetime import date

    from app.services import configuracao_service

    data_original = configuracao_service.obter_data_ultimo_backup_automatico()
    configuracao_service.definir_data_ultimo_backup_automatico(date.today())

    try:
        resultado = backup_service.verificar_e_executar_backup_automatico_se_necessario()
        assert resultado is None
    finally:
        if data_original is not None:
            configuracao_service.definir_data_ultimo_backup_automatico(data_original)
