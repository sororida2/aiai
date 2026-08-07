from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any, Callable

from agents import FunctionTool, function_tool

from framework.harness.logging_setup import get_logger
from framework.workflow.registry import WorkflowRegistry
from framework.workflow.state_machine import AwaitingHumanAction

logger = get_logger("registry")


@dataclass
class ToolSpec:
    name: str
    description: str
    func: Callable
    """원본(undecorated) 함수. SDK `function_tool()`은 데코레이트한 함수를 `FunctionTool`
    객체로 통째로 바꿔버려서(JSON 문자열 인자를 받는 `on_invoke_tool`만 남음) 서비스가
    다른 서비스를 파이썬 함수처럼 직접 호출하는 패턴(`registry.tool_for(name)`)이 안 된다.
    그래서 원본을 따로 보존해두고, SDK에 넘길 물건은 `function_tool` 필드에 별도로 둔다."""

    function_tool: FunctionTool
    """`Agent(tools=[...])`에 그대로 넣을 SDK 객체."""

    output_schema: dict[str, Any] | None = None
    workflow_registry: WorkflowRegistry | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)


class ServiceConsistencyError(Exception):
    """auto-discovery 직후 registry.validate()가 tool 카탈로그의 문제를 발견하면 던진다."""


class ToolRegistry:
    """새 서비스 = 새 tool 파일 등록. `main.py`가 조립하는 triage `Agent`는 이 registry만 참조한다."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register_tool(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool '{spec.name}' already registered")
        self._tools[spec.name] = spec

    def tools(self) -> dict[str, ToolSpec]:
        return dict(self._tools)

    def tool_for(self, name: str) -> ToolSpec:
        """이름 하나로 등록된 tool을 바로 찾는다 — `tools()`처럼 전체 dict를 복사하지 않는다.

        반환값(`ToolSpec`) 자체가 호출 가능하므로(`__call__`), 서비스가 다른 서비스를
        합성할 때 `registry.tool_for("weather")(location=...)`처럼 SDK를 거치지 않고
        원본 함수를 바로 부르면 된다 — `discover_services()`의 import 순서와 무관하게
        안전하도록 항상 호출 시점(스텝 본문 안)에 조회해서 쓴다.
        """
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"tool '{name}' is not registered")
        return spec

    def function_tools(self) -> list[FunctionTool]:
        """`Agent(tools=...)`에 그대로 넣을 SDK `FunctionTool` 목록."""
        return [spec.function_tool for spec in self._tools.values()]

    def validate(self) -> None:
        """등록된 tool 카탈로그의 참조 무결성을 검사한다 (registry 내부 상태만으로 판단 가능한 것만).

        workflow(파일) 내부의 step/next/judged/human_action 무결성은 여기가 아니라 각 파일의
        `WorkflowRegistry.validate()`(-> `WorkflowConsistencyError`)가 담당한다.
        """
        logger.info("validating registry: tools=%d", len(self._tools))
        if not self._tools:
            logger.error("no tool registered")
            raise ServiceConsistencyError("no tool registered — services/ 아래 워크플로우가 하나도 import되지 않았다")
        logger.info("registry validation passed")


registry = ToolRegistry()


def tool(
    name: str,
    description: str,
    *,
    output_schema: dict[str, Any] | None = None,
    workflow_registry: WorkflowRegistry | None = None,
    pausable: bool = False,
) -> Callable:
    """SDK `function_tool()`을 감싸 등록한다. 예전 `@tool`+`@guardrail`을 합친 자리다.

    `pausable=True`면 SDK의 `function_tool(..., failure_error_function=None)`을 쓴다 —
    기본값(SDK가 tool 함수의 예외를 모델에게 보여줄 에러 메시지로 바꿔버림)을 끄는
    옵트아웃이다. `AwaitingHumanAction`이 "일시정지 신호"라는 의미를 유지하려면
    모델에게 삼켜지지 않고 `Runner.run()` 밖으로 그대로 전파돼야 하므로,
    `human_action`(pause 가능) 노드가 있는 tool은 반드시 이 옵션을 켠다
    (§ human-in-the-loop, `subscription_status`가 실제 사례).

    데코레이터는 (SDK `@function_tool`과 달리) **원본 함수를 그대로 돌려준다** — 그래야 같은
    파일 안에서 `steps.step()`이 감싸거나, 다른 서비스가 `registry.tool_for(name)`으로 원본을
    직접 호출하거나, resume() 경로가 SDK를 우회해서 원본을 바로 부를 수 있다.

    `output_schema`는 예전처럼 tool 데코레이터에 붙여두지만 검증은 더 이상 여기서 안 한다 —
    guardrail이 SDK 관례대로 Agent 단위(`@output_guardrail`, `harness/guardrail.py`)로
    옮겨갔기 때문에, 여기 저장해두는 스키마는 그 Agent 레벨 guardrail 함수가 실행 시점에
    `registry.tool_for(name).output_schema`로 찾아 쓰는 참고 자료일 뿐이다.

    `workflow_registry`는 이 tool 내부에 `human_action`(pause 가능) 노드가 있을 때만
    넘긴다 — 멈췄던 지점을 재개하는 resume 로직이 그 tool 전용 `WorkflowRegistry`를 찾아야
    하기 때문(§ human-in-the-loop, `failure_error_function=None`과 함께 씀).
    """

    def decorator(func: Callable) -> Callable:
        actual_func = func
        kwargs: dict[str, Any] = {"name_override": name, "description_override": description}
        if pausable:
            kwargs["failure_error_function"] = None  # SDK 기본 에러 삼키기를 끔 — 예외가 그대로 전파됨

            @functools.wraps(func)
            def actual_func(*args: Any, **fkwargs: Any) -> Any:  # noqa: F811
                # AwaitingHumanAction에 이 tool 이름을 자동으로 찍어둔다 — manual_review 같은
                # 내부 노드는 "자기가 어느 tool에 속해 있는지" 몰라도 된다는 원칙(§ state_machine.py)을
                # 지키면서, main.py의 resume()이 어떤 workflow_registry를 찾을지 알 수 있게 한다.
                try:
                    return func(*args, **fkwargs)
                except AwaitingHumanAction as e:
                    e.tool_name = name
                    raise

        wrapped = function_tool(**kwargs)(actual_func)
        registry.register_tool(
            ToolSpec(
                name=name,
                description=description,
                func=actual_func,
                function_tool=wrapped,
                output_schema=output_schema,
                workflow_registry=workflow_registry,
            )
        )
        actual_func.__tool_name__ = name
        return actual_func

    return decorator
