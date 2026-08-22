@echo off
setlocal enabledelayedexpansion

echo ================================================
echo  Sistema de Fiado - Preparar banco de dados
echo ================================================
echo.
echo Use isto SOMENTE ao configurar um servidor PostgreSQL NOVO, que ainda
echo nao tem o banco do sistema.
echo.
echo Se este computador so vai se CONECTAR a um servidor que os outros
echo computadores da loja ja usam, NAO rode isso - so configure o .env com
echo os mesmos dados dos outros computadores e abra o SistemaFiado.exe
echo direto (ele so confere se esta tudo atualizado, nao mexe em nada).
echo.
pause

if not exist ".env" (
    echo.
    echo ERRO: arquivo .env nao encontrado nesta pasta.
    echo Copie .env.example para .env e preencha antes de continuar.
    pause
    exit /b 1
)

if not exist "provisionar_banco.sql" (
    echo.
    echo ERRO: provisionar_banco.sql nao encontrado nesta pasta.
    pause
    exit /b 1
)

set "DB_HOST="
set "DB_PORT="
set "DB_NAME="
set "DB_USER="
set "DB_PASSWORD="

for /f "usebackq tokens=1* delims==" %%A in (".env") do (
    if "%%A"=="DB_HOST" set "DB_HOST=%%B"
    if "%%A"=="DB_PORT" set "DB_PORT=%%B"
    if "%%A"=="DB_NAME" set "DB_NAME=%%B"
    if "%%A"=="DB_USER" set "DB_USER=%%B"
    if "%%A"=="DB_PASSWORD" set "DB_PASSWORD=%%B"
)

if "%DB_HOST%%DB_PORT%%DB_NAME%%DB_USER%%DB_PASSWORD%"=="" (
    echo.
    echo ERRO: nao consegui ler os dados de conexao do .env. Confira se as
    echo linhas DB_HOST, DB_PORT, DB_NAME, DB_USER e DB_PASSWORD estao
    echo preenchidas.
    pause
    exit /b 1
)

echo.
echo Servidor:        %DB_HOST%:%DB_PORT%
echo Banco a criar:    %DB_NAME%
echo Usuario a criar:  %DB_USER%
echo.

set "PSQL_EXE="
where psql >nul 2>nul
if errorlevel 1 (
    for /d %%D in ("C:\Program Files\PostgreSQL\*") do set "PSQL_EXE=%%D\bin\psql.exe"
    if not defined PSQL_EXE (
        echo ERRO: psql.exe nao encontrado no PATH nem em
        echo "C:\Program Files\PostgreSQL\*". Instale o PostgreSQL neste
        echo servidor primeiro, ou adicione o psql ao PATH, e rode de novo.
        pause
        exit /b 1
    )
) else (
    set "PSQL_EXE=psql"
)

set /p PGADMIN_USER=Usuario administrador do PostgreSQL (Enter para "postgres"):
if "%PGADMIN_USER%"=="" set "PGADMIN_USER=postgres"

echo.
echo Sera solicitada a senha do usuario administrador "%PGADMIN_USER%" a seguir
echo (a senha definida na instalacao do PostgreSQL nesse servidor).
echo.

"%PSQL_EXE%" -h %DB_HOST% -p %DB_PORT% -U %PGADMIN_USER% -d postgres ^
    -v dbname=%DB_NAME% -v dbuser=%DB_USER% -v dbpassword=%DB_PASSWORD% ^
    -v ON_ERROR_STOP=1 -f provisionar_banco.sql

if errorlevel 1 (
    echo.
    echo Nao foi possivel preparar o banco - veja a mensagem de erro acima.
    pause
    exit /b 1
)

echo.
echo ================================================
echo  Banco preparado com sucesso!
echo ================================================
echo.
echo PROXIMO PASSO: o banco ainda nao tem nenhum usuario cadastrado - sem
echo isso, ninguem consegue logar no sistema. Rode CriarUsuarioAdmin.exe
echo para criar o primeiro usuario Administrador (ele tambem cria as
echo tabelas do banco automaticamente, se ainda nao existirem).
echo.
set /p ABRIR=Rodar CriarUsuarioAdmin.exe agora? (S/N):
if /i "%ABRIR%"=="S" start "" "CriarUsuarioAdmin.exe"

pause
exit /b 0
