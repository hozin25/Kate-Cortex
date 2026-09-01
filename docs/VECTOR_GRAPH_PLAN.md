# 语义空间三维可视化改动清单

> 目标：把向量索引后的 1024 维语义空间降维到三维，在 Library 内以「立体」
> tab 展示可旋转/缩放/悬停的条目点云，让「哪些条目语义相近、合集聚不聚得拢」
> 一眼可见。
>
> 版本：v1 · 2026-09-01 · 状态：**已实施**（执行记录与两处算法偏差见
> [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) 阶段 7）
>
> 已拍板的选型（2026-09-01 讨论）：
> 1. 降维走 **scikit-learn**（t-SNE 为主、PCA 兜底），**不引入 numba/UMAP**
>    ——个人规模（数百条）下 t-SNE 全量重算 1~2s，UMAP 的速度与 transform
>    优势体现不出来，不值得背上 llvmlite 的打包负担；
> 2. 着色维度：**按合集**（信息现成、零算法成本）；不做 k-means 聚类着色；
> 3. 入口：Library 页内加 **「列表 / 立体」tab**，不加侧边栏导航项。
>
> 定位：向量检索（[VECTOR_SEARCH_PLAN.md](./VECTOR_SEARCH_PLAN.md)）的可视化
> 延伸，纯本地计算、**零出网**（只读已存向量，不再调用 embedding 接口）。

---

## 0. 设计原则

1. **投影 = 派生视图的派生视图**：entries_vec 已经是「可随时清空重建」的索引，
   3D 坐标再派生一层，**不落库**——后端进程内存缓存即可，重启后首次打开
   重算 1~2s。固定 `random_state` 后同输入必同输出，布局跨重启稳定。
2. **优雅降级对齐向量检索**：vec 扩展缺失 / 向量表为空 / 条目数不足 →
   前端展示对应空态，tab 本身不藏（用户能看到「为什么没有图」）。
3. **计算不阻塞**：sklearn 是重依赖，**函数体内懒加载**，不进 main.py 的
   import 链，应用启动耗时零变化。
4. **签名缓存**：内存缓存 keyed on `(embedding_provider, embedding_model,
   vec_count, entries_total, max_entries_updated_at)`——增删改条目、切换
   embedding provider/model 后首次 GET 自动重算，无需手动刷新按钮兜底
   （按钮仍保留，用于 tab 停留期间的强制刷新）。
5. **明确不做（一期）**：不做 bloom 后处理（additive blending 软粒子已够
   「辉光」）；不做查询向量投影与邻居连线（二期亮点）；不做 xyz 落库持久化；
   不做 2D 视图切换。

## 1. 前置 spike（阶段 0，≈0.5h）

- [ ] `uv add scikit-learn`（清华镜像；numpy 随之带入）
- [ ] 确认 `sqlite_vec` 包的 blob → float 反序列化 API（`deserialize_float32`
      或 `struct.unpack(f"{n}f", blob)` 兜底）
- [ ] 用 FakeEmbedder 造 200 条 1024 维样本，实测 `TSNE(n_components=3,
      metric="cosine", random_state=42)` 的耗时与 `perplexity` 上限行为，
      校准 §2 的阈值常量

## 2. 核心算法约定（projection.py）

输入：entries_vec 全量向量（先做 **L2 归一化**——cosine 语义只看方向）。
输出：归一化到 `[-1, 1]` 立方体的 (x, y, z)，前端不感知原始量纲。

| 条目数 n | 行为 | method 字段 |
|---|---|---|
| n < 3 | 不计算，返回空点集 | `insufficient` |
| 3 ≤ n < 20 | PCA(n_components=3) | `pca` |
| 20 ≤ n ≤ 5000 | t-SNE（`perplexity=min(30, (n-1)/3)` 自适应满足「perplexity < n」约束，`init="pca"`，`metric="cosine"`，`random_state=42`，barnes_hut） | `tsne` |
| n > 5000 | 降级 PCA + log warning（个人库预期达不到） | `pca` |

**实施修正（2026-09-01，实测驱动）**：

