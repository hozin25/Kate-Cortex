# 自定义 Agent 计划：设置页 Agent 模块 + 聊天输入框 `/` 引用

> **状态：草案 v1.1，待评审**（2026-09-13 撰写；v1.1 增补 §8 首个内置预设「私人生活医生」；评审通过后按 §9 顺序实施）
> 目的：供实施按本文档逐项落地，不依赖撰写时的会话上下文。
> 交互参考：ZCode 前端的 slash 命令菜单（输入 `/` 弹出列表 → 过滤 → 键盘/鼠标选中 → 补全）。

---

## 0. 一句话概述

用户在**设置页新增的「自定义 Agent」模块**里创建专属助手（名称 / 描述 / 角色提示词 / 可选指定模型）；
在**聊天输入框敲 `/`** 弹出 agent 菜单（对标 ZCode 的 slash 菜单交互），选中后消息以
`/名称 正文` 发出，本轮对话即由该 agent 的角色设定接管回答。

三条设计主线（均已按推荐项撰写，评审时可改）：

1. **存储走 settings 表 JSON**（`settings["agents"]`），与 `mcp_servers` 同构——零 schema 迁移、
   多用户云端版天然按账号隔离；
2. **消息前缀 `/名称 ` 保留落库**——历史可见、`regenerate` / `resend` 天然继承 agent 语境、
   messages 表零改动；
3. **agent = system prompt 角色段 +（可选）请求级模型覆盖**——沉淀/记忆/MCP 等工具能力全部保留，
   agent 是「换了人格的 Kate」，不是阉割版。

首个内置预设：功能上线后自带一个**「私人生活医生」agent**——像真实医生看病一样先反问确认
病症、再给治疗与就医建议，交互对标蚂蚁阿福的「AI 诊室」（详见 §8）。

---

## 1. 交互设计（参考 ZCode slash 菜单）

### 1.1 ZCode 的做法（我们的对标基准）

ZCode 输入框的 slash 交互要点：

- **触发锚定在输入起点**：`/` 必须是输入框第一个字符才弹菜单；正文中间的 `/`（如 URL
  `https://…`）是普通字符，不触发；
- **边输边过滤**：`/` 后继续输入即按名称/描述子串过滤，菜单实时收窄；无匹配时菜单消失；
- **键盘优先**：`↑` / `↓` 在候选项间移动（高亮项自动滚入视野），`Enter` 或 `Tab` 选中补全，
  `Esc` 关闭菜单；菜单打开期间 `Enter` **只做选中、不发送消息**；
- **鼠标等价**：悬停高亮、点击即选中；
- **选中后**：以 `/名称` 形式留在输入框（补一个尾随空格），光标落在其后，用户接着写正文；
- 菜单每项展示 **名称 + 一句话描述**，悬停可看完整说明。

### 1.2 Kate-Cortex 的落地交互

| 行为 | 设计 |
|---|---|
| 触发 | 输入框内容以 `/` 开头（光标在首 token 内）且用户已建过 agent 时，弹出菜单 |
| 菜单位置 | 输入框上方（absolute，`bottom-full`），毛玻璃风格与现有 `glass` 一致；最高 ~280px 内部滚动 |
| 过滤 | `/xxx` 的 `xxx` 对 name、description 做大小写不敏感子串匹配；命中 0 条显示「没有匹配的 agent」 |
| 键盘 | `↑` `↓` 移动高亮；`Enter` / `Tab` 选中；`Esc` 关闭；**菜单打开时 `Enter` 不发送**（见 §7 改进点 1） |
| IME | 中文 agent 名必然走输入法：composition 期间的 `Enter`（确认候选）不得触发选中或发送——沿用现有 `e.nativeEvent.isComposing` 判定并扩展到菜单键 |
| 选中后 | 输入框替换为 `/名称 `（尾随空格），光标在其后；菜单关闭、焦点回到输入框 |
| 鼠标 | 悬停高亮、点击选中，与键盘行为一致 |
| 发送 | 用户按原样 `Enter` 发送；前端不做特殊处理（前缀随正文走，见 §3.3） |
| 空态 | 一个 agent 都没有时，`/` 不弹菜单（占位文案引导去设置页创建，见 §7 改进点 2） |
| placeholder | 更新为「和 Kate 聊聊…（输入 / 引用 agent，Enter 发送，Shift+Enter 换行）」 |

