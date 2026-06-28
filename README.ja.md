# 🐡 Fugu Vibe CLI

[English](README.md) | [中文](README.zh.md) | **日本語**

**Sakana Fugu** 専用の CLI ツール。非同期ボイスコントロール、エージェントオーケストレーション可視化、無制限プロンプトモードを搭載しています。

> **Fugu** は Sakana AI の分散型マルチエージェント推論システムです。各リクエストを 1〜3 個の専門エージェントに動的にルーティングします。本 CLI は Fugu の独自アーキテクチャを最大限に活用します。

## ✨ 機能

| 機能 | 説明 |
|---------|-------------|
| 🧭 **オーケストレーション可視化** | リアルタイムダッシュボードで内部ルーティング決定、ワーカーアクティベーション、検証フェーズを表示 |
| 🎤 **ボイスコントロール** | プッシュトゥトーク音声入力、VAD 自動セグメンテーション、Faster-Whisper ローカル STT |
| ⚡ **非同期タスク** | git-worktree 分離による並列実行と DAG 依存関係管理 |
| 🔓 **無制限モード** | セーフティガードレールを無効化し、制約なしのプロンプト制御を実現 |
| 📡 **完全な API サポート** | Responses API およびすべての Fugu 固有パラメータに対応 |
| 🔄 **ストリーム耐性** | 2 時間アイドルタイムアウト、自動再接続、Sakana 推奨のリトライポリシー |

## 🚀 クイックスタート

### 必要条件