1. **t-SNE 前先 PCA 预降维到 min(50, n-1)**——原定「t-SNE 直接作用于
   1024 维」实测不稳：高维小样本下 3D t-SNE 退化为球壳散点（2 簇 24 点
   簇间/簇内距离比 0.98x，即完全无分离）。PCA 预处理是 t-SNE 的标准前置，
   修复后 2 簇 1.40x、4 簇 48 点 ~1.6x、n=200 耗时 0.65s 且逐位确定。
   PCA 的隐式中心化顺带消解了 FakeEmbedder 正象限向量的相关性
2. **坐标归一化**：原定「逐维 min-max 后等比缩放」自相矛盾（逐维拉伸不
   保形），实现为**质心居中 + 等比缩放**，最长坐标 ≤1 即整体落在
   [-1, 1]，相对形状严格保持

## 3. 后端改动

| 文件 | 改动 | 性质 |
|---|---|---|
| `backend/pyproject.toml` | 依赖 +`scikit-learn` | 改 |
| `backend/src/kate_cortex/projection.py` | `ProjectionCache`（签名缓存 + 懒加载 sklearn） | **新** |
| `backend/src/kate_cortex/routes/embeddings.py` | `GET /projection`、`POST /projection/refresh` | 改 |
| `backend/src/kate_cortex/models.py` | `ProjectionPoint` / `ProjectionOut` | 改 |
| `backend/src/kate_cortex/main.py` | `app.state.projection` 装配 | 改 |

### projection.py（新）

```python
@dataclass
class ProjectionPoint:
    entry_id: str
    title: str
    collections: list[str]
    source: str
    x: float; y: float; z: float

class ProjectionCache:
    def __init__(self, conn): ...
    def get(self, refresh: bool = False) -> ProjectionResult:
        # 1. SELECT v.entry_id, e.title, e.source, v.embedding
        #      FROM entries_vec v JOIN entries e ON e.id = v.entry_id
        # 2. SELECT entry_id, name FROM entry_collections JOIN collections（按名排序）
        # 3. 签名 = (provider, model, vec数, entries总数, MAX(updated_at))，
        #    命中缓存且非 refresh → 直接返回
        # 4. L2 归一化 → §2 分派算法 → 归一化坐标 → 写缓存
```

- **不依赖 embedder**：只读已存向量。删了 key 但向量还在 → 立体视图照常
  可看（区别于 rebuild 的 available 门槛）。
- 缓存是实例属性（dict），随 `app.state.projection` 存活；测试直接实例化。

### 路由（embeddings.py 追加）

- `GET /api/embeddings/projection` → `ProjectionOut`；vec 扩展缺失 →
  `{available: false, method: "unavailable", points: []}`（对齐 status 的
  200-带-available 语义，前端据此渲染空态而非报错）。
- `POST /api/embeddings/projection/refresh` → 同结构，`refresh=True` 强制重算。

### models.py

```python
class ProjectionPointOut(BaseModel):
    entry_id: str; title: str
    collections: list[str]; source: str
    x: float; y: float; z: float

class ProjectionOut(BaseModel):
    available: bool
    method: Literal["tsne", "pca", "insufficient", "unavailable"]
    n: int; computed_ms: int
    points: list[ProjectionPointOut]
```

## 4. 前端改动

| 文件 | 改动 | 性质 |
|---|---|---|
| `frontend/package.json` | +`three` `@react-three/fiber@^9` `@react-three/drei@^10` | 改 |
| `frontend/src/renderer/src/components/library/pointColors.ts` | 合集→颜色映射纯函数 | **新** |
| `frontend/src/renderer/src/components/library/VectorGraph.tsx` | 3D 视图组件 | **新** |
| `frontend/src/renderer/src/pages/LibraryPage.tsx` | 「列表 / 立体」tab（`?view=graph`） | 改 |
| `frontend/src/renderer/src/types.ts` | Projection 类型 | 改 |

### LibraryPage tab

- 标题行下加双 tab（lucide `List` / `Orbit` 图标），状态进 `useSearchParams`：
  `/library`（列表）与 `/library?view=graph`（立体），与现有 collection 过滤
  参数共存、刷新可保持。
- `view=graph` 时渲染 `<VectorGraph />` 替换搜索行 + 合集 chips + 网格区。

### pointColors.ts（纯函数，可单测）

- 固定 10 色板（对齐 aurora 主题：indigo / violet / cyan / emerald / amber /
  rose / sky / fuchsia / teal / lime），合集按名称排序后稳定取色；
- 点色 = 第一个合集；多合集条目 tooltip 里展示全部；无合集 = zinc 灰。

