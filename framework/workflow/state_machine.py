from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from framework.harness.logging_setup import get_logger
from framework.harness.tracing import tracer
from framework.registry.decorators import ToolRegistry, WorkflowStepSpec

logger = get_logger("state_machine")


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
        logger.info("state machine start: entry='%s'", self.entry)

        while current is not None:
            spec = steps.get(current)
            if spec is None:
                logger.error("unknown workflow step '%s'", current)
                raise KeyError(f"unknown workflow step '{current}'")

            with tracer.span(name=current, kind="step"):
                outcome = spec.func(context)

            if spec.next is None:
                logger.info("state machine done: step='%s' (no next map)", current)
                return context

            # outcome이 spec.next의 키 밖이면 @workflow_step의 wrapper가 이미 그 자리에서
            # ValueError를 던졌을 것이므로, 여기 도달했다면 outcome은 항상 유효한 키다.
            next_step = spec.next[outcome]
            logger.info("step '%s' -> outcome=%r -> next='%s'", current, outcome, next_step)

            if next_step == TERMINAL:
                logger.info("state machine done: step='%s'", current)
                return context

            if next_step == current:
                retries[current] = retries.get(current, 0) + 1
                logger.debug("step '%s' retry %d/%s", current, retries[current], spec.max_retries or "∞")
                if spec.max_retries and retries[current] > spec.max_retries:
                    logger.error("step '%s' exceeded max_retries=%d", current, spec.max_retries)
                    raise MaxRetriesExceeded(f"step '{current}' exceeded max_retries={spec.max_retries}")

            current = next_step

        return context
