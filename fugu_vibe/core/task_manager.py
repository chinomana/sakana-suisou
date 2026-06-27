"""
Async task manager with git-worktree isolation and DAG dependencies.

Supports:
- Parallel task execution with configurable limits
- Task dependencies (DAG - Directed Acyclic Graph)
- Git worktree isolation per task
- Auto-merge on completion
- Background/foreground execution modes
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from git import Repo
from git.exc import GitCommandError

from fugu_vibe.core.event_bus import EventBus, EventType

if TYPE_CHECKING:
    from fugu_vibe.api.client import FuguClient
    from fugu_vibe.config import Config

logger = structlog.get_logger()


class TaskStatus(Enum):
    """Task lifecycle states."""

    PENDING = "pending"           # Waiting for dependencies
    QUEUED = "queued"             # Ready but waiting for slot
    RUNNING = "running"           # Currently executing
    COMPLETED = "completed"       # Successfully finished
    FAILED = "failed"             # Error occurred
    CANCELLED = "cancelled"       # User cancelled
    MERGED = "merged"             # Changes merged to main


@dataclass
class Task:
    """A single Fugu task with metadata."""

    # Identity
    task_id: str
    name: str
    description: str = ""
    
    # Execution
    prompt: str = ""
    model: str = "fugu-ultra"
    effort: str = "xhigh"
    web_search: bool = False
    files: list[str] = field(default_factory=list)  # Files to include in context
    
    # Dependencies
    depends_on: list[str] = field(default_factory=list)  # task_ids
    
    # Git
    branch: str = ""
    worktree_path: str = ""
    
    # Status
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Results
    output: str = ""
    error: str = ""
    token_usage: dict = field(default_factory=dict)
    
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        if self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return None

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)


class TaskManager:
    """
    Manages async Fugu tasks with git-worktree isolation.
    
    Usage:
        manager = TaskManager(config, fugu_client)
        await manager.start()
        
        # Submit tasks
        task1 = await manager.submit("Refactor auth", prompt="...")
        task2 = await manager.submit("Write tests", prompt="...", depends_on=[task1.task_id])
        
        # Monitor
        status = await manager.status()
        
        # Shutdown
        await manager.close()
    """

    def __init__(self, config: Config, fugu_client: FuguClient, event_bus: EventBus | None = None):
        self.config = config
        self.client = fugu_client
        self.event_bus = event_bus
        self.task_config = config.tasks
        
        # Task storage
        self._tasks: dict[str, Task] = {}
        self._dependency_graph: dict[str, set[str]] = defaultdict(set)
        self._reverse_deps: dict[str, set[str]] = defaultdict(set)
        
        # Concurrency control
        self._semaphore: asyncio.Semaphore | None = None
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        
        # Git
        self._repo: Repo | None = None
        self._repo_root: Path | None = None
        
        # State
        self._running = False
        self._scheduler_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Initialize task manager and git repo."""
        self._semaphore = asyncio.Semaphore(self.task_config.max_parallel)
        self._running = True
        
        # Initialize git
        self._init_git()
        
        # Start scheduler
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info(
            "task_manager_started",
            max_parallel=self.task_config.max_parallel,
            repo_root=str(self._repo_root) if self._repo_root else None,
        )

    async def close(self) -> None:
        """Shutdown task manager."""
        self._running = False
        
        # Cancel running tasks
        for task_id, task in self._running_tasks.items():
            task.cancel()
            self._tasks[task_id].status = TaskStatus.CANCELLED
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("task_manager_stopped")

    def _init_git(self) -> None:
        """Initialize git repository for worktree management."""
        try:
            # Find git repo from current directory
            self._repo = Repo(search_parent_directories=True)
            self._repo_root = Path(self._repo.working_dir)
        except Exception:
            # No git repo - use temp directory
            self._repo_root = Path(tempfile.mkdtemp(prefix="fugu-vibe-"))
            self._repo = Repo.init(self._repo_root)
            logger.warning("no_git_repo_found", using_temp=str(self._repo_root))

    async def submit(
        self,
        name: str,
        prompt: str,
        description: str = "",
        model: str | None = None,
        effort: str = "xhigh",
        web_search: bool = False,
        files: list[str] | None = None,
        depends_on: list[str] | None = None,
        **metadata: Any,
    ) -> Task:
        """
        Submit a new task for execution.
        
        Args:
            name: Task name
            prompt: The prompt/instruction for Fugu
            description: Optional description
            model: Model to use (default from config)
            effort: Reasoning effort level
            web_search: Enable web search
            files: Files to include in context
            depends_on: Task IDs this task depends on
            **metadata: Additional metadata
        """
        task_id = self._generate_task_id(name)
        
        task = Task(
            task_id=task_id,
            name=name,
            description=description,
            prompt=prompt,
            model=model or self.config.model.default,
            effort=effort,
            web_search=web_search,
            files=files or [],
            depends_on=depends_on or [],
            metadata=metadata,
        )
        
        self._tasks[task_id] = task
        
        # Build dependency graph
        for dep_id in task.depends_on:
            self._dependency_graph[task_id].add(dep_id)
            self._reverse_deps[dep_id].add(task_id)
        
        # Check if ready to run
        if self._is_ready(task_id):
            task.status = TaskStatus.QUEUED
            await self._queue.put(task_id)
        else:
            task.status = TaskStatus.PENDING
        
        await self._emit(EventType.TASK_CREATED, {"task_id": task_id, "name": name})
        logger.info("task_submitted", task_id=task_id, name=name, deps=task.depends_on)
        
        return task

    async def status(self, task_id: str | None = None) -> dict[str, Any]:
        """Get status of all tasks or a specific task."""
        if task_id:
            task = self._tasks.get(task_id)
            if not task:
                return {"error": f"Task {task_id} not found"}
            return self._task_to_dict(task)
        
        return {
            "tasks": [self._task_to_dict(t) for t in self._tasks.values()],
            "running": len(self._running_tasks),
            "queued": self._queue.qsize(),
            "max_parallel": self.task_config.max_parallel,
        }

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task."""
        task = self._tasks.get(task_id)
        if not task or task.is_terminal:
            return False
        
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
        
        task.status = TaskStatus.CANCELLED
        await self._emit(EventType.TASK_CANCELLED, {"task_id": task_id})
        return True

    def _is_ready(self, task_id: str) -> bool:
        """Check if all dependencies are satisfied."""
        task = self._tasks[task_id]
        for dep_id in task.depends_on:
            dep = self._tasks.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def _generate_task_id(self, name: str) -> str:
        """Generate a unique task ID."""
        timestamp = str(time.time())
        hash_input = f"{name}-{timestamp}"
        return f"{name.lower().replace(' ', '-')}-{hashlib.md5(hash_input.encode()).hexdigest()[:8]}"

    def _create_worktree(self, task: Task) -> str:
        """Create a git worktree for isolated task execution."""
        if not self.task_config.use_git_worktree or not self._repo:
            # Use temp directory
            wt_path = tempfile.mkdtemp(prefix=f"fugu-{task.task_id}-")
            task.branch = f"fugu-task-{task.task_id}"
            return wt_path
        
        # Create branch and worktree
        branch_name = f"fugu-task-{task.task_id}"
        wt_path = self._repo_root / ".fugu-worktrees" / task.task_id
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Create branch from main
            main_branch = self.task_config.git_default_branch
            self._repo.create_head(branch_name, getattr(self._repo.heads, main_branch))
            
            # Create worktree
            self._repo.git.worktree("add", str(wt_path), branch_name)
            task.branch = branch_name
            
        except GitCommandError as e:
            logger.warning("worktree_creation_failed", error=str(e))
            # Fallback to temp
            wt_path = Path(tempfile.mkdtemp(prefix=f"fugu-{task.task_id}-"))
        
        return str(wt_path)

    def _merge_worktree(self, task: Task) -> bool:
        """Merge completed task back to main branch."""
        if not self.task_config.auto_merge or not task.branch:
            return False
        
        try:
            # Switch to main and merge
            main_branch = self.task_config.git_default_branch
            main = getattr(self._repo.heads, main_branch)
            self._repo.head.reference = main
            self._repo.git.merge(task.branch, no_ff=True, m=f"Merge fugu task: {task.name}")
            
            # Clean up worktree
            self._repo.git.worktree("remove", task.worktree_path, force=True)
            
            task.status = TaskStatus.MERGED
            logger.info("task_merged", task_id=task.task_id)
            return True
            
        except GitCommandError as e:
            logger.error("merge_failed", task_id=task.task_id, error=str(e))
            return False

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop processing the task queue."""
        while self._running:
            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                
                # Acquire semaphore slot
                async with self._semaphore:
                    if task_id in self._tasks and not self._tasks[task_id].is_terminal:
                        self._running_tasks[task_id] = asyncio.create_task(
                            self._execute_task(task_id)
                        )
                        
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("scheduler_error")

    async def _execute_task(self, task_id: str) -> None:
        """Execute a single Fugu task."""
        task = self._tasks[task_id]
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        await self._emit(EventType.TASK_STARTED, {"task_id": task_id})
        
        try:
            # Create worktree
            task.worktree_path = self._create_worktree(task)
            
            # Build messages
            messages = [{"role": "user", "content": task.prompt}]
            
            # Execute via Fugu client
            output_parts = []
            async for chunk in self.client.send(
                messages=messages,
                model=task.model,
                effort=task.effort,  # type: ignore
                web_search=task.web_search,
            ):
                if chunk.type == "content":
                    output_parts.append(chunk.content)
                elif chunk.type == "token_usage":
                    task.token_usage = {
                        "input": chunk.token_usage.input_tokens,
                        "output": chunk.token_usage.output_tokens,
                        "orchestration": chunk.token_usage.orchestration_tokens,
                    }
                
                # Emit progress
                await self._emit(
                    EventType.TASK_PROGRESS,
                    {"task_id": task_id, "output_length": len("".join(output_parts))},
                )
            
            task.output = "".join(output_parts)
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            
            # Auto-merge if enabled
            if self.task_config.auto_merge:
                self._merge_worktree(task)
            
            await self._emit(EventType.TASK_COMPLETED, {
                "task_id": task_id,
                "duration": task.duration,
                "tokens": task.token_usage,
            })
            
            # Wake up dependent tasks
            await self._wake_dependents(task_id)
            
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            raise
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            await self._emit(EventType.TASK_FAILED, {"task_id": task_id, "error": str(e)})
            logger.error("task_failed", task_id=task_id, error=str(e))
        finally:
            self._running_tasks.pop(task_id, None)

    async def _wake_dependents(self, completed_task_id: str) -> None:
        """Check and queue tasks that were waiting on the completed task."""
        for dependent_id in self._reverse_deps[completed_task_id]:
            if dependent_id in self._tasks:
                task = self._tasks[dependent_id]
                if task.status == TaskStatus.PENDING and self._is_ready(dependent_id):
                    task.status = TaskStatus.QUEUED
                    await self._queue.put(dependent_id)

    async def _emit(self, event_type: EventType, data: dict[str, Any]) -> None:
        """Emit event to bus."""
        if self.event_bus:
            await self.event_bus.emit(event_type, data, source="task_manager")

    def _task_to_dict(self, task: Task) -> dict[str, Any]:
        """Convert task to dictionary representation."""
        return {
            "task_id": task.task_id,
            "name": task.name,
            "description": task.description,
            "status": task.status.value,
            "model": task.model,
            "effort": task.effort,
            "depends_on": task.depends_on,
            "branch": task.branch,
            "worktree": task.worktree_path,
            "duration": task.duration,
            "token_usage": task.token_usage,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
