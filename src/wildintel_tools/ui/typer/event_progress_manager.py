from dataclasses import dataclass
from typing import Optional, Literal
from queue import Queue, Empty
from collections import deque
import threading
import time

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live


# =========================================================
# EVENTS
# =========================================================

@dataclass
class Event:
    type: str


@dataclass
class TaskEvent(Event):
    task_name: str
    state: str  # start | running | end | fail
    advance: int = 1
    total: Optional[int] = None
    description: Optional[str] = None

    item_name: Optional[str] = None
    item_status: Optional[Literal["start", "end", "fail"]] = None
    item_description: Optional[str] = None


@dataclass
class LogEvent(Event):
    message: str


_SENTINEL = None  # put into queue to stop the renderer


# =========================================================
# MANAGER (PRODUCERS ONLY - THREAD SAFE VIA QUEUE)
# =========================================================

class EventProgressManager:
    def __init__(self, max_logs: int = 10):
        self.queue: Queue = Queue()
        self.logs = deque(maxlen=max_logs)

        self.console = Console()

        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
        )

        self.tasks = {}

        self.layout = Layout()
        self.layout.split(
            Layout(name="progress"),
            Layout(name="logs"),
        )

    # -------------------------
    # Public API (safe for threads)
    # -------------------------
    def emit_task(self, event: TaskEvent):
        self.queue.put(event)

    def log(self, message: str):
        self.queue.put(LogEvent(type="log", message=message))

    def stop(self):
        self.queue.put(_SENTINEL)


# =========================================================
# RENDERER (ONLY THREAD TOUCHING RICH)
# =========================================================

class Renderer:
    def __init__(self, manager: EventProgressManager):
        self.m = manager

    def run(self):
        with Live(self.m.layout, console=self.m.console, refresh_per_second=10):
            while True:
                try:
                    event = self.m.queue.get(timeout=0.1)
                except Empty:
                    continue

                if event is _SENTINEL:
                    break

                if isinstance(event, LogEvent):
                    self._handle_log(event)

                elif isinstance(event, TaskEvent):
                    self._handle_task(event)

                self.m.layout["progress"].update(self.m.progress)
                self._render_logs()

    # -------------------------
    def _handle_log(self, event: LogEvent):
        self.m.logs.append(event.message)
        self._render_logs()

    def _render_logs(self):
        self.m.layout["logs"].update(
            Panel("\n".join(self.m.logs), title="Logs")
        )

    # -------------------------
    def _handle_task(self, e: TaskEvent):
        if e.task_name not in self.m.tasks:
            task_id = self.m.progress.add_task(
                e.description or e.task_name,
                total=e.total,
            )
            self.m.tasks[e.task_name] = task_id

        task_id = self.m.tasks[e.task_name]

        if e.total is not None:
            self.m.progress.update(task_id, total=e.total)

        if e.state == "start":
            self.m.progress.update(
                task_id,
                description=f"▶ {e.description or e.task_name}",
            )

        elif e.state == "running":
            self.m.progress.advance(task_id, e.advance)
            if e.item_name and e.item_status == "start":
                self._handle_log(LogEvent(type="log", message=f"… {e.item_name}" + (f" — {e.item_description}" if e.item_description else "")))
            elif e.item_name and e.item_status == "end":
                self._handle_log(LogEvent(type="log", message=f"✔ {e.item_name}" + (f" — {e.item_description}" if e.item_description else "")))
            elif e.item_name and e.item_status == "fail":
                self._handle_log(LogEvent(type="log", message=f"✖ {e.item_name}" + (f" — {e.item_description}" if e.item_description else "")))

        elif e.state == "end":
            self.m.progress.update(
                task_id,
                completed=next((t.total for t in self.m.progress.tasks if t.id == task_id), None) or 1,
                description=f"✔ {e.description or e.task_name}",
            )
            self.m.progress.stop_task(task_id)
            del self.m.tasks[e.task_name]

        elif e.state == "fail":
            self.m.progress.update(
                task_id,
                description=f"✖ {e.task_name}",
            )
            self.m.progress.stop_task(task_id)
            del self.m.tasks[e.task_name]


# =========================================================
# WORKERS
# =========================================================

def worker(name: str, manager: EventProgressManager):
    manager.emit_task(TaskEvent(
        type="task",
        task_name=name,
        state="start",
        total=5,
        description=f"Processing {name}",
    ))

    for i in range(5):
        time.sleep(0.4)

        manager.emit_task(TaskEvent(
            type="task",
            task_name=name,
            state="running",
            advance=1,
            item_name=f"{name}-step-{i}",
            item_status="end",
            item_description=f"step {i} done",
        ))

    manager.emit_task(TaskEvent(
        type="task",
        task_name=name,
        state="end",
        description=f"Processing {name}",
    ))


def run_jobs(manager: EventProgressManager, n_workers: int = 3):
    threads = []

    for i in range(n_workers):
        t = threading.Thread(
            target=worker,
            args=(f"task_{i}", manager),
            daemon=True,
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    manager.log("All tasks completed")
    manager.stop()


# =========================================================
# EXAMPLE USAGE (INCLUDED IN SAME FILE)
# =========================================================

if __name__ == "__main__":
    manager = EventProgressManager()
    renderer = Renderer(manager)

    ui_thread = threading.Thread(target=renderer.run, daemon=True)
    ui_thread.start()

    run_jobs(manager, n_workers=5)

    ui_thread.join()
