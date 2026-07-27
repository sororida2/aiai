from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from framework.registry.decorators import ToolRegistry, WorkflowStepSpec


class MaxRetriesExceeded(Exception):
    pass


TERMINAL = "DONE"


@dataclass
class StateMachine:
    """청약진행상황처럼 순서·분기·순환이 이미 알려진 도메인을 위한 고정 파이프라인.

    @workflow_step의 next 맵이 결정론적 분기/순환을 코드로 못박고,
    judged 함수만 실행 시점에 모델 판단으로 넘어간다(bounded choices는
    @judged 데코레이터가 강제).
    """

    registry: ToolRegistry
    entry: str

    def steps(self) -> dict[str, WorkflowStepSpec]:
        return self.registry.workflow_steps()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        steps = self.steps()
        current = self.entry
        retries: dict[str, int] = {}

        while current is not None:
            spec = steps.get(current)
            if spec is None:
                raise KeyError(f"unknown workflow step '{current}'")

            outcome = spec.func(context)

            if spec.next is None:
                return context

            next_step = spec.next.get(outcome)
            if next_step is None:
                raise ValueError(f"step '{current}' produced unmapped outcome '{outcome}'")

            if next_step == TERMINAL:
                return context

            if next_step == current:
                retries[current] = retries.get(current, 0) + 1
                if spec.max_retries and retries[current] > spec.max_retries:
                    raise MaxRetriesExceeded(f"step '{current}' exceeded max_retries={spec.max_retries}")

            current = next_step

        return context
