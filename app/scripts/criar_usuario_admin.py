"""Script utilitário: cria (ou recria a senha de) um usuário administrador.

Necessário apenas para o primeiro acesso ao sistema, já que ainda não
existe uma tela de gerenciamento de usuários (isso pode ser adicionado em
uma etapa futura, se desejado). Depois de ter ao menos um Administrador
cadastrado, a criação de novos usuários poderá ser feita pela própria
interface.

Uso (rodando a partir do código-fonte):
    python -m app.scripts.criar_usuario_admin

Também é empacotado como um executável próprio (``CriarUsuarioAdmin.exe``,
ver ``fiado.spec``), para não depender de Python instalado num computador
novo — só rodar o .exe uma vez, antes de abrir o SistemaFiado.exe pela
primeira vez. Garante o esquema do banco (cria as tabelas se ainda não
existirem) antes de criar o usuário, então pode ser o primeiro passo,
mesmo num banco vazio.
"""

from __future__ import annotations

import getpass

from app.database.connection import session_scope
from app.database.migrar import aplicar_esquema_banco
from app.models.usuario import PerfilUsuario
from app.repositories import usuario_repository
from app.services.auth_service import gerar_hash_senha


def main() -> None:
    """Coleta os dados no terminal e cria o usuário administrador."""
    print("=== Criação de usuário Administrador ===")

    try:
        aplicar_esquema_banco()
    except Exception as erro:
        print(f"Não foi possível preparar o banco de dados: {erro}")
        print("Confira os dados de conexão no .env antes de tentar de novo.")
        return

    nome = input("Nome completo: ").strip()
    login = input("Login: ").strip()
    senha = getpass.getpass("Senha: ")
    confirmacao = getpass.getpass("Confirme a senha: ")

    if senha != confirmacao:
        print("As senhas não conferem. Operação cancelada.")
        return

    if not nome or not login or not senha:
        print("Nome, login e senha são obrigatórios. Operação cancelada.")
        return

    with session_scope() as session:
        existente = usuario_repository.buscar_por_login(session, login)
        if existente is not None:
            print(f"Já existe um usuário ativo com o login '{login}'. Operação cancelada.")
            return

        usuario_repository.criar_usuario(
            session,
            nome=nome,
            login=login,
            senha_hash=gerar_hash_senha(senha),
            perfil=PerfilUsuario.ADMINISTRADOR,
        )

    print(f"Usuário administrador '{login}' criado com sucesso.")


if __name__ == "__main__":
    main()
