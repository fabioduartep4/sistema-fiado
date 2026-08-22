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

echo [1/4] Criando ambiente virtual (venv), se ainda nao existir...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

echo.
echo [2/4] Instalando dependencias do projeto...
pip install -r requirements.txt
if errorlevel 1 goto erro

echo.
echo [3/4] Instalando o PyInstaller...
pip install pyinstaller
if errorlevel 1 goto erro

echo.
echo [4/4] Gerando o executavel (pode demorar alguns minutos)...
pyinstaller fiado.spec --noconfirm
if errorlevel 1 goto erro

echo.
echo [5/5] Copiando arquivos auxiliares para dist\SistemaFiado...
copy /y .env.example dist\SistemaFiado\ >nul
copy /y preparar_banco.bat dist\SistemaFiado\ >nul
copy /y provisionar_banco.sql dist\SistemaFiado\ >nul
copy /y criar_admin_emergencia.sql dist\SistemaFiado\ >nul

echo.
echo ============================================
echo  Pronto!
echo ============================================
echo Os executaveis estao em dist\SistemaFiado\:
echo  - SistemaFiado.exe        (o programa)
echo  - CriarUsuarioAdmin.exe   (cria o 1o usuario administrador)
echo.
echo PROXIMO PASSO: copie a pasta "dist\SistemaFiado" inteira para o
echo computador de destino. Dentro dela:
echo  - Copie ".env.example" para ".env" e preencha com os dados do
echo    servidor PostgreSQL da rede.
echo  - Se for um servidor PostgreSQL NOVO (ainda sem o banco do sistema):
echo    1) rode "preparar_banco.bat" (cria o banco/usuario/schema)
echo    2) rode "CriarUsuarioAdmin.exe" (cria o 1o login do sistema)
echo    3) abra "SistemaFiado.exe" e logue com o usuario criado
echo  - Se for so mais um computador se conectando a um servidor que os
echo    outros ja usam, pule os passos acima e abra o SistemaFiado.exe direto.
echo.
pause
exit /b 0

:erro
echo.
echo Algo deu errado (veja a mensagem de erro acima). O executavel nao foi gerado.
pause
exit /b 1
