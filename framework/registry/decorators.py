from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from framework.harness.logging_setup import get_logger
from framework.workflow.registry import WorkflowRegistry

logger = get_logger("registry")


@dataclass
class ToolSpec:
    name: str
    description: str
    func: Callable
    input_schema: dict[str, Any]
    workflow_registry: WorkflowRegistry | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """spec 자체를 호출 가능하게 만들어, 호출부가 `.func`를 직접 알 필요가 없게 한다."""
        return self.func(*args, **kwargs)


@dataclass
class GuardrailSpec:
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    func: Callable


class ServiceConsistencyError(Exception):
    """auto-discovery 직후 registry.validate()가 tool/guardrail 카탈로그의 참조 무결성 위반을 발견하면 던진다.

    서비스 하나가 부분적으로만 구현된 채(등록은 되지만 내부적으로 깨진 상태) 조용히
    넘어가는 걸 막는 게 목적 — StateMachine.run() 시점까지 미루지 않고 기동 시점에 fail-fast.
    workflow(파일) 내부의 step/next/judged/human_action 무결성은 여기가 아니라 각 파일의
    `WorkflowRegistry.validate()`(-> `WorkflowConsistencyError`)가 담당한다.
    """


class ToolRegistry:
    """새 서비스 = 새 tool 파일 등록. 오케스트레이터는 이 registry만 참조한다.

    workflow_step/judged/human_action은 여기 없다 — 그건 tool(파일) 내부 배선이라
    각 파일이 갖는 `framework.workflow.registry.WorkflowRegistry` 인스턴스가 따로 관리한다.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._guardrails: dict[str, GuardrailSpec] = {}

    def register_tool(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool '{spec.name}' already registered")
        self._tools[spec.name] = spec

    def register_guardrail(self, name: str, spec: GuardrailSpec) -> None:
        self._guardrails[name] = spec

    def tools(self) -> dict[str, ToolSpec]:
        return dict(self._tools)

    def tool_for(self, name: str) -> ToolSpec:
        """이름 하나로 등록된 tool을 바로 찾는다 — `tools()`처럼 전체 dict를 복사하지 않는다.

        반환값(`ToolSpec`) 자체가 호출 가능하므로(`__call__`), 호출부는 `.func`를
        직접 알 필요 없이 `registry.tool_for(name)(...)`처럼 바로 쓰면 된다.
        """
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"tool '{name}' is not registered")
        return spec

    def guardrail_for(self, name: str) -> GuardrailSpec | None:
        return self._guardrails.get(name)

    def output_schema_for(self, name: str) -> Callable[[], dict[str, Any]]:
        """다른 tool의 output_schema를 참조하는 thunk를 돌려준다 — 호출부는 lambda를 안 써도 된다.

        `registry.guardrail_for(name).output_schema`를 지금 당장 읽으면 discover_services()의
        import 순서상 그 tool이 아직 등록 전일 수 있다(예: `subscription_weather_flow`가
        알파벳상 `weather`보다 먼저 import됨). 그래서 여기서는 즉시 읽지 않고, 나중에
        `harness/schema.py`의 `validate_schema()`가 실제 검증 시점에 호출할 thunk만 돌려준다 —
        `@guardrail(output_schema={"weather": registry.output_schema_for("weather")})`처럼 dict
        리터럴 안에 바로 쓸 수 있다(dict 자체는 그 자리에서 진짜 dict로 만들어지고, 이 값만
        나중에 풀림). `input_schema_for()`와 이름을 분리해둔 이유: 하나의 이름(`schema_for`)이
        input/output 둘 중 뭘 주는지 애매해지는 걸 피하려는 것 — 실수로 반대 스키마를
        가져오는 조용한 버그를 막는다.
        """
        return lambda: self.guardrail_for(name).output_schema

    def input_schema_for(self, name: str) -> Callable[[], dict[str, Any]]:
        """`output_schema_for()`와 대칭 — 다른 tool의 input_schema를 참조하는 thunk를 돌려준다."""
        return lambda: self.guardrail_for(name).input_schema

    def validate(self) -> None:
        """등록된 tool/guardrail 사이의 참조 무결성을 검사한다 (registry 내부 상태만으로 판단 가능한 것만).

        auto-discovery로 서비스를 스캔한 직후 한 번 호출하는 걸 전제로 한다. 각 서비스
        파일 내부의 step/next 그래프 무결성은 그 파일이 import되는 시점에 자기 자신의
        `WorkflowRegistry.validate()`로 이미 검증됐으므로 여기서 다시 보지 않는다.
        """
        logger.info(
            "validating registry: tools=%d guardrails=%d", len(self._tools), len(self._guardrails),
        )
        if not self._tools:
            logger.error("no tool registered")
            raise ServiceConsistencyError("no tool registered — services/ 아래 워크플로우가 하나도 import되지 않았다")

        for tool_name, guardrail_spec in self._guardrails.items():
            tool_spec = self._tools.get(tool_name)
            if tool_spec is not None and guardrail_spec.func is not tool_spec.func:
                logger.error("tool '%s' guardrail registered on a mismatched function", tool_name)
                raise ServiceConsistencyError(
                    f"tool '{tool_name}'의 guardrail이 다른 함수에 등록됐다 — "
                    "@guardrail을 @tool보다 아래(먼저 적용되게)에 선언했는지, "
                    "함수 이름이 tool name과 다른지 확인하라"
                )

        logger.info("registry validation passed")


registry = ToolRegistry()


def _infer_schema(func: Callable) -> dict[str, Any]:
    sig = inspect.signature(func)
    return {
        name: (param.annotation if param.annotation is not inspect.Parameter.empty else Any)
        for name, param in sig.parameters.items()
        if name != "self"
    }


def tool(name: str, description: str, *, workflow_registry: WorkflowRegistry | None = None) -> Callable:
    """오케스트레이터가 커플링되는 유일한 표면(스키마+설명)을 선언한다.

    `workflow_registry`는 이 tool이 내부적으로 human_action(pause/resume)을 쓸 때만
    필요하다 — `Orchestrator.resume()`이 "멈췄던 step부터 재개"하려면 그 step이 등록된
    파일의 `WorkflowRegistry` 인스턴스를 알아야 하기 때문. pause 없이 끝까지 실행되는
    tool은 생략해도 된다.
    """

    def decorator(func: Callable) -> Callable:
        registry.register_tool(
            ToolSpec(
                name=name,
                description=description,
                func=func,
                input_schema=_infer_schema(func),
                workflow_registry=workflow_registry,
            )
        )
        func.__tool_name__ = name
        return func

    return decorator


def guardrail(*, input_schema: dict[str, Any] | None = None, output_schema: dict[str, Any] | None = None) -> Callable:
    """tool 옆에 검증 규칙을 선언한다. 하네스 엔진은 이 선언을 읽기만 하고 tool 이름을 알지 못한다.

    dict 값 자리에 인자 없는 callable(`registry.schema_for(name)`이 돌려주는 thunk)을 넣으면,
    `harness/schema.py`의 `validate_schema()`가 그 값을 실제 검증 시점(tool이 호출될 때)에
    평가한다 — 다른 서비스의 output_schema를 재사용할 때 discover_services()의 import 순서와
    무관하게 안전해진다(§ ARCHITECTURE.md "서비스를 조합하는 서비스" 절).
    """

    def decorator(func: Callable) -> Callable:
        name = getattr(func, "__tool_name__", func.__name__)
        registry.register_guardrail(
            name, GuardrailSpec(input_schema=input_schema, output_schema=output_schema, func=func)
        )
        return func

    return decorator
