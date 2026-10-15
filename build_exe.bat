@echo off
REM build_exe.bat — gera o executavel (.exe) do Sistema de Gestao de Fiado.
REM Rode este arquivo (duplo clique, ou pelo terminal) de dentro da pasta
REM do projeto (onde ficam requirements.txt e fiado.spec).
REM
REM Pre-requisito: Python 3.13 instalado e no PATH.

echo ============================================
echo  Sistema de Fiado - Gerar executavel (.exe)
echo ============================================
echo.

echo [1/5] Criando ambiente virtual (venv), se ainda nao existir...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

echo.
echo [2/5] Instalando dependencias do projeto...
pip install -r requirements.txt
if errorlevel 1 goto erro

echo.
echo [3/5] Instalando o PyInstaller...
pip install pyinstaller
if errorlevel 1 goto erro

echo.
echo [4/5] Gerando o executavel (pode demorar alguns minutos)...
pyinstaller fiado.spec --noconfirm
if errorlevel 1 goto erro

echo.
echo [5/5] Copiando arquivos auxiliares para dist\SistemaFiado...
copy /y .env.example dist\SistemaFiado\ >nul
copy /y preparar_banco.bat dist\SistemaFiado\ >nul
copy /y provisionar_banco.sql dist\SistemaFiado\ >nul
copy /y criar_admin_emergencia.sql dist\SistemaFiado\ >nul
copy /y atualizar_instalacao.bat dist\SistemaFiado\ >nul
copy /y instalar_backup_agendado.bat dist\SistemaFiado\ >nul
copy /y atualizar.bat dist\SistemaFiado\ >nul
copy /y atualizar.ps1 dist\SistemaFiado\ >nul
REM versao.txt: e por ele que o atualizar.bat sabe qual versao esta instalada.
python -c "from app.versao import VERSAO; print(VERSAO)" > dist\SistemaFiado\versao.txt
if errorlevel 1 goto erro

REM A pasta "build" e so rascunho do PyInstaller: os .exe que ficam la dentro
REM NAO funcionam (falta a DLL do Python). Apaga para ninguem abrir o errado.
if exist build rmdir /s /q build

REM Confere se os arquivos que o sistema le em tempo de execucao entraram no
REM pacote. Sem eles o programa nao consegue preparar o banco (migracoes) e
REM fica sem icone.
set "PACOTE=dist\SistemaFiado\_internal"
if not exist "%PACOTE%\alembic.ini" goto pacote_incompleto
if not exist "%PACOTE%\app\database\migrations\env.py" goto pacote_incompleto
if not exist "%PACOTE%\app\database\migrations\versions\775425f06865_estrutura_inicial.py" goto pacote_incompleto
if not exist "%PACOTE%\app\assets\icon.ico" goto pacote_incompleto

echo.
echo ============================================
echo  Pronto!
echo ============================================
echo Os executaveis estao em dist\SistemaFiado\:
echo  - SistemaFiado.exe        (o programa)
echo  - CriarUsuarioAdmin.exe   (cria o 1o usuario administrador)
echo  - BackupAgendado.exe      (backup diario sem abrir o sistema)
echo.
echo ATENCAO: use SEMPRE os .exe de dentro de dist\SistemaFiado.
echo.
echo PROXIMO PASSO: copie a pasta "dist\SistemaFiado" inteira para o
echo computador de destino. Dentro dela:
echo  - Copie ".env.example" para ".env" e preencha com os dados do
echo    servidor PostgreSQL da rede.
echo  - Se for um servidor PostgreSQL NOVO (ainda sem o banco do sistema):
echo    1) rode "preparar_banco.bat" (cria o banco/usuario/schema)
echo    2) rode "CriarUsuarioAdmin.exe" (cria o 1o login do sistema)
echo    3) abra "SistemaFiado.exe" e logue com o usuario criado
echo  - Se o computador JA tem o sistema instalado (atualizacao): rode
echo    "atualizar_instalacao.bat" e informe a pasta instalada. Nao cole por cima.
echo    Nas proximas vezes, com a versao publicada no GitHub, basta rodar
echo    "atualizar.bat" na pasta instalada: ele baixa e troca sozinho.
echo  - No computador onde o banco fica (servidor): rode
echo    "instalar_backup_agendado.bat" uma vez, para o backup diario rodar sozinho.
echo  - Se for so mais um computador se conectando a um servidor que os
echo    outros ja usam, pule os passos acima e abra o SistemaFiado.exe direto.
echo.
start "" explorer "dist\SistemaFiado"
pause
exit /b 0

:pacote_incompleto
echo.
echo ERRO: o executavel foi gerado INCOMPLETO - faltam as migracoes do banco
echo (_internal\app\database\migrations), o alembic.ini ou o icone.
echo NAO use esta pasta. Confira se a pasta "app\database\migrations" existe no
echo projeto e rode o build_exe.bat de novo.
pause
exit /b 1

:erro
echo.
echo Algo deu errado (veja a mensagem de erro acima). O executavel nao foi gerado.
pause
exit /b 1
