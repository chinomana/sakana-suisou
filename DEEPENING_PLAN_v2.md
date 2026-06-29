# Fugu Vibe CLI 深化方案（修订版 v2）

> 综合 Fugu 模型特殊性后的差异化深化方案  
> 核心洞察：**Fugu 是厚编排黑箱模型，CLI 不应做传统编排，而应做精良的工具层与状态持久化**  
> 修订日期：2026-06-29

---

## 一、关键发现：Fugu 不是传统模型，是编排即服务

### 1.1 Fugu 的架构特殊性（基于研究综合）

| Fugu 特性 | 传统 CLI（Claude Code）的处理方式 | 对 CLI 设计的影响 |
|---|---|---|
| **Multi-Agent MoA 编排**（TRINITY: Thinker/Worker/Verifier + Conductor） | Claude Code 自己实现 Agent Loop、Subagent、计划分解 | **CLI 不需要自己做编排层**——Fugu 内部有 Conductor 做任务分解，有 Verifier 做审查 |
| **黑箱路由**（API 不暴露内部 agent 状态） | 自己的权限系统、上下文组装、工具池 | **CLI 无法也无需控制内部 routing**——只能推断，不能干预 |
| **1M Token 上下文**（Fugu Ultra） | 多层 compaction（Snip→Microcompact→Collapse→Auto-Compact） | **不需要激进压缩**——1M 窗口足够承载整个中等项目；但需要智能文件选择 |
| **递归自修正**（Fugu 读取自身输出并启动修正 workflow） | 自己实现重试循环、错误恢复 | **不需要复杂的重试策略**——Fugu 会自己 retry；CLI 只需确保工具返回准确 |
| **~14 小时自主实验**（123 次实验序列） | 单会话、断线即终止 | **必须支持超长会话 + 断线恢复**——这是 Fugu 的核心优势，CLI 必须承接 |
| **Orchestration Tokens**（独立成本指标） | 无此概念 | **需要可视化 orchestration 开销**——这是 Fugu 独有的成本维度 |
| **No `previous_response_id`**（每次发送完整历史） | 依赖 server-side 会话存储 | **CLI 必须自己管理完整历史**——不能有状态泄漏，必须本地持久化 |
| **`instructions` 影响内部 agent 行为** | 标准 system prompt | **需要精心设计的 instructions 模板**——不只是 system prompt，而是 Fugu 内部角色分配的输入 |
| **模型池动态选择**（Claude/GPT/Gemini 混合） | 用户选择模型或路由层 | **不需要模型选择 UI**——Fugu 自己做；但 CLI 应提供 `effort` 级别控制 |

### 1.2 核心设计原则转变

```
传统 CLI 架构（Claude Code）:          Fugu CLI 架构（应然）:
┌─────────────────────────┐          ┌─────────────────────────┐
│  用户                     │          │  用户                     │
│    ↓                     │          │    ↓                     │
│  CLI 编排层（厚）          │          │  CLI 工具层（精良）        │
│  ├─ 计划分解              │          │  ├─ 精确文件操作          │
│  ├─ Subagent 调度         │          │  ├─ Shell 执行（结构化）   │
│  ├─ 上下文压缩（5层）      │          │  ├─ 测试/验证闭环          │
│  ├─ 验证循环              │          │  ├─ 状态持久化/断线恢复      │
│  ├─ 重试恢复              │          │  └─ 成本监控              │
│  ↓                       │          │  ↓                       │
│  模型（薄，仅生成文本）     │          │  Fugu（厚编排，黑箱）      │
│  ├─ 单次调用              │          │  ├─ Conductor 任务分解     │
│  └─ 无内部验证            │          │  ├─ Worker 并行执行        │
│                          │          │  ├─ Verifier 交叉验证      │
│                          │          │  └─ 递归自修正             │
└─────────────────────────┘          └─────────────────────────┘
```

**核心原则：CLI 不是 Fugu 的"大脑"，而是 Fugu 的"手"——提供精确、可靠、可验证的工具执行面。**

