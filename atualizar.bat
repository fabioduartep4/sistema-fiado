@echo off
REM atualizar.bat - baixa a versao mais recente do Sistema de Fiado do GitHub
REM e atualiza ESTA pasta (a do SistemaFiado.exe). Precisa de internet.
REM
REM Feche o sistema antes de rodar. O ".env" e a pasta "app" (configuracoes,
REM backups e logs) nao sao alterados. O trabalho todo esta no atualizar.ps1,
REM que precisa estar na mesma pasta.
REM
REM Uso sem perguntas:  atualizar.bat -Sim

if not exist "%~dp0atualizar.ps1" (
    echo Nao encontrei o atualizar.ps1 nesta pasta. Os dois arquivos andam juntos.
    pause
    exit /b 1
)

REM Tudo numa linha so: a atualizacao troca este proprio arquivo, e o Windows
REM le os .bat aos poucos - uma linha ja lida nao e afetada pela troca.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0atualizar.ps1" %* & (if "%~1"=="" pause) & exit /b
