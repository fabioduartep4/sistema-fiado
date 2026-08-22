-- provisionar_banco.sql
--
-- Prepara um servidor PostgreSQL NOVO para o Sistema de Gestao de Fiado:
-- cria o usuario e o banco de dados do sistema (se ainda nao existirem) e
-- garante que o schema "public" existe, com as permissoes certas para o
-- usuario do sistema. Depois disso, o proprio SistemaFiado.exe cria todas
-- as tabelas sozinho, na primeira vez que abrir (ver app/database/migrar.py).
--
-- Nao precisa ser rodado em cada computador — só uma vez por servidor
-- PostgreSQL novo. Computadores que só vão se conectar a um servidor que
-- outros computadores da loja já usam não precisam disso.
--
-- Seguro rodar mais de uma vez (idempotente): só cria o que ainda não
-- existir, nunca apaga nada.
--
-- Normalmente chamado por preparar_banco.bat (que já passa as variáveis
-- certas, lidas do .env). Para rodar manualmente:
--   psql -h HOST -p PORTA -U postgres -d postgres ^
--        -v dbname=fiado_db -v dbuser=fiado_user -v dbpassword=SENHA ^
--        -v ON_ERROR_STOP=1 -f provisionar_banco.sql

SELECT 'CREATE ROLE ' || quote_ident(:'dbuser') || ' LOGIN PASSWORD ' || quote_literal(:'dbpassword')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'dbuser')
\gexec

SELECT 'CREATE DATABASE ' || quote_ident(:'dbname') || ' OWNER ' || quote_ident(:'dbuser')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'dbname')
\gexec

GRANT ALL PRIVILEGES ON DATABASE :"dbname" TO :"dbuser";

\connect :dbname

-- O schema "public" normalmente já vem em todo banco novo, mas recriamos
-- aqui por segurança (mesmo problema que já apareceu antes: banco sem
-- "public", causando o erro "no schema has been selected to create in").
CREATE SCHEMA IF NOT EXISTS public AUTHORIZATION :"dbuser";
GRANT ALL ON SCHEMA public TO :"dbuser";
ALTER ROLE :"dbuser" IN DATABASE :"dbname" SET search_path TO public;

\echo 'Banco de dados preparado com sucesso — pode abrir o SistemaFiado.exe agora.'