---

## 二、功能放开：传统 CLI 做但 Fugu CLI 不需要做的

### 2.1 放开列表（可降级或移除）

| # | 传统功能 | 为什么可以放开 | 替代方案 |
|---|---|---|---|
| F1 | **复杂 Subagent 系统** | Fugu 内部有 TRINITY 的 Worker 分配，不需要 CLI 再实现一层 | 保留简单的任务分解提示（通过 `instructions`） |
| F2 | **5 层上下文压缩管道** | 1M 上下文 + Fugu 内部管理，不需要 CLI 激进压缩 | 轻量摘要 + 文件树缓存（见下文） |
| F3 | **自定义模型路由/选择** | Fugu 内部 Conductor 做动态路由到 Claude/GPT/Gemini | CLI 仅提供 `effort` 参数（high/xhigh/max） |
| F4 | **内置验证循环** | Fugu 有 Verifier agent 做交叉验证 | CLI 只需要确保工具结果准确、完整 |
| F5 | **复杂重试策略** | Fugu 递归自修正，会自己 retry | CLI 只需处理网络/流式层面的 resilience（已有） |
| F6 | **计划模式（Planning Mode）** | Fugu 内部 Conductor 做任务分解 | 可选保留 `/plan` 作为人工确认前触发，但不强制 |
| F7 | **Hooks 生命周期系统** | 可以简化，因为 Fugu 内部已有生命周期管理 | 保留基础的事件钩子（pre/post tool）用于审计 |
| F8 | **Skills 系统（复杂）** | Fugu 的 `instructions` 可以承担大部分角色定义 | 简化为 `.fugu/instructions.md` 项目模板 |

### 2.2 放开的理由：不重复 Fugu 已做的事情

**Claude Code 需要自己做计划分解**，因为 Claude 模型本身不会分解任务——它只是一个单次调用的模型。Claude Code 的 Agent Loop 需要手动实现 "read → plan → execute → verify" 循环。

**Fugu 内部已经做了这个循环**：Conductor 分解任务 → Worker 执行 → Verifier 验证 → 如果失败则递归修正。如果 CLI 再包一层同样的循环，就是**冗余的编排层**，会：
- 增加延迟（双重计划）
- 增加 token 浪费（双重上下文）
- 降低 Fugu 内部优化效果（CLI 的压缩/截断会干扰 Fugu 的 routing 决策）

---

## 三、功能新增：传统 CLI 没有但 Fugu CLI 必须做的

### 3.1 新增列表

| # | 新增功能 | 理由 | 优先级 |
|---|---|---|---|
| **N1** | **工具结果结构化**（structured tool output） | Fugu 的 Verifier 需要准确、可解析的工具结果来验证；原始文本输出容易误判 | 🔴 最高 |
| **N2** | **文件树摘要缓存**（codebase index） | 1M 上下文可以容纳大量文件，但盲目发全部文件浪费 token；需要智能选择发哪些文件 | 🔴 最高 |
| **N3** | **超长会话持久化 + 断线恢复** | Fugu Ultra 支持 14 小时序列实验；CLI 必须能断线重连、恢复状态 | 🔴 最高 |
| **N4** | **Orchestration 成本监控** | `orchestration_tokens` 是 Fugu 独有成本；需要实时展示和预算告警 | 🔴 高 |
| **N5** | **Instructions 模板系统** | Fugu 的 `instructions` 影响内部 agent 角色分配；需要项目级模板 | 🟡 高 |
| **N6** | **Fugu 特殊参数优化** | `effort` 级别自适应、`truncation` 策略、`unlimited_mode` 与工具的配合 | 🟡 高 |
| **N7** | **测试/验证结果结构化** | Fugu 的 Verifier 需要知道"测试通过了 3/5"，而非原始 pytest 输出 | 🟡 高 |
| **N8** | **智能文件选择（Context Assembly）** | 1M 窗口虽大但不能全发；需要基于文件树/符号索引选择相关文件 | 🟡 高 |
| **N9** | **Session 状态快照** | 长程任务中保存可恢复点，类似 checkpoint 但针对 Fugu 的完整历史 | 🟡 中 |
| **N10** | **Fugu 流式阶段推断增强** | 从 SSE 流推断 Fugu 内部阶段（routing/worker/verification/synthesis），展示给用户 | 🟡 中 |

