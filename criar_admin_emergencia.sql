-- criar_admin_emergencia.sql
--
-- Cria o primeiro usuário Administrador direto no banco, via SQL — usar
-- SÓ quando o CriarUsuarioAdmin.exe não roda (ex.: bloqueado pelo Windows
-- SmartScreen/Defender como app não reconhecido, algo comum em .exe do
-- PyInstaller sem assinatura digital).
--
-- Rode via psql ou pgAdmin, conectado no banco "fiado_db" (ou o nome que
-- você configurou) do servidor de destino:
--   psql -h HOST -p PORTA -U fiado_user -d fiado_db -f criar_admin_emergencia.sql
--
-- O login criado abaixo é "admin" com a senha temporária "admin123" —
-- TROQUE a senha assim que logar pela primeira vez, pela tela "Usuários"
-- do próprio sistema (Administrador > Usuários > Redefinir senha).
--
-- Se quiser um login/senha diferente do padrão, troque 'admin' abaixo e
-- gere um hash novo rodando isto (numa máquina que tenha o projeto e o
-- venv instalados, ex.: onde o .exe foi gerado):
--   venv\Scripts\python.exe -c "from app.services.auth_service import gerar_hash_senha; print(gerar_hash_senha('SUA_SENHA_AQUI'))"
-- e cole o resultado no lugar do hash abaixo.

INSERT INTO usuarios (id, ativo, criado_em, atualizado_em, nome, login, senha_hash, perfil)
VALUES (
    gen_random_uuid(),
    true,
    now(),
    now(),
    'Administrador',
    'admin',
    '$argon2id$v=19$m=65536,t=3,p=4$vebLl5WPFGBrH4hYOQcb8Q$5WfySyEZrkXUoamJIzUOGYKrg7nwywDaxUYJXoMFd2Q',
    'ADMINISTRADOR'
)
ON CONFLICT (login) DO NOTHING;

\echo 'Usuario "admin" (senha temporaria "admin123") criado - troque a senha apos o primeiro login.'
