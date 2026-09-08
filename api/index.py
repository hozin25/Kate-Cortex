"""Vercel Python serverless 入口：直接导出 FastAPI ASGI 应用。

kate_cortex 源码不在 PyPI，由 vercel.json 的 functions.includeFiles
随函数打包，这里把 backend/src 加进 sys.path。

数据落在 /tmp（serverless 实例的临时盘）：实例回收/冷启动后清空，
仅作在线试用；正式使用请装桌面端（数据全本地）。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "backend", "src"))

os.environ.setdefault("KATE_VAULT_PATH", "/tmp/kate-cortex/vault")
os.environ.setdefault("KATE_DB_PATH", "/tmp/kate-cortex/vault/index.sqlite")

from kate_cortex.main import app  # noqa: E402
