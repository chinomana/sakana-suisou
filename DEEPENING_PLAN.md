# Fugu Vibe CLI 深化方案：从原型到重型开发利器

> 版本：v0.1 → 目标：Terminal-Bench 2.1 竞争力级 CLI  
> 对标参考：Claude Code (v2.1.88)、OpenAI Codex CLI、OpenHands、Aider  
> 评估日期：基于 2026-06-29 代码快照

---

## 一、现状总览：一个扎实的原型

当前 `fugu-vibe-cli` 是一个**结构清晰、意图明确**的 Alpha 级 CLI，具备以下核心能力：

| 维度 | 当前状态 | 代码位置 |
|---|---|---|
| API 接入 | 完整支持 Sakana Fugu Responses API + Chat Completions API，流式解析正确 | `api/client.py`, `api/stream_parser.py`, `api/request_builder.py` |
| 交互会话 | 基于 `prompt_toolkit` 的 REPL，支持附件、slash 命令 | `cli/commands/vibe.py` |
| 基础文件工具 | 5 个工具暴露给模型：`file_list`, `file_read`, `file_search`, `file_write`, `file_mkdir` | `agent/registry.py` |
| 终端执行 | 人工 `/terminal` 命令，手动审批，安全策略基础 | `tools/terminal.py` |
| 补丁管理 | 捕获模型输出中的 diff，人工 `/apply` 审批 | `core/patch_capture.py`, `tools/patch.py` |
| 任务编排 | 基于 DAG 的异步任务队列，git worktree 隔离，自动合并 | `core/task_manager.py`, `utils/git.py` |
| 流式可视化 | 事件总线 + Rich 仪表盘（可选，独立终端） | `ui/dashboard.py`, `ui/components.py` |
| 配置系统 | 5 级配置层级（CLI → 环境变量 → 项目 → 用户 → 默认），Pydantic 强类型 | `config/settings.py` |
| 会话管理 | 本地 markdown 日志 + 上下文持久化 + 基础 compaction | `core/session_output.py`, `context/manager.py` |
| 语音输入 | 骨架代码，未实际可用 | `voice/` |

**核心代码规模**：约 40 个文件，核心逻辑约 2,500–3,000 行。架构上采用**分层设计**（CLI → Core → API → External），事件驱动解耦，代码质量良好。

---

## 二、对标分析：顶级 CLI 的标杆能力

### 2.1 对标矩阵

| 能力维度 | Claude Code (v2.1.88) | Codex CLI (Rust) | OpenHands | 当前 fugu-vibe | 差距等级 |
|---|---|---|---|---|---|
| **内置工具数量** | 54 个（19 常驻 + 35 条件） | 约 30+ | 20+ | 5 个文件工具 + 终端 | 🔴 严重 |
| **MCP 扩展** | 原生支持，工具池动态组装 | 支持 `~/.codex/config.toml` | 有限 | ❌ 无 | 🔴 严重 |
| **代码编辑能力** | 结构化编辑（替换/插入/删除），非全量覆盖 | 智能编辑 | 文件写入 | 仅 `file_write`（全量覆盖） | 🔴 严重 |
| **权限系统** | 7 模式 + ML 自动分类器 + 按命令审批 | 审批模式 | 基础审批 | 终端 `off/ask/auto-safe`；文件工具无审批 | 🟡 中等 |
| **Hooks 生命周期** | PreToolUse / PostToolUse / SessionStart 等 | 有限 | 无 | ❌ 无 | 🟡 中等 |
| **Skills 系统** | `.claude/skills/` 可复用方法论 | `AGENTS.md` | 自定义 prompt | ❌ 无 | 🟡 中等 |
| **上下文压缩** | 5 层管道（Snip → Microcompact → Collapse → Auto-Compact） | 基础 | 手动 | 仅本地摘要 compaction | 🔴 严重 |
| **Subagent 委托** | 原生支持，隔离上下文窗口 | 支持 | 多 agent | ❌ 无 | 🟡 中等 |
| **Session Checkpoints** | 自动快照，可恢复 | 无 | 无 | ❌ 无 | 🟡 中等 |
| **Sandbox 执行** | 可选沙箱，工作区隔离 | 基础 | Docker 隔离 | 仅 git worktree | 🟡 中等 |
| **测试/验证闭环** | 自动运行测试，失败反馈循环 | 有限 | 支持 | 无自动测试集成 | 🟡 中等 |
| **Web 抓取** | 内置 WebFetch 工具 | 基础 | 支持 | 仅 API 级 `web_search` | 🟡 中等 |
| **代码库索引** | 无原生索引，依赖文件工具 | 无 | 无 | 无 | 🟢 轻微（Fugu 上下文大） |
| **可视化** | 终端内嵌，实时流 | 终端流 | Web UI | Rich 仪表盘（独立终端） | 🟡 中等 |
| **Voice** | 无 | 无 | 无 | 骨架，不可用 | 🟡 中等 |
| **Headless / CI** | `claude-p` 模式，SDK 暴露 | 支持 | 支持 | `submit` 基础，无 headless | 🟡 中等 |
| **插件系统** | 4 层机制（Hooks → Skills → Plugins → MCP） | 基础 | 插件架构 | ❌ 仅架构图 | 🔴 严重 |

