from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from framework.harness.guardrail import GuardrailChain
from framework.harness.logging_setup import get_logger
from framework.harness.tracing import tracer
from framework.prompts.store import PromptStore
from framework.registry.decorators import ToolRegistry

logger = get_logger("orchestrator")


class AgentRunner(Protocol):
    """LLM 라우팅 판단 자체는 SDK(OpenAI Agents SDK 등)의 몫.

    오케스트레이터 엔진은 특정 SDK에 커플링되지 않도록 이 Protocol만 요구한다.
    """

    def choose_tool(self, request: str, tool_catalog: list[dict[str, Any]], prompt: str) -> str: ...


@dataclass
class Orchestrator:
    registry: ToolRegistry
    prompt_store: PromptStore
    agent_runner: AgentRunner

    def __post_init__(self) -> None:
        self.guardrails = GuardrailChain(self.registry)

    def _catalog(self) -> list[dict[str, Any]]:
        return [
            {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema}
            for spec in self.registry.tools().values()
        ]

    def handle(self, request: str, **kwargs: Any) -> dict[str, Any]:
        logger.info("request received: %r kwargs=%s", request, kwargs)
        with tracer.start_trace(name="orchestrator") as trace:
            prompt = self.prompt_store.common_prompt()
            tool_name = self.agent_runner.choose_tool(request, self._catalog(), prompt)
            logger.info("tool selected: %s (via %s)", tool_name, type(self.agent_runner).__name__)

            spec = self.registry.tools().get(tool_name)
            if spec is None:
                logger.error("agent chose unregistered tool '%s'", tool_name)
                raise KeyError(f"agent chose unregistered tool '{tool_name}'")

            with tracer.span(name=tool_name, kind="tool"):
                result = self.guardrails.run(tool_name, lambda: spec.func(**kwargs), kwargs)

            logger.info("request done: tool=%s result_keys=%s", tool_name, list(result))
            return result