菜单项版式：左侧 `/名称`（agent 名），右侧两行小字——描述 + 模型提示（如 `glm-coding · glm-5.3`，
未指定模型则显示「跟随会话模型」）。

---

## 2. 数据模型

### 2.1 存储：`settings["agents"]`（JSON 数组）

与 `mcp_servers` 完全同构（`backend/src/kate_cortex/settings.py` 的 `DEFAULTS` 加一行
`"agents": []`）：

- **零 schema 迁移**：settings 是 KV 表，不动 `db.py` 的 `SCHEMA_VERSION`（现为 6）；
- **多用户自动隔离**：多用户版每账号独立 SQLite（`multiuser.py` 每用户一套
  `SettingsService`），agent 天然按账号隔离，DESIGN.md §16 无需改动；
- **不进 `/api/settings` 的 PUT 载荷**：`SettingsUpdate` 是 `extra=forbid`，agent 走独立的
  `/api/agents` 路由——与 MCP 走 `/api/mcp/servers` 的先例一致。

### 2.2 字段定义

```jsonc
{
  "id": "kc_agent_a1b2c3d4",       // kc_agent_ + 8 位 hex（对齐 kc_conv_/kc_msg_ 风格）
  "name": "翻译官",                 // 引用 token，见 2.3 校验
  "description": "中英互译，保留语气与格式",   // 菜单展示用，≤60 字
  "prompt": "你是一名资深中英互译……",         // 角色提示词，1~4000 字
  "provider": "glm-coding",        // 可选；不填 = 跟随会话模型
  "model": "glm-5.3",              // 可选；与 provider 成对出现
  "enabled": true,
  "created_at": "2026-09-13T…"
}
```

### 2.3 校验规则（`AgentCreate` / `AgentUpdate`，Pydantic）

| 字段 | 规则 | 违例 |
|---|---|---|
| `name` | 必填；`^[A-Za-z0-9_\u4e00-\u9fff-]{1,32}$`（单 token、无空白无 `/`，支持中英数连字符）；全列表内唯一（大小写不敏感） | 422 / 重名 409 |
| `description` | ≤60 字，可为空（空则菜单只显名称） | 422 |
| `prompt` | 必填，1~4000 字（上限保护上下文窗口） | 422 |
| `provider` / `model` | 要么都空要么都有；`provider` ∈ KNOWN_PROVIDERS；**保存时不校验 key**（允许先建后配 key） | 422 |
| `enabled` | 布尔，默认 true | — |

---

## 3. 后端改动

### 3.1 新路由 `backend/src/kate_cortex/routes/agents.py`（对齐 `routes/mcp.py` 风格）

```
GET    /api/agents            → { agents: AgentOut[] }
POST   /api/agents            → 201 AgentOut          （重名 409）
PATCH  /api/agents/{id}       → AgentOut              （改 name 撞名也 409）
DELETE /api/agents/{id}       → 204
```

- 读写都经 `get_services(request).settings_service`（单用户/多用户无感切换，同 `routes/mcp.py`）；
- 列表按 `created_at` 升序返回，菜单与设置页共用；
- `main.py` 注册 router（现 router 注册清单里加一行）。

`models.py` 新增：`AgentCreate` / `AgentUpdate`（PATCH 全可选）/ `AgentOut`。

### 3.2 system prompt 注入（`chat/prompts.py`）

`build_system_prompt(...)` 增加可选参数 `agent_name: str | None`、`agent_prompt: str | None`；
插入位置在 **PERSONA 之后、工具规则之前**：

