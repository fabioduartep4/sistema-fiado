# -*- mode: python ; coding: utf-8 -*-
"""Especificação do PyInstaller para o Sistema de Gestão de Fiado.

Gera uma pasta (modo --onedir) com dois executáveis e todas as
dependências — inicialização mais rápida e mais confiável para aplicações
Qt do que o modo --onefile (que extrai tudo para uma pasta temporária a
cada abertura):

- ``SistemaFiado.exe``: o programa em si (interface gráfica).
- ``CriarUsuarioAdmin.exe``: ferramenta de linha de comando para criar o
  primeiro usuário administrador num banco novo (ver
  app/scripts/criar_usuario_admin.py) — sem isso, não haveria como logar
  pela primeira vez num banco vazio sem ter Python instalado.

Os dois compartilham as mesmas bibliotecas na mesma pasta de saída (via
``MERGE``), então não duplicam espaço em disco.

Uso (a partir da raiz do projeto, no Windows):
    pyinstaller fiado.spec --noconfirm

Ou simplesmente rode build_exe.bat, que faz isso por você.

O resultado fica em dist/SistemaFiado/ — essa pasta inteira é o que deve
ser copiada para cada computador.

Inclui alembic.ini e a pasta de migrações como dados empacotados — o
sistema usa isso para criar/atualizar as tabelas do banco automaticamente
ao iniciar (ver app/database/migrar.py), sem precisar rodar alembic
manualmente em cada computador novo.
"""

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# SQLAlchemy e psycopg carregam alguns módulos dinamicamente (dialeto do
# PostgreSQL, driver psycopg), o que o PyInstaller não detecta sozinho
# apenas seguindo os imports — por isso listamos explicitamente aqui.
hidden_imports = (
    collect_submodules("sqlalchemy.dialects.postgresql")
    + collect_submodules("psycopg")
    + [
        "argon2",
        "argon2_cffi_bindings",
        "PySide6.QtSvg",
        "lxml.etree",
    ]
)

a_app = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("alembic.ini", "."),
        ("app/database/migrations", "app/database/migrations"),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

a_admin = Analysis(
    ["app/scripts/criar_usuario_admin.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("alembic.ini", "."),
        ("app/database/migrations", "app/database/migrations"),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

MERGE(
    (a_app, "SistemaFiado", "SistemaFiado"),
    (a_admin, "CriarUsuarioAdmin", "CriarUsuarioAdmin"),
)

pyz_app = PYZ(a_app.pure, a_app.zipped_data, cipher=block_cipher)
pyz_admin = PYZ(a_admin.pure, a_admin.zipped_data, cipher=block_cipher)

exe_app = EXE(
    pyz_app,
    a_app.scripts,
    [],
    exclude_binaries=True,
    name="SistemaFiado",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # esconde o console (janela preta) — é um app gráfico
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

exe_admin = EXE(
    pyz_admin,
    a_admin.scripts,
    [],
    exclude_binaries=True,
    name="CriarUsuarioAdmin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # precisa de terminal — pede nome/login/senha digitados
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe_app,
    a_app.binaries,
    a_app.zipfiles,
    a_app.datas,
    exe_admin,
    a_admin.binaries,
    a_admin.zipfiles,
    a_admin.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SistemaFiado",
)
