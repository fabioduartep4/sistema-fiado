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


def test_backup_manual_tambem_vai_para_a_pasta_da_nuvem(usuario_admin_teste, tmp_path, monkeypatch):
    from app.services import nuvem_service

    monkeypatch.setattr(nuvem_service, "_ARQUIVO_CONFIG", tmp_path / "config_local.json")
    nuvem = tmp_path / "drive"
    nuvem.mkdir()
    nuvem_service.definir_pasta(usuario_admin_teste, str(nuvem))

    resultado = backup_service.fazer_backup_manual(usuario_admin_teste, str(tmp_path / "local"))

    copia = nuvem / Path(resultado.caminho_arquivo).name
    assert copia.exists()
    assert copia.read_bytes() == Path(resultado.caminho_arquivo).read_bytes()
    assert nuvem_service.obter_status().ultimo_erro is None


def test_backup_continua_valendo_se_a_nuvem_falhar(usuario_admin_teste, tmp_path, monkeypatch):
    from app.services import nuvem_service

    monkeypatch.setattr(nuvem_service, "_ARQUIVO_CONFIG", tmp_path / "config_local.json")
    nuvem = tmp_path / "drive"
    nuvem.mkdir()
    nuvem_service.definir_pasta(usuario_admin_teste, str(nuvem))
    nuvem.rmdir()  # o Google Drive não está aberto

    resultado = backup_service.fazer_backup_manual(usuario_admin_teste, str(tmp_path / "local"))

    assert Path(resultado.caminho_arquivo).exists()  # o backup local foi feito normalmente
    assert nuvem_service.obter_status().ultimo_erro


def test_backup_de_hoje_feito_por_outro_computador_ainda_vai_para_a_nuvem(
    usuario_admin_teste, tmp_path, monkeypatch
):
    """O backup diário já foi feito (data de hoje gravada no banco), mas este
    computador, que tem a pasta da nuvem, ainda não mandou nada hoje."""
    from datetime import date

    from app.services import configuracao_service, nuvem_service

    monkeypatch.setattr(nuvem_service, "_ARQUIVO_CONFIG", tmp_path / "config_local.json")
    nuvem = tmp_path / "drive"
    nuvem.mkdir()
    pasta_original = configuracao_service.obter_pasta_backup()
    data_original = configuracao_service.obter_data_ultimo_backup_automatico()
    configuracao_service.definir_pasta_backup(usuario_admin_teste, str(tmp_path / "local"))
    configuracao_service.definir_data_ultimo_backup_automatico(date.today())
    try:
        # Sem a nuvem configurada: nada a fazer, como sempre.
        assert backup_service.verificar_e_executar_backup_automatico_se_necessario() is None
        assert not (tmp_path / "local").exists() or not list((tmp_path / "local").glob("*.zip"))

        nuvem_service.definir_pasta(usuario_admin_teste, str(nuvem))
        resultado = backup_service.verificar_e_executar_backup_automatico_se_necessario()

        assert resultado is not None  # não havia backup local de hoje: gerou um
        assert (nuvem / Path(resultado.caminho_arquivo).name).exists()

        # Já mandou hoje: não gera nem copia de novo.
        assert backup_service.verificar_e_executar_backup_automatico_se_necessario() is None
        assert len(list(nuvem.glob("*.zip"))) == 1
    finally:
        configuracao_service.definir_pasta_backup(usuario_admin_teste, pasta_original)
        if data_original is not None:
            configuracao_service.definir_data_ultimo_backup_automatico(data_original)


@pytest.fixture
def _backup_em_pasta_temporaria(usuario_admin_teste, tmp_path, monkeypatch):
    """Pasta de backup e pasta da nuvem temporárias; ao final, desfaz as
    datas gravadas no banco para não interferir nos outros testes."""
    from datetime import date

    from app.services import configuracao_service, nuvem_service

    monkeypatch.setattr(nuvem_service, "_ARQUIVO_CONFIG", tmp_path / "config_local.json")
    pasta_original = configuracao_service.obter_pasta_backup()
    data_automatico_original = configuracao_service.obter_data_ultimo_backup_automatico()
    configuracao_service.definir_pasta_backup(usuario_admin_teste, str(tmp_path / "local"))
    yield tmp_path
    configuracao_service.definir_pasta_backup(usuario_admin_teste, pasta_original)
    configuracao_service.definir_data_ultimo_backup_agendado(date(2000, 1, 1))  # "nunca rodou"
    configuracao_service.definir_data_ultimo_backup_automatico(data_automatico_original or date(2000, 1, 1))


def test_backup_agendado_faz_um_por_dia_e_vai_para_a_nuvem(usuario_admin_teste, _backup_em_pasta_temporaria):
    from app.services import nuvem_service

    nuvem = _backup_em_pasta_temporaria / "drive"
    nuvem.mkdir()
    nuvem_service.definir_pasta(usuario_admin_teste, str(nuvem))

    primeiro = backup_service.fazer_backup_agendado()
    assert primeiro is not None
    assert Path(primeiro.caminho_arquivo).parent == _backup_em_pasta_temporaria / "local"
    assert (nuvem / Path(primeiro.caminho_arquivo).name).exists()

    # O agendamento pode disparar de novo no mesmo dia (horário marcado + computador que ligou).
    assert backup_service.fazer_backup_agendado() is None
    assert len(list((_backup_em_pasta_temporaria / "local").glob("*.zip"))) == 1


def test_outros_computadores_nao_fazem_backup_enquanto_o_servidor_faz(_backup_em_pasta_temporaria):
    from datetime import date, timedelta

    from app.services import configuracao_service

    hoje = date.today()
    configuracao_service.definir_data_ultimo_backup_automatico(date(2000, 1, 1))  # "hoje ainda não foi feito"

    # Servidor fez o backup agendado ontem: quem abre o sistema hoje cedo não faz outro.
    configuracao_service.definir_data_ultimo_backup_agendado(hoje - timedelta(days=1))
    assert backup_service.servidor_esta_fazendo_o_backup() is True
    assert backup_service.verificar_e_executar_backup_automatico_se_necessario() is None
    assert not list((_backup_em_pasta_temporaria / "local").glob("*.zip"))

    # Servidor parado há dias (agendamento quebrou): os outros reassumem.
    configuracao_service.definir_data_ultimo_backup_agendado(
        hoje - timedelta(days=backup_service.DIAS_DE_TOLERANCIA_DO_AGENDAMENTO + 1)
    )
    assert backup_service.servidor_esta_fazendo_o_backup() is False
    assert backup_service.verificar_e_executar_backup_automatico_se_necessario() is not None
    assert len(list((_backup_em_pasta_temporaria / "local").glob("*.zip"))) == 1


def test_programa_do_backup_agendado_devolve_codigo_de_saida(_backup_em_pasta_temporaria, monkeypatch):
    from app.scripts import backup_agendado

    assert backup_agendado.main([]) == 0  # fez o backup
    assert backup_agendado.main([]) == 0  # já feito hoje: também é sucesso
    assert backup_agendado.main(["--agora"]) == 0
    assert len(list((_backup_em_pasta_temporaria / "local").glob("*.zip"))) >= 1

    def _falhar(**_kwargs):
        raise backup_service.BackupError("pg_dump falhou")

    monkeypatch.setattr(backup_service, "fazer_backup_agendado", _falhar)
    assert backup_agendado.main([]) == 1  # falha vira código 1, sem derrubar o programa