### 2.2 关键差距深度解读

#### 🔴 G1: 工具贫乏（Tool Poverty）—— 最大瓶颈

当前模型仅有 5 个文件工具可用。重型开发任务需要**至少 15–20 个精心设计的工具**才能覆盖：

- **文件操作**：`read`（✓）, `write`（✓但全量）, `edit`（✗——最关键缺失）, `list`（✓）, `search`（✓但仅字面量）, `grep`（✗——正则搜索）, `glob`（✗）
- **代码操作**：`read_code`（✗——AST/符号感知）, `edit_code`（✗——结构化替换）, `delete`（✗）
- **Shell 执行**：`bash`（✗——模型可调用的自动执行，非人工 `/terminal`）, `run_test`（✗）, `run_linter`（✗）
- **Git 操作**：`git_status`（✗）, `git_diff`（✗——仅人工查看）, `git_commit`（✗）, `git_log`（✗）
- **网络**：`web_fetch`（✗——抓取具体 URL）, `web_search`（✓）
- **项目管理**：`read_todo`（✗）, `write_todo`（✗）

> **为什么这是最大瓶颈**：Fugu 是 multi-agent 模型，其内部编排能力（routing、worker 分配、verification）只有在**工具丰富**时才能发挥。工具贫乏时，模型被迫用长文本输出代替精确操作，导致幻觉率高、应用困难。

#### 🔴 G2: 无结构化编辑（No Structured Editing）

当前 `file_write` 是**全量覆盖**。这是 Agent CLI 的**致命缺陷**之一：
- 模型必须输出整个文件内容，浪费 token
- 容易破坏未修改部分（上下文丢失导致）
- 无法做局部修改（如"把函数 A 的参数从 int 改为 str"）

顶级 CLI 都提供 `edit` 工具，支持：
```json
{
  "old_string": "def foo(x: int):",
  "new_string": "def foo(x: str):"
}
```
或更强大的基于行号/AST 的编辑。

#### 🔴 G3: 无 MCP 支持（Missing MCP）

MCP (Model Context Protocol) 已成为**事实标准**。Claude Code、Codex CLI、Goose、Cline 都支持。MCP 让 CLI 可以：
- 连接数据库、API、文档系统
- 复用社区工具（如浏览器自动化、Slack 通知）
- 团队共享自定义工具集

无 MCP = 封闭系统，无法借力生态。

#### 🔴 G4: 上下文管理初级（Primitive Context Management）

当前 compaction 仅将旧对话转为本地摘要。对比 Claude Code 的 5 层管道：
1. **Snip** - 截断早期消息
2. **Microcompact** - 基于规则的轻量压缩
3. **Context Collapse** - 结构化提取关键信息
4. **Auto-Compact** - LLM 驱动的智能压缩
5. **CLAUDE.md 层级** - 项目级上下文注入

长程重型任务中，**上下文管理质量 = 成功率**。当前方案在 10+ 轮后会出现严重的上下文漂移。

#### 🟡 G5: Agent Loop 过于简单

当前 `AgentLoop` 是一个 `while` 循环，固定 `max_tool_rounds=3`。缺乏：
- **重试策略**：工具失败时无自动重试/回退
- **错误恢复**：API 异常终止整个会话
- **计划模式**：执行前无显式任务分解
- **并行工具调用**：当前是串行执行

#### 🟡 G6: 安全与治理薄弱

- 文件工具**无审批**直接执行（模型可随意写入/覆盖文件）
- 无**权限模式**（Claude Code 有 7 种：auto-edit-only、ask-execute、auto-execute 等）
- 无**session checkpoint**（无法回滚到安全状态）
- 终端执行是**人工命令**而非模型自动执行，限制了自主性

#### 🟡 G7: 无测试/验证闭环

