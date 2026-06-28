# 🐡 Fugu Vibe CLI

[English](README.md) | **中文** | [日本語](README.ja.md)

专为 **Sakana Fugu** 打造的 CLI 工具，支持异步语音控制、智能体编排可视化、以及无限制提示模式（unlimited prompt mode）。

> **Fugu** 是 Sakana AI 的分布式多智能体推理系统，每个请求可动态路由至 1–3 个专家智能体。本 CLI 充分利用了 Fugu 独特的架构特性。

## ✨ 特性

| 特性 | 描述 |
|---------|-------------|
| 🧭 **编排可视化** | 实时仪表盘展示 Fugu 内部路由决策、工作节点激活及验证阶段 |
| 🎤 **语音控制** | 按键语音输入，支持 VAD 自动分段与 Faster-Whisper 本地语音识别 |
| ⚡ **异步任务** | 基于 git-worktree 隔离的并行任务执行与 DAG 依赖管理 |
| 🔓 **无限制模式** | 覆盖安全护栏，获得完全无约束的提示控制权 |
| 📡 **完整 API 支持** | 完整支持 Responses API 与所有 Fugu 专属参数 |
| 🔄 **流式韧性** | 2 小时空闲超时、自动重连、Sakana 推荐的重试策略 |

## 🚀 快速开始

### 环境要求