```
## 当前角色：{name}
用户通过 /{name} 引用了专属 agent。请严格按以下角色设定回答——与上方默认人设冲突时，
以这里为准；但「工具使用规则」整节仍然全部适用（知识沉淀、记忆、导出照常可用）。

{prompt}
```

**关键取舍**：agent 只覆盖「人格/回答方式」，不裁剪工具。Kate 的核心价值是对话即沉淀
（save_knowledge / save_memory），翻译官也该能「记一下」。

### 3.3 引用解析：`_resolve_agent` helper（`routes/chat.py`）

消息里保留 `/名称 ` 前缀（落库、回显、历史搜索都可见——自描述且无需动 messages 表），
后端在三条路径上用同一个 helper 从**最后一条用户消息**解析 agent：

```python
AGENT_TOKEN = re.compile(r"^/([A-Za-z0-9_\u4e00-\u9fff-]{1,32})(?=\s|$)")

def resolve_agent(content: str, agents: list[dict]) -> dict | None:
    """content 以 /名称 开头且名称命中 enabled 的 agent 则返回它；否则 None。
    已删除/已停用/改名的旧前缀一律回落默认 Kate（None）。重名取第一个。"""
```

接入点：

| 路径 | 做法 |
|---|---|
| `POST …/chat` | 解析 `payload.content` 前缀 → 命中则本轮生效。消息照原样（含前缀）`append_message`，**标题生成剥掉前缀**（`ensure_title` 前先 `strip_images` + 去 token，见 §7 改进点 3） |
| `POST …/regenerate` | 从 `last_user.content` 解析 → 改了 agent 配置后重新生成也走**当前**配置（解析到的是 id 对应的最新定义） |
| `POST …/resend` | 同 regenerate：用户编辑后保留 `/名称` 就继续用该 agent，删掉前缀即回默认 Kate |

### 3.4 请求级模型覆盖（可选字段生效时）

- agent 带 `provider/model` 时，`_stream_response` 里
  `provider_factory(agent.provider, agent.model)` 构造**本轮** provider，**不改会话**的
  provider/model（右上角模型选择器不受影响，发完这条消息会话还是原模型）；
- 发图 vision 门控同样按**生效模型**判定；agent 指定的模型没配 key → 400
  `「agent ×× 指定的 glm-coding 未配置 API key，请先到设置页填写」`；
- 前端 `visionSupported` 门控按会话模型计算，agent 覆盖时会失准——接受现状：后端 400 兜底
  （现有链路已有该兜底），前端错误信息原样展示（§7 改进点 4）。

### 3.5 agent loop 透传（`chat/agent.py`）

`run_agent_chat(...)` 加 `agent: dict | None = None` 参数，取 `agent["name"]/["prompt"]`
传给 `build_system_prompt`；其余零改动（工具表、SSE、落库均不变）。

---

## 4. 前端改动

### 4.1 类型与数据源

- `types.ts` 加 `Agent` 接口（字段同 §2.2）；
- 新建 `stores/agents.ts`（zustand）：`agents / load() / add / update / remove`——
  **ChatPage 与 SettingsPage 共用同一份**，设置页增删改后聊天页菜单即时可见（无需刷新）；
  数据加载用 promise 链（house rule：react-hooks v7 的 `set-state-in-effect`）。

### 4.2 `ChatInput.tsx`：`/` 菜单（本次唯一的交互难点）

保持 textarea 非受控现状，加一个轻量菜单状态：

```tsx
const [menu, setMenu] = useState<{ open: boolean; query: string; active: number } | null>(null)
```

- `onInput` / `onKeyDown` 里计算光标前文本：`/^\/(\S*)$/.test(el.value.slice(0, el.selectionStart))`
  命中且 `agents.length > 0` → 打开菜单、`query = $1`；条件破坏（空格、删光、光标移走）→ 关闭；
- 新组件 `AgentMenu`（可放同文件）：绝对定位在输入容器上方，渲染过滤结果 + 高亮项 + 悬停/点击；
- `handleKeyDown` **菜单打开时优先拦截** `↑ ↓ Enter Tab Escape`（`preventDefault`），全部带
  `!e.nativeEvent.isComposing` 守卫；其余按键走现有逻辑；
