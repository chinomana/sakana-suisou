"""
Orchestration inference engine: reverse-engineers Fugu's internal
multi-agent coordination from streaming response patterns.

Since Sakana Fugu's API does not expose internal routing decisions,
we use multi-signal temporal analysis to infer:
- Routing decisions (which models were selected)
- Worker activation (parallel agent execution)
- Verification phases (quality checking)
- Coordination overhead (orchestration token burn)
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import structlog

from fugu_vibe.api.stream_parser import StreamChunk, TokenUsage
from fugu_vibe.core.event_bus import EventBus, EventType

if TYPE_CHECKING:
    from fugu_vibe.config import Config

logger = structlog.get_logger()


class OrchestrationPhase(Enum):
    """Inferred phases of Fugu's internal orchestration."""

    IDLE = "idle"
    ROUTING = "routing"           # Deciding which models to use
    WORKER_ACTIVE = "worker"      # Sub-agent executing
    VERIFYING = "verifying"       # Quality check / self-correction
    SYNTHESIZING = "synthesizing" # Combining worker outputs
    DONE = "done"
    ERROR = "error"


@dataclass
class WorkerInfo:
    """Inferred worker agent information."""

    worker_id: str
    inferred_model: str = "unknown"
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None
    token_count: int = 0
    section_markers: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        end = self.end_time or time.monotonic()
        return end - self.start_time


@dataclass
class OrchestrationState:
    """Current inferred state of Fugu's orchestration."""

    phase: OrchestrationPhase = OrchestrationPhase.IDLE
    start_time: float = field(default_factory=time.monotonic)
    routing_model: str | None = None
    routing_confidence: float | None = None
    workers: list[WorkerInfo] = field(default_factory=list)
    current_worker: WorkerInfo | None = None
    verification_count: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def active_workers(self) -> int:
        return sum(1 for w in self.workers if w.end_time is None)


@dataclass
class OrchestrationEvent:
    """Structured orchestration event for TUI consumption."""

    phase: OrchestrationPhase
    timestamp: float
    message: str
    details: dict = field(default_factory=dict)
    worker_id: str | None = None
    model: str | None = None
    confidence: float | None = None
    tokens: TokenUsage | None = None