重型开发 = 写代码 + 运行测试 + 分析失败 + 修复。当前 CLI：
- 无自动测试触发
- 无 lint/typecheck 自动运行
- 无"修复失败测试"的闭环工作流

---

## 三、深化方案：五阶段施工路径

基于**影响/依赖排序**（先解决阻塞瓶颈，再增强体验），分为 5 个阶段：

### Phase A: 工具层补全（解决 G1/G2/G7）—— 最高优先级

**目标**：让模型具备精确操作代码库的能力，这是重型开发的基础。

**A1. 核心编辑工具 `edit`（必须最先实现）**
- 实现 `file_edit` 工具：支持 `old_string`/`new_string` 替换
- 实现 `file_delete` 工具：删除文件
- 扩展 `file_read`：支持行号范围读取，返回带行号的内容
- 扩展 `file_search`：支持正则表达式搜索（`grep`）
- 新增 `file_glob`：按模式批量发现文件

**A2. Shell 执行工具自动化（将终端从人工变为模型工具）**
- 新增 `bash` 工具：模型可调用的 shell 执行
- 安全策略：命令分类器（safe/unsafe/ask），自动执行白名单命令（`git status`, `pytest`, `npm test` 等），危险命令需人工确认
- 超时控制、输出截断、工作区逃逸检测
- 废弃当前纯人工的 `/terminal` 命令（或降级为 fallback）

**A3. Git 工具集**
- 新增 `git_status`, `git_diff`, `git_log`, `git_show` 工具
- 可选 `git_commit`（需配置策略）
- 让模型能感知代码变更状态

**A4. 测试/验证闭环**
- 新增 `run_test` 工具：配置测试命令（`pytest`, `npm test`, `cargo test`），自动运行
- 新增 `run_lint` 工具：运行 linter（`ruff`, `eslint`, `clippy`）
- 结果自动注入对话上下文，驱动修复循环

**A5. 任务/计划工具**
- 新增 `read_todo` / `write_todo`：模型可读写任务清单
- 新增 `plan_task`：显式任务分解（可选，增强可解释性）

**A6. Web 抓取**
- 新增 `web_fetch`：抓取具体 URL 内容（区别于 `web_search`）

> **A 阶段验收标准**：模型可用工具 ≥ 15 个，能完成"修改某个函数并运行测试验证"的完整闭环，无需人工介入执行命令。

---

### Phase B: 上下文与记忆升级（解决 G4）

**目标**：支持长程任务（50+ 轮）不丢失上下文。

**B1. 多层级上下文注入（CLAUDE.md 模式）**
- 自动检测并加载工作区 `.fugu-vibe.md` / `.fugu/skills/*.md`
- 层级：工作区级 → 项目级 → 用户级 → 系统级
- 内容注入到系统 instructions 或初始 context

**B2. LLM 驱动的智能 Compaction**
- 将当前本地摘要替换为**基于 LLM 的压缩**：
  - 提取关键决策、已确认的事实、待办事项
  - 保留最近 N 轮完整对话，更早的压缩为结构化摘要
- 压缩触发条件：token 阈值 / 轮数阈值 / 用户命令 `/compact`

**B3. 代码库快照（轻量级索引）**
- 可选：维护文件树摘要（每个文件的摘要 + 符号列表）
- 模型可通过 `file_search` 快速定位相关文件
- 考虑 Tree-sitter 轻量集成（仅索引，不依赖）

**B4. 跨会话记忆**
- 将 `.fugu-vibe/context/current.json` 升级为结构化记忆
- 记录：项目约定、常见错误、已确认的设计决策
- 新会话自动加载相关记忆

> **B 阶段验收标准**：完成 30 轮对话的复杂重构任务后，模型仍能准确知道最初的设计约束和未完成的待办。

---

### Phase C: 安全与治理（解决 G6）

**目标**：让 CLI 能无人值守运行重型任务，同时保证安全。

**C1. 权限模式系统**
- 实现 4 级模式：
  - `ask`：所有写入/执行前确认（默认）
  - `auto-safe`：白名单命令自动执行，其他确认
  - `auto-edit`：文件编辑自动，执行确认
  - `auto`：全部自动（仅推荐在 CI/已知任务）
- 配置文件 `[safety] mode = "ask"`

**C2. 命令分类器**
- 基于正则 + 启发式的命令安全分类：
  - `safe`：`git status`, `pytest`, `ls`, `cat`
  - `edit-safe`：`sed`, `perl -pi`（但有限制）
  - `unsafe`：`rm -rf`, `curl | sh`, `sudo`, `chmod 777`
- 分类器可配置扩展

