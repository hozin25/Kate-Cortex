# -*- mode: python ; coding: utf-8 -*-
# Kate-Cortex 后端打包（IMPLEMENTATION_PLAN 阶段 5.4）
# 构建：uv run pyinstaller kate_cortex.spec
# 产物：dist/kate-cortex-server.exe（onefile，无控制台）
#   - 打包模式 config 依赖 sys.frozen → vault 默认 %USERPROFILE%\Kate-Cortex\vault
#   - jieba 词典、sqlite-vec 原生库、sklearn 依赖需显式/钩子收集

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = []

# jieba：主词典等包数据
for pkg in ("jieba", "sqlite_vec"):
    pkg_all = collect_all(pkg)
    datas += pkg_all[0]
    binaries += pkg_all[1]
    hiddenimports += pkg_all[2]

# uvicorn 的可插件发现依赖静态导入列表
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

a = Analysis(
    ["run_server.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="kate-cortex-server",
    debug=False,
    strip=False,
    upx=False,  # 杀软误报重灾区，关掉
    console=False,
    disable_windowed_traceback=False,
)