- 选中：`el.value = value.slice(0, tokenStart) + '/' + name + ' ' + value.slice(caret)`，设光标、
  关菜单、`el.focus()`、重跑 autoSize；
- props 增加 `agents: Agent[]`（ChatPage 从 `stores/agents.ts` 取）。

**不改 `stores/chat.ts` 的 sendMessage**：发送的 `content` 本身就带 `/名称 ` 前缀，后端解析——
乐观渲染、SSE、落库全链路零改动。

### 4.3 `SettingsPage.tsx`：新增「自定义 Agent」GlassPanel

位置放在「外部工具（MCP）」面板之后（同为「扩展 Kate 能力」类目），lucide `Bot` 图标：

- **列表区**：每个 agent 一行卡片（复用 MCP 卡片版式）——`/名称` + 描述 + 模型 chip +
  启用 ToggleSwitch + 编辑 + 删除（`window.confirm` 确认，文案提示「历史消息里的 /名称 将回落默认 Kate」）；
- **编辑**：行内展开表单（不引入 modal 体系），字段 = 新增表单复用；
- **新增表单**（面板底部，对齐 MCP 的行内新增）：名称 / 描述 / 提示词 textarea /
  可选「指定模型」（provider 下拉复用 `PROVIDERS` 常量 + model 自由输入，提示「留空跟随会话模型；
  需已配置对应 Key」）/ 添加按钮；
- 校验错误（422/409）经 `toast.error` 展示后端 detail（与 MCP 一致）。

---

## 5. 测试

**后端**（`backend/tests/`，pytest，基线 342 通过后追加）：

- agents CRUD：建/查/改/删、重名 409、name 字符集与长度 422、provider 非法 422、
  多用户目录下互不可见（沿用现有 multiuser 测试手法）；
- `resolve_agent`：命中 / 不命中 / 停用 / 已删除 / 无前缀 / 恰好含 `/` 的 URL 正文；
- system prompt：注入后 PERSONA 后出现角色段、工具规则仍在；无 agent 时与现状逐字节一致（回归）；
- chat 路由：带前缀发消息 → prompt 含 agent 段（fake provider 断言 messages[0]）；agent 指定
  未配 key 的 provider → 400；regenerate / resend 继承解析；标题不含 `/名称`；
- 预设种子：全新库 `GET /api/agents` 返回含「私人生活医生」；删除后重新加载不复活
  （DEFAULTS 种子语义，见 §8.2）。

**前端**（vitest，基线 25 通过后追加）：

- `AgentMenu`：过滤（name/description）、↑↓ 高亮循环、Enter/Tab 选中后输入框内容与光标、
  Esc 关闭、无匹配占位；
- `ChatInput`：菜单打开时 Enter 不发送（`isComposing` 时也不选中不发送）；
- SettingsPage agent 面板：新增/编辑/删除走 mock api 后列表刷新（`vi.hoisted` mock 手法）。

---

## 6. 文档同步（收尾提交）

- `docs/DESIGN.md`：§4.1 端点表加 `/api/agents`；§6.2 system prompt 构成补「agent 角色段」；
  §8.1 页面组件补 AgentMenu 与设置页 Agent 面板；
- `README.md` 核心特性加一条「自定义 Agent：设置页创建专属助手，聊天输入 `/` 一键引用」。

---

## 7. 评审要点 & 顺带发现的改进点

**需要拍板的决策**（文档按推荐项撰写，可改）：

1. **agent 是否可指定模型** → 推荐「是，可选成对字段，请求级生效不落会话」。成本可控
   （provider_factory 本就按 (provider, model) 构造），收益明显（如「编程助手」绑 glm-coding）。
   若想再砍，v1 可只做 prompt；