**C3. Session Checkpoints**
- 每 N 轮或每次文件写入后自动 `git commit`（类似 Aider 的 micro-commits）
- 提供 `/checkpoint` 命令手动保存
- 提供 `/undo` 回滚到上一 checkpoint
- 仪表盘显示 checkpoint 历史

**C4. 审批 UI**
- 文件写入前显示 diff 预览（类似 `git diff --cached`）
- 终端内确认：`Apply this change? [y/n/d(iff)]`
- 批量模式：一次审批多个同类操作

> **C 阶段验收标准**：运行 10 轮自主重构任务，中间无需人工干预，所有修改可回滚。

---

### Phase D: Agent Loop 增强（解决 G5）

**目标**：让 Agent 更智能、更自主、更可靠。

**D1. 重试与错误恢复**
- 工具失败时自动重试（配置 `max_retries`）
- API 异常时优雅降级（切换 endpoint、重试、保存状态）
- 流式中断后恢复（已部分实现，需增强）

**D2. 计划模式（Planning Mode）**
- 新增 `/plan` 命令：先让模型输出任务分解计划，人工确认后执行
- 或自动模式：复杂任务（>3 文件变更）自动触发计划步骤
- 计划作为结构化 todo 注入上下文

**D3. 并行工具调用**
- Fugu API 支持 `parallel_tool_calls`，当前 AgentLoop 串行执行
- 重构为并行 dispatch：多个 `file_read` 同时执行
- 结果聚合后统一返回模型

**D4. 子任务委托（轻量级 Subagent）**
- 利用 Fugu 的 multi-agent 特性，通过 `instructions` 参数实现轻量委托
- 或本地实现：复杂任务拆分为子任务，由 TaskManager 调度
- 每个子任务有独立上下文，结果合并

**D5. 智能循环终止**
- 当前固定 `max_tool_rounds=3`
- 改进为：检测到"完成"信号（如模型说"完成"、无新工具调用）时终止
- 或超时/预算控制

> **D 阶段验收标准**：模型能自主完成 5 文件以上的跨模块重构，包含测试、修复、验证。

---

### Phase E: 可视化与扩展性（解决 G3 + 体验）

**目标**：提供一流开发体验，开放扩展生态。

**E1. MCP 协议支持**
- 实现 MCP Client：连接外部 MCP Server
- 工具动态加载：`fugu-vibe mcp add <server>`
- 工具池动态组装（类似 Claude Code 的 `assembleToolPool`）
- 工具 schemas 缓存与懒加载

**E2. 仪表盘增强**
- 当前仪表盘仅读取 `events.jsonl`，无法实时渲染流式内容
- 方案：将仪表盘改为**WebSocket / 共享内存**模式，与主会话实时同步
- 或：内置终端内分屏模式（tmux-style 或 Rich 的 split）
- 新增：代码 diff 预览、文件树变更视图、测试状态面板

**E3. Skills 系统**
- `.fugu/skills/` 目录：可复用 prompt 模板
- 格式：YAML frontmatter + markdown 内容
- 示例：`python-refactor.md`, `api-design.md`, `test-driven.md`
- 用户 `/skill <name>` 加载，自动注入 instructions

**E4. Hooks 系统**
- 生命周期钩子（shell 脚本或可执行文件）：
  - `pre-tool-use`：审批、修改参数
  - `post-tool-use`：日志、lint、通知
  - `session-start`：加载自定义上下文
- 接收 JSON on stdin，返回 JSON 修改行为

**E5. Headless / SDK 模式**
- `fugu-vibe run --script task.md`：非交互式执行
- 返回结构化结果（JSON exit code）
- 适合 CI/CD 集成

**E6. 语音（可选降级）**
- 鉴于语音实现复杂度高，建议**暂不投入**，或外包为可选插件
- 当前占位代码可保留，标记为 `experimental`

> **E 阶段验收标准**：能通过 MCP 连接数据库工具，Skills 可复用，仪表盘实时展示代码变更。

---

## 四、实施优先级与依赖关系

```
Phase A (工具层) ──→ Phase B (上下文) ──→ Phase D (Agent Loop)
     │                    │                   │
     │                    │                   │
     └────────────────────┴───────────────────┘
                          │
                          ▼
                   Phase C (安全治理)
                          │
                          ▼
                   Phase E (MCP/可视化/扩展)
```

