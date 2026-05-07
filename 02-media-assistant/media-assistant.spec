# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files


tiktoken_datas = []

try:
    tiktoken_datas = collect_data_files('tiktoken')
except Exception:
    pass


a = Analysis(
    ['video_subtitle_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.py', '.'),
        ('llm_manager.py', '.'),
        ('.venv/lib/python3.11/site-packages/faster_whisper/assets', 'faster_whisper/assets'),
    ] + tiktoken_datas,
    hiddenimports=['faster_whisper', 'ctranslate2', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on', 'fastapi', 'starlette.routing', 'starlette.responses', 'starlette.middleware.cors', 'pydantic', 'pydantic_core', 'anyio._backends._asyncio', 'sniffio', 'PIL.Image', 'python_multipart', 'h11', 'tiktoken_ext.openai_public'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='media-assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='media-assistant',
)
