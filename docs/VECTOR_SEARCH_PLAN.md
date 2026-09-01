# 向量混合检索（语义检索）改动清单

> 目标：为 RAG 与记忆召回补上语义召回能力，解决 FTS5 字面匹配无法跨同义改写
> 命中的问题（DESIGN.md §7 记录的「问身份↔只有学生」真实案例）。
>
> 版本：v1 · 2026-09-01 · 状态：**已实施**（阶段 0~D 全部完成，阶段 E 记忆
> 召回向量增强留二期；执行记录见 [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) 阶段 6）
>
> 增补（同日）：§3 的「一期只接 GLM」扩展为双 provider——新增硅基流动
> `BAAI/bge-m3`（免费档，1024 维原生匹配向量表），settings 加
> `embedding_provider` / `embedding_api_key`，切换后须重建索引（向量空间不互通）。
>
> 定位：对应竞品分析的 P1 第一项，兑现 README 已承诺的 sqlite-vec。

---

## 0. 设计原则（先拍板，再动手）

1. **向量索引 = 第三类索引**：与 FTS 同级，md 仍是唯一事实来源。向量表可随时
   删掉重建，重建不碰 md、不碰 SQLite 业务表。
2. **优雅降级**：未配 glm key、或 sqlite-vec 扩展加载失败 → 功能整体退化为
   纯 FTS，**现有行为与现有测试零变化**（`Storage.vectors = None` 即关闭）。
3. **写入路径不被网络拖垮**：embedding 是网络调用，永远放在 SQLite 事务提交
   **之后**执行；失败只 log warning，条目照常保存，由 backfill 补嵌。
4. **「重新索引」不隐式花钱**：`reindex()` 只清空向量表；重嵌必须走显式的
   重建端点/按钮（避免一键 reindex 对大库产生隐性 API 调用）。
5. **明确不做（一期）**：Library 搜索框仍纯 FTS（搜代码/报错要精确匹配）；
   不做多 embedding provider 选型（只接 GLM embedding-3，接口留扩展）；
   不做本地 Ollama（二期再议）；SSE 协议 / prompts / 前端 chat UI 零改动。

---

## 1. 前置 spike（阶段 0，动手前先跑通，≈0.5h）

- [ ] `uv add sqlite-vec`（清华镜像已有该包）
- [ ] 验证 Windows + Python 3.12（python.org 构建）下扩展加载可用：
  ```python
  import sqlite3, sqlite_vec
  conn = sqlite3.connect(":memory:")
  conn.enable_load_extension(True)
  sqlite_vec.load(conn)
  conn.enable_load_extension(False)
  ```
- [ ] 确认安装版本的 vec0 语法是否支持「TEXT 主键列 + distance_metric」：
  ```sql
  CREATE VIRTUAL TABLE t USING vec0(
    entry_id TEXT PRIMARY KEY,
    embedding float[1024] distance_metric=cosine
  );
  ```
  若不支持 → 兜底模式：vec0 只含向量列（隐式 rowid），另建普通映射表
  `entries_vec_map(vec_rowid INTEGER PRIMARY KEY, entry_id TEXT UNIQUE)`。
  本清单其余部分两种模式通用。
- [ ] 真实 key 冒烟一次 embedding 接口（写入 `smoke_embedding.py`，对齐现有
  smoke_*.py 模式）。

---

## 2. 改动文件总览

| 文件 | 改动 | 性质 |
|---|---|---|
| `backend/pyproject.toml` | 依赖 +`sqlite-vec` | 改 |
| `backend/src/kate_cortex/providers/embedding.py` | `GLMEmbedder` / `FakeEmbedder` / `EmbeddingUnavailable` | **新** |
| `backend/src/kate_cortex/vectors.py` | `VectorIndex`（与 `Search` 对等的索引类） | **新** |
| `backend/src/kate_cortex/db.py` | SCHEMA_VERSION 5、扩展加载、vec0 表 | 改 |
| `backend/src/kate_cortex/storage.py` | 写/删/重建路径挂 `vectors` | 改 |
| `backend/src/kate_cortex/chat/rag.py` | `retrieve()` RRF 混合检索 | 改 |
| `backend/src/kate_cortex/settings.py` + `models.py` | `embedding_model` 设置项 | 改 |
| `backend/src/kate_cortex/routes/embeddings.py` | `GET status` / `POST rebuild` | **新** |
| `backend/src/kate_cortex/main.py` | 装配 embedder → VectorIndex → Storage | 改 |
| `frontend/.../SettingsPage.tsx` | 向量状态行 + 重建按钮 | 改 |
| `backend/tests/`（多处）+ `smoke_embedding.py` | 见 §7 | 新/改 |
| `docs/DESIGN.md` §7.2、`README.md`、`IMPLEMENTATION_PLAN.md` | 见 §8 | 改 |

---

## 3. 阶段 A：Provider 层 embedding 客户端

`providers/embedding.py`（新）：