class OrchestrationAnalyzer:
    """
    Analyzes Fugu streaming patterns to infer internal orchestration.

    Strategy: Since Fugu doesn't expose internal routing, we use
    temporal pattern analysis:

    1. Initial delay > threshold → routing decision phase
    2. Token burst patterns → worker activation
    3. Content section markers → parallel worker boundaries
    4. Quality phrases → verification phase
    5. Token cost ratios → orchestration overhead estimation
    """

    # Signal thresholds (tunable via config)
    ROUTING_DELAY_THRESHOLD = 5.0      # seconds suggesting routing
    WORKER_BURST_WINDOW = 3.0          # seconds of high-rate tokens
    WORKER_BURST_MIN_TOKENS = 50       # minimum tokens for burst
    VERIFICATION_KEYWORDS = [          # phrases suggesting self-check
        "let me verify",
        "double-check",
        "confirm",
        "actually",
        "wait",
        "reconsider",
        "alternative",
        "let me think",
        "on second thought",
    ]
    SECTION_MARKERS = [                # structural markers
        "## ",
        "### ",
        "---",
        "===",
    ]

    def __init__(self, config: Config | None = None, event_bus: EventBus | None = None):
        self.config = config
        self.event_bus = event_bus
        self.state = OrchestrationState()

        # Signal buffers
        self._token_buffer: deque[tuple[float, int]] = deque(maxlen=1000)
        self._content_buffer: str = ""
        self._first_token_time: float | None = None
        self._last_token_time: float | None = None
        self._token_rate_window: list[tuple[float, int]] = []

        # Detection state
        self._routing_detected = False
        self._worker_count = 0
        self._verification_detected = False

        logger.info("orchestration_analyzer_initialized")

    async def analyze_chunk(self, chunk: StreamChunk) -> OrchestrationEvent | None:
        """
        Process a stream chunk and emit orchestration events.
        Returns an event if a phase transition is detected.
        """
        now = time.monotonic()

        # Track timing
        if self._first_token_time is None and chunk.type in ("content", "reasoning"):
            self._first_token_time = now
            # Initial delay detection → routing phase
            initial_delay = chunk.elapsed_time
            if initial_delay > self.ROUTING_DELAY_THRESHOLD and not self._routing_detected:
                return await self._detect_routing(chunk, initial_delay)

        # Track token usage
        if chunk.type == "token_usage" and chunk.token_usage:
            self.state.token_usage.update(chunk.token_usage)
            if chunk.routing_confidence:
                self.state.routing_confidence = chunk.routing_confidence
            await self._emit_token_update()

        # Content analysis
        if chunk.type == "content":
            self._token_buffer.append((now, len(chunk.content)))
            self._content_buffer += chunk.content

            # Check for worker burst patterns
            event = await self._detect_worker_patterns(now, chunk)
            if event:
                return event

            # Check for verification markers
            event = await self._detect_verification(chunk)
            if event:
                return event

        self._last_token_time = now
        return None

    async def _detect_routing(self, chunk: StreamChunk, delay: float) -> OrchestrationEvent:
        """Detect routing decision phase from initial delay."""
        self._routing_detected = True
        self.state.phase = OrchestrationPhase.ROUTING

        # Infer routing model from confidence if available
        confidence = chunk.routing_confidence or min(delay / 30.0, 0.95)
        self.state.routing_confidence = confidence

        # Infer model from delay profile
        inferred_model = self._infer_model_from_delay(delay)
        self.state.routing_model = inferred_model

        event = OrchestrationEvent(
            phase=OrchestrationPhase.ROUTING,
            timestamp=time.monotonic(),
            message=f"Routing decision ({delay:.1f}s delay)",
            model=inferred_model,
            confidence=confidence,
            details={"delay_seconds": delay, "inferred": True},
        )

        await self._emit_event(event)
        return event

    async def _detect_worker_patterns(self, now: float, chunk: StreamChunk) -> OrchestrationEvent | None:
        """Detect worker activation from token burst patterns."""
        # Calculate rolling token rate
        window_start = now - self.WORKER_BURST_WINDOW
        recent_tokens = [
            size for ts, size in self._token_buffer
            if ts >= window_start
        ]

        if len(recent_tokens) < 3:
            return None

        rate = sum(recent_tokens) / self.WORKER_BURST_WINDOW

        # High rate suggests active worker
        if rate > self.WORKER_BURST_MIN_TOKENS and self.state.phase != OrchestrationPhase.WORKER_ACTIVE:
            self._worker_count += 1
            self.state.phase = OrchestrationPhase.WORKER_ACTIVE

            worker = WorkerInfo(
                worker_id=f"W{self._worker_count}",
                inferred_model=self.state.routing_model or "unknown",
            )
            self.state.workers.append(worker)
            self.state.current_worker = worker

            event = OrchestrationEvent(
                phase=OrchestrationPhase.WORKER_ACTIVE,
                timestamp=now,
                message=f"Worker-{self._worker_count} active (rate: {rate:.0f} tok/s)",
                worker_id=worker.worker_id,
                model=worker.inferred_model,
                details={"token_rate": rate, "inferred": True},
            )

            await self._emit_event(event)
            return event

        # Rate drop suggests worker transition
        if rate < 10 and self.state.phase == OrchestrationPhase.WORKER_ACTIVE:
            if self.state.current_worker:
                self.state.current_worker.end_time = now
            self.state.phase = OrchestrationPhase.SYNTHESIZING

            event = OrchestrationEvent(
                phase=OrchestrationPhase.SYNTHESIZING,
                timestamp=now,
                message="Synthesizing worker outputs",
                details={"workers_completed": self._worker_count, "inferred": True},
            )

            await self._emit_event(event)
            return event

        return None

    async def _detect_verification(self, chunk: StreamChunk) -> OrchestrationEvent | None:
        """Detect verification phase from content markers."""
        lower_content = chunk.content.lower()

        for keyword in self.VERIFICATION_KEYWORDS:
            if keyword in lower_content and not self._verification_detected:
                self._verification_detected = True
                self.state.phase = OrchestrationPhase.VERIFYING
                self.state.verification_count += 1

                event = OrchestrationEvent(
                    phase=OrchestrationPhase.VERIFYING,
                    timestamp=time.monotonic(),
                    message=f"Self-verification (#{self.state.verification_count})",
                    details={"trigger": keyword, "inferred": True},
                )

                await self._emit_event(event)
                return event

        return None

    def _infer_model_from_delay(self, delay: float) -> str:
        """Infer which model was routed based on delay profile."""
        # Heuristic: longer delays suggest more complex routing (fugu-ultra)
        # or specific model selection
        if delay < 2.0:
            return "fugu-direct"  # Fast path, no routing
        elif delay < 8.0:
            return "fugu-routed"  # Single model routing
        elif delay < 20.0:
            return "fugu-ultra"   # Multi-agent coordination
        else:
            return "fugu-ultra-complex"  # Deep multi-agent

    async def _emit_event(self, event: OrchestrationEvent) -> None:
        """Emit orchestration event to event bus."""
        if self.event_bus:
            await self.event_bus.emit(
                EventType.ORCH_ROUTING if event.phase == OrchestrationPhase.ROUTING else
                EventType.ORCH_WORKER if event.phase == OrchestrationPhase.WORKER_ACTIVE else
                EventType.ORCH_VERIFY if event.phase == OrchestrationPhase.VERIFYING else
                EventType.ORCH_DONE,
                data={
                    "phase": event.phase.value,
                    "message": event.message,
                    "model": event.model,
                    "confidence": event.confidence,
                    "worker_id": event.worker_id,
                    "details": event.details,
                },
                source="orchestration_analyzer",
            )

    async def _emit_token_update(self) -> None:
        """Emit token usage update."""
        if self.event_bus:
            await self.event_bus.emit(
                EventType.TOKEN_UPDATE,
                data={
                    "input_tokens": self.state.token_usage.input_tokens,
                    "output_tokens": self.state.token_usage.output_tokens,
                    "orchestration_tokens": self.state.token_usage.orchestration_tokens,
                    "total_tokens": self.state.token_usage.total_tokens,
                },
                source="orchestration_analyzer",
            )

    async def finalize(self) -> OrchestrationEvent:
        """Finalize orchestration analysis and emit summary."""
        self.state.phase = OrchestrationPhase.DONE

        # Close any open workers
        for worker in self.state.workers:
            if worker.end_time is None:
                worker.end_time = time.monotonic()

        event = OrchestrationEvent(
            phase=OrchestrationPhase.DONE,
            timestamp=time.monotonic(),
            message=(
                f"Orchestration complete: {len(self.state.workers)} workers, "
                f"{self.state.verification_count} verifications, "
                f"{self.state.elapsed:.1f}s total"
            ),
            tokens=self.state.token_usage,
            details={
                "total_workers": len(self.state.workers),
                "total_verifications": self.state.verification_count,
                "total_elapsed": self.state.elapsed,
                "routing_model": self.state.routing_model,
            },
        )

        await self._emit_event(event)
        return event