- Python 3.11+（推奨: 3.12；macOS では 3.14 の `pyexpat` 既知の問題あり）
- [uv](https://github.com/astral-sh/uv)（推奨）または pip 24+

### ソースからインストール

```bash
# クローン
git clone https://github.com/fugu-vibe/fugu-vibe-cli.git
cd fugu-vibe-cli

# uv でインストール（推奨）
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e .

# または pip
pip install -e ".[all]"
```

### 認証

```bash
# API キーを設定（https://console.sakana.ai/api-keys またはプロキシプロバイダから取得）
export SAKANA_API_KEY="your-key-here"

# またはインタラクティブログインコマンド
fugu-vibe auth login
```

### Vibe Coding を開始

```bash
# フルダッシュボード付きのインタラクティブセッション
fugu-vibe vibe

# Fugu Ultra モデル、最大推論強度
fugu-vibe vibe --model fugu-ultra --effort xhigh

# カスタム / プロキシ API ベースURL
fugu-vibe vibe --base-url https://your-proxy.com/v1

# ボイスコントロール有効
fugu-vibe vibe --voice

# 無制限プロンプトモード（ガードレール無効）
fugu-vibe vibe --unlimited
```

## 📋 コマンドリファレンス

### `vibe` — インタラクティブセッション

```bash
fugu-vibe vibe [OPTIONS]

オプション：
  -m, --model TEXT       モデル（fugu | fugu-ultra）
  -e, --effort CHOICE    推論強度：high | xhigh | max
  --base-url TEXT        API ベースURL の上書き（プロキシ / 非公式エンドポイント用）
  -w, --web-search       ウェブ検索ツールを有効化
  --no-viz              可視化を無効化
  -v, --voice           ボイス入力を有効化
  -u, --unlimited       無制限プロンプトモード
```

### `submit` — 非同期タスク送信

```bash
fugu-vibe submit "タスク名" -p "プロンプト..." [OPTIONS]

オプション：
  -p, --prompt TEXT      必須：タスクプロンプト
  -d, --description TEXT タスク説明
  -m, --model TEXT       モデル上書き
  -e, --effort CHOICE    推論強度
  -w, --web-search       ウェブ検索を有効化
  --depends-on TEXT      タスク依存関係（複数回指定可）
  -f, --files TEXT       コンテキストファイル（複数回指定可）
  --wait                 完了を待機
  -u, --unlimited        無制限プロンプトモード

# 例：
fugu-vibe submit "認証のリファクタリング" -p "認証モジュールをリファクタリング..."
fugu-vibe submit "テストを書く" -p "..." --depends-on <task-id>
fugu-vibe submit "深い分析" -p "..." --effort xhigh --wait
```

### `status` — タスク状態

```bash
fugu-vibe status [TASK_ID] [OPTIONS]

オプション：
  -w, --watch   ウォッチモード（自動更新）
  --json        JSON 出力

# 例：
fugu-vibe status              # すべてのタスク
fugu-vibe status <task-id>    # 特定のタスク
fugu-vibe status -w           # リアルタイム監視
```

### `attach` — 実行中タスクへアタッチ

```bash
fugu-vibe attach <task-id>
```

### `voice` — ボイスモード

```bash
fugu-vibe voice [OPTIONS]

オプション：
  -c, --continuous   連続ボイスモード
  -w, --web-search   ウェブ検索を有効化
  -m, --model TEXT   モデル上書き
  -e, --effort       推論強度
```

### `config` — 設定管理

```bash
fugu-vibe config show              # 現在の設定を表示
fugu-vibe config init              # プロジェクト設定を作成
fugu-vibe config init --global     # グローバル設定を作成
fugu-vibe config set model.default fugu-ultra
fugu-vibe config path              # 設定ファイルの場所を表示
```

## ⚙️ 設定

設定優先順位（高い順）：
1. CLI コマンドライン引数
2. 環境変数（`FUGU_VIBE_*`）
3. プロジェクト設定（`.fugu-vibe.toml`）
4. ユーザー設定（`~/.config/fugu-vibe/config.toml`）
5. デフォルト値

### `.fugu-vibe.toml` サンプル

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

### プロキシ / 非公式 API ベースURL の使用

リバースプロキシまたは非公式エンドポイントを経由してリクエストをルーティングできます：

**CLI パラメータ（最高優先度、コマンドごと）：**
```bash
fugu-vibe vibe --base-url https://your-proxy.com/v1
fugu-vibe submit "タスク" -p "..." --base-url https://your-proxy.com/v1
```

**環境変数：**
```bash
export FUGU_VIBE_API_BASE_URL="https://your-proxy.com/v1"
export SAKANA_API_KEY="sk-your-key"
fugu-vibe vibe
```

**設定ファイル（永続）：**
```toml
[api]
base_url = "https://your-proxy.com/v1"
```

> ⚠️ **注意：** API キーまたは `.fugu-vibe.toml` をバージョン管理にコミットしないでください。プロジェクト `.gitignore` はこれらをデフォルトで除外しています。

## 🧭 オーケストレーション可視化

ダッシュボードは Fugu 内部のマルチエージェント協調を表示します：

```
┌──────────────────────────────────────────────┐
│ 🐡 Fugu Ultra - オーケストレーションダッシュボード│
├──────────────────┬───────────────────────────┤
│ 🧭 ルーティング：  │ 出力パネル（リアルタイム   │
│   gpt-5.5 (87%)  │ ストリーミングコンテンツ）│
│                  │                           │
│ ⚡ ワーカー-1    │                           │
│   アクティブ     │                           │
│   (45 tok/s)     │                           │
│                  │                           │
│ 🔍 検証          │                           │
│   #1             │                           │
├──────────────────┼───────────────────────────┤
│ 📥 入力: 3.2k    │ 📋 タスク                  │
│ 📤 出力: 12.8k   │ 🔄 認証のリファクタリング  │
│ ⚙️  オーケスト: 8.4k│ ⏳ テストを書く [待機中]  │
│ 📊 合計: 24.4k   │                           │
└──────────────────┴───────────────────────────┘
```

Fugu の API は内部ルーティングを公開しないため、CLI は**マルチシグナル推論**を使用します：
- 初期遅延 → ルーティング決定
- Token バーストパターン → ワーカーアクティベーション
- コンテンツマーカー → 並列ワーカー境界
- Token コスト比率 → オーケストレーションオーバーヘッド

## 🎤 ボイス入力

ボイスモードの使用：
- **VAD**（Voice Activity Detection）による自動セグメンテーション
- **Faster-Whisper** によるローカル STT
- 設定可能なキーによるプッシュトゥトーク（デフォルト：Space）

```bash
# ボイスサポートをインストール
pip install fugu-vibe-cli[voice]

# ボイスセッションを開始
fugu-vibe vibe --voice

# または専用ボイスモード
fugu-vibe voice --continuous
```

## 🏗️ アーキテクチャ

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│  CLI     │  │  コア    │  │  API     │  │ 外部サービス│
│ (Click)  │  │  エンジン  │  │  レイヤー  │  │          │
├──────────┤  ├──────────┤  ├──────────┤  ├──────────┤
│ vibe     │  │ TaskMgr  │  │ FuguClient│  │ Sakana  │
│ submit   │  │ OrchViz  │  │ Request   │  │  API    │
│ status   │  │ EventBus │  │ Stream    │  │         │
│ voice    │  │ GitWT    │  │ Parser    │  │         │
└────┬─────┘  └────┬─────┘  └────┬─────┘  └─────────┘
     │             │             │
┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐
│   TUI    │  │  ボイス   │  │   可視化  │
│ (Rich)   │  │(Whisper) │  │(Timeline)│
└──────────┘  └──────────┘  └──────────┘
```

## 📚 Fugu API の特性

本 CLI は Fugu の独自の API 動作を処理します：

| パラメータ | Fugu の動作 | CLI 処理 |
|-----------|--------------|--------------|
| `temperature` | 受け入れるが**無視** | 警告をログ |
| `parallel_tool_calls` | 受け入れるが**無視** | 警告をログ |
| `previous_response_id` | **受け入れない** | 完全な履歴を送信 |
| `reasoning.effort` | `high` / `xhigh` / `max` | 完全対応 |
| `tools` | ビルトイン `web_search` | `--web-search` で有効化 |
| `max_output_tokens` | 最大 32768 | 設定可能 |
| オーケストレーション Token | 第 3 の Token カテゴリー | 独立して追跡 |

## 🔧 開発

```bash
# クローン
git clone https://github.com/fugu-vibe/fugu-vibe-cli.git
cd fugu-vibe-cli

# uv でインストール（推奨）
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# テストを実行
pytest

# リント
ruff check .
mypy fugu_vibe/
```

### 既知の問題と修正

| 問題 | 修正 |
|-------|-----|
| macOS で Python 3.14 `pyexpat` クラッシュ | Python 3.11–3.13 を使用 |
| PyPI に `asyncio-subprocess-tee` なし | 依存から削除；`asyncio.subprocess` を使用 |
| `api/__init__.py` インポートパスエラー | 修正済：`fugu_vibe.request_builder` → `fugu_vibe.api.request_builder` |

## 📄 ライセンス

MIT ライセンス — 詳細は [LICENSE](LICENSE) ファイルを参照。

---

**Sakana AI とは無関係。** Fugu は Sakana AI の商標です。