```python
class EmbeddingUnavailable(Exception): ...   # 未配 key / 扩展缺失，用于降级判断

class GLMEmbedder:
    model = "embedding-3"
    dimensions = 1024          # 256/512/1024/2048 可选；改维度必须重建向量表
    MAX_BATCH = 64             # 官方单请求上限
    TRUNCATE_CHARS = 1500      # 单条 3072 token 上限内的安全截断

    def __init__(self, api_key: str): ...
    def embed(self, texts: list[str]) -> list[list[float]]:
        # openai SDK: client.embeddings.create(model, input=batch, dimensions)
        # 内部按 MAX_BATCH 切批；单条先截断
```

- base_url 复用 `glm` 的 `https://open.bigmodel.cn/api/paas/v4`（OpenAI 兼容，
  **复用现有 glm provider key，用户零新配置**）。
- `FakeEmbedder`：确定性向量，测试用。支持注入「语义簇」——同一簇的文本映射到
  同一近似向量（如「感冒/保暖/健康」一簇、「出去玩/出行/天气」一簇），专门
  验证「出去玩↔感冒」这类跨词面召回场景。
- key 解析时机：对齐 `ProviderFactory` 的「每请求从 settings 构建」哲学——
  由 main.py 装配一个小适配器，每次调用时读 settings 里的 glm key，缺 key
  抛 `EmbeddingUnavailable`。避免「用户后配 key 需重启」的问题。

## 4. 阶段 B：存储层（db / vectors / storage）

### db.py

- `SCHEMA_VERSION = 5`
- `Database.__init__`：connect 后尝试加载 sqlite-vec 扩展；成功置
  `self.vec_enabled = True`，失败（未安装/平台不支持）log warning 并置 False，
  **不影响启动**。
- vec0 建表**不进 `_migrate` 链**，放在 `init_schema()` 里：`vec_enabled` 时
  每次启动 `CREATE VIRTUAL TABLE IF NOT EXISTS entries_vec ...`（幂等、零成本）。
  理由：扩展可用性与 schema 版本正交，避免「迁移到 v5 但扩展缺失」的中间态。
- 迁移链只需 `if current < 5: pass` 占位（版本号推进 + 按需建表，无数据搬迁）。

### vectors.py（新，与 search.py 对等）

```python
@dataclass
class VectorHit:
    entry_id: str
    distance: float          # cosine distance，越小越近

class VectorIndex:
    def __init__(self, conn, embedder_factory): ...
    def index_entry(self, entry_id, title, content) -> None
        # 文本 = f"{title}\n\n{content[:TRUNCATE_CHARS]}"，先 DELETE 再 INSERT
        # embedder 抛错 → log warning 直接返回（写入路径绝不被网络阻断）
    def remove_entry(self, entry_id) -> None
    def query(self, text: str, limit: int = 10) -> list[VectorHit]
        # SELECT entry_id, distance FROM entries_vec
        #   WHERE embedding MATCH ? AND k = ? ORDER BY distance
        # 参数用 sqlite_vec.serialize_float32(查询向量)
    def backfill(self, storage, batch=64) -> int
        # entries LEFT JOIN entries_vec 找缺向量的条目，分批嵌入、分批 commit，
        # 返回本次补嵌条数（幂等，可续跑）；单条失败计数不中断
    def status(self) -> tuple[int, int]      # (已索引, 总条目)
```

### storage.py 挂钩（全部走 `self.vectors if self.vectors else None`）

| 位置 | 改动 |
|---|---|
| `__init__(config, db, search)` | 加可选参数 `vectors: VectorIndex \| None = None`；`None` 即纯 FTS 旧模式（**现有测试与调用零改动**） |
| `create_entry` → `_write_db` 之后 | 事务提交后调 `vectors.index_entry(...)`（不在 `with self.conn` 内） |
| `update_entry` | 同上：FTS `index_entry` 所在事务完成后补向量 |
| `delete_entry` | 与 `search.remove_entry` 并列加 `vectors.remove_entry` |
| `restore_entry` | `_write_db` 后补 `vectors.index_entry` |
| `reindex()` | 加 `DELETE FROM entries_vec`（只清不嵌，见 §0.4） |

### main.py 装配

```python
embedder_factory = settings 适配器（读 glm key，缺 key 返回 None）
vector_index = VectorIndex(database.conn, embedder_factory) if database.vec_enabled else None
storage = Storage(config, database, search, vectors=vector_index)
app.state.vector_index = vector_index   # 供 routes/embeddings.py 使用
```

## 5. 阶段 C：rag.py 混合检索（RRF 融合）

`retrieve()` 改造（签名不变，调用方 `routes/chat.py` 零改动）：

```
1. fts 命中  = storage.search.query(query, limit=TOP_K * 2)
2. vec 命中  = storage.vectors.query(query, limit=TOP_K * 2)   # vectors 为 None 则跳过
3. RRF 融合：score(d) = Σ_通道 1 / (60 + rank_d)   # K=60，按 entry_id 去重
4. 取融合后 top TOP_K → 按现状 hydrate 成 KnowledgeSnippet（截断 500 字）
```

