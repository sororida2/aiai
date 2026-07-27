from __future__ import annotations

import contextlib
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Span:
    name: str
    kind: str
    start: float
    end: float | None = None
    children: list["Span"] = field(default_factory=list)


@dataclass
class Trace:
    trace_id: str
    root: Span


class Tracer:
    """하나의 요청(Trace) 안에 Orchestrator Span, 그 아래 Tool Span들이 중첩된다."""

    def __init__(self) -> None:
        self._stack: list[Span] = []
        self.current_trace: Trace | None = None

    @contextlib.contextmanager
    def start_trace(self, name: str):
        root = Span(name=name, kind="orchestrator", start=time.monotonic())
        self.current_trace = Trace(trace_id=str(uuid.uuid4()), root=root)
        self._stack = [root]
        try:
            yield self.current_trace
        finally:
            root.end = time.monotonic()

    @contextlib.contextmanager
    def span(self, name: str, kind: str = "tool"):
        parent = self._stack[-1]
        child = Span(name=name, kind=kind, start=time.monotonic())
        parent.children.append(child)
        self._stack.append(child)
        try:
            yield child
        finally:
            child.end = time.monotonic()
            self._stack.pop()


tracer = Tracer()