### 3.2 新增功能详解

#### N1: 工具结果结构化——这是最关键的新增

传统 CLI（如 Claude Code）的工具返回原始文本，因为模型（Claude）可以解析任何文本。但 Fugu 的 **Verifier agent 需要快速、准确地判断工具结果是否正确**。

**对比示例**：

```
❌ 传统方式（原始文本，Fugu Verifier 难以解析）:
$ pytest tests/test_auth.py
======================== test session starts ========================
platform darwin -- Python 3.12.0
rootdir: /workspace
plugins: anyio-4.0.0

 tests/test_auth.py::test_login ✓
 tests/test_auth.py::test_logout ✗
   AssertionError: assert 401 == 200
 tests/test_auth.py::test_register ✓

======================== 1 failed, 2 passed ========================

✅ Fugu 优化方式（结构化 JSON，Verifier 秒判）:
{
  "command": "pytest tests/test_auth.py",
  "exit_code": 1,
  "summary": {
    "total": 3,
    "passed": 2,
    "failed": 1,
    "errors": 0
  },
  "failures": [
    {
      "test": "test_logout",
      "file": "tests/test_auth.py",
      "line": 42,
      "error": "AssertionError: assert 401 == 200",
      "snippet": "    def test_logout():\n        resp = client.post('/logout')\n>       assert resp.status_code == 200\nE       assert 401 == 200"
    }
  ],
  "duration_seconds": 1.23,
  "output_truncated": false
}
```

**所有工具都应返回结构化结果**：
- `file_read`: `{content, lines, size, encoding, truncated}`
- `file_list`: `{files: [{path, size, type, last_modified}]}`
- `bash`: `{exit_code, stdout, stderr, duration, command}`
- `git_status`: `{modified: [{path, status}], untracked: [...], branch}`
- `run_test`: `{summary, failures, duration, coverage}`

这能让 Fugu 的 Verifier 快速判断："测试失败了 1 个，在 logout 函数，assert 401==200，需要修复权限检查"。

#### N2: 文件树摘要缓存（Codebase Index）

Fugu Ultra 有 1M 上下文，可以发很多文件。但问题不是"能不能发"，而是**"发哪些文件才能让 Fugu 的 Conductor 做出最优 routing"**。

实现：
```python
# 在 session 启动时或定期更新
class CodebaseIndex:
    """Lightweight file tree + symbol summary for context assembly."""
    
    def build(self):
        # 1. 扫描文件树（排除 node_modules, .git, etc.）
        # 2. 对每个文件提取：前 50 行 + 函数/类签名列表（轻量解析）
        # 3. 生成文件摘要："auth.py - 登录/权限相关，包含 login(), logout(), check_permission()"
        # 4. 缓存到 .fugu-vibe/index.json
        
    def select_for_context(self, query: str, max_tokens: int) -> list[str]:
        # 基于 query 关键词匹配文件摘要，选择最相关的文件
        # 返回文件列表，按相关性排序
```

**使用方式**：在发送 prompt 前，先让 Fugu 的 Conductor "看到"项目全貌（文件树 + 摘要），它自己决定哪些文件需要读取。这比 CLI 自己决定发哪些文件更优，因为 Fugu 知道它内部 Workers 需要什么。

#### N3: 超长会话持久化 + 断线恢复

Fugu 可以做 14 小时的序列实验。但当前 CLI：
- 流中断后仅重试 SSE 连接，不恢复会话状态
- 如果进程崩溃，整个对话历史丢失（因为 Fugu 不接受 `previous_response_id`）
- 没有后台持久化