- RRF 的好处：FTS rank 与 cosine distance **不可直接比较**，排名融合免归一化。
- vectors 为 None 时退化为现状（纯 FTS top-3），`test_rag.py` 现有 10 个用例
  原样通过。
- `citations` SSE 事件结构不变，**前端 chat 相关零改动**。
- `list_entries(q=...)`（Library 搜索框）一期保持纯 FTS（§0.5）。

延迟影响：RAG 开启时每条用户消息多一次 embedding 往返（~100-300ms），
发生在 SSE 生成前的检索阶段，可接受。

## 6. 阶段 D：设置、端点与前端

- `settings.py` `DEFAULTS` 加 `"embedding_model": "embedding-3"`（一期不暴露
  维度设置，常量写死 1024；`models.py` 的 `SettingsOut/SettingsUpdate` 同步加）。
- `routes/embeddings.py`（新，挂 `/api`）：
  - `GET /api/embeddings/status` → `{"available": bool, "indexed": n, "total": m}`
    （available = glm key 已配 且 vec_enabled；前端据此展示/禁用）
  - `POST /api/embeddings/rebuild` → 清空向量表 + 全量 backfill，返回
    `{"indexed": n, "total": m, "failed": k}`（个人规模同步执行即可）
- 前端 `SettingsPage.tsx`：新增「语义检索」区块——状态行（已索引 x/y）+
  「重建向量索引」按钮 + 一句隐私说明（条目标题与正文前 1500 字将发送至
  智谱 embedding 接口，与对话共用同一出网边界）。ChatPage 不动。

## 7. 阶段 E（可选，二期独立做）：记忆召回向量增强

`chat/memory.py` `recall()`：vectors 可用时，对「记忆」合集条目做向量召回
（相似度阈值 cos-sim ≥ 0.35，即 distance ≤ 0.65），与关键词打分结果 RRF 合并
——零关键词重合但语义相近的记忆也能「想起」。keywords 机制保留不动
（可解释、且是 resident 注入的基础）。一期不做，单独评估效果后再上。

## 8. 测试与文档

测试（沿用现有分层）：

- `test_vectors.py`（新）：index/remove/query；`index_entry` 嵌入失败不抛；
  backfill 补漏与幂等；status 计数
- `test_db.py`：v4→v5 版本推进；vec 扩展缺失（模拟 `vec_enabled=False`）正常启动
- `test_rag.py`：RRF 融合排序与去重；纯 FTS 回退；FakeEmbedder 语义簇端到端
  ——「明天出去玩要准备什么」召回只写了「感冒…注意保暖」的条目（今天的
  FTS 下该用例必然空手而归，这是本项目的验收用例）
- `test_chat_api.py` / `test_agent_api.py`：fixture 加可选 FakeEmbedder 分支，
  默认 None 保持现状断言
- `smoke_embedding.py`（新）：真实 GLM key 冒烟

文档：

- `DESIGN.md` §7 增补「§7.2 向量混合检索」（对齐 §7.1 的增补写法）；
  §14 勾掉「embedding provider 选型」
- `README.md` 技术栈 sqlite-vec 从承诺变事实；补 GLM embedding-3 说明
- `IMPLEMENTATION_PLAN.md` 按惯例记录阶段与测试数

## 9. 风险与注意

| 风险 | 对策 |
|---|---|
| Windows 下扩展加载失败 | 阶段 0 spike 先验证；失败则 `vec_enabled=False` 降级，不阻塞其余功能 |
| PyInstaller 打包需带 sqlite-vec 原生库 | 本阶段不做打包；在（未来的）打包阶段清单里挂账 |
| 维度/模型常量变更 | vec0 `float[1024]` 定死；换维度 → 走 rebuild 端点整表重建 |
| backfill 是 O(n) 次 API 调用 | 分批（64）+ 逐批 commit + 进度日志；个人规模（数百条）秒级 |
| 隐私 | 出网内容 = 标题 + 正文前 1500 字 → 智谱；与 LLM 对话同一边界，设置页明示 |
| GLM 限流（并发/在途请求） | 批量上限 64 + 顺序调用即可，个人规模远低于阈值 |

## 10. 实施顺序与工作量

| 阶段 | 内容 | 预估 |
|---|---|---|
| 0 | spike：装包、扩展加载、vec0 语法验证、embedding 冒烟 | 0.5h |
| A | providers/embedding.py + FakeEmbedder + 单测 | 0.5 天 |
| B | db v5 + vectors.py + storage 挂钩 + 单测 | 0.5 天 |
| C | rag RRF 融合 + 语义簇验收用例 | 0.25 天 |
| D | 设置/端点 + 前端设置页 + 文档 | 0.5 天 |
| E（可选） | memory recall 向量增强 | 0.5 天 |

合计（不含 E）：约 1.5~2 人天，对齐 DESIGN §12 的估算粒度。
