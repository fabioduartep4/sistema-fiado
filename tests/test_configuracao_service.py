"""Testes de integração do serviço de configurações globais.

Como estas são configurações globais (uma única linha por chave,
compartilhada por toda a rede), a fixture ``_preservar_configuracoes``
salva os valores atuais e os restaura ao final de cada teste que os
altera — sem isso, os testes mudariam permanentemente a configuração real
do banco usado.

Gravam de verdade no banco configurado em ``.env``. Só rodam com
``RODAR_TESTES_INTEGRACAO=1`` (ver ``tests/conftest.py``).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.database.connection import session_scope
from app.repositories import configuracao_repository
from app.services import configuracao_service, usuario_service
from app.services.configuracao_service import ModoDataPadrao, ModoTema
from app.services.usuario_service import PermissaoNegadaError

pytestmark = pytest.mark.integration

_CHAVES_GLOBAIS = [
    configuracao_service.CHAVE_MODO_DATA_PADRAO,
    configuracao_service.CHAVE_PASTA_BACKUP,
    configuracao_service.CHAVE_PASTA_XML,
    configuracao_service.CHAVE_DATA_ULTIMO_BACKUP_AUTOMATICO,
    configuracao_service.CHAVE_TEMA,
]


@pytest.fixture
def _preservar_configuracoes():
    with session_scope() as session:
        originais = {
            chave: (
                configuracao.valor
                if (configuracao := configuracao_repository.buscar_por_chave(session, chave))
                else None
            )
            for chave in _CHAVES_GLOBAIS
        }

    yield

    with session_scope() as session:
        for chave, valor in originais.items():
            if valor is not None:
                configuracao_repository.definir(session, chave, valor)


def _criar_funcionario_teste(usuario_admin_teste):
    from app.models.usuario import PerfilUsuario
    from app.services import auth_service

    login = f"teste_func_config_{uuid.uuid4().hex[:10]}"
    funcionario = usuario_service.criar_usuario(
        usuario_admin_teste, "Funcionário de Teste Config", login, "senha-func-123",
        PerfilUsuario.FUNCIONARIO,
    )
    usuario_funcionario = auth_service.autenticar(login, "senha-func-123")
    return funcionario, usuario_funcionario


def test_funcionario_nao_pode_alterar_modo_data_padrao(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        configuracao_service.definir_modo_data_padrao(usuario_funcionario, ModoDataPadrao.DIA_ATUAL)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_definir_e_obter_modo_data_padrao(usuario_admin_teste, _preservar_configuracoes) -> None:
    configuracao_service.definir_modo_data_padrao(usuario_admin_teste, ModoDataPadrao.DIA_ATUAL)
    assert configuracao_service.obter_modo_data_padrao() == ModoDataPadrao.DIA_ATUAL

    configuracao_service.definir_modo_data_padrao(usuario_admin_teste, ModoDataPadrao.DIA_ANTERIOR)
    assert configuracao_service.obter_modo_data_padrao() == ModoDataPadrao.DIA_ANTERIOR


def test_definir_pasta_backup_em_branco_e_rejeitada(usuario_admin_teste) -> None:
    with pytest.raises(ValueError):
        configuracao_service.definir_pasta_backup(usuario_admin_teste, "   ")


def test_definir_e_obter_pasta_backup(usuario_admin_teste, _preservar_configuracoes, tmp_path) -> None:
    nova_pasta = str(tmp_path / "backups_teste")
    configuracao_service.definir_pasta_backup(usuario_admin_teste, nova_pasta)
    assert configuracao_service.obter_pasta_backup() == nova_pasta


def test_definir_pasta_xml_em_branco_e_rejeitada(usuario_admin_teste) -> None:
    with pytest.raises(ValueError):
        configuracao_service.definir_pasta_xml(usuario_admin_teste, "")


def test_definir_e_obter_pasta_xml(usuario_admin_teste, _preservar_configuracoes, tmp_path) -> None:
    nova_pasta = str(tmp_path / "xmls_teste")
    configuracao_service.definir_pasta_xml(usuario_admin_teste, nova_pasta)
    assert configuracao_service.obter_pasta_xml() == nova_pasta


def test_definir_e_obter_data_ultimo_backup_automatico(_preservar_configuracoes) -> None:
    data_teste = date(2026, 1, 15)
    configuracao_service.definir_data_ultimo_backup_automatico(data_teste)
    assert configuracao_service.obter_data_ultimo_backup_automatico() == data_teste


def test_obter_tema_sem_configuracao_retorna_claro_por_padrao(_preservar_configuracoes) -> None:
    with session_scope() as session:
        configuracao = configuracao_repository.buscar_por_chave(
            session, configuracao_service.CHAVE_TEMA
        )
        if configuracao is not None:
            session.delete(configuracao)

    assert configuracao_service.obter_tema() == ModoTema.CLARO


def test_funcionario_nao_pode_alterar_tema(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        configuracao_service.definir_tema(usuario_funcionario, ModoTema.ESCURO)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_definir_e_obter_tema(usuario_admin_teste, _preservar_configuracoes) -> None:
    configuracao_service.definir_tema(usuario_admin_teste, ModoTema.ESCURO)
    assert configuracao_service.obter_tema() == ModoTema.ESCURO

    configuracao_service.definir_tema(usuario_admin_teste, ModoTema.CLARO)
    assert configuracao_service.obter_tema() == ModoTema.CLARO