**为什么是这个顺序**：
1. **A 必须先于 B/C/D**：没有足够工具，上下文再好也无用武之地；安全治理需要工具作为治理对象
2. **B 与 D 可并行**：上下文管理是独立模块，Agent Loop 增强不依赖 B（但 B 能提升 D 的效果）
3. **C 在 A 之后**：安全是对工具的治理，无工具则无需治理
4. **E 最后**：MCP 和可视化是体验增强，不影响核心功能；且 MCP 需要稳定工具层作为基础

---

## 五、技术选型建议

| 需求 | 建议方案 | 理由 |
|---|---|---|
| 代码编辑 | 自研 `old_string`/`new_string` 编辑 + 行号编辑 | 无需依赖，Aider/Codex 已验证 |
| 正则搜索 | 自研 `ripgrep` 封装 | 系统通常已安装，性能极好 |
| AST 感知 | Phase B 后引入 Tree-sitter（可选） | 不是阻塞需求，Fugu 上下文大 |
| MCP Client | 自研 SSE/stdio 传输层 | 协议简单，Python 生态不成熟 |
| 沙箱 | 可选 Docker / 默认 git worktree | 与 OpenHands 一致，务实 |
| 仪表盘 | Rich Live + 共享 JSONL → 后期 WebSocket | 渐进增强 |
| 压缩 | 调用 Fugu API 做 LLM 压缩 | 利用模型能力，成本可控 |

---

## 六、验收基准

| 阶段 | 验收测试 | 通过标准 |
|---|---|---|
| A | 给模型任务："将 `auth.py` 中的 `login()` 函数改为异步，并运行测试验证" | 模型自动：`read` → `edit` → `bash(pytest)` → 失败 → `read` 测试 → `edit` 修复 → `bash(pytest)` → 通过。全程无人工 `/terminal` 输入。 |
| B | 完成 20 轮对话后，问模型："最初我们为什么要改 `auth.py`？" | 模型准确回答原始动机。 |
| C | 运行任务，中间触发一次 `rm -rf` 类危险命令 | 被拦截，用户收到确认请求；`/undo` 可回滚所有文件变更。 |
| D | 任务："重构认证模块，影响 login、logout、register 三个函数，确保所有测试通过" | 模型自动分解计划，并行读取文件，顺序编辑，运行测试，失败则修复，最终通过。 |
| E | 连接一个 MCP Server（如文件系统），通过 `fugu-vibe mcp add` | 新工具出现在模型可用工具列表中，可被调用。 |

---

## 七、风险与规避

| 风险 | 影响 | 规避策略 |
|---|---|---|
| 工具过多导致上下文膨胀 | 🔴 高 | MCP 工具懒加载；内置工具仅激活模型实际使用的；Skills 按需注入 |
| 编辑工具产生错误 patch | 🔴 高 | 编辑前自动 `read` 验证 `old_string` 匹配；不匹配时返回错误供模型重试 |
| 自主执行导致数据丢失 | 🔴 高 | 强制 checkpoint（git commit）在每次写入前；默认 `ask` 模式 |
| Fugu API 变更 | 🟡 中 | 抽象 API 层（已做），配置兼容版本切换 |
| 长任务 token 成本失控 | 🟡 中 | 预算告警；token 使用实时显示；任务级预算上限 |
| 复杂度增长导致维护困难 | 🟡 中 | 严格模块化（当前已好）；每阶段后重构；测试覆盖率要求 |

---

## 八、总结

当前 `fugu-vibe-cli` 的**架构骨架优秀**，但**肌肉（工具层）和神经系统（上下文管理、安全治理）尚未发育**。对标 Claude Code + Fable 5 的 83.1% Terminal-Bench 2.1 成绩，核心差距在于：

1. **工具数量不足**（5 vs 54）且**缺少结构化编辑**
2. **无安全治理**，无法无人值守
3. **上下文管理初级**，长程任务漂移严重
4. **无 MCP 扩展**，封闭生态

**五阶段施工路径**按依赖排序：
- **A（工具层）** 解决"能不能做"的问题
- **B（上下文）** 解决"做久了还记不记得"的问题
- **C（安全）** 解决"敢不敢放手让它做"的问题
- **D（Agent Loop）** 解决"做得聪明不聪明"的问题
- **E（扩展）** 解决"能不能融入生态"的问题

按此方案逐步实施，预计 **Phase A+B 完成后**即可承担中型开发任务，**Phase C+D 完成后**可对标重型任务（打平主流开源 CLI），**Phase E 完成后**具备生态竞争力。

---

*方案生成时间：2026-06-29*  
*基于代码版本：v0.1.0*  
*核心参考：Claude Code v2.1.88 架构分析、Codex CLI、OpenHands、Aider、Terminal-Bench 2.1  leaderboard*
