@echo off
REM instalar_backup_agendado.bat - agenda o backup diario no Windows.
REM
REM Rode UMA VEZ, no computador onde o banco de dados fica (o servidor), de
REM dentro da pasta do sistema (a que tem o BackupAgendado.exe e o .env).
REM
REM Cria uma tarefa no Agendador de Tarefas do Windows que roda o
REM BackupAgendado.exe todo dia no horario escolhido. Se o computador estiver
REM desligado nessa hora, o backup roda assim que ele for ligado. Ninguem
REM precisa abrir o Sistema de Fiado.
REM
REM A tarefa roda com o usuario do Windows que esta logado agora - e so com
REM ele logado. E de proposito: a pasta do Google Drive so existe para o
REM usuario que esta com o Google Drive aberto.
REM
REM Uso sem perguntas:   instalar_backup_agendado.bat 12:00
REM Para desinstalar:    instalar_backup_agendado.bat remover

setlocal
set "PASTA=%~dp0"
if "%PASTA:~-1%"=="\" set "PASTA=%PASTA:~0,-1%"
set "TAREFA=SistemaFiado - Backup diario"

echo ============================================
echo  Sistema de Fiado - Backup agendado
echo ============================================
echo.

if /i "%~1"=="remover" goto remover

if not exist "%PASTA%\BackupAgendado.exe" goto sem_programa
if not exist "%PASTA%\.env" goto sem_env

set "HORARIO=%~1"
if not "%HORARIO%"=="" goto tem_horario
echo A que horas fazer o backup todo dia? Escolha um horario em que este
echo computador costuma estar ligado. Formato HH:MM (exemplo: 12:00).
echo.
set /p "HORARIO=Horario [12:00]: "
if "%HORARIO%"=="" set "HORARIO=12:00"
:tem_horario

echo.
echo Criando a tarefa "%TAREFA%" para as %HORARIO%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "try {" ^
  "  $hora = [datetime]::ParseExact('%HORARIO%', 'HH:mm', $null);" ^
  "  $acao = New-ScheduledTaskAction -Execute '%PASTA%\BackupAgendado.exe' -WorkingDirectory '%PASTA%';" ^
  "  $gatilho = New-ScheduledTaskTrigger -Daily -At $hora;" ^
  "  $opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
  "  Register-ScheduledTask -TaskName '%TAREFA%' -Action $acao -Trigger $gatilho -Settings $opcoes -Description 'Backup diario do banco do Sistema de Fiado.' -Force | Out-Null;" ^
  "  exit 0" ^
  "} catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto falha_ao_agendar

echo.
echo Fazendo um backup agora, para testar...
"%PASTA%\BackupAgendado.exe" --agora
if errorlevel 1 goto falha_no_teste

echo.
echo ============================================
echo  Pronto! Backup agendado para todo dia as %HORARIO%.
echo ============================================
echo O backup de teste foi feito com sucesso. Confira o arquivo na pasta de
echo backup (a que aparece na tela Backups do sistema).
echo.
echo Para mandar tambem para o Google Drive: abra o Sistema de Fiado NESTE
echo computador uma vez e, em Backups, escolha a pasta do Google Drive.
echo.
if "%~1"=="" pause
exit /b 0

:remover
schtasks /Delete /TN "%TAREFA%" /F >nul 2>&1
if errorlevel 1 (
    echo Nao havia backup agendado neste computador.
) else (
    echo Backup agendado removido deste computador.
)
echo.
if "%~2"=="" pause
exit /b 0

:sem_programa
echo Nao encontrei o BackupAgendado.exe nesta pasta. Rode este arquivo de
echo dentro da pasta do sistema (a mesma do SistemaFiado.exe).
goto erro
:sem_env
echo Nao encontrei o arquivo ".env" nesta pasta. Configure a conexao com o
echo banco (copie ".env.example" para ".env" e preencha) antes de agendar.
goto erro
:falha_ao_agendar
echo.
echo Nao consegui criar a tarefa. Confira o horario (formato HH:MM) e tente
echo de novo. Se continuar, clique com o botao direito neste arquivo e escolha
echo "Executar como administrador".
goto erro
:falha_no_teste
echo.
echo A tarefa foi criada, mas o backup de teste FALHOU.
echo Veja o motivo no fim do arquivo:  %PASTA%\app\logs\erros.log
echo O mais comum: o "pg_dump" do PostgreSQL nao esta no PATH deste computador,
echo ou os dados do ".env" estao errados.
goto erro
:erro
echo.
if "%~1"=="" pause
exit /b 1