2. **`/名称` 前缀保留在消息里** → 推荐保留（自描述、regenerate/resend 天然继承、零 schema 改动）。
   代价是模型输入里也带前缀——实测语义干扰可忽略；若在意，可在 `_history_messages` 里对
   命中 agent 的历史消息剥前缀（一行事，列为后续可选项）；
3. **agent prompt 与默认人设的关系** → 推荐叠加覆盖（角色段优先），工具规则永不裁剪。

**本次必须一并处理的点**（都是实现时容易踩的）：

1. **`Enter` 冲突**：菜单打开时 Enter 必须选中而非发送——现 `handleKeyDown` 里 Enter 直接
   `submit()`，需在菜单分支提前 return；且 IME 组合期间的 Enter（确认候选）两者都不能触发
   （中文 agent 名必踩）；
2. **placeholder 与空态文案**：没有 agent 时 `/` 不弹菜单，placeholder 补「输入 / 引用 agent」
   的前提提示，设置页空态引导「创建第一个 agent」；
3. **`ensure_title` 剥前缀**：否则新会话标题以 `/翻译官` 开头（`routes/chat.py:147`）；
4. **vision 门控失准**：agent 覆盖模型后，前端按会话模型算的 `visionSupported` 不准——接受
   后端 400 兜底，但 400 文案在 agent 生效时应指名 agent 指定的模型（§3.4 已含）；
5. **菜单与 autoSize 共处**：菜单 absolute 定位不占流，textarea 自动增高不顶飞菜单；
   点击菜单项用 `onMouseDown + preventDefault` 防止 textarea blur 抢先关菜单；
6. **重名与更名的回落语义**：历史消息里的旧前缀在 agent 更名/删除后回落默认 Kate——交互上
   可接受（消息正文语义还在），删除确认文案要说明。

**明确不做（v1 边界）**：agent 级 RAG/记忆开关（跟随全局）；agent 导入导出；vault 导入合并
agents（settings 不在导入范围，与 MCP 同现状）；`@` 式正文任意位置引用（`/` 锚定输入起点已够用，
且避免 URL 误触）；对标阿福生态里的挂号 / 医保咨询 / 真人医生在线转接 / 医院推荐（超出 Kate
定位，「私人生活医生」只给就医科室与紧急程度指引）。

---

## 8. 首个内置预设：私人生活医生（对标蚂蚁阿福）

> 2026-09-13 评审增补：功能上线后第一个可用的 agent 要是「私人生活医生」——具备专业医疗
> 知识，解答用户提到的医疗问题，并像真实医生看病一样**先反问、确认病症，再给治疗方案**。
> 交互对标蚂蚁阿福（蚂蚁集团 AI 健康助手，2025-12 由 AQ 升级而来，月活 3000 万+）的「AI 诊室」。

### 8.1 从阿福对标什么

| 阿福的做法 | Kate 的落地 |
|---|---|
| 引入真实临床诊疗思路，以**结构化多轮主动追问**替代简单问答（围绕病史、症状细节、用药情况） | §8.3 问诊流程：主诉 → 追问 → 复述确认 → 分级意见 |
| 追问时让用户**勾选不舒服的部位**（选项式采集，降低表达负担） | 提问规范：一次 ≤3 问、能给选项就给选项（「疼了几天？A 1-2 天 B 3-7 天 C 更久」） |
| **个人健康档案**贯穿问诊与健康陪伴 | 直接复用 Kate 自动记忆：过敏史 / 慢病 / 长期用药本就是工具规则要求沉淀的「耐久事实」，问诊前 recall_memory 先翻档案 |
| 拍照识别解读**化验单 / 体检报告 / 药盒 / 皮肤照片** | 视觉模型下走现有多模态链路（把该 agent 指定为带视觉的模型即可，见 §3.4） |
| 明确「AI 回答并非医疗诊断」，严肃需求**转真人医生** | 免责声明一句 + 红旗症状强制就医指引；**不做**挂号 / 医保 / 真人转接 / 医院推荐（§7 不做清单） |
| **健康陪伴**（日常健康管理） | 「生活医生」第二职责：睡眠 / 饮食 / 运动 / 慢病监测 / 体检解读 |

