"""Testes de integração de autenticação e checagens de permissão.

Gravam de verdade no banco configurado em ``.env``. Só rodam com
``RODAR_TESTES_INTEGRACAO=1`` (ver ``tests/conftest.py``).
"""

from __future__ import annotations

import uuid

import pytest

from app.services import auth_service, cliente_service, usuario_service
from app.services.usuario_service import PermissaoNegadaError

pytestmark = pytest.mark.integration


def test_autenticar_com_senha_errada_levanta_erro(usuario_admin_teste) -> None:
    with pytest.raises(auth_service.CredenciaisInvalidasError):
        auth_service.autenticar(usuario_admin_teste.login, "senha-completamente-errada")


def test_autenticar_com_login_inexistente_levanta_erro() -> None:
    with pytest.raises(auth_service.CredenciaisInvalidasError):
        auth_service.autenticar("login-que-nao-existe-de-jeito-nenhum", "qualquer-senha")


def test_autenticar_com_sucesso_retorna_dados_do_usuario(usuario_admin_teste, senha_usuario_teste) -> None:
    resultado = auth_service.autenticar(usuario_admin_teste.login, senha_usuario_teste)
    assert resultado.login == usuario_admin_teste.login
    assert resultado.eh_administrador is True


def test_funcionario_nao_pode_excluir_cliente(usuario_admin_teste) -> None:
    """Confirma a correção de permissão aplicada na etapa 9."""
    from app.models.usuario import PerfilUsuario

    login = f"teste_func_permissao_{uuid.uuid4().hex[:10]}"
    funcionario = usuario_service.criar_usuario(
        usuario_admin_teste, "Funcionário de Teste", login, "senha-func-123",
        PerfilUsuario.FUNCIONARIO,
    )
    usuario_funcionario_autenticado = auth_service.autenticar(login, "senha-func-123")

    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Permissao Exclusao", [], [], []
    )

    with pytest.raises(PermissaoNegadaError):
        cliente_service.excluir_cliente(usuario_funcionario_autenticado, cliente.id)

    # limpeza (com o admin, que tem permissão)
    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)
    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_funcionario_nao_pode_gerenciar_usuarios(usuario_admin_teste) -> None:
    from app.models.usuario import PerfilUsuario

    login = f"teste_func_permissao2_{uuid.uuid4().hex[:10]}"
    funcionario = usuario_service.criar_usuario(
        usuario_admin_teste, "Funcionário de Teste 2", login, "senha-func-123",
        PerfilUsuario.FUNCIONARIO,
    )
    usuario_funcionario_autenticado = auth_service.autenticar(login, "senha-func-123")

    with pytest.raises(PermissaoNegadaError):
        usuario_service.listar_usuarios(usuario_funcionario_autenticado)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_login_e_logout_sao_registrados_no_historico(usuario_admin_teste, senha_usuario_teste) -> None:
    from app.services import relatorio_service

    auth_service.autenticar(usuario_admin_teste.login, senha_usuario_teste)
    auth_service.encerrar_sessao(usuario_admin_teste)

    historico = relatorio_service.listar_historico(usuario_admin_teste, entidade="Usuario", limite=50)
    acoes_deste_usuario = [
        h.acao for h in historico if h.entidade_id == usuario_admin_teste.id
    ]
    assert "login" in acoes_deste_usuario
    assert "logout" in acoes_deste_usuario