### VectorGraph.tsx

- 数据：组件内 `useEffect` + `api.get<ProjectionOut>('/embeddings/projection')`，
  本地 state 即可，**不建 zustand store**（单点消费、无跨页共享）。加载中
  复用 `Spinner`。
- 场景：`<Canvas>` + `<points>`（BufferGeometry：position + color 属性）+
  `PointsMaterial`（`vertexColors` + `AdditiveBlending` + canvas 生成的径向
  渐变软粒子贴图）+ drei `<OrbitControls>`（旋转/缩放/平移）。
- 交互：
  - 悬停：`raycaster.params.Points.threshold` 随相机距离缩放，命中后 HTML 层
    玻璃拟态 tooltip（标题 + 合集徽章 + 正文首行）；
  - 点击：`navigate(/entries/${id})`；
  - 图例：右上角按合集着色的可点图例，点击隐藏/显示该合集点集（数组过滤）；
  - 角标：`{n} 条 · {method === 'pca' ? 'PCA 预览' : 't-SNE'} · 重算按钮`。
- 降级：`available=false`（扩展缺失）/ `insufficient`（少于 3 条）/
  WebGL 不可用（`WebGL.isWebGL2Available()` 检测 + Canvas 外层 try）→
  复用 `EmptyState` 给出对应文案。
- 测试策略：jsdom 无 WebGL，**Canvas 挂载路径不写组件测试**；空态分支、
  pointColors 纯函数正常测（Canvas 渲染质量靠人工验收）。

## 5. 测试

后端（沿用 `vector_storage` fixture + FakeEmbedder 语义簇）：

- `test_projection.py`（新）：
  - 造两个语义簇 × 各 ≥10 条（标题含簇关键词、正文各异）→ 同簇点两两距离
    显著小于跨簇（对齐 test_rag 的验收用例风格）；
  - 缓存：同签名两次 `get()` 坐标逐位相等；新增条目后签名变化 → 点数更新；
  - 阈值：n=2 → `insufficient`；n=10 → `pca`；坐标全部落在 [-1, 1]；
  - refresh=True 绕过缓存强制重算。
- `test_embeddings_api.py`（改）：vec 缺失 → `available=false`；
  FakeEmbedder + 已索引数据 → 200 且 points 结构完整；refresh 端点。

## 6. 文档

- `DESIGN.md` §7 增补「§7.3 语义空间三维视图」（对齐 §7.2 写法，注明
  派生视图不落库、零出网）；
- `README.md` 功能列表 + 技术栈补 scikit-learn / three.js；
- `IMPLEMENTATION_PLAN.md` 按惯例记录阶段与测试数。

## 7. 风险与注意

| 风险 | 对策 |
|---|---|
| sklearn import 拖慢启动 | 函数体内懒加载，启动 import 链零变化 |
| t-SNE 布局漂移（重算后整体排布变化） | 固定 seed 保证同输入同输出；签名缓存让布局只在库内容变化后变化 |
| perplexity ≥ n 报错 | 自适应 `min(30, (n-1)/3)`，spike 实测校准 |
| FakeEmbedder 簇内向量过于相似导致测试不稳定 | 造数据时标题混入簇关键词 + 正文各异的 text noise 分量 |
| jsdom 无 WebGL | 组件测试只覆盖空态与纯函数；3D 呈现走人工验收 |
| 低配机 WebGL 禁用 | `WebGL.isWebGL2Available()` 预检 + EmptyState 降级 |
| numpy/sklearn 增重后端环境 | 本地桌面应用无感；与 sqlite-vec 一并挂账未来 PyInstaller 打包清单 |

## 8. 实施顺序与工作量

| 阶段 | 内容 | 预估 |
|---|---|---|
| 0 | spike：装包、反序列化 API 确认、t-SNE 耗时/阈值实测 | 0.5h |
| A | projection.py + 端点 + models + main 装配 + 单测 | 0.5 天 |
| B | 前端依赖 + tab + VectorGraph 基础场景（点云/控制器/着色） | 1 天 |
| C | 打磨：tooltip、图例过滤、空态/加载态/WebGL 降级、refresh 按钮 | 0.5 天 |
| D | API 测试补充 + 文档 | 0.25 天 |

合计：约 2~2.5 人天，对齐 DESIGN §12 的估算粒度。
