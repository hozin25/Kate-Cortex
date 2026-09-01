"""立体视图冒烟数据（VECTOR_GRAPH_PLAN.md §5）：向临时 vault 播种语义簇条目并建向量索引

用法：
    uv run python tests/smoke_projection.py          # 播种（幂等，可重复跑）
    KATE_VAULT_PATH=... KATE_DB_PATH=... uv run uvicorn kate_cortex.main:app --port 1738
    浏览器打开 http://localhost:5173/#/library?view=graph 人工验收

路径固定在系统临时目录 kate-graph-smoke 下，与 uvicorn 进程共享。
FakeEmbedder 纯本地确定性向量，零出网、不碰用户真实库。
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kate_cortex.config import Config
from kate_cortex.db import connect as db_connect
from kate_cortex.providers.embedding import FakeEmbedder
from kate_cortex.search import Search
from kate_cortex.storage import Storage
from kate_cortex.vectors import VectorIndex

CLUSTERS = {
    "生活健康": ["感冒", "保暖", "健康", "出去玩"],
    "编程": ["redis", "python", "fastapi", "连接池"],
    "出行": ["天气", "旅行", "行李", "路线"],
    "美食": ["烹饪", "食谱", "火候", "食材"],
}

TITLES = {
    "生活健康": ["感冒护理要点", "保暖穿搭清单", "健康作息表", "周末出去玩计划"],
    "编程": ["Redis 连接池配置", "Python 虚拟环境", "FastAPI 中间件", "Redis 缓存策略"],
    "出行": ["周末旅行路线", "天气与穿衣", "行李打包清单", "出行交通备选"],
    "美食": ["家常食谱汇总", "火候与时间", "食材采购清单", "烹饪入门笔记"],
}


def main() -> None:
    root = Path(tempfile.gettempdir()) / "kate-graph-smoke"
    vault = root / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    db_path = root / "index.sqlite"

    config = Config(vault_path=vault, db_path=db_path)
    database = db_connect(db_path)
    index = VectorIndex(database.conn, lambda: FakeEmbedder(clusters=CLUSTERS))
    storage = Storage(
        config=config, db=database, search=Search(database.conn), vectors=index
    )

    for name, keywords in CLUSTERS.items():
        for i in range(10):
            title = f"{TITLES[name][i % len(TITLES[name])]}（{i + 1}）"
            content = (
                f"关于{name}的第{i + 1}条记录：{keywords[i % len(keywords)]}相关"
                f"的场景笔记，条目编号 {i + 1}，用于立体视图聚簇验收。"
            )
            existing = storage.list_entries()
            if any(e.title == title for e in existing[0]):
                continue
            storage.create_entry(
                title=title, source="manual", content=content, collections=[name]
            )

    result = index.backfill(storage)
    indexed, total = index.status()
    print(f"vault: {vault}")
    print(f"db:    {db_path}")
    print(f"backfill: +{result.embedded} (failed {result.failed})")
    print(f"status:   {indexed}/{total}")


if __name__ == "__main__":
    main()