实现需求：
1. **每轮对话后自动保存完整历史**到 `.fugu-vibe/sessions/{session_id}/history.jsonl`
2. **断线检测**：SSE 流中断时标记 `connection_lost`，记录最后收到的 chunk
3. **重连策略**：
   - 如果 Fugu 还在运行（通过 status API 检查），用完整历史重新建立 SSE 连接
   - 如果 Fugu 会话已终止，用完整历史重新发送请求（成本较高，但可恢复）
4. **后台模式**：`fugu-vibe run --background --task-file task.md` → 在后台运行，定期保存状态，可 `fugu-vibe attach {session_id}` 重新连接
5. **Session 心跳**：每 5 分钟发送轻量 ping，保持连接活跃

#### N4: Orchestration 成本监控

Fugu 的 `orchestration_tokens` 是**纯协调开销**（不产出的 token）。对于重型任务，这可能占 20-50% 总成本。必须监控：

```python
class TokenBudget:
    """Track and alert on token usage, especially orchestration overhead."""
    
    def __init__(self, max_total: int, max_orchestration_ratio: float = 0.5):
        self.max_total = max_total
        self.max_orch_ratio = max_orchestration_ratio
        
    def check(self, usage: TokenUsage) -> Alert | None:
        total = usage.input + usage.output + usage.orchestration
        if usage.orchestration / total > self.max_orch_ratio:
            return Alert(
                level="warning",
                message=f"Orchestration overhead {usage.orchestration/total:.1%} — "
                        f"consider simplifying task or reducing effort level"
            )
        if total > self.max_total * 0.8:
            return Alert(level="warning", message="Token budget 80% consumed")
        if total > self.max_total:
            return Alert(level="critical", message="Token budget exceeded")
```

仪表盘需要展示：
- 三栏 token：Input / Output / Orchestration（已有）
- **Orchestration Ratio 告警**（新增）
- **Budget Progress Bar**（新增）
- **Cost Estimate**（基于单价估算，新增）

#### N5: Instructions 模板系统

Fugu 的 `instructions` 不只是 system prompt，它会影响内部 Conductor 的任务分解和 Worker 的角色分配。

设计：
```
.fugu/instructions.md          # 项目级（最高优先级）
~/.config/fugu-vibe/instructions.md  # 用户级
```

模板格式：
```markdown
---
project_type: python-backend
framework: fastapi
conventions:
  - Use type hints everywhere
  - Prefer pydantic models for validation
  - Tests go in tests/ mirroring src/ structure
  - Use pytest with fixtures
---

# Project Context

This is a Python backend API using FastAPI + SQLAlchemy + Alembic.

## Architecture
- `src/api/` - Route handlers
- `src/services/` - Business logic
- `src/models/` - Pydantic + SQLAlchemy models
- `src/db/` - Database layer
- `tests/` - Pytest test suite

## Testing
Run tests with: `pytest tests/ -v`
Use fixtures in `tests/conftest.py` for DB setup.
```

CLI 在构建请求时，将 `instructions` 与项目模板合并，影响 Fugu 的 routing 决策。

---

## 四、修订后的五阶段施工路径（v2）