- Python 3.11+（推荐 3.12；macOS 上 3.14 存在 `pyexpat` 已知问题）
- [uv](https://github.com/astral-sh/uv)（推荐）或 pip 24+

### 从源码安装

```bash
# 克隆
git clone https://github.com/fugu-vibe/fugu-vibe-cli.git
cd fugu-vibe-cli

# 使用 uv 安装（推荐）
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e .

# 或使用 pip
pip install -e ".[all]"
```

### 认证

```bash
# 设置 API 密钥（从 https://console.sakana.ai/api-keys 或你的中转商获取）
export SAKANA_API_KEY="your-key-here"

# 或使用交互式登录命令
fugu-vibe auth login
```

### 开始 Vibe Coding

```bash
# 交互式会话，带完整仪表盘
fugu-vibe vibe

# 使用 Fugu Ultra 模型，最大推理强度
fugu-vibe vibe --model fugu-ultra --effort xhigh

# 指定自定义 / 中转 API 地址
fugu-vibe vibe --base-url https://your-proxy.com/v1

# 启用语音控制
fugu-vibe vibe --voice

# 无限制提示模式（关闭安全护栏）
fugu-vibe vibe --unlimited
```

## 📋 命令参考

### `vibe` — 交互式会话

```bash
fugu-vibe vibe [OPTIONS]

选项：
  -m, --model TEXT       模型（fugu | fugu-ultra）
  -e, --effort CHOICE    推理强度：high | xhigh | max
  --base-url TEXT        覆盖 API 基础地址（用于中转 / 非官方端点）
  -w, --web-search       启用网络搜索工具
  --no-viz              关闭可视化
  -v, --voice           启用语音输入
  -u, --unlimited       无限制提示模式
```

### `submit` — 异步任务提交

```bash
fugu-vibe submit "任务名称" -p "提示词..." [OPTIONS]

选项：
  -p, --prompt TEXT      必填：任务提示词
  -d, --description TEXT 任务描述
  -m, --model TEXT       模型覆盖
  -e, --effort CHOICE    推理强度
  -w, --web-search       启用网络搜索
  --depends-on TEXT      任务依赖（可多次指定）
  -f, --files TEXT       上下文文件（可多次指定）
  --wait                 等待任务完成
  -u, --unlimited        无限制提示模式

# 示例：
fugu-vibe submit "重构认证" -p "重构认证模块..."
fugu-vibe submit "编写测试" -p "..." --depends-on <task-id>
fugu-vibe submit "深度分析" -p "..." --effort xhigh --wait
```

### `status` — 任务状态

```bash
fugu-vibe status [TASK_ID] [OPTIONS]

选项：
  -w, --watch   监视模式（自动刷新）
  --json        以 JSON 输出

# 示例：
fugu-vibe status              # 所有任务
fugu-vibe status <task-id>    # 特定任务
fugu-vibe status -w           # 实时监控
```

### `attach` — 附加到运行中的任务

```bash
fugu-vibe attach <task-id>
```

### `voice` — 语音模式

```bash
fugu-vibe voice [OPTIONS]

选项：
  -c, --continuous   连续语音模式
  -w, --web-search   启用网络搜索
  -m, --model TEXT   模型覆盖
  -e, --effort       推理强度
```

### `config` — 配置管理

```bash
fugu-vibe config show              # 显示当前配置
fugu-vibe config init              # 创建项目配置
fugu-vibe config init --global     # 创建全局配置
fugu-vibe config set model.default fugu-ultra
fugu-vibe config path              # 显示配置文件位置
```

## ⚙️ 配置

配置优先级（从高到低）：
1. CLI 命令行参数
2. 环境变量（`FUGU_VIBE_*`）
3. 项目配置（`.fugu-vibe.toml`）
4. 用户配置（`~/.config/fugu-vibe/config.toml`）
5. 默认值

### `.fugu-vibe.toml` 示例

```toml
[api]
base_url = "https://api.sakana.ai/v1"
timeout = 7200
stream_idle_timeout_ms = 7200000

[model]
default = "fugu-ultra"
reasoning_effort = "xhigh"
max_output_tokens = 32768

[orchestration]
viz_mode = "full"
show_token_usage = true
infer_workers = true

[voice]
enabled = true
push_to_talk_key = "space"
silence_timeout = 2.0

[tasks]
max_parallel = 5
use_git_worktree = true
auto_merge = true

[prompt]
unlimited_mode = false
```

### 使用中转 / 非官方 API 地址

你可以通过反向代理或非官方端点路由请求：

**通过 CLI 参数（最高优先级，按命令生效）：**
```bash
fugu-vibe vibe --base-url https://your-proxy.com/v1
fugu-vibe submit "任务" -p "..." --base-url https://your-proxy.com/v1
```

**通过环境变量：**
```bash
export FUGU_VIBE_API_BASE_URL="https://your-proxy.com/v1"
export SAKANA_API_KEY="sk-your-key"
fugu-vibe vibe
```

**通过配置文件（持久化）：**
```toml
[api]
base_url = "https://your-proxy.com/v1"
```

> ⚠️ **注意：** 请勿将 API 密钥或 `.fugu-vibe.toml` 提交到版本控制。项目 `.gitignore` 已默认排除这些文件。

## 🧭 编排可视化

仪表盘展示 Fugu 内部多智能体协调过程：

```
┌──────────────────────────────────────────────┐
│ 🐡 Fugu Ultra - 编排仪表盘                   │
├──────────────────┬───────────────────────────┤
│ 🧭 路由：        │ 输出面板（实时流式内容）    │
│   gpt-5.5 (87%)  │                           │
│                  │                           │
│ ⚡ 工作节点-1    │                           │
│   激活中         │                           │
│   (45 tok/s)     │                           │
│                  │                           │
│ 🔍 验证          │                           │
│   #1             │                           │
├──────────────────┼───────────────────────────┤
│ 📥 输入: 3.2k    │ 📋 任务                   │
│ 📤 输出: 12.8k   │ 🔄 重构认证 [运行中]      │
│ ⚙️  编排: 8.4k   │ ⏳ 编写测试 [等待中]      │
│ 📊 总计: 24.4k   │                           │
└──────────────────┴───────────────────────────┘
```

由于 Fugu 的 API 不暴露内部路由，CLI 使用**多信号推断**：
- 初始延迟 → 路由决策
- Token 突发模式 → 工作节点激活
- 内容标记 → 并行工作节点边界
- Token 成本比率 → 编排开销

## 🎤 语音输入

语音模式使用：
- **VAD**（语音活动检测）自动分段
- **Faster-Whisper** 本地语音识别
- 按键通话（默认：空格键）

```bash
# 安装语音支持
pip install fugu-vibe-cli[voice]

# 启动语音会话
fugu-vibe vibe --voice

# 或专用语音模式
fugu-vibe voice --continuous
```

## 🏗️ 架构

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│  CLI     │  │  核心    │  │   API    │  │ 外部服务 │
│ (Click)  │  │  引擎    │  │  层      │  │          │
├──────────┤  ├──────────┤  ├──────────┤  ├──────────┤
│ vibe     │  │ TaskMgr  │  │ FuguClient│  │ Sakana  │
│ submit   │  │ OrchViz  │  │ Request   │  │  API    │
│ status   │  │ EventBus │  │ Stream    │  │         │
│ voice    │  │ GitWT    │  │ Parser    │  │         │
└────┬─────┘  └────┬─────┘  └────┬─────┘  └─────────┘
     │             │             │
┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐
│   TUI    │  │  语音    │  │   可视化 │
│ (Rich)   │  │(Whisper) │  │(Timeline)│
└──────────┘  └──────────┘  └──────────┘
```

## 📚 Fugu API 特性

本 CLI 处理了 Fugu 独特的 API 行为：

| 参数 | Fugu 行为 | CLI 处理 |
|-----------|--------------|--------------|
| `temperature` | 接受但**忽略** | 记录警告 |
| `parallel_tool_calls` | 接受但**忽略** | 记录警告 |
| `previous_response_id` | **不接受** | 发送完整历史 |
| `reasoning.effort` | `high` / `xhigh` / `max` | 完全支持 |
| `tools` | 内置 `web_search` | `--web-search` 启用 |
| `max_output_tokens` | 最高 32768 | 可配置 |
| 编排 Token | 第三类 Token | 独立追踪 |

## 🔧 开发

```bash
# 克隆
git clone https://github.com/fugu-vibe/fugu-vibe-cli.git
cd fugu-vibe-cli

# 使用 uv 安装（推荐）
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check .
mypy fugu_vibe/
```

### 已知问题与修复

| 问题 | 修复 |
|-------|-----|
| macOS 上 Python 3.14 `pyexpat` 崩溃 | 使用 Python 3.11–3.13 |
| PyPI 上不存在 `asyncio-subprocess-tee` | 从依赖中移除；使用 `asyncio.subprocess` |
| `api/__init__.py` 导入路径错误 | 已修复：`fugu_vibe.request_builder` → `fugu_vibe.api.request_builder` |

## 📄 许可证

MIT 许可证 — 详见 [LICENSE](LICENSE) 文件。

---

**与 Sakana AI 无关联。** Fugu 是 Sakana AI 的商标。
