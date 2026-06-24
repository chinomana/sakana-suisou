# Fugu Vibe CLI - Architecture Design

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FUGU VIBE CLI                                     │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │   CLI Layer  │  │   Core Engine │  │    API Layer  │  │  External Svcs  │ │
│  │  (Click)     │  │  (Async)      │  │  (OpenAI SDK) │  │  (Sakana API)   │ │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤  ├─────────────────┤ │
│  │ submit       │  │ TaskManager  │──│ FuguClient   │──│ Responses API   │ │
│  │ status       │  │ Orchestrator │  │ RequestBuilder│  │ Chat Completions│ │
│  │ attach       │  │ EventBus     │  │ StreamParser │  │ Models API      │ │
│  │ voice        │  │ ConfigManager│  │ TokenTracker │  │ Built-in Tools  │ │
│  │ config       │  │ GitWorktree  │  │ RetryHandler │  │                 │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────────────────┘ │
│         │                 │                  │                               │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐                       │
│  │    TUI Layer  │  │  Voice Layer  │  │  Viz Layer    │                       │
│  │  (Rich/Textual)│  │ (Whisper/VAD) │  │ (Orchestration│                       │
│  ├───────────────┤  ├───────────────┤  │  Visualizer)  │                       │
│  │ LiveDashboard │  │ VoiceRecorder │  ├───────────────┤                       │
│  │ TaskTreeView  │  │ STTEngine     │  │ PatternMatcher│                       │
│  │ TokenMonitor  │  │ CommandParser │  │ StateRenderer │                       │
│  │ LogPanel      │  │ AudioPipeline │  │ CostEstimator │                       │
│  └───────────────┘  └───────────────┘  └───────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. Module Architecture

### 2.1 API Layer (`fugu_vibe/api/`)

```python
# Core abstraction: FuguClient
class FuguClient:
    """
    Low-level Sakana API client wrapping OpenAI SDK.
    Handles both Responses API and Chat Completions API.
    """
    
    # Key responsibilities:
    # - Authentication (API key, custom model pool)
    # - Request building (special Fugu parameters)
    # - Streaming with resilience (2h timeout, retries)
    # - Token tracking (input, output, orchestration)
    # - Response parsing (content, tool calls, reasoning)
```

**Special Request Body Format Support:**
- `reasoning.effort`: `"high" | "xhigh" | "max"` 
- `tools`: Built-in `web_search` tool
- `max_output_tokens`: Up to 32768
- `truncation`: `"auto"` (default) or `"disabled"`
- `text.format`: JSON Schema output
- `store`: Conversation persistence
- `metadata`: Custom key-value pairs

**Ignored/Overridden Parameters:**
- `temperature`: Accepted but ignored (Fugu controls)
- `parallel_tool_calls`: Ignored (server forces true)
- `previous_response_id`: Not accepted (send full history)

### 2.2 Core Engine (`fugu_vibe/core/`)

```python
# TaskManager: Async task queue with DAG dependencies
class TaskManager:
    """
    Manages concurrent Fugu tasks with git-worktree isolation.
    Supports task dependencies (DAG), parallel execution, 
    and background/foreground modes.
    """
    
    # Key features:
    # - Git worktree auto-creation per task
    # - Task dependency resolution (DAG)
    # - Parallel execution (configurable max)
    # - Auto-merge on completion
    # - Background/foreground attach

# Orchestrator: Fugu's internal pattern inference
class OrchestrationAnalyzer:
    """
    Infers Fugu's internal orchestration from stream patterns.
    Produces structured events for the visualization layer.
    """
    
    # Inference signals:
    # - Long initial delays → routing decision
    # - Token burst patterns → worker assignment
    # - Interleaved content sections → parallel workers
    # - Quality check markers → verification phase
    # - Token cost breakdown → orchestration tokens
```

### 2.3 TUI Layer (`fugu_vibe/ui/`)

```python
# LiveDashboard: Main TUI with orchestration view
class OrchestrationDashboard:
    """
    Rich-based live dashboard showing:
    - Real-time orchestration timeline
    - Task status tree
    - Token consumption meter
    - Streaming content panel
    - Voice input status
    """

# Components:
# - OrchestrationTimeline: Visual timeline of routing decisions
# - TaskTree: Hierarchical task status view  
# - TokenMeter: Real-time token consumption (3 categories)
# - StreamPanel: Live content output
# - VoiceIndicator: Recording/speaking status
```

### 2.4 Voice Layer (`fugu_vibe/voice/`)

```python
# VoicePipeline: Async voice command system
class VoicePipeline:
    """
    Push-to-talk voice input with:
    - VAD (Voice Activity Detection) for auto-segmentation
    - Faster-Whisper local STT
    - Command intent parsing
    - Async task submission from voice
    """

# Components:
# - AudioRecorder: PyAudio-based recording with VAD
# - STTEngine: Faster-Whisper transcription
# - CommandParser: NLU for extracting task commands
# - VoiceSession: Continuous voice interaction mode
```

## 3. Data Flow

### 3.1 Normal Request Flow

```
User Input
    │
    ▼
┌─────────────┐
│ CLI Parser  │── Parse command + options
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ RequestBuilder│── Construct Fugu-specific request body
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│ FuguClient  │────▶│ Sakana API   │── 2h stream idle timeout
└──────┬──────┘     └──────┬───────┘
       │                   │
       │◀── Stream ────────┘
       │
       ▼
┌─────────────┐
│StreamParser │── Parse SSE chunks, extract content + tool calls
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│OrchestrationAnalyzer│── Infer internal routing from timing/patterns
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌─────────┐
│ TUI   │ │ EventBus│── Broadcast to all listeners
│ Render│ └────┬────┘
└───────┘      │
               ▼
         ┌──────────┐
         │ File/Log │
         │  Output  │
         └──────────┘
```