```
Phase A: 工具层 + 结构化（解决 N1/G1/G2）—— 最高优先级
    ├─ A1: 核心编辑工具（edit/delete，保留）
    ├─ A2: 结构化 Shell 执行（bash 工具，返回 JSON）
    ├─ A3: 结构化测试/验证（run_test/run_lint，返回 JSON）
    ├─ A4: 结构化 Git 工具（git_status/git_diff，返回 JSON）
    ├─ A5: 文件树/搜索工具（file_glob/grep，返回 JSON）
    └─ A6: 所有工具统一返回结构化格式

Phase B: 上下文组装 + 持久化（解决 N2/N3/G4）
    ├─ B1: 文件树摘要缓存（CodebaseIndex）
    ├─ B2: 智能文件选择（select_for_context）
    ├─ B3: 每轮自动保存完整历史
    ├─ B4: 断线检测 + 重连恢复
    └─ B5: 后台模式（background + attach）

Phase C: 安全治理（解决 G6，但简化）
    ├─ C1: 权限模式（ask/auto-safe/auto-edit/auto）
    ├─ C2: 文件写入 checkpoint（git commit 每轮）
    ├─ C3: /undo 回滚（基于 checkpoint）
    └─ C4: 命令分类器（简化版，因为 Fugu 内部有 Verifier）
    
    ⚠️ 简化：不需要 7 层权限，因为 Fugu 的 Verifier 会交叉验证

Phase D: Fugu 特殊优化（解决 N4/N5/N6/N7）
    ├─ D1: Orchestration Token 监控 + Budget Alert
    ├─ D2: Instructions 模板系统
    ├─ D3: effort 自适应（根据任务复杂度自动调整）
    ├─ D4: 工具反馈质量优化（错误信息结构化、truncation 策略）
    └─ D5: 流式阶段推断增强（从 SSE 提取 Fugu 内部状态）

Phase E: 扩展生态（解决 G3 + 体验）
    ├─ E1: MCP 协议支持（保留，但优先级降低）
    ├─ E2: 仪表盘增强（实时成本 + 阶段可视化）
    ├─ E3: Headless / SDK 模式
    └─ E4: 语音（保持占位，不投入）
```

### 4.1 与原方案的关键差异

| 维度 | 原方案（v1） | 修订方案（v2） | 理由 |
|---|---|---|---|
| **Subagent** | Phase D 实现 | **移除** | Fugu 内部有 Conductor + Worker |
| **Compaction** | 5 层管道（B 阶段） | **简化为文件树缓存 + 轻量摘要** | 1M 上下文足够，Fugu 内部管理 |
| **Planning Mode** | Phase D | **降级为可选 `/plan` 命令** | Fugu 内部做计划分解 |
| **Hooks** | Phase E 完整系统 | **简化为事件审计** | Fugu 内部有生命周期管理 |
| **Skills** | Phase E 复杂系统 | **简化为 `.fugu/instructions.md`** | Fugu 的 instructions 承担角色定义 |
| **工具结构化** | 未提及 | **Phase A 核心要求** | Fugu Verifier 需要结构化输入 |
| **Codebase Index** | 未提及 | **Phase B 核心** | 帮助 Fugu Conductor 做最优 routing |
| **断线恢复** | 基础 SSE 重连 | **完整会话持久化 + 后台模式** | Fugu 支持 14h 长程任务 |
| **Orchestration 成本** | 仅展示 | **Budget + Alert** | 协调开销可能占 20-50% |
| **MCP** | 高优先级 | **降低优先级** | 先把 Fugu 工具层做精良，再扩展 |

---

## 五、技术选型调整

| 需求 | 原方案 | 修订方案 | 理由 |
|---|---|---|---|
| 上下文压缩 | 调用 LLM 压缩 | **本地文件树摘要 + 选择性发送** | 不干扰 Fugu 内部 routing |
| 代码索引 | 可选 Tree-sitter | **必须实现（轻量）** | 1M 窗口需要智能文件选择 |
| 测试解析 | 原始输出 | **pytest-json + 结构化解析** | Fugu Verifier 需要 |
| 历史持久化 | markdown 日志 | **JSONL 完整历史 + 断线恢复** | Fugu 无 server-side 会话 |
| 权限系统 | 4 模式 | **3 模式（ask/auto-safe/auto）** | Fugu Verifier 降低安全需求 |
| 沙箱 | Docker 可选 | **Git checkpoint 足够** | 简化，Fugu 不执行本地代码 |
| 仪表盘协议 | 共享 JSONL | **WebSocket / mmap 共享** | 实时流式需要更低延迟 |

---

## 六、Fugu 特殊 API 参数优化建议

