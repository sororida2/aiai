from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any, Callable

from framework.harness.logging_setup import get_logger
from framework.harness.schema import SchemaViolation, validate_schema

logger = get_logger("workflow_registry")


@dataclass
class WorkflowStepSpec:
    order: int
    source: str | None
    next: dict[str, str] | None
    max_retries: int
    func: Callable


@dataclass
class JudgedSpec:
    choices: tuple[str, ...]
    confidence_required: str
    func: Callable


@dataclass
class HumanActionSpec:
    choices: tuple[str, ...]
    payload_schemas: dict[str, dict[str, Any]] | None
    func: Callable


class WorkflowConsistencyError(Exception):
    """`WorkflowRegistry.validate()`가 이 workflow(파일) 내부의 참조 무결성 위반을 발견하면 던진다.

    `framework.registry.decorators.ServiceConsistencyError`와 대상이 다르다 — 그건
    전역 tool 카탈로그(모든 서비스 import가 끝난 뒤)에 대한 검사고, 이건 파일 하나의
    step/next 그래프에 대한 검사라 그 파일이 자기 자신을 다 정의한 시점에 바로 낼 수 있다.
    """


class WorkflowRegistry:
    """workflow_step/judged/human_action은 tool(파일) 단위로 이 인스턴스가 소유한다.

    전역 `ToolRegistry`(framework.registry.decorators.registry)와 달리 이건 파일마다
    새로 만드는 로컬 네임스페이스다. 스텝 이름이 다른 파일과 겹쳐도 충돌하지 않고,
    `next` 참조도 이 인스턴스 안에 등록된 이름만 가리킬 수 있다 — order/next/max_retries가
    "이 workflow 안에서" 무슨 의미인지는 파일마다 다를 수 있으므로, 전역으로 공유할
    이유가 없다는 게 이 분리의 핵심 근거다.
    """

    def __init__(self) -> None:
        self._steps: dict[str, WorkflowStepSpec] = {}
        self._judged: dict[str, JudgedSpec] = {}
        self._human_actions: dict[str, HumanActionSpec] = {}

    def steps(self) -> dict[str, WorkflowStepSpec]:
        return dict(self._steps)

    def judged_for(self, name: str) -> JudgedSpec | None:
        return self._judged.get(name)

    def human_action_for(self, name: str) -> HumanActionSpec | None:
        return self._human_actions.get(name)

    def step(
        self,
        order: int,
        *,
        source: str | None = None,
        next: dict[str, str] | None = None,
        max_retries: int = 0,
    ) -> Callable:
        """결정론적 분기/순환은 여기 next 맵으로 고정한다. agent 재추론 대상이 아니다."""

        def decorator(func: Callable) -> Callable:
            name = func.__name__

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> str:
                outcome = func(*args, **kwargs)
                if next is not None and outcome not in next:
                    logger.error(
                        "step '%s' returned outcome %r, not in declared next %s", name, outcome, list(next)
                    )
                    raise ValueError(f"step '{name}' returned outcome '{outcome}', not in declared next {list(next)}")
                return outcome

            self._steps[name] = WorkflowStepSpec(
                order=order, source=source, next=next, max_retries=max_retries, func=wrapper
            )
            wrapper.__step_name__ = name
            return wrapper

        return decorator

    def judged(self, choices: tuple[str, ...], *, confidence_required: str = "confirmed") -> Callable:
        """선택지를 유한 집합으로 강제 — 이 제약이 없으면 자유 위임과 구분이 사라진다."""

        def decorator(func: Callable) -> Callable:
            name = func.__name__
            self._judged[name] = JudgedSpec(choices=choices, confidence_required=confidence_required, func=func)

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> str:
                result = func(*args, **kwargs)
                if result not in choices:
                    logger.error("judged node '%s' returned %r, not in bounded choices %s", name, result, choices)
                    raise ValueError(f"judged node '{name}' returned '{result}', not in bounded choices {choices}")
                logger.info("judged '%s' -> %r", name, result)
                return result

            wrapper.__judged_name__ = name
            return wrapper

        return decorator

    def human_action(
        self, choices: tuple[str, ...], *, payload_schemas: dict[str, dict[str, Any]] | None = None
    ) -> Callable:
        """`judged()`와 계약(bounded choices)은 같지만 판단 주체가 모델이 아니라 사람이다.

        함수는 사람의 답이 아직 없으면 `framework.workflow.state_machine.AwaitingHumanAction`을
        던져 실행을 멈추고, 답이 있으면 `{"action": <choices 중 하나>, ...payload}` 형태의
        dict를 반환해야 한다. action별로 다른 payload 구조가 필요하면(예: "서류추가요청"은
        어떤 서류가 더 필요한지 담아야 함) `payload_schemas`에 action별 스키마를 선언한다 —
        action 종류 자체는 여전히 유한 집합(bounded)이고, 그 안의 세부 데이터만 자유롭게
        구조화된다는 원칙(자유 라우팅과 구분되는 judged branch의 핵심)은 그대로 유지된다.
        """

        def decorator(func: Callable) -> Callable:
            name = func.__name__
            self._human_actions[name] = HumanActionSpec(choices=choices, payload_schemas=payload_schemas, func=func)

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> str:
                result = func(*args, **kwargs)
                action = result.get("action") if isinstance(result, dict) else result
                if action not in choices:
                    logger.error(
                        "human_action '%s' returned action %r, not in bounded choices %s", name, action, choices
                    )
                    raise ValueError(f"human_action '{name}' returned action {action!r}, not in bounded choices {choices}")

                schema = (payload_schemas or {}).get(action)
                if schema is not None:
                    try:
                        validate_schema(result, schema)
                    except SchemaViolation as e:
                        logger.error("human_action '%s' payload invalid for action %r: %s", name, action, e.detail)
                        raise ValueError(
                            f"human_action '{name}' payload invalid for action {action!r}: {e.detail}"
                        ) from e

                logger.info("human_action '%s' -> %r", name, action)
                return action

            wrapper.__human_action_name__ = name
            return wrapper

        return decorator

    def validate(self) -> None:
        """이 workflow(파일) 하나만으로 판단 가능한 참조 무결성을 검사한다.

        전역 registry.validate()(tool/guardrail 카탈로그 검사)와 달리, 다른 서비스가
        전부 import되길 기다릴 필요가 없다 — 이 인스턴스에 등록된 이름만으로 next/judged/
        human_action 참조가 전부 닫혀 있으므로, 이 파일이 자기 정의를 마친 시점(모듈
        하단)에 바로 호출해 fail-fast할 수 있다.
        """
        logger.info(
            "validating workflow: steps=%d judged=%d human_actions=%d",
            len(self._steps), len(self._judged), len(self._human_actions),
        )
        step_names = set(self._steps)
        for step_name, step_spec in self._steps.items():
            if step_spec.next is None:
                continue
            for outcome, target in step_spec.next.items():
                if target == "DONE" or target in step_names:  # "DONE" == workflow.state_machine.TERMINAL
                    continue
                logger.error("workflow_step '%s' next[%r]='%s' is unresolved", step_name, outcome, target)
                raise WorkflowConsistencyError(
                    f"workflow_step '{step_name}'의 next[{outcome!r}]='{target}'가 이 파일에 등록된 "
                    f"step 이름 어디에도 없다 (오타 의심)"
                )

        for judged_name in self._judged:
            if judged_name not in self._steps:
                logger.error("judged node '%s' registered without step()", judged_name)
                raise WorkflowConsistencyError(
                    f"judged node '{judged_name}'가 step() 없이 등록됐다 — "
                    "judged 노드는 반드시 step()과 함께 선언해야 state machine에 편입된다"
                )

        for action_name, action_spec in self._human_actions.items():
            if action_name not in self._steps:
                logger.error("human_action node '%s' registered without step()", action_name)
                raise WorkflowConsistencyError(
                    f"human_action node '{action_name}'가 step() 없이 등록됐다 — "
                    "human_action 노드는 반드시 step()과 함께 선언해야 state machine에 편입된다"
                )
            for action in action_spec.payload_schemas or {}:
                if action not in action_spec.choices:
                    logger.error(
                        "human_action node '%s' has payload_schemas for action %r, not in declared choices %s",
                        action_name, action, action_spec.choices,
                    )
                    raise WorkflowConsistencyError(
                        f"human_action node '{action_name}'의 payload_schemas 키 '{action}'가 "
                        f"choices {action_spec.choices} 안에 없다 (오탈자 의심)"
                    )

        logger.info("workflow validation passed")