### 3.2 Async Task Flow

```
Voice/CLI Command
    │
    ▼
┌─────────────┐
│ TaskManager │── Create task, assign worktree
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  GitWorktree │── Create isolated branch/worktree
│   Manager    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ DAG Resolver │── Check dependencies, queue if needed
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────┐
│ TaskRunner  │────▶│FuguClient│
│ (async)     │◀────│          │
└──────┬──────┘     └──────────┘
       │
       ▼
┌─────────────┐
│ AutoMerger  │── Merge worktree back on success
└──────┬──────┘
       │
       ▼
    ┌──────┐
    │ Done │── Notify user, update task tree
    └──────┘
```

## 4. Key Design Decisions

### 4.1 Why not extend codex-fugu?

| Aspect | codex-fugu | fugu-vibe-cli |
|--------|-----------|---------------|
| Architecture | Codex CLI wrapper | Native async Python |
| Orchestration visibility | None | Full inference + visualization |
| Voice input | None | Push-to-talk + VAD |
| Async tasks | Synchronous | DAG-based parallel |
| Prompt control | Fixed base_instructions | Overrideable/unlimited |
| Timeout handling | 2h fixed | Configurable with heartbeat |
| Extensibility | Limited by Codex | Plugin architecture |

### 4.2 Orchestration Inference Strategy

Since Fugu's API does not expose internal routing decisions, we use **multi-signal inference**:

```python
SIGNALS = {
    # Signal              →  Inference
    "initial_delay > 5s"  →  "routing_decision",
    "token_burst_rate"    →  "worker_active", 
    "section_markers"     →  "worker_boundary",
    "interleaved_content" →  "parallel_workers",
    "quality_phrases"     →  "verification_phase",
    "orchestration_tokens"→  "coordination_cost",
}
```

### 4.3 Git Worktree Concurrency Model

```
main branch
    │
    ├── worktree-1/  (task T1: refactor auth)
    │     └── .fugu/   (task metadata)
    │
    ├── worktree-2/  (task T2: write tests ← depends on T1)
    │     └── .fugu/
    │
    └── worktree-3/  (task T3: docs update)
          └── .fugu/

Auto-merge: T1 completes → merge to main → T2 starts
```

## 5. Configuration Hierarchy

```python
# Priority (highest first):
# 1. CLI flags (--model, --effort, --voice)
# 2. Environment variables (FUGU_VIBE_*)  
# 3. Project config (.fugu-vibe.toml)
# 4. User config (~/.config/fugu-vibe/config.toml)
# 5. Defaults

DEFAULT_CONFIG = {
    "api": {
        "base_url": "https://api.sakana.ai/v1",
        "timeout": 7200,  # 2 hours
        "max_retries": 5,
        "stream": True,
    },
    "model": {
        "default": "fugu-ultra",
        "reasoning_effort": "xhigh",
        "max_output_tokens": 32768,
    },
    "orchestration": {
        "viz_mode": "full",       # full | compact | none
        "show_token_usage": True,
        "infer_workers": True,
        "heartbeat_interval": 30,  # seconds
    },
    "voice": {
        "enabled": False,
        "engine": "faster-whisper",  # faster-whisper | whisper-api
        "model": "base",
        "language": "auto",
        "push_to_talk_key": "space",
        "vad_mode": 3,  # aggressiveness 0-3
        "auto_submit": True,
    },
    "tasks": {
        "max_parallel": 5,
        "use_git_worktree": True,
        "auto_merge": True,
        "timeout": 1800,  # 30 min per task
    },
    "prompt": {
        "unlimited_mode": False,  # override base_instructions
        "custom_instructions": None,
    },
}
```

## 6. Event System

```python
# Central event bus for decoupled communication
class EventBus:
    """
    Async event bus connecting all components.
    Used for: TUI updates, logging, task notifications,
    orchestration events, voice triggers.
    """

# Event types:
ORCHESTRATION_START = "orchestration:start"
ORCHESTRATION_ROUTING = "orchestration:routing"  # inferred
ORCHESTRATION_WORKER = "orchestration:worker"    # inferred
ORCHESTRATION_VERIFY = "orchestration:verify"    # inferred
ORCHESTRATION_DONE = "orchestration:done"
STREAM_CONTENT = "stream:content"
STREAM_TOOL_CALL = "stream:tool_call"
STREAM_DONE = "stream:done"
TASK_CREATED = "task:created"
TASK_STARTED = "task:started"
TASK_PROGRESS = "task:progress"
TASK_COMPLETED = "task:completed"
TASK_FAILED = "task:failed"
VOICE_RECORDING = "voice:recording"
VOICE_TRANSCRIBED = "voice:transcribed"
VOICE_COMMAND = "voice:command"
TOKEN_UPDATE = "token:update"
```

## 7. Plugin Architecture (Future)

```python
# Plugin interface for extensibility
class FuguVibePlugin(ABC):
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod  
    def on_orchestration_event(self, event: OrchestrationEvent) -> None: ...
    
    @abstractmethod
    def on_stream_chunk(self, chunk: StreamChunk) -> None: ...
    
    @abstractmethod
    def on_task_complete(self, task: Task) -> None: ...
```
