@echo off
REM atualizar_instalacao.bat - atualiza uma instalacao existente do Sistema de Fiado.
REM
REM Fica dentro de dist\SistemaFiado (o build_exe.bat copia para la). Rode de
REM la, informando a pasta onde o sistema esta instalado neste computador.
REM
REM O que ele faz, na pasta instalada:
REM  - apaga os programas antigos (os .exe e a pasta _internal inteira);
REM  - copia os novos;
REM  - NAO mexe no ".env" nem na pasta "app" (backups e logs).
REM
REM Isso evita "colar por cima", que mistura arquivos de versoes diferentes e
REM faz o programa parar de abrir (erro "Failed to load Python DLL").
REM
REM Uso opcional sem perguntas:  atualizar_instalacao.bat "C:\caminho\da\instalacao"

setlocal
set "ORIGEM=%~dp0"
if "%ORIGEM:~-1%"=="\" set "ORIGEM=%ORIGEM:~0,-1%"

echo ============================================
echo  Sistema de Fiado - Atualizar instalacao
echo ============================================
echo.

if not exist "%ORIGEM%\SistemaFiado.exe" goto origem_errada
if not exist "%ORIGEM%\_internal" goto origem_errada

set "DESTINO=%~1"
if not "%DESTINO%"=="" goto tem_destino
echo Cole abaixo o caminho da pasta onde o sistema esta instalado
echo (a pasta que tem o SistemaFiado.exe e o arquivo .env) e aperte Enter.
echo.
set /p "DESTINO=Pasta instalada: "
:tem_destino
set "DESTINO=%DESTINO:"=%"
if "%DESTINO%"=="" goto sem_destino
if "%DESTINO:~-1%"=="\" set "DESTINO=%DESTINO:~0,-1%"

if not exist "%DESTINO%\SistemaFiado.exe" goto destino_errado
if /i "%DESTINO%"=="%ORIGEM%" goto mesma_pasta

tasklist /FI "IMAGENAME eq SistemaFiado.exe" 2>nul | find /I "SistemaFiado.exe" >nul
if not errorlevel 1 goto sistema_aberto

echo.
echo [1/2] Removendo os programas antigos de:
echo       %DESTINO%
if exist "%DESTINO%\_internal" rmdir /s /q "%DESTINO%\_internal"
if exist "%DESTINO%\_internal" goto falha_ao_apagar
del /q "%DESTINO%\SistemaFiado.exe" "%DESTINO%\CriarUsuarioAdmin.exe" "%DESTINO%\BackupAgendado.exe" 2>nul

echo [2/2] Copiando a versao nova...
robocopy "%ORIGEM%" "%DESTINO%" /E /XF .env /XD app /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto falha_ao_copiar

echo.
echo ============================================
echo  Pronto! Instalacao atualizada.
echo ============================================
echo O ".env" e a pasta "app" (backups e logs) foram mantidos.
echo Abra o SistemaFiado.exe e confira o numero da versao na tela de login.
echo.
if "%~1"=="" pause
exit /b 0

:origem_errada
echo Este arquivo precisa ser rodado de dentro da pasta dist\SistemaFiado
echo gerada pelo build_exe.bat (a que tem o SistemaFiado.exe e a pasta _internal).
goto erro
:sem_destino
echo Nenhuma pasta informada.
goto erro
:destino_errado
echo Nao encontrei o SistemaFiado.exe em:
echo   %DESTINO%
echo Confira o caminho. Se for a primeira instalacao neste computador, basta
echo copiar esta pasta inteira para o lugar desejado e criar o ".env".
goto erro
:mesma_pasta
echo A pasta instalada e esta pasta sao a mesma - nao ha o que atualizar.
goto erro
:sistema_aberto
echo O Sistema de Fiado esta aberto neste computador. Feche e rode de novo.
goto erro
:falha_ao_apagar
echo Nao consegui apagar a pasta _internal antiga (algum arquivo em uso?).
echo Feche o sistema e tente de novo. Nada foi copiado.
goto erro
:falha_ao_copiar
echo A copia falhou. Rode de novo; se continuar, copie a pasta inteira a mao
echo (guardando antes o ".env" e a pasta "app" da instalacao antiga).
goto erro
:erro
echo.
if "%~1"=="" pause
exit /b 1
