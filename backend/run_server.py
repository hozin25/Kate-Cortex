"""打包版后端入口：PyInstaller 主程序（kate-cortex-server.exe）

用法：kate-cortex-server.exe [--port 1738]；打包模式下 config 依赖
sys.frozen 自动把 vault 切到 %USERPROFILE%\Kate-Cortex\vault。

注意：直接 import app 对象（而非传字符串给 uvicorn）——PyInstaller 的
静态分析追不到运行时字符串导入，会漏打整个 kate_cortex 包。
"""

import sys

import uvicorn

from kate_cortex.main import app


def main() -> None:
    port = 1738
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            pass
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