### 6.1 `effort` 自适应策略

| 任务特征 | 建议 `effort` | 理由 |
|---|---|---|
| 简单问答（< 3 文件） | `high` | 低延迟，Fugu 可能直接回答 |
| 中型重构（3-10 文件） | `xhigh` | 需要 Worker 并行 + Verifier |
| 重型重构（> 10 文件 / 跨模块） | `max` | 需要完整 Conductor 分解 + 多 Worker |
| 调试/修复失败测试 | `xhigh` | 需要 Verifier 分析失败原因 |
| 探索性研究 | `max` | 需要多模型对比 + 深度验证 |

CLI 可自动检测任务复杂度：
```python
def infer_effort(prompt: str, context_files: list[str]) -> str:
    complexity = 0
    if len(context_files) > 10: complexity += 2
    if any(k in prompt.lower() for k in ["refactor", "rewrite", "architecture", "redesign"]): complexity += 2
    if any(k in prompt.lower() for k in ["fix", "debug", "test"]): complexity += 1
    if any(k in prompt.lower() for k in ["explain", "review", "simple"]): complexity -= 1
    
    if complexity >= 3: return "max"
    if complexity >= 1: return "xhigh"
    return "high"
```

### 6.2 `truncation` 策略

- 默认 `auto`：Fugu 内部管理
- 当文件很多时（> 20 文件），建议 CLI 先发送文件树摘要，让 Fugu 选择读取哪些文件，而不是发送全部文件内容

### 6.3 `unlimited_mode` 与工具的配合

当 `unlimited_mode=true` 时，Fugu 的 safety guardrails 被降低。CLI 需要：
- 强制 `ask` 权限模式（不自动执行危险操作）
- 更严格的 checkpoint 频率（每轮写入都 commit）
- 显示警告："Unlimited mode: Fugu safety guardrails disabled. CLI approval mode enforced."

---

## 七、验收标准（修订）

| 阶段 | 验收测试 | 通过标准 |
|---|---|---|
| **A** | 给 Fugu 任务："修复 `auth.py` 中的 logout 函数，运行测试验证" | Fugu 自动：`read` → `edit` → `run_test`（返回结构化 JSON）→ 看到 1 失败 → `read` 测试文件 → `edit` 修复 → `run_test` → 通过。工具结果均为结构化 JSON，非原始文本。 |
| **B** | 提交 50 文件项目的重构任务，中途断网 30 秒 | 恢复连接后，Fugu 继续执行任务，未丢失上下文；CLI 显示"Reconnected, resuming from turn 12"。 |
| **C** | 运行任务，Fugu 尝试写入敏感文件（`.env`） | 被拦截，显示 diff 预览，用户确认后才执行。`/undo` 可回滚。 |
| **D** | 完成 20 轮重型重构，检查 orchestration token 比例 | 仪表盘显示 orchestration 开销 < 40%；如果超过，触发告警。 |
| **E** | 连接 MCP Server，扩展工具集 | 新工具出现在 Fugu 可用工具列表，可被调用。 |

---

## 八、核心设计哲学

> **"Don't build a brain on top of a brain. Build hands that the brain can trust."**
>
> — Fugu 已经是一个编排大脑（Conductor + TRINITY）。CLI 不需要再做一层编排。CLI 应该做的是：
> 1. **精良的工具**（精确、结构化、可验证）
> 2. **可靠的状态**（持久化、可恢复、不丢失）
> 3. **透明的成本**（orchestration 开销可视化、预算控制）
> 4. **智能的上下文**（帮助 Fugu 的 Conductor 做最优 routing）

---

*修订版 v2 基于 Fugu 多 Agent MoA 架构（TRINITY + Conductor）、1M 上下文窗口、递归自修正、~14 小时自主实验能力综合设计。*
*参考：Sakana Fugu Technical Report (arXiv 2606.21228v2)、VentureBeat / MindStudio / Analytics Vidhya 分析、Claude Code v2.1.88 架构。*
