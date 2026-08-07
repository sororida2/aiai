from __future__ import annotations

import json
import os
import pathlib
import re
from typing import Any

from dotenv import load_dotenv

import services
from framework.harness.logging_setup import configure_logging, get_logger
from framework.llm.openai_client import complete
from framework.orchestrator import Orchestrator
from framework.prompts.store import PromptStore
from framework.registry.decorators import registry
from framework.registry.discovery import discover_services

logger = get_logger("main")

load_dotenv()
configure_logging()  # LOG_LEVEL 환경변수(기본 INFO) — discover_services()보다 먼저 호출해야 그 로그도 잡힌다

FRAMEWORK_DIR = pathlib.Path(__file__).parent / "framework"

discover_services(services)  # services/<name>/workflow.py를 전부 import해 등록 트리거
registry.validate()  # 등록된 tool/guardrail 사이 참조 무결성 검사 (workflow_step/next는 각 파일이 import 시점에 자체 검증)


class FirstMatchRunner:
    """OpenAI Agents SDK Agent/Runner를 대체하는 스캐폴드용 스텁. OPENAI_API_KEY가
    없을 때(오프라인 샘플 테스트) build_orchestrator()의 기본 fallback으로 쓰인다.

    실제 배포 시에는 이 Protocol 구현체만 SDK 기반으로 교체하면 되고,
    orchestrator.py의 라우팅 엔진 코드는 건드리지 않는다.
    """

    def choose_tool(self, request: str, tool_catalog: list[dict[str, Any]], prompt: str) -> str:
        # 이름이 긴 tool부터 검사한다 — 짧은 이름이 긴 이름의 substring인 경우
        # (예: "weather"가 "subscription_weather_flow" 안에 포함됨) 오탐을 막기 위함.
        for entry in sorted(tool_catalog, key=lambda e: len(e["name"]), reverse=True):
            if entry["name"] in request:
                return entry["name"]
        raise ValueError(f"no tool matched request: {request!r}")

    def extract_arguments(
        self, request: str, tool_name: str, input_schema: dict[str, Any], known: dict[str, Any]
    ) -> dict[str, Any]:
        # 진짜 자연어 이해가 아니라 거친 휴리스틱이다 — 오프라인 스텁이라는 원래
        # 성격 그대로, 숫자형 필드만 요청 문자열에서 첫 숫자를 뽑아 채운다. 문자열형
        # 필드(국가 코드 등)는 이 스텁으로는 못 채운다 — "미국" -> "US" 같은 변환은
        # 진짜 의미 이해가 필요해서 OpenAIRunner(실제 LLM) 쪽 몫으로 남겨둔다.
        #
        # type_ is int로는 안 된다 — 이 프로젝트 전체가 `from __future__ import
        # annotations`를 쓰기 때문에 런타임엔 타입 힌트가 실제 타입 객체가 아니라
        # 문자열("int")로 들어온다(PEP 563, 지연 평가). 그래서 문자열/실제 타입
        # 둘 다 받아들이도록 이름으로 비교한다.
        extracted: dict[str, Any] = {}
        for name, type_ in input_schema.items():
            type_name = type_ if isinstance(type_, str) else getattr(type_, "__name__", str(type_))
            if type_name == "int":
                match = re.search(r"\d+", request)
                if match:
                    extracted[name] = int(match.group())
        logger.debug("FirstMatchRunner.extract_arguments: request=%r -> %s (숫자 필드만 채움)", request, extracted)
        return extracted


class OpenAIRunner:
    """AgentRunner Protocol의 OpenAI 기반 구현체.

    orchestrator.py는 이 클래스를 모른다 — Protocol에만 의존하므로 여기 교체는
    main.py(조립 지점)에서만 일어난다.
    """

    def choose_tool(self, request: str, tool_catalog: list[dict[str, Any]], prompt: str) -> str:
        names = {entry["name"] for entry in tool_catalog}
        catalog_text = "\n".join(f"- {entry['name']}: {entry['description']}" for entry in tool_catalog)
        user = (
            f"등록된 tool 목록:\n{catalog_text}\n\n"
            f"요청: {request}\n\n"
            "위 tool 중 이 요청에 가장 적합한 tool의 name만 정확히 출력하라. "
            "적합한 tool이 없으면 NONE이라고만 출력하라."
        )
        choice = complete(system=prompt, user=user)
        if choice not in names:
            raise ValueError(f"no tool matched request: {request!r} (model returned {choice!r})")
        return choice

    def extract_arguments(
        self, request: str, tool_name: str, input_schema: dict[str, Any], known: dict[str, Any]
    ) -> dict[str, Any]:
        fields = "\n".join(f"- {name}: {getattr(type_, '__name__', type_)}" for name, type_ in input_schema.items())
        user = (
            f"tool '{tool_name}' 호출에 필요한 값 중 아직 안 채워진 필드:\n{fields}\n\n"
            f"이미 알고 있는 값: {known}\n\n"
            f"사용자 요청: {request}\n\n"
            "위 요청에서 각 필드의 값을 최대한 추측해 JSON 객체 하나로만 답하라. "
            "확실히 알 수 없는 필드는 그 키 자체를 결과에 넣지 마라(null도 쓰지 마라 — "
            "억지로 채우는 것보다 비워두는 게 낫다). 설명이나 다른 텍스트 없이 JSON만 출력하라."
        )
        raw = complete(system="너는 자연어 요청에서 tool 호출 인자를 최대한 추출하는 역할이다.", user=user)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("extract_arguments: model output was not valid JSON: %r", raw)
            return {}
        if not isinstance(parsed, dict):
            logger.warning("extract_arguments: model output was not a JSON object: %r", raw)
            return {}
        return parsed


def build_orchestrator() -> Orchestrator:
    agent_runner: Any = OpenAIRunner() if os.environ.get("OPENAI_API_KEY") else FirstMatchRunner()
    return Orchestrator(
        registry=registry,
        prompt_store=PromptStore(base_dir=FRAMEWORK_DIR / "prompts"),
        agent_runner=agent_runner,
    )


if __name__ == "__main__":
    orchestrator = build_orchestrator()
    #print(orchestrator.handle("subscription_status 조회해줘", applicant_id="A123"))
    #print(orchestrator.handle("weather 조회해줘", location="Seoul"))
    #print(orchestrator.handle("subscription_weather_flow 조회해줘", applicant_id="A123"))
    print(orchestrator.handle("applicant_list 보여줘")["table"])
    #print(orchestrator.handle("public_holiday 조회해줘", year=2026, country_code="US"))
    #print(orchestrator.handle("exchange_rate 조회해줘", base="USD", symbols="KRW,EUR,JPY"))  # base=USD 자체가 미국 타겟
    #print(orchestrator.handle("ip_geolocation 조회해줘", ip="8.8.8.8"))  # Google Public DNS — 위치가 이미 미국(Virginia)으로 잡힘
    #print(orchestrator.handle("university_search 조회해줘", country_code="US")["universities"][:5])  # 전체는 2000개가 넘어 앞 5개만
    print(orchestrator.handle("미국에 있는 대학 5개만 보여줘"))
    print(orchestrator.handle("143.248.1.1의 위치한 나라를 알려줘"))
    print(orchestrator.handle("미국의 2026년 공휴일을 알려줘"))
    print(orchestrator.handle("미국 달러를 원화, 유로, 일본 엔으로 환전하면 얼마야?"))
    print(orchestrator.handle("A123 신청자의 진행상황과 그 지역 날씨를 알려줘"))
