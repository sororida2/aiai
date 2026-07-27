from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    func: Callable
    input_schema: dict[str, Any]


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
class GuardrailSpec:
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    func: Callable


class ServiceConsistencyError(Exception):
    """auto-discovery 직후 registry.validate()가 참조 무결성 위반을 발견하면 던진다.

    서비스 하나가 부분적으로만 구현된 채(등록은 되지만 내부적으로 깨진 상태) 조용히
    넘어가는 걸 막는 게 목적 — StateMachine.run() 시점까지 미루지 않고 기동 시점에 fail-fast.
    """


class ToolRegistry:
    """새 서비스 = 새 tool 파일 등록. 오케스트레이터는 이 registry만 참조한다."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._workflow_steps: dict[str, WorkflowStepSpec] = {}
        self._judged: dict[str, JudgedSpec] = {}
        self._guardrails: dict[str, GuardrailSpec] = {}

    def register_tool(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool '{spec.name}' already registered")
        self._tools[spec.name] = spec

    def register_workflow_step(self, name: str, spec: WorkflowStepSpec) -> None:
        self._workflow_steps[name] = spec

    def register_judged(self, name: str, spec: JudgedSpec) -> None:
        self._judged[name] = spec

    def register_guardrail(self, name: str, spec: GuardrailSpec) -> None:
        self._guardrails[name] = spec

    def tools(self) -> dict[str, ToolSpec]:
        return dict(self._tools)

    def workflow_steps(self) -> dict[str, WorkflowStepSpec]:
        return dict(self._workflow_steps)

    def guardrail_for(self, name: str) -> GuardrailSpec | None:
        return self._guardrails.get(name)

    def judged_for(self, name: str) -> JudgedSpec | None:
        return self._judged.get(name)

    def validate(self) -> None:
        """등록된 스펙들 사이의 참조 무결성을 검사한다 (registry 내부 상태만으로 판단 가능한 것만).

        auto-discovery로 서비스를 스캔한 직후 한 번 호출하는 걸 전제로 한다 — 개별 모듈을
        import하는 시점이 아니라, 모든 서비스가 등록을 마친 뒤에 전체 그래프를 봐야 next
        참조처럼 다른 모듈이 등록한 step을 가리키는 경우까지 정확히 검사할 수 있다.
        """
        if not self._tools:
            raise ServiceConsistencyError("no tool registered — services/ 아래 워크플로우가 하나도 import되지 않았다")

        step_names = set(self._workflow_steps)
        for step_name, step_spec in self._workflow_steps.items():
            if step_spec.next is None:
                continue
            for outcome, target in step_spec.next.items():
                if target == "DONE" or target in step_names:  # "DONE" == workflow.state_machine.TERMINAL
                    continue
                raise ServiceConsistencyError(
                    f"workflow_step '{step_name}'의 next[{outcome!r}]='{target}'가 등록된 "
                    f"step 이름 어디에도 없다 (오타 의심)"
                )

        for judged_name in self._judged:
            if judged_name not in self._workflow_steps:
                raise ServiceConsistencyError(
                    f"judged node '{judged_name}'가 @workflow_step 없이 등록됐다 — "
                    "judged 노드는 반드시 @workflow_step과 함께 선언해야 state machine에 편입된다"
                )

        for tool_name, guardrail_spec in self._guardrails.items():
            tool_spec = self._tools.get(tool_name)
            if tool_spec is not None and guardrail_spec.func is not tool_spec.func:
                raise ServiceConsistencyError(
                    f"tool '{tool_name}'의 guardrail이 다른 함수에 등록됐다 — "
                    "@guardrail을 @tool보다 아래(먼저 적용되게)에 선언했는지, "
                    "함수 이름이 tool name과 다른지 확인하라"
                )


registry = ToolRegistry()


def _infer_schema(func: Callable) -> dict[str, Any]:
    sig = inspect.signature(func)
    return {
        name: (param.annotation if param.annotation is not inspect.Parameter.empty else Any)
        for name, param in sig.parameters.items()
        if name != "self"
    }


def tool(name: str, description: str) -> Callable:
    """오케스트레이터가 커플링되는 유일한 표면(스키마+설명)을 선언한다."""

    def decorator(func: Callable) -> Callable:
        registry.register_tool(
            ToolSpec(name=name, description=description, func=func, input_schema=_infer_schema(func))
        )
        func.__tool_name__ = name
        return func

    return decorator


def workflow_step(
    order: int,
    *,
    source: str | None = None,
    next: dict[str, str] | None = None,
    max_retries: int = 0,
) -> Callable:
    """결정론적 분기/순환은 여기 next 맵으로 고정한다. agent 재추론 대상이 아니다."""

    def decorator(func: Callable) -> Callable:
        name = func.__name__
        registry.register_workflow_step(
            name,
            WorkflowStepSpec(order=order, source=source, next=next, max_retries=max_retries, func=func),
        )
        func.__step_name__ = name
        return func

    return decorator


def judged(choices: tuple[str, ...], *, confidence_required: str = "confirmed") -> Callable:
    """선택지를 유한 집합으로 강제 — 이 제약이 없으면 자유 위임과 구분이 사라진다."""

    def decorator(func: Callable) -> Callable:
        name = func.__name__
        registry.register_judged(
            name, JudgedSpec(choices=choices, confidence_required=confidence_required, func=func)
        )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            result = func(*args, **kwargs)
            if result not in choices:
                raise ValueError(f"judged node '{name}' returned '{result}', not in bounded choices {choices}")
            return result

        wrapper.__judged_name__ = name
        return wrapper

    return decorator


def guardrail(
    *, input_schema: dict[str, Any] | None = None, output_schema: dict[str, Any] | None = None
) -> Callable:
    """tool 옆에 검증 규칙을 선언한다. 하네스 엔진은 이 선언을 읽기만 하고 tool 이름을 알지 못한다."""

    def decorator(func: Callable) -> Callable:
        name = getattr(func, "__tool_name__", func.__name__)
        registry.register_guardrail(
            name, GuardrailSpec(input_schema=input_schema, output_schema=output_schema, func=func)
        )
        return func

    return decorator