> 参考：[蚂蚁阿福官网](https://chat.antafu.com/) ·
> [蚂蚁集团：AQ 升级为蚂蚁阿福](https://www.antgroup.com/news-media/press-releases/1765785600000) ·
> [人民日报：AI 健康开出更多「良方」（多轮主动追问）](https://paper.people.com.cn/rmrbhwb/pc/content/202603/16/content_30145443.html) ·
> [产品拆解：蚂蚁阿福如何重构就医体验](https://www.woshipm.com/ai/6319148.html)

### 8.2 交付形态：DEFAULTS 种子，而非硬编码功能

`settings.py` 的 `DEFAULTS["agents"]` 初始列表直接带这个 agent：没动过 agent 列表的库
（含存量库，`get_all` 以 DEFAULTS 兜底）自动获得；用户对 agent 列表做任何增删改后列表整体
持久化、以库内为准——**删了就是删了，不复活**。它与用户自建 agent 完全同权，设置页可
编辑 / 停用 / 改名 / 删除。

- **name**：`私人生活医生`（名称即 `/` 引用 token；嫌长可自行改成「医生」，改名不影响行为）
- **description**：`像真实医生一样问诊：先反问确认症状，再给居家处理与就医指引`
- **provider / model**：留空（跟随会话模型；想解锁拍报告解读，把它指定成带视觉的模型即可）
- 提示词以 Python 常量随代码分发（放 `settings.py` 或独立 `agent_presets.py`）

### 8.3 预设提示词全文

```text
你是「私人生活医生」，用户的私人健康顾问：具备三甲医院全科医生的医学素养，说话温和、
通俗、有条理。你有两项职责：一是像真实门诊医生一样问诊与解答医疗问题，二是作为生活
医生管理用户的日常健康（睡眠、饮食、运动、慢病、体检）。

## 问诊流程（用户描述身体不适时）
1. 先判断信息量：主诉、病程、伴随症状已经充分 → 直接进入第 3 步；不充分 → 先追问。
2. 像医生看病一样结构化反问（一次最多 3 个问题，能选项化就选项化）：
   - 症状本身：部位、性质（胀痛/刺痛/绞痛，持续/阵发）、程度（0-10 打几分）、
     起病时间与变化趋势；
   - 诱因与缓解因素：吃了什么、做了什么、怎么才能缓解；
   - 伴随症状：发热、恶心、乏力等；
   - 背景：既往病史、过敏史、正在用的药（先查记忆档案，查不到再问）；年龄与特殊人群
     （孕期/哺乳期、儿童、老人、慢性病患者必问）。
3. 复述确认：「我理解你的情况是……对吗？」得到确认或纠正后才给意见。
4. 给出分级意见，固定四块、结论先行：
   - 可能方向：2-3 个按可能性排序，各用一句通俗的话解释，并明确说「这不是确诊」；
   - 居家处理：护理要点 + 非处方药参考（给通用用法并提醒以说明书为准；绝不给处方药的
     具体用药方案）；
   - 就医指引：什么情况必须去医院（红旗症状逐条列出）、建议挂的科室、就诊前准备；
   - 观察与随访：几天内无好转、或出现什么变化时需要就医。

## 安全红线（优先级高于以下一切）
- 红旗症状（胸痛、呼吸困难、意识模糊或晕厥、剧烈头痛、抽搐、大出血、高热不退、
  儿童精神萎靡、孕期出血等）：首句立即提醒拨打 120 或去急诊，再给等待期注意事项，
  不走完整问诊流程。
- 不下确诊结论，不开发方，不替用户做「吃/不吃药」的强制决定，只给循证建议与决策依据。
- 精神心理困扰（自伤念头、长期情绪低落）：先温和接住情绪，建议精神科/心理门诊，
  主动提供心理援助热线等求助渠道。
- 涉及用药与诊断意见的回复，末尾附一句：「以上为健康建议，不能替代执业医师的当面诊断」。
- 用户的过敏史、慢性病、长期用药属于耐久事实，按工具规则存入记忆；给方案前先回忆档案，
  主动规避已知过敏与常见相互作用（如「你在长期服 X，注意别与 Y 同服」）。

## 日常健康管理（用户聊到睡眠/饮食/运动/体检/慢病时）
- 以生活顾问口吻给可执行的小步建议（具体到做什么、什么频率），不堆砌养生术语；
- 慢病用户（高血压、糖尿病等）关注监测数据的规律，异常值按红旗思路提示就医；
- 用户发来体检报告/化验单/药盒照片时：先客观读出关键指标，再逐项通俗解释并给下一步
  建议；看不清或不确定的指标如实说明，不编造。

## 语气
- 通俗不吓人：既不轻描淡写也不制造焦虑；坏消息直说，但永远跟着给出路；
- 一次说清楚一件事，分块小标题，不一次倒十条例行公事；
- 明确的一次性科普问题（如「孕妇能喝咖啡吗」）直接回答，不触发问诊反问。
```

### 8.4 验收脚本

1. **问诊闭环**：「我最近头疼」→ 一次 ≤3 问地反问（部位/性质/病程/伴随/用药史），复述确认后
   输出四块：可能方向（按可能性排序、注明非确诊）+ 居家处理 + 就医指引（红旗清单 + 挂号
   科室）+ 观察期建议；
2. **红旗升级**：「胸口剧烈疼痛，喘不上气」→ **首句**提醒拨打 120 / 急诊并给等待期注意事项，
   不走完整问诊流程；
3. **科普直答**：「孕妇每天最多能喝多少咖啡」→ 直接作答，不触发问诊反问；
4. **档案联动**：先说「我对青霉素过敏」（记忆沉淀），再问「嗓子发炎吃什么药」→ 回答主动
   避开青霉素类并提及已知过敏史；
5. **日常管理**：「最近总失眠」→ 生活顾问口吻给可执行的睡眠建议，与问诊语气区分开。

---

## 9. 实施顺序与提交切分

| # | 内容 | 涉及 | 提交文案 |
|---|---|---|---|
| 1 | 后端 agents CRUD + 校验 + 测试 | `settings.py`(DEFAULTS) · `models.py` · `routes/agents.py` · `main.py` · tests | `feat: agents CRUD (/api/agents, settings["agents"] 存储)` |
| 2 | 后端对话链路注入 + 测试 | `chat/prompts.py` · `chat/agent.py` · `routes/chat.py`(resolve_agent ×3 路径 + 模型覆盖 + 标题剥前缀) · tests | `feat: /名称 前缀引用 agent：system prompt 角色段 + 请求级模型覆盖` |
| 3 | 前端设置页 Agent 模块 | `types.ts` · `stores/agents.ts` · `SettingsPage.tsx` · tests | `feat: 设置页「自定义 Agent」模块（增删改查/启停/指定模型）` |
| 4 | 前端 `/` 引用菜单 | `ChatInput.tsx`(AgentMenu + 键盘/IME) · `ChatPage.tsx`(接 agents store + placeholder) · tests | `feat: 聊天输入 / 弹出 agent 菜单（对标 ZCode slash 交互）` |
| 5 | 文档同步 | `DESIGN.md` · `README.md` · 本文档状态行 | `docs: 自定义 agent 设计与端点入册` |
| 6 | 内置预设「私人生活医生」 | `settings.py`（DEFAULTS 种子 + prompt 常量）· tests（种子/删除持久化）· §8.4 人工验收 | `feat: 内置「私人生活医生」预设 agent（阿福式问诊提示词）` |

每步收尾复跑基线：`cd backend && uv run pytest`；
`cd frontend && pnpm typecheck && pnpm lint && pnpm test`。

**预估工作量**：#1、#3 各约半天；#2、#4 各约一天（#4 含交互细节打磨）；#5 半小时内；
#6 半天（主要花在提示词打磨与 §8.4 验收脚本的实测调整）。
