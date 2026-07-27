from __future__ import annotations

import contextlib
import time
import uuid
from dataclasses import dataclass, field

from framework.harness.logging_setup import get_logger

logger = get_logger("tracing")


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
        logger.info("trace %s start [%s] %s", self.current_trace.trace_id[:8], root.kind, name)
        try:
            yield self.current_trace
        finally:
            root.end = time.monotonic()
            logger.info(
                "trace %s end   [%s] %s duration=%.3fs",
                self.current_trace.trace_id[:8], root.kind, name, root.end - root.start,
            )

    @contextlib.contextmanager
    def span(self, name: str, kind: str = "tool"):
        # StateMachine.run()이 span()을 쓰기 때문에, tool 함수가 오케스트레이터 없이
        # 단독 호출(직접 테스트 등)돼서 활성 trace가 없는 경우도 있다 — 그때는 암묵적
        # 루트를 하나 열어서 IndexError 없이 동작하게 한다.
        opened_root = False
        if not self._stack:
            self._stack = [Span(name="untraced", kind="root", start=time.monotonic())]
            opened_root = True

        parent = self._stack[-1]
        child = Span(name=name, kind=kind, start=time.monotonic())
        parent.children.append(child)
        self._stack.append(child)
        indent = "  " * (len(self._stack) - 1)
        logger.info("%sspan start [%s] %s", indent, kind, name)
        try:
            yield child
        finally:
            child.end = time.monotonic()
            logger.info("%sspan end   [%s] %s duration=%.3fs", indent, kind, name, child.end - child.start)
            self._stack.pop()
            if opened_root:
                self._stack = []


tracer = Tracer()
