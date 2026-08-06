# Agent Loop 프레임워크 — 코드 구성

`README.md`(왜 이 구조가 필요한가)와 `ai_framework_2.md`(설계 철학)의 논의가 실제로 어떤 파일·클래스로 구현됐는지 매핑한 문서다. `services/` 아래 네 서비스가 각기 다른 절의 살아있는 예시다 — `subscription_status`(레거시 어댑터 + human-in-the-loop 판단 노드), `weather`(인증 없는 외부 실 API 어댑터), `subscription_weather_flow`(서비스를 조합하는 서비스), `applicant_list`(입력 없는 목록 조회 + 표 형식 렌더링). `main.py`가 실행 진입점이고, `examples/human_action_demo.py`가 human-in-the-loop 일시정지/재개를 터미널에서 직접 확인해보는 실행 가능한 예시다.

## 열린 질문 요약

아직 구현하지 않고 의도적으로 열어둔 논의들 — 전부 "실제 use case/환경이 아직 안 정해졌다"는 같은 이유로 보류 중이다. 각 항목의 전체 맥락은 § 아래 "현재 스캐폴드의 한계"에 있다.

- **서비스 간 겹치는 필드를 어떻게 공유할지** — `applicant_list`/`subscription_status`처럼 일부 필드만 겹치는 두 서비스의 스키마를 어디까지 공유 자산으로 뽑아낼지. 파라미터가 여럿이고 일부만 겹치는 실제 use case가 나오기 전까진 보류.
- **`applicant_list`의 표(`table`) 렌더링 포맷** — 마크다운 파이프 표가 최종 형태인지 여부는 이 결과를 어디서 보여줄지(실행/렌더링 환경)에 달려 있는데 그 환경 자체가 아직 안 정해짐.
- **LangGraph의 checkpointer식 영속화가 필요한가** — `Orchestrator.resume()`이 멈춘 상태를 프로세스 메모리로만 들고 있는 한계. 사람이 몇 시간~며칠 뒤에 판단하는 실제 시나리오나 분산 배포가 실제로 필요해지기 전까진 보류.
- **병렬 분기(fan-out/join)가 필요한가** — `StateMachine`은 순차 실행만 지원. 의존관계 없는 두 호출을 동시에 불러야 할 만큼 느린 실제 사례가 나오기 전까진 보류.
- **tool 본문에 `complete()`를 직접 호출하는 것의 트레이드오프** — bounded choices(감사 가능)를 포기하는 대신 완전히 자유로운 생성을 얻는 선택. 정형화가 원천적으로 불가능한 자유 텍스트 생성이 목적인 tool이 실제로 필요해지기 전까진 열어만 둠.
- **`manual_review` 앞에 AI 기반 중요도 분류(triage)를 넣을지** — "덜 중요한 판단은 AI에게 위임"은 예전에 시도했다가 이름-행동 모순으로 되돌린 구조와 같아서, 다시 하려면 `triage`(AI, 중요도만 분류)와 `manual_review`(사람, 실제 결정)를 역할 분리해야 함. 사람에게 넘어가는 케이스 중 "AI가 걸러줬어도 됐을" 구체적 사례가 쌓이기 전까진 보류.

## 디렉토리 구조

```
framework/                  ← 엔진. 새 서비스를 추가해도 손대지 않는 것이 목표.
├── registry/decorators.py  ← @tool·@guardrail 데코레이터 + 전역 ToolRegistry(+ validate()) — tool 카탈로그(라우팅 표면)만 관리
├── registry/discovery.py    ← services/<name>/workflow.py 자동 스캔·import (discover_services)
├── orchestrator.py          ← Triage 라우팅 (Orchestrator, AgentRunner Protocol) + 일시정지/재개(resume())
├── harness/
│   ├── schema.py             ← 스키마 검증 원시 요소 (OptionalField/optional/validate_schema) — guardrail과
│   │                            human_action의 payload 검증이 공유
│   ├── guardrail.py          ← Input/Output 검증 체인 (GuardrailChain, schema.py 위에 얹힘)
│   ├── tracing.py            ← Trace/Span 중첩 기록 + 그 자리에서 로그로도 출력 (Tracer)
│   └── logging_setup.py      ← LOG_LEVEL 환경변수 기반 로깅 설정 (configure_logging, get_logger)
├── prompts/store.py         ← 공통/도메인 프롬프트 계층 조립 (PromptStore)
├── prompts/common/          ← 공통 오케스트레이터 프롬프트 (orchestrator.md)
├── semantic/mapping.py      ← 레거시 원시값→정규화값 (SemanticMapping, MappedValue)
├── adapters/base.py         ← 양면 어댑터 추상 (BaseAdapter: call / normalize / execute)
├── llm/openai_client.py     ← OpenAI 호출 얇은 wrapper (complete()) — 엔진이 아니라 필요한 지점에서 opt-in으로 import
└── workflow/
    ├── registry.py           ← WorkflowRegistry(.step()·.judged()·.human_action()·.validate()) — tool(파일)마다 로컬 인스턴스를 하나씩 만들어 씀
    └── state_machine.py      ← 고정 파이프라인 실행기 (StateMachine) + AwaitingHumanAction(사람의 답 대기 신호)

services/                   ← 설정. 새 서비스 추가 시 여기만 늘어난다 (main.py도 안 건드림 — auto-discovery).
├── subscription_status/
│   ├── adapter.py           ← SubscriptionStatusAdapter(BaseAdapter)
│   ├── mapping.json          ← 상태코드 confirmed/inferred 매핑 테이블
│   ├── workflow.py           ← 로컬 WorkflowRegistry(steps) 기반 파이프라인 + @human_action 노드(manual_review, 사람의
│   │                            action 선택을 기다렸다가 이어서 실행) + 최상위 @tool
│   └── prompts/subscription_status.md  ← 이 tool 전용 프롬프트
├── weather/                  ← 두 번째 살아있는 예시 (외부 실 API 연동 케이스, 인증 불필요)
│   ├── adapter.py           ← WeatherAdapter(BaseAdapter), Open-Meteo 지오코딩 + 현재 날씨 호출
│   ├── mapping.json          ← WMO weather code(공식 문서화 표) → 한국어 정규화 테이블
│   ├── workflow.py           ← 분기/재시도가 없어 WorkflowRegistry/StateMachine 없이 @tool이 어댑터를 직접 호출
│   └── prompts/weather.md    ← 이 tool 전용 프롬프트
├── subscription_weather_flow/← 세 번째 예시: 어댑터 서비스가 아니라 "서비스를 조합하는 서비스"
│   ├── workflow.py           ← adapter.py/mapping.json 없음 — subscription_status()/weather() tool 함수를
│   │                            그대로 호출해 조합하는 로컬 WorkflowRegistry(steps) 2단계 + 최상위 @tool
│   └── prompts/subscription_weather_flow.md
└── applicant_list/            ← 네 번째 예시: 입력 없는 tool + 표 형식 렌더링
    ├── adapter.py           ← ApplicantListAdapter(BaseAdapter), 20명 스텁 목록 + subscription_status와
    │                            같은 5단계 상태 체계(별도 mapping.json, 값은 동일)로 정규화
    ├── mapping.json
    ├── workflow.py           ← weather와 마찬가지로 WorkflowRegistry 없이 @tool이 어댑터 직접 호출 + 마크다운 표(`table`) 조립
    └── prompts/applicant_list.md

main.py                     ← 조립 지점 (discover_services + registry.validate(), build_orchestrator,
                                OpenAIRunner/FirstMatchRunner) + 실행 예시. 서비스 추가 시 더 이상 손대지 않아도 됨.
examples/human_action_demo.py ← human-in-the-loop 일시정지/재개를 터미널에서 직접 확인하는 실행 가능한 예시
                                (main.py의 build_orchestrator()를 그대로 재사용)
guides/legacy_adapter_guide.md ← 신규 서비스 추가 가이드
.env / .env.example         ← OPENAI_API_KEY, OPENAI_MODEL, LOG_LEVEL (.env는 커밋 안 함; weather는 키 불필요)
```

## 컴포넌트별 역할

### `registry/decorators.py` — 전역 tool 카탈로그
전역 `registry = ToolRegistry()`에는 딱 두 종류 스펙만 모인다.
- `@tool(name, description, workflow_registry=None)` → `ToolSpec` (오케스트레이터가 유일하게 커플링되는 표면). `workflow_registry`는 이 tool 내부에 `@human_action`(pause 가능) 노드가 있을 때만 넘긴다 — § 아래 "human-in-the-loop" 절.
- `@guardrail(input_schema=..., output_schema=...)` → `GuardrailSpec`

`workflow_step`/`judged`/`human_action`은 여기 없다 — **왜 없는지가 이 리팩터의 핵심**이다(§ 아래 `workflow/registry.py` 절). `@tool`만 전역이어야 하는 이유는 단순하다: 오케스트레이터가 라우팅하려면 모든 서비스의 tool을 한 곳에서 봐야 하기 때문. 반면 파이프라인 내부의 스텝/분기는 그 tool 하나만의 배선이라 전역으로 공유할 이유가 없다.

`ToolRegistry.tool_for(name)`은 이름 하나로 등록된 tool을 바로 찾는다(`tools()`처럼 전체 dict를 복사하지 않고, 없으면 `KeyError`로 명확히 실패). 돌려주는 `ToolSpec`은 `__call__`을 구현해서 그 자체가 호출 가능하다 — 호출부가 `.func`라는 내부 속성 이름을 몰라도 `registry.tool_for(name)(**kwargs)`로 바로 쓸 수 있다. 이건 서비스가 다른 서비스를 부를 때 쓰는 방식이다(§ 아래 "서비스를 조합하는 서비스" 절) — `registry.tools()` 전체 조회는 오케스트레이터(카탈로그를 통째로 봐야 함)나 진단용으로 남겨두고, 이름 하나만 필요한 경우엔 `tool_for()`를 쓴다.

모듈을 import하는 순간 `@tool`/`@guardrail` 데코레이터가 실행되며 등록된다. 예전에는 `main.py`에 서비스마다 `from services.<name> import workflow as _`를 나열해 이 import를 직접 트리거했지만, 지금은 `framework/registry/discovery.py`의 `discover_services()`가 `services/` 아래를 스캔해서 대신 트리거한다 (§ 아래 `registry/discovery.py` 절).

### `workflow/registry.py` — tool(파일)마다 독립된 로컬 workflow 네임스페이스
**왜 이게 별도 모듈로 분리됐는가.** 원래는 `workflow_step`/`judged`/`human_action`도 전역 `ToolRegistry` 하나에 함수 이름으로만 키를 걸어 등록했다. 이 설계에는 세 가지 문제가 있었다.

1. **스텝 이름 충돌이 조용히 덮어써진다.** 전역 dict라 서로 다른 두 서비스 파일이 우연히 같은 함수명을 쓰면(`register_tool`과 달리 중복 검사가 없어서) 나중에 import된 쪽이 앞의 등록을 조용히 덮어쓴다.
2. **`next` 참조가 파일 경계를 모른다.** 검증이 "등록된 step 이름 전체 집합" 안에 있는지만 봐서, A 서비스의 `next`가 실수로 B 서비스의 step 이름을 가리켜도 통과된다.
3. **`order`가 전역에서는 의미가 성립하지 않는다.** `subscription_weather_flow`처럼 이미 등록된 tool을 재사용해 새 조합을 만들 때, 같은 스텝이 어떤 workflow에 속하느냐에 따라 "몇 번째로 실행되는가"가 달라질 수 있는데, `order`/`next`가 스텝 자체(전역 스펙)에 고정돼 있으면 애초에 "여러 workflow가 같은 스텝을 다르게 조합"하는 게 불가능하다.

그래서 `order`/`next`/`max_retries`(그리고 그 위에 얹히는 `judged`/`human_action`)를 전역 `ToolRegistry`에서 떼어내 `WorkflowRegistry`라는 별도 클래스로 옮겼다. 각 `services/<name>/workflow.py`는 자기 전용 인스턴스를 하나 만든다:
```python
steps = WorkflowRegistry()          # 이 파일 전용 — 다른 파일과 이름이 겹쳐도 충돌 불가능

@steps.step(order=1, next={"완료": "DONE"})
def fetch_weather(context): ...

steps.validate()                    # 이 파일만으로 즉시 검증 가능 (다른 서비스 import를 기다릴 필요 없음)
```
- `steps.step(order, *, source=None, next=None, max_retries=5)` — 예전 `@workflow_step`과 동일한 계약(결정론적 분기/순환을 `next` dict로 고정, 반환값이 `next`의 키 밖이면 즉시 `ValueError`)이지만 이 인스턴스 안에서만 이름공간이 닫힌다. `max_retries`는 선언 안 해도 기본 5 — "선언 안 하면 무제한"이 아니라 "선언 안 하면 5"라서 순환 폭주 방지가 항상 켜져 있다(§ 아래 `workflow/state_machine.py` 절).
- `steps.judged(choices=...)` / `steps.human_action(choices=..., payload_schemas=None)` — 예전 `@judged`/`@human_action`과 동일한 계약, 등록 위치만 이 인스턴스로 바뀜.
- `steps.validate()` — 이 파일 안에서만 판단 가능한 참조 무결성(아래 절)을 검사하고 `WorkflowConsistencyError`를 던진다. **다른 서비스가 전부 import되길 기다릴 필요가 없어서** 파일 하단에서 바로 호출해 즉시 fail-fast할 수 있다 — 예전엔 전역 `registry.validate()`가 모든 서비스 import가 끝난 뒤(`main.py`)에야 이 검사를 할 수 있었던 것과 대조적이다.

`StateMachine(registry=..., entry=...)`의 `registry` 파라미터도 이제 전역 `ToolRegistry`가 아니라 이 `WorkflowRegistry` 인스턴스를 받는다(§ 아래 `workflow/state_machine.py` 절) — 각 서비스의 `build_state_machine()`이 자기 `steps`를 넘긴다.

**`step()` vs `judged()`/`human_action()` — 헷갈리기 쉬운 지점.** 기준은 단 하나, "이 스텝의 결과값이 코드 로직으로 나오는가, 판단(모델 또는 사람)으로 나오는가"뿐이다.

| | `steps.step()` | `steps.judged()` | `steps.human_action()` |
|---|---|---|---|
| 필수 여부 | 모든 스텝에 필수 — 없으면 state machine이 이 함수를 아예 모른다 | 선택 — "이 스텝은 모델이 결정한다"는 표시일 때만 추가로 얹는다 | 선택 — "이 스텝은 사람이 결정한다"는 표시일 때만 추가로 얹는다 |
| 하는 일 | `next={...}`로 다음 스텝(라우팅) 결정 | 반환값이 `choices` 밖이면 즉시 차단 (라우팅은 모름) | 반환값의 `action`이 `choices` 밖이거나 그 action의 payload가 스키마를 어기면 즉시 차단 |
| 등록 위치 | 이 파일의 `WorkflowRegistry._steps` | 같은 인스턴스의 `._judged` (별도) | 같은 인스턴스의 `._human_actions` (별도) |
| 왜 필요한가 | 파이프라인 그래프 자체를 코드로 고정하기 위해 | 모델 출력은 예측 불가능하므로 bounded 안전망이 필요해서 | 사람의 선택도 bounded해야 감사 가능하고, payload가 붙는 action은 그 구조까지 검증해야 해서 |

코드가 직접 결정하는 스텝(`fetch_status`)은 `steps.step()` 단독, 판단이 필요한 스텝은 `steps.step()` + (`steps.judged()` 또는 `steps.human_action()`) 이중으로 붙는다 — 판단 데코레이터가 라우팅을 대신하는 게 아니라, `step()`의 라우팅 계약 위에 "이 값은 모델/사람이 만든 것"이라는 제약을 얹는 것뿐이다. `WorkflowRegistry.validate()`가 "judged/human_action인데 step이 없는" 반쪽짜리 선언을 그 파일 import 시점에 바로 잡아내는 것도 이 관계(둘 다 step에 종속) 때문이다. 지금 `services/` 전체에서 실제로 쓰이는 건 `steps.human_action()`(`manual_review`)뿐이고 `steps.judged()`는 코드로는 남아있지만 등록된 서비스가 하나도 없다 — § 아래 "현재 스캐폴드의 한계" 참고.

**언제 `WorkflowRegistry`/`StateMachine`을 아예 생략하는가.** `weather`/`applicant_list`는 원래 이 절의 패턴대로 `steps = WorkflowRegistry()` + `steps.step(order=1, next={"완료": "DONE"})` 하나만 등록해서 썼는데, 이건 순수 의례(ceremony)였다 — 분기도 재시도도 판단 노드도 없이 "어댑터 한 번 부르고 끝"이라 `next`/`entry`/`StateMachine.run()`이 어떤 실제 결정도 안 하고 그냥 함수 호출 하나를 대신 전달하기만 했다. 그래서 이 둘은 `WorkflowRegistry`/`StateMachine`을 걷어내고 `@tool` 함수 본문에서 어댑터를 직접 호출하도록 되돌렸다:
```python
@tool(name="weather", description="...")
@guardrail(output_schema=WEATHER_OUTPUT_SCHEMA)
def weather(location: str) -> dict[str, Any]:
    return WeatherAdapter().execute(location=location)
```
기준은 **분기(`next`가 outcome에 따라 갈리는가)·재시도(`max_retries`)·판단 노드(`judged`/`human_action`)가 하나라도 있는가**다. 하나라도 있으면 `WorkflowRegistry`가 실제로 일(그래프 고정, bounded 강제)을 하므로 그대로 쓴다(`subscription_status`가 셋 다 있음). 셋 다 없으면 `StateMachine`은 "step 하나 부르고 바로 DONE"만 반복하는 빈 껍데기이므로 안 쓴다. `subscription_weather_flow`는 분기/재시도/판단은 없지만 **두 tool 호출 사이의 순서와 데이터 의존관계**(region → location) 자체가 코드 로직이라 `WorkflowRegistry`를 유지했다 — 이 기준은 "스텝이 몇 개인가"가 아니라 "그 사이에 실제로 코드가 결정할 게 있는가"임에 유의.

이 변경으로 로그의 `state machine start`/`span(kind="step")` 한 단계가 `weather`/`applicant_list`에서는 더 이상 안 찍힌다 — 어차피 `Orchestrator.handle()`이 찍는 tool 단위 span(`span(kind="tool")`)과 1:1이었던 정보라 손실은 없다(§ 아래 "로깅" 절).

### `registry/discovery.py` + 두 단계 일관성 검사 — auto-discovery
`main.py`가 서비스를 일일이 알 필요가 없게 만드는 지점. Python은 모듈을 실제로 import하기 전까진 그 안의 데코레이터를 실행하지 않으므로, 등록이 일어나려면 누군가는 각 `services/<name>/workflow.py`를 import해야 한다 — `discover_services(services)`가 `pkgutil.iter_modules(services.__path__)`로 하위 패키지를 전부 찾아 그 `workflow.py`를 대신 import해준다.

일관성 검사는 이제 두 단계로 나뉜다.
- **파일 단위, import 시점 즉시** — 각 `workflow.py` 하단의 `steps.validate()`(`WorkflowRegistry.validate()`)가 그 파일의 `next`/`judged`/`human_action` 참조 무결성을 검사한다. 이 파일 하나로 판단 가능한 검사라 다른 서비스를 기다릴 필요가 없다.
- **전역 카탈로그 단위, discovery 이후 한 번** — `main.py`가 `discover_services()` 직후 `registry.validate()`(`ToolRegistry.validate()`)를 호출해 tool/guardrail 카탈로그를 검사한다:
  - 등록된 tool이 하나도 없으면 즉시 실패 (서비스 폴더는 있는데 아무것도 안 잡힌 상태)
  - 모든 `@guardrail`은 실제로 그 tool의 함수 자체에 등록돼야 함 — `@guardrail`을 `@tool`보다 위(나중에 적용되게)에 잘못 쓰거나 함수 이름이 tool name과 다르면, `guardrail()` 데코레이터가 `func.__name__`으로 fallback하면서 엉뚱한 키에 등록되는 조용한 버그가 생기는데 이걸 잡아낸다

`discover_services()`도 자체적으로 한 단계 fail-fast한다: `services/<name>/`에 `workflow.py` 자체가 없으면 `ServiceConsistencyError`로 명확히 실패하고, `workflow.py`는 있지만 그 안에서 다른 import가 실패한 "진짜 버그"는 오진하지 않고 원래 예외 그대로 전파한다(`ModuleNotFoundError.name`으로 구분).

### `orchestrator.py` — 라우팅 + 일시정지/재개
`Orchestrator.handle()`이 요청 하나의 진입점이다.
1. `tracer.start_trace("orchestrator")`로 Trace 시작
2. `PromptStore.common_prompt()` + `registry.tools()`를 카탈로그로 넘겨 `AgentRunner.choose_tool()` 호출 — 실제 라우팅 판단은 SDK 몫이며, 엔진은 `AgentRunner` Protocol에만 의존해 SDK에 비커플링
3. 선택된 tool을 `GuardrailChain.run()`으로 감싸 실행, 그 안에서 `tracer.span()`으로 Tool Span 기록

`main.py`의 `build_orchestrator()`는 `OPENAI_API_KEY`가 있으면 `OpenAIRunner`(실제 모델에 tool 카탈로그를 주고 name 하나만 고르게 함)를, 없으면 `FirstMatchRunner`(요청 문자열에 tool 이름이 포함되는지만 검사하는 오프라인 스텁)를 `agent_runner`로 선택한다. 두 클래스 모두 `AgentRunner` Protocol만 구현하므로 `orchestrator.py` 자체는 어느 쪽을 쓰든 안 바뀐다 — 이 스위칭도 `main.py`(조립 지점)의 책임이다.

**실제 운영 환경에서 발견·수정한 라우팅 버그.** `OpenAIRunner`로 실행 중 `"weather 조회해줘"`(location은 `kwargs`로 별도 전달) 요청이 모델의 `'NONE'` 응답으로 라우팅 실패했다. `DEBUG` 로그로 실제 프롬프트를 확인해보니, `weather`/`subscription_weather_flow`처럼 description에 "location 하나만 입력받는다" 식으로 필수 입력을 명시한 tool만 실패하고, 그런 문구가 없는 `subscription_status`/`applicant_list`는 정상 라우팅됐다 — 원인은 `common/orchestrator.md`의 "*description에 명시된 입력 스키마 밖의 것을 추측하지 마라*"/"*적합한 tool이 없으면 억지로 고르지 마라*" 규칙이, "요청 텍스트에 인자 값이 없다"를 "적합한 tool이 없다"로 모델이 오판하게 만든 것이었다. 실제로는 인자 값이 `kwargs`로 호출자가 별도로 채워주는 구조라(§ 위 흐름), 라우팅(어떤 tool의 의도에 맞는가)과 인자 채움(텍스트가 그 값을 담고 있는가)은 별개인데 프롬프트가 이 둘을 구분하지 못했던 것. `common/orchestrator.md`에 "요청 텍스트에 tool의 입력 인자 값이 구체적으로 적혀 있지 않아도 된다 — 그 값은 호출자가 별도로 채워 넣는다"는 규칙을 한 줄 추가해 해결했다 — 오늘의 `WorkflowRegistry` 리팩터와는 무관한, 원래부터 있던 라우팅 프롬프트 설계의 갭이었다.

**일시정지/재개.** `spec.func(**kwargs)` 실행 중 내부의 `@human_action` 노드가 `AwaitingHumanAction`을 던지면(§ 아래 "human-in-the-loop" 절), `handle()`은 이 예외를 그대로 죽게 두지 않고 `{"status": "awaiting_human_action", "tool": ..., "step": ..., "choices": [...], "context": ...}`를 정상 반환값으로 돌려준다 — 대화가 여기서 사람의 답을 기다리며 멈춘다는 뜻이다. 호출자가 사람의 답을 받으면 `Orchestrator.resume(tool_name, context, step, action)`을 불러 멈췄던 `step`부터 이어서 실행한다: `self.registry.tools()[tool_name].workflow_registry`로 그 tool 전용 `WorkflowRegistry`를 찾아(§ `workflow/registry.py` 절 — `@tool(workflow_registry=steps)`로 연결해둔 것), `context["human_action"] = action`을 채운 뒤 `StateMachine(registry=tool_spec.workflow_registry, entry=step).run(context)`를 다시 돌린다. `workflow_registry`가 없는 tool(`weather`처럼 pause가 없는 tool)에 `resume()`을 부르면 즉시 `ValueError`로 막는다. `resume()`도 같은 `GuardrailChain`을 거치므로 최종 완료 시 output guardrail은 그대로 적용된다.

### `harness/schema.py` — 스키마 검증 원시 요소
`OptionalField`/`optional()`/`SchemaViolation`/`validate_schema()`가 여기 산다. 원래 `harness/guardrail.py` 안에 있던 걸, `@human_action`의 payload 검증(§ 아래 "human-in-the-loop" 절)이 똑같은 재귀 검증 로직을 필요로 하면서 공유 모듈로 뺐다 — guardrail도 human_action도 이 모듈에만 의존하고 서로는 모른다. `validate_schema(value, schema, path="")`가 스키마 값의 형태로 세 가지를 구분한다.
- `Any` → 필드 존재 여부만 확인
- `{"choices": [...]}` → enum 제약
- `{"choices": ...}`가 없는 순수 dict → **중첩 스키마**로 간주해 재귀 검증. 실패 시 `path`가 `subscription.status`처럼 점(dot) 경로로 어느 중첩 레벨에서 깨졌는지 보여준다.

기본적으로 스키마에 선언된 키는 전부 필수지만, 조건부 경로에만 채워지는 필드는 `optional(schema)`(`OptionalField` wrapper)로 감싸 선언한다 — 필드가 없으면 통과, 있으면 `inner` 규칙으로 그대로 검증한다. 위반 시 `SchemaViolation(detail)`을 던지며, 호출자(`guardrail.py`/`workflow.registry.WorkflowRegistry.human_action`)가 각자의 맥락(`stage`/`tool_name` 또는 `human_action 이름`/`action`)을 붙여 자기 예외 타입(`GuardrailViolation`/`ValueError`)으로 다시 던진다.

### `harness/guardrail.py` — 개입 권한을 가진 검증
`GuardrailChain.run()`은 `registry.guardrail_for(tool_name)`으로 선언을 읽어 input → 호출 → output 순으로 검증한다. **엔진 코드 어디에도 tool 이름이 하드코딩되지 않는다** — `if tool_name == ...` 분기가 생기면 안티패턴이라는 설계 원칙(`ai_framework_2.md`)이 그대로 구현된 지점. 실제 검증은 `harness/schema.py`의 `validate_schema()`에 위임하고, `_validate()`는 그 결과에 `stage`(input/output)·`tool_name`을 붙여 `GuardrailViolation`으로 감싸고 로깅만 담당한다(`subscription_status.workflow`의 `status`/`status_confidence`/`manual_review_decision` 필드, `subscription_weather_flow`의 중첩 검증이 실제 예시). 스키마 없음/통과는 `DEBUG`로, 위반은 예외를 던지기 직전 `ERROR`로 로깅한다.

### `harness/logging_setup.py` — 로그 레벨 설정
`configure_logging()`이 `LOG_LEVEL` 환경변수(기본 `INFO`)로 표준 `logging`을 한 번 설정한다. `main.py`가 `load_dotenv()` 직후, `discover_services()`보다 먼저 호출해야 discovery/validate 단계 로그도 같은 레벨로 잡힌다(`main.py` 참고). `get_logger(name)`은 전부 `agent_loop.<name>` 네임스페이스 아래 로거를 돌려주므로, 특정 모듈만 레벨을 따로 올리고 싶으면(예: `logging.getLogger("agent_loop.adapter").setLevel(logging.DEBUG)`) 표준 `logging` API를 그대로 쓰면 된다.

### `harness/tracing.py` — 관측이자 로깅의 뼈대
`Tracer`는 스택 기반으로 `Span`을 중첩시킨다. `start_trace`가 루트(kind="orchestrator")를 열고, `span()` 호출마다 현재 스택 최상단의 자식으로 붙는다. Tool이 늘어나도 상위 구조(Trace → Orchestrator Span → Tool Span*)는 그대로 유지된다는 설계가 스택 구현으로 자연히 보장됨.

각 `start_trace`/`span` 진입·종료 시점에 `INFO` 레벨로 로그를 찍고, 중첩 깊이(`len(self._stack)`)만큼 들여쓰기를 붙인다 — `Trace`/`Span` 객체(`tracer.current_trace`)는 원래도 만들어지고 있었지만 그걸 읽어서 보여주는 코드가 어디에도 없었던 게 실제 gap이었다(§ 로깅 절 참고). `workflow/state_machine.py`가 각 `steps.step()` 실행을 `tracer.span(kind="step")`으로 감싸면서, tool 단위보다 한 단계 더 세밀한 "이 tool 안에서 지금 어느 스텝을 도는지"까지 같은 메커니즘으로 로그에 잡힌다 — 단, `weather`/`applicant_list`처럼 `StateMachine`을 아예 안 쓰는 tool은 이 "step" span 없이 tool 단위 span까지만 찍힌다(§ 위 "언제 WorkflowRegistry를 생략하는가" 참고).

`span()`은 활성 trace가 없는 상태(예: 오케스트레이터를 거치지 않고 `subscription_status(applicant_id=...)`처럼 `StateMachine`을 쓰는 tool 함수를 직접 호출·테스트하는 경우)에도 안전하게 동작한다 — 스택이 비어 있으면 이름 없는 암묵적 루트를 하나 열어서 쓰고, 빠져나갈 때 다시 비운다. `StateMachine.run()`이 항상 `span()`을 쓰게 되면서 이 케이스를 처음부터 고려해야 했다.

### `prompts/store.py` — 프롬프트 계층
`common_prompt()` (공통) + `tool_prompt()` (도메인별, `services/<name>/prompts/<tool_name>.md`) + 선택적 few-shot을 `compose()`가 `---`로 이어붙인다. 오케스트레이터는 `common_prompt()`만 써서 `OpenAIRunner.choose_tool()`에 넘긴다. `compose()` + `framework.llm.openai_client.complete()` 조합(도메인별 judged 노드가 실제로 모델을 호출하는 배선)은 원래 `manual_review`가 살아있는 예시였는데, `manual_review`가 사람 판단(`@human_action`)으로 바뀌면서 지금은 이 조합을 실제로 쓰는 서비스가 없다 — 당시 전용이던 `services/subscription_status/prompts/manual_review.md`는 완전히 죽은 파일이라 삭제했고, `compose()`/`complete()` 자체는 재사용 가능한 프레임워크 능력이라 남겨뒀다 (§ 아래 "현재 스캐폴드의 한계" 참고). `complete()` 자체는 모델/프롬프트 길이·응답 미리보기를 `INFO`로, system/user 프롬프트 원문 전체를 `DEBUG`로 로깅한다 — 프롬프트에 개인정보가 실릴 수 있는 서비스라면 운영 환경에서 `LOG_LEVEL=DEBUG`를 켜지 않도록 주의.

### `semantic/mapping.py` — 레거시 의미 정규화
`SemanticMapping.normalize(raw_value)`가 `mapping.json`을 찾아 `MappedValue(raw, value, confidence)`를 반환. 매핑에 없으면 `UnmappedValueError`로 즉시 실패 (fail-fast). `MappedValue.require_confirmed()`는 `confidence != "confirmed"`면 예외를 던져, `inferred` 값이 판단 분기에 잘못 쓰이는 걸 타입 수준에서 막는다.

### `adapters/base.py` — 양면 어댑터
`BaseAdapter`는 `call()`(프로토콜적 면 — 레거시 스펙에 종속)과 `normalize()`(의미론적 면 — `SemanticMapping`에 종속)를 분리해 각각 독립적으로 오버라이드하게 강제한다. `execute()`는 `normalize(call())`로 둘을 합성만 한다 — 이 한 곳에서 `call()`/`normalize()` 각각의 입출력을 `DEBUG`로 로깅하므로, 어떤 어댑터를 새로 만들어도(레거시 원시값 로깅을) 따로 구현할 필요가 없다.

### `workflow/state_machine.py` — 고정 파이프라인 실행기
`StateMachine.run()`은 `entry`부터 시작해 `WorkflowStepSpec.func(context)`가 반환한 outcome 문자열을 `next` dict에서 찾아 다음 단계로 이동한다. `next`가 없거나 `TERMINAL("DONE")`이면 종료. 판단 노드도 그냥 하나의 step으로 등록되며(`steps.judged()`/`steps.human_action()` + `steps.step()` 이중 데코레이터), state machine 입장에서는 outcome이 code-driven이든 model-driven이든 human-driven이든 구분하지 않는다 — bounded choices라는 계약만 `judged()`/`human_action()`이 보장한다. 각 스텝 실행을 `tracer.span(name=현재_step, kind="step")`으로 감싸고, 진입("state machine start")·전이("step 'X' -> outcome=... -> next='Y'")·종료를 `INFO`로 로깅한다.

`StateMachine.registry`는 전역 `ToolRegistry`가 아니라 `workflow.registry.WorkflowRegistry` 인스턴스다 — 각 서비스의 `build_state_machine()`이 자기 파일 전용 `steps`를 넘긴다(§ `workflow/registry.py` 절). 그래서 `steps()` 메서드가 보는 스텝 집합은 그 파일에 등록된 것으로 자연히 한정된다.

`outcome`이 `next`의 키 밖인지 확인하는 검증은 여기 없다 — `steps.step()`의 wrapper(`workflow/registry.py`)가 함수 반환 즉시 검사해서 `ValueError`를 던지므로, `run()`이 `spec.next[outcome]`을 인덱싱하는 시점엔 `outcome`이 항상 유효한 키임이 보장된다(`judged()`/`human_action()`이 각자의 bounded 값 밖을 함수 반환 즉시 막는 것과 동일한 위치·방식). 이 즉시 검증 덕분에 `services/subscription_status/workflow.py`의 실제 버그(`mapping.json`의 `"10"→"접수완료"`가 `fetch_status`의 `next`에는 빠져 있던 것)를 테스트 중 바로 잡아낼 수 있었다.

**순환 방지(`max_retries`) — self-loop뿐 아니라 여러 스텝을 왕복하는 순환까지.** `context[RETRY_COUNTS_KEY]`(`"_step_retry_counts"`, 프레임워크 예약 키)에 스텝별로 "완료된" 실행 횟수를 기록한다 — `spec.func(context)`가 예외 없이 outcome을 반환했을 때만 카운트가 올라간다. 어떤 스텝이든 다시 진입하려는 시점에 이미 완료된 횟수가 `max_retries + 1`(기본 5+1=6)에 도달했으면 실행 전에 `MaxRetriesExceeded`로 막는다. 예전엔 `next_step == current`(자기 자신으로 도는 것)일 때만 카운트했는데, 그러면 `evaluate → generate → evaluate → ...`처럼 **서로 다른 두 스텝 이상을 왕복하는 순환은 전혀 감지하지 못했다** — 지금은 스텝 이름 기준으로 재진입 자체를 세므로 몇 개 스텝을 거치는 순환이든 막힌다.

이 카운트를 `StateMachine.run()`의 로컬 변수가 아니라 **`context` 안에** 두는 이유는 `Orchestrator.resume()`이 멈출 때마다 새 `StateMachine` 인스턴스로 `run()`을 다시 호출하기 때문이다(그때그때 로컬 변수는 초기화됨) — 순환이 `human_action`처럼 멈추는 노드를 거치면 카운트가 resume 경계를 넘어 살아남아야 실제로 보호가 된다. `context`는 resume()에 그대로 전달되는 유일한 것이라 여기 둔다. 스텝 작성자는 이 키를 직접 건드릴 필요가 없다.

"완료된" 실행만 센다는 게 핵심이다 — 사람이 `human_action`의 bounded choices 밖의 값을 입력해 `ValueError`가 나거나 아직 답이 없어 `AwaitingHumanAction`으로 멈춘 시도는 카운트되지 않는다. 사람이 입력을 몇 번 틀렸는지는 자동 순환 폭주와 무관한 문제라 같은 예산을 쓰면 안 된다는 판단(§ 아래 "human-in-the-loop" 절과도 연결).

**`AwaitingHumanAction` — 일시정지.** `spec.func(context)` 호출이 이 예외를 던지면(§ 아래 "human-in-the-loop" 절), `run()`은 이를 에러가 아니라 정상적인 일시정지 신호로 취급한다: 예외 객체에 `step`(현재 step 이름)과 `context`(그 시점까지의 실행 상태)를 채워 넣고 그대로 다시 던진다 — raise한 쪽(예: `manual_review`)은 자기 step 이름을 몰라도 되고, `StateMachine`이 그 자리에서 알아서 채워준다.

### human-in-the-loop — `steps.human_action()` + `AwaitingHumanAction` + `Orchestrator.resume()`
"사람의 의사결정이 필요하면 action 목록을 보여주고 고르게 해야 한다"는 요구가 `manual_review`에 실제로 배선된 지점이다. 세 조각으로 나뉜다.

- **`WorkflowRegistry.human_action(choices, payload_schemas=None)`** — `judged()`와 계약(bounded choices)은 같지만 판단 주체가 모델이 아니라 사람이다. 함수는 `context`에 사람의 답이 이미 있으면(`context.get("human_action")`) `{"action": <choices 중 하나>, **payload}` 형태의 dict를 반환하고, 없으면 `AwaitingHumanAction(choices=...)`을 던진다. `action`은 여전히 유한 집합(bounded)이어야 감사 가능하다는 원칙(`ai_framework_2.md`의 judged branch 정의)을 그대로 유지하면서, action별로 다른 payload가 필요한 경우(예: `manual_review`의 `"서류추가요청"`이 어떤 서류가 더 필요한지 담아야 하는 것)는 `payload_schemas={"서류추가요청": {"field": Any}}`처럼 action에 종속된 스키마를 따로 선언해 `harness.schema.validate_schema()`로 검증한다. 이 분리가 핵심이다 — **action의 종류는 닫혀 있고(bounded), 그 안의 세부 데이터만 구조화**되므로 자유 라우팅과 구분되는 judged branch의 안전성이 그대로 유지된다. 검증을 통과하면 래퍼가 `context["human_action"]`을 지운다(관례상 `func(context: dict[str, Any])`로 호출되므로 `args[0]`가 context) — 안 지우면 같은 human_action 노드가 순환 안에서(예: evaluator가 이전 스텝으로 되돌리는 구조) 다시 방문될 때 새 결정을 기다리지 않고 예전 답을 그대로 재사용해버리는 버그가 있었다(발견 즉시 수정).
- **`workflow.state_machine.AwaitingHumanAction`** — 위에서 설명한 일시정지 신호. `manual_review`는 raise만 하고, `StateMachine.run()`이 `step`/`context`를 채워 넣는다.
- **`orchestrator.Orchestrator.handle()`/`resume()`** — `handle()`은 이 예외를 받으면 크래시 대신 `{"status": "awaiting_human_action", "tool": ..., "step": ..., "choices": [...], "context": ...}`를 반환한다. 사람의 답이 오면 호출자가 `resume(tool_name, context, step, action)`을 불러 `context["human_action"] = action`을 채우고, `tool_spec.workflow_registry`(`@tool(workflow_registry=steps)`로 연결된 이 tool 전용 `WorkflowRegistry`)를 써서 `StateMachine(registry=tool_spec.workflow_registry, entry=step).run(context)`로 멈췄던 지점부터 재개한다.

`manual_review`의 실제 배선(`services/subscription_status/workflow.py`):
```python
steps = WorkflowRegistry()

MANUAL_REVIEW_CHOICES = ("승인", "반려", "서류추가요청")


@steps.step(order=2, next={"승인": "DONE", "반려": "DONE", "서류추가요청": "DONE"})
@steps.human_action(
    choices=MANUAL_REVIEW_CHOICES,
    payload_schemas={"서류추가요청": {"field": Any}},
)
def manual_review(context: dict[str, Any]) -> dict[str, Any]:
    human_action_input = context.get("human_action")
    if human_action_input is None:
        raise AwaitingHumanAction(choices=MANUAL_REVIEW_CHOICES)
    context["last_result"]["manual_review_decision"] = human_action_input
    return human_action_input


steps.validate()

# ... 최상위 @tool(subscription_status, workflow_registry=steps)가 이 steps를 Orchestrator.resume()에 연결한다
```
전에는 이 지점에서 OpenAI에게 "자동승인/수동검토 중 뭘 고를지"를 대신 판단시켰다(`@judged` + `complete()`). "manual_review"라는 이름 자체가 "사람이 검토해야 하는 케이스"라는 뜻인데 정작 모델이 그 판단을 대신하고 있었던 게 원래의 모순이었고, 지금은 이름 그대로 실제 사람의 답을 기다린다.

choices 이름도 그 흔적을 정리했다 — "자동승인"(모순: 사람이 고르는데 "자동"?)/"수동검토"(모순: 이미 `manual_review` 안인데 또 "수동검토"로?)는 AI가 "사람에게 넘길지 말지"를 판단하던 시절의 이분법이 그대로 남은 것이었다. 지금은 이 노드 자체가 사람이 보고 있는 지점이므로, 사람이 실제로 내리는 결정(승인/반려)으로 바꿨다.

**실행 가능한 예시 — `examples/human_action_demo.py`.** 위 배선이 실제로 pause → 사람 입력 → resume까지 도는 걸 터미널에서 직접 확인할 수 있다. `main.py`의 `build_orchestrator()`를 그대로 재사용하고, 레거시 어댑터가 아직 스텁이라(`SubscriptionStatusAdapter.call()`이 항상 confirmed 응답만 반환) `manual_review`까지 못 가는 문제는 이 스크립트 안에서만 어댑터를 몽키패치해 `status_code="99"`(inferred)를 강제하는 방식으로 우회한다 — 실제 레거시 연동이 붙으면 이 몽키패치는 필요 없다. 흐름:
```
$ python examples/human_action_demo.py
[사람 확인 필요] tool=subscription_status step=manual_review
가능한 action: 승인, 반려, 서류추가요청
고를 action을 입력하세요: 서류추가요청
어떤 서류가 더 필요한가요?: 소득증빙서류

최종 결과: {'applicant_id': 'A123', 'status': '보류', 'status_confidence': 'inferred',
            'region': 'Seoul', 'manual_review_decision': {'action': '서류추가요청', 'field': '소득증빙서류'}}
```
bounded choices 밖의 값을 입력하면(`@human_action`이 던지는 `ValueError`) 크래시 대신 "다시 골라주세요"로 재입력을 받는다 — orchestrator 레벨의 `resume()` 호출이 실패해도 대화 자체는 안 끊어진다는 걸 보여준다.

**알려진 한계** (자세한 건 § 아래 "현재 스캐폴드의 한계"): `Orchestrator.resume()`은 tool이 `context["last_result"]`를 그대로 반환하는 관례에 기대므로 `subscription_status`에서만 쓸 수 있고(`subscription_weather_flow`처럼 자체적으로 반환값을 조립하는 tool은 대상이 아님), 세션 영속화 계층이 없어 호출자가 paused response의 `context`를 직접 들고 있다가 넘겨야 하며, "action이 실제로 다른 capability를 호출·연결한다"(예: `"서류추가요청"`이 서류 재제출 처리 tool로 실제 핸드오프하는 것)는 아직 구현하지 않았다 — 지금은 action + payload까지만 만들고, 실제로 연결할 대상 capability가 생겼을 때 그 실행 로직을 얹기로 결정했다.

### 서비스를 조합하는 서비스 — `services/subscription_weather_flow/workflow.py`
`common/orchestrator.md`가 "하나의 요청이 여러 tool을 필요로 하면 ... 고정 서브 workflow(capability)로 등록되어 있는지 먼저 확인하라"고 지시하는 지점의 구현체. `Orchestrator.handle()`은 요청당 tool 하나만 고르므로(§`orchestrator.py`), 두 tool을 함께 써야 하는 요청은 에이전트가 즉석에서 두 번 호출하게 두지 않고 이렇게 **상위 capability 하나로 미리 고정**한다.

- `registry`에 등록되는 다른 서비스와 달리 `adapter.py`/`mapping.json`이 없다 — 자신만의 레거시/외부 연동이 없고, 이미 등록된 `subscription_status`/`weather` **tool을 그대로 호출**해서 결과를 합성만 한다.
- **다른 서비스의 함수를 직접 import하지 않는다.** `query_subscription`/`query_weather` 스텝 본문 안에서 `registry.tool_for("subscription_status")`처럼 전역 `ToolRegistry`를 이름(문자열)으로 조회해 호출한다 — `from services.subscription_status.workflow import subscription_status`처럼 정확한 모듈 경로와 함수 이름을 직접 아는 게 아니다. 오케스트레이터가 tool을 고를 때 이름 문자열에만 커플링되는 것과 같은 원칙을 서비스 간 호출에도 적용한 것 — 원래는 직접 import였는데, "조합 서비스가 다른 서비스의 내부 구현(정확한 함수 이름)까지 알아야 하는 건 `discover_services()`가 없애려던 결합을 다시 만드는 것"이라는 지적으로 고쳤다. 조회를 **스텝 함수 본문 안에서(모듈 로드 시점이 아니라 호출 시점에)** 하기 때문에 `discover_services()`가 서비스를 어떤 순서로 import하든 안전하다(`subscription_weather_flow`가 알파벳 순서상 `weather`보다 먼저 import돼도, 실제 함수가 호출되는 시점엔 이미 전부 등록이 끝나 있음). `ToolRegistry.tool_for(name)`은 `tools()`처럼 전체 dict를 복사하지 않고 이름 하나만 찾으며(없으면 `KeyError`로 명확히 실패), 반환하는 `ToolSpec`이 `__call__`을 구현해서(spec 자체가 호출 가능) 호출부가 `.func`를 몰라도 되게 했다 — "몇 단계를 거치든 상관없지만 `.func`라는 내부 속성 이름은 안 보였으면 좋겠다"는 요청으로 다듬은 형태.
- 다만 output 스키마 상수(`SUBSCRIPTION_STATUS_OUTPUT_SCHEMA`/`WEATHER_OUTPUT_SCHEMA`, 바로 아래 문단)는 여전히 직접 import한다 — `@guardrail(output_schema=...)`는 모듈이 로드되는 순간(데코레이터 적용 시점)에 그 값이 이미 있어야 하는데, 그 시점엔 아직 등록 안 된 서비스도 있을 수 있어 registry 조회로는 안전하게 바꿀 수 없다(§ 아래 "현재 스캐폴드의 한계"에 이 잔여 결합을 기록해둠).
- 내부에서 `subscription_status()`/`weather()`를 (이제 registry를 통해) 호출하는 건 그 두 tool 각각의 `GuardrailChain.run()`(input 검증 포함)을 거치지 않는다는 뜻이다 — `subscription_status.workflow`가 내부적으로 `SubscriptionStatusAdapter`를 직접 호출하고 오케스트레이터의 개입 없이 결과를 합성하는 것과 동일한 "capability가 capability를 감싼다" 패턴이다.
- 다만 output 쪽 **내용물 검증**은 우회되지 않는다. `subscription_weather_flow`의 guardrail은 `{"subscription": Any, "weather": Any}`처럼 존재 여부만 보는 대신, 각 서비스의 `workflow.py`가 노출하는 `SUBSCRIPTION_STATUS_OUTPUT_SCHEMA` / `WEATHER_OUTPUT_SCHEMA` 상수를 그대로 import해 `{"subscription": SUBSCRIPTION_STATUS_OUTPUT_SCHEMA, "weather": WEATHER_OUTPUT_SCHEMA}`로 중첩 선언한다(§ `harness/guardrail.py`의 중첩 스키마 검증). `_validate()`가 재귀적으로 내려가 `subscription.status`/`weather.condition` 같은 중첩 필드까지 enum·optional 규칙을 그대로 적용하므로, 조합 서비스를 오케스트레이터로 호출하는 경로에서는 결과적으로 내용 검증이 이뤄진다. 스키마를 두 tool 모듈에서 재사용하기 때문에 중복 선언 없이 단일 소스로 유지된다.

### 입력 없는 목록 조회 + 표 렌더링 — `services/applicant_list/workflow.py`
청약 신청자 20명(스텁)과 각자의 진행 단계를 한 번에 보여주는 tool. 구조적으로는 `weather`와 같은 "단순 어댑터 서비스"(`adapter.py`/`mapping.json`, 분기 없어 `WorkflowRegistry` 생략)이지만 두 가지가 다르다.

- **입력이 없다.** `@tool` 함수가 `applicant_list()`로 파라미터 0개 — `_infer_schema()`(`registry/decorators.py`)가 빈 `input_schema`를 추론하는 첫 사례다. 목록 전체를 고정 조회하는 tool은 라우팅에 필요한 인자가 없어도 된다는 걸 보여준다.
- **`mapping.json`을 `subscription_status`와 공유하지 않고 따로 둔다.** 두 서비스가 같은 레거시 청약 시스템의 다른 API(목록 vs 상세)를 표현한다는 설정이라 값(코드→상태 5종)은 우연히 동일하지만, "서비스는 자기 매핑 자산을 스스로 갖는다"는 원칙(§ 신규 서비스 추가 가이드)을 그대로 따른다 — import로 공유하면 결합이 생기고, 두 API가 실제로는 다른 속도로 바뀔 수 있는 별개의 레거시 엔드포인트라는 전제와 맞지 않는다.
- **최상위 `@tool` 함수가 표현(presentation)까지 조립한다.** `adapter.normalize()`는 의미 정규화(코드→값+confidence)까지만 하고, `applicant_list()`가 그 위에서 `_render_table()`로 마크다운 표 문자열을 만들어 `{"applicants": [...], "table": "..."}`로 반환한다 — 구조화된 데이터와 표 문자열을 같이 주는 이유는, 채팅 인터페이스에 그대로 얹었을 때 20행짜리 표가 실제로 읽을 만한지(이번 서비스를 추가한 실험 목적)를 그 자리에서 확인할 수 있게 하기 위해서다.
- **"목록 → 상세" 두 단계는 하나의 capability로 묶지 않았다.** `subscription_weather_flow`(region 데이터를 다음 tool 입력으로 자동 전달)와 달리, `applicant_list`의 tool description은 "사용자가 특정 신청자를 지목하면 `subscription_status(applicant_id=...)`로 이어서 조회하라"고만 안내하고 실제 연결은 만들지 않았다 — 두 호출이 같은 요청 안에서 항상 함께 일어나는 게 아니라(목록만 보고 끝낼 수도 있음), 별개의 대화 턴에서 사용자가 고른 이름을 사람(또는 그 위의 agent 판단)이 applicant_id로 옮겨서 다음 요청을 만드는 구조이기 때문이다 — 이게 **고정 서브 workflow로 묶어야 하는 경우(subscription_weather_flow)와 개별 tool로 남겨야 하는 경우(applicant_list → subscription_status)를 가르는 기준**이다: 데이터 의존관계가 매 호출마다 결정론적으로 이어지면 묶고, 사람이 매번 다르게 골라야 하면 개별 tool로 남긴다.

## 서비스-프레임워크 연결도

지금 구현된 4개 서비스가 프레임워크의 어떤 조각에 실제로 연결되는지를 시각화한 다이어그램은 `agent_loop_architecture_diagrams.html`의 "8. 현재 구현된 서비스 ↔ 프레임워크 연결도" 절에 있다(SVG로 직접 그려서 마크다운 뷰어의 mermaid 렌더링 품질에 의존하지 않음 — 브라우저로 그 HTML 파일을 열어서 확인). 읽는 법은 아래와 같다.

읽는 법:
- **오케스트레이터는 전역 `ToolRegistry`만 안다** — 어떤 서비스가 몇 개 있는지, 내부 구조가 뭔지는 모른다.
- **`WorkflowRegistry`는 서비스마다 쓰거나 안 쓰거나다** — `subscription_status`/`subscription_weather_flow`만 실제로 쓰고(분기/재시도/판단 노드가 있어서), `weather`/`applicant_list`는 아예 안 쓴다(§ "언제 WorkflowRegistry를 생략하는가").
- **`subscription_weather_flow`의 두 점선(직접 호출)**: `subscription_status`/`weather`의 tool 함수를 **직접** 호출한다는 뜻 — 이 경로는 각 tool의 `GuardrailChain.run()`(input 검증)을 우회한다(§ "서비스를 조합하는 서비스" 절).
- **`applicant_list`의 라벨 붙은 점선(prompt만)**: `subscription_status`로 이어지는 걸 tool description 문구로만 안내하고 코드로 연결하지 않았다 — 사람이 매번 다른 신청자를 고르는 시나리오라 고정 서브 workflow로 안 묶은 결과다(§ "입력 없는 목록 조회" 절).

## 요청 하나의 전체 흐름 (`main.py` 예시 기준)

```
orchestrator.handle("subscription_status 조회해줘", applicant_id="A123")
  └─ tracer.start_trace("orchestrator")
     └─ agent_runner.choose_tool(...) → "subscription_status"
        └─ guardrails.run("subscription_status", spec.func, {...})
           ├─ input 검증 (spec 없으면 스킵 — 이 tool은 output_schema만 선언)
           └─ spec.func(applicant_id="A123") 호출
              = subscription_status(applicant_id="A123")   [services/subscription_status/workflow.py]
                └─ StateMachine(entry="fetch_status").run(context)
                   ├─ fetch_status: SubscriptionStatusAdapter().execute(applicant_id=...)
                   │    ├─ call()      → 레거시 원시 응답 {"status_code": "20"} (현재 스텁)
                   │    └─ normalize() → mapping.json 조회 → {"status": "서류미비", "status_confidence": "confirmed"}
                   │    outcome = "서류미비" → next 맵에 따라 종료(DONE)
                   │    (만약 confidence != confirmed였다면 outcome="미확인" → manual_review로 진입)
              → context["last_result"] 반환
           └─ output 검증: status/status_confidence가 선언된 enum 안에 있는지 확인
     └─ tracer: Trace 안에 subscription_status Tool Span 기록하고 종료
```

`fetch_status`의 outcome이 `"미확인"`이면(confidence가 `inferred`) `manual_review`로 진입하는데, 이 노드는 사람의 답이 필요해 여기서 한 번 더 갈린다.

```
StateMachine.run() 계속 (entry 이후 manual_review 진입)
  └─ manual_review(context) 호출 — context에 아직 "human_action" 없음
       └─ raise AwaitingHumanAction(choices=("승인","반려","서류추가요청"))
            → StateMachine.run()이 잡아 step="manual_review", context=현재 context를 채워 다시 던짐
       → guardrails.run()이 output 검증 없이 그대로 전파 (완료된 결과가 아니므로)
       → Orchestrator.handle()이 받아서 정상 반환값으로 변환:
            {"status": "awaiting_human_action", "tool": "subscription_status",
             "step": "manual_review", "choices": ["승인","반려","서류추가요청"], "context": {...}}
  ⋯ (사람이 다음 턴에 답을 고름: 예 {"action": "서류추가요청", "field": "소득증빙서류"}) ⋯
orchestrator.resume("subscription_status", context, "manual_review", {"action": "서류추가요청", "field": "소득증빙서류"})
  └─ tool_spec = registry.tools()["subscription_status"]  → tool_spec.workflow_registry (= subscription_status.workflow.steps)
     context["human_action"] = {"action": "서류추가요청", "field": "소득증빙서류"}
     └─ StateMachine(registry=tool_spec.workflow_registry, entry="manual_review").run(context)  — 멈췄던 지점부터 재개
          └─ manual_review(context) 재호출 — 이번엔 context["human_action"]이 있음
               → @human_action이 action("서류추가요청")을 choices로, payload({"field":...})를
                 payload_schemas["서류추가요청"]으로 검증 (밖이면 ValueError)
               → context["last_result"]["manual_review_decision"] = {"action": "서류추가요청", "field": "소득증빙서류"}
               outcome = "서류추가요청" → next 맵에 따라 종료(DONE)
     → context["last_result"] 반환
  └─ output 검증: status/status_confidence가 enum 안에 있는지, manual_review_decision(optional)이
     있다면 존재만 확인(Any — 세부 검증은 이미 @human_action이 끝냄)
```

나머지 두 tool은 같은 골격(라우팅 → guardrail → tool 함수)을 훨씬 짧게 탄다.

```
orchestrator.handle("weather 조회해줘", location="Seoul")
  → weather(location="Seoul")   [services/weather/workflow.py]
     └─ WeatherAdapter().execute(location="Seoul")  — 분기/재시도가 없어 WorkflowRegistry/StateMachine 없이 직접 호출
          ├─ call()      → 지오코딩(도시명→좌표) + Open-Meteo 현재 날씨 실 호출
          └─ normalize() → mapping.json(WMO code) 조회 → {"condition": "대체로 맑음", ...}

orchestrator.handle("subscription_weather_flow 조회해줘", applicant_id="A123")
  → subscription_weather_flow(applicant_id="A123")   [services/subscription_weather_flow/workflow.py]
     └─ StateMachine(entry="query_subscription").run(context)
        ├─ query_subscription: subscription_status(applicant_id="A123") 직접 호출 (guardrail 안 거침)
        │    → context["subscription_result"] = {..., "region": "Seoul"}
        └─ query_weather: weather(location=subscription_result["region"]) 직접 호출
             → context["weather_result"] = {...}
     → {"subscription": ..., "weather": ...} 반환
        └─ guardrail output 검증: {"subscription": SUBSCRIPTION_STATUS_OUTPUT_SCHEMA, "weather": WEATHER_OUTPUT_SCHEMA}로
           중첩 검증 — subscription.status/weather.condition 등 내부 필드까지 enum·optional 규칙 그대로 적용
```

## 로깅

`LOG_LEVEL` 환경변수(`.env`, 기본 `INFO`)로 전체 로깅 레벨을 정한다. `main.py`가 기동 직후 `configure_logging()`을 한 번 호출해 표준 `logging`을 설정하므로, 이후 `discover_services()`부터 `orchestrator.handle()`까지 전 과정이 같은 스트림에 시간순으로 찍힌다 — 요청 하나가 오케스트레이터 라우팅부터 state machine의 스텝 전이, 어댑터 호출, (있다면) 사람의 판단 대기/재개까지 어떻게 흘렀는지 콘솔 출력 하나로 전부 볼 수 있다(§ 위 "요청 하나의 전체 흐름"과 대응).

- **INFO** (기본값): "지금 어떤 단계를 지나는지"만 보여주는 요약 라인 — trace/span 시작·종료(들여쓰기로 중첩 깊이 표현), state machine 스텝 전이, guardrail 통과 여부, judged/human_action 노드의 최종 선택("state machine paused: ... awaiting human action from (...)" 포함), (judged 노드가 실제로 모델을 호출하면) OpenAI 호출의 모델명·길이·응답 미리보기.
- **DEBUG**: 위에 더해 어댑터 `call()`/`normalize()`의 실제 payload, guardrail 스킵/통과 상세, OpenAI system/user 프롬프트 원문까지 — 로컬 디버깅 전용. 레거시 원시값이나 프롬프트에 개인정보가 실릴 수 있으므로 운영 환경에서는 켜지 않는다.
- **WARNING 이상**: 정상 흐름은 거의 안 찍히고 예외 직전 `ERROR` 로그만 남는다.

`LOG_LEVEL=INFO`로 `subscription_status` 하나를 조회하면 이런 식으로 찍힌다(시간·trace id는 매번 다름):

```
INFO  agent_loop.orchestrator      | request received: 'subscription_status 조회해줘' kwargs={'applicant_id': 'A123'}
INFO  agent_loop.tracing           | trace 6c80695b start [orchestrator] orchestrator
INFO  agent_loop.orchestrator      | tool selected: subscription_status (via FirstMatchRunner)
INFO  agent_loop.tracing           |   span start [tool] subscription_status
INFO  agent_loop.state_machine     | state machine start: entry='fetch_status'
INFO  agent_loop.tracing           |     span start [step] fetch_status
INFO  agent_loop.tracing           |     span end   [step] fetch_status duration=0.000s
INFO  agent_loop.state_machine     | step 'fetch_status' -> outcome='서류미비' -> next='DONE'
INFO  agent_loop.state_machine     | state machine done: step='fetch_status'
INFO  agent_loop.tracing           |   span end   [tool] subscription_status duration=0.001s
INFO  agent_loop.orchestrator      | request done: tool=subscription_status result_keys=[...]
INFO  agent_loop.tracing           | trace 6c80695b end   [orchestrator] orchestrator duration=0.001s
```

`subscription_weather_flow`처럼 tool이 다른 tool을 직접 호출하는 경우, 안쪽 `subscription_status`가 여는 `state machine start`/`span`이 바깥쪽 `query_subscription` 스텝 span 밑에 한 단계 더 들여써져서 나온다 — 합성 관계가 로그 들여쓰기 그대로 드러난다. `weather`는 이제 자체 `StateMachine`이 없어 `query_weather` 스텝 span 밑에 별도 "state machine start" 없이 어댑터 호출 로그만 바로 붙는다.

**알려진 한계**: `Tracer._stack`은 `Tracer` 싱글턴 하나가 공유하는 상태라 스레드 세이프하지 않다 — 지금 스캐폴드는 요청을 동기적으로 하나씩 처리하는 걸 전제로 하며, 나중에 요청을 동시에(멀티스레드/비동기) 처리하게 되면 이 부분을 `contextvars` 기반으로 바꿔야 한다.

## 설계축 ↔ 코드 매핑

| 설계 문서의 개념 | 코드 |
|---|---|
| 오케스트레이터 (인터페이스에만 커플링) | `orchestrator.Orchestrator` + `AgentRunner` Protocol |
| Tool Registry (양면 어댑터의 의미론적 면 등록) | `registry.decorators.ToolRegistry` / `@tool` |
| 프로토콜적 면 vs 의미론적 면 분리 | `adapters.base.BaseAdapter.call()` vs `.normalize()` |
| Prompt Store (공통/도메인/few-shot 계층) | `prompts.store.PromptStore` |
| 공통 하네스 — Input/Output Guardrail 체인 | `harness.guardrail.GuardrailChain` |
| 공통 하네스 — Tracing | `harness.tracing.Tracer` |
| 결정론적 분기/순환 | `workflow.registry.WorkflowRegistry.step(next=...)`(파일마다 로컬 인스턴스) + `workflow.state_machine.StateMachine` |
| Judged branch (bounded choices, 판단 주체=모델) | `workflow.registry.WorkflowRegistry.judged(choices=...)` — 현재 등록된 서비스는 없음(§ 아래 한계) |
| Human-in-the-loop judged branch (bounded choices + payload, 판단 주체=사람) | `workflow.registry.WorkflowRegistry.human_action(choices=..., payload_schemas=...)` + `workflow.state_machine.AwaitingHumanAction` + `orchestrator.Orchestrator.resume()`(tool별 `workflow_registry`로 재개) |
| confirmed/inferred 매핑 관리 | `semantic.mapping.SemanticMapping` / `MappedValue` |
| 미확인 값 fail-fast | `semantic.mapping.UnmappedValueError` |
| 도메인 흐름 전체를 하나의 capability로 등록 | `services/subscription_status/workflow.py`의 최상위 `@tool subscription_status` (내부 state machine을 감싸 단일 tool로 노출) |
| 외부 실 API를 가진 서비스 (프로토콜적 면 = 실제 HTTP 호출, 인증 불필요) | `services/weather/adapter.WeatherAdapter.call()` (Open-Meteo 지오코딩 + 현재 날씨) |
| 사람에게 action 목록을 보여주고 고르게 하는 실제 배선 | `services/subscription_status/workflow.py`의 `manual_review()` — `@human_action` + `AwaitingHumanAction`으로 일시정지, `Orchestrator.resume()`으로 재개 |
| 여러 tool을 고정 서브 workflow로 미리 묶기 (에이전트가 즉석에서 여러 tool을 잇지 않게) | `services/subscription_weather_flow/workflow.py`의 최상위 `@tool subscription_weather_flow` — `subscription_status()` → `weather()` 순차 호출, `region` 필드로 데이터 연결 |
| 서비스 auto-discovery + 기동 시점 일관성 검사 | `registry.discovery.discover_services()` + `registry.decorators.ToolRegistry.validate()` |
| Optional 필드 + 중첩 스키마 검증 (조합 서비스의 하위 tool 결과까지 boundary에서 검증) | `harness.schema.optional()`(`OptionalField`) + `validate_schema()`의 재귀 검증 — `harness.guardrail`과 `workflow.registry.WorkflowRegistry.human_action`이 공유, `services/subscription_weather_flow/workflow.py`가 `SUBSCRIPTION_STATUS_OUTPUT_SCHEMA`/`WEATHER_OUTPUT_SCHEMA`를 재사용 |
| 레벨 조절 가능한 단계별 로깅 | `harness.logging_setup.configure_logging()`(`LOG_LEVEL`) + `harness.tracing.Tracer`(trace/span을 로그로도 출력) |
| 입력 없는 tool + 결정론적 데이터 의존관계가 없어 별도 tool로 남긴 "목록 → 상세" 패턴 | `services/applicant_list/workflow.py`의 최상위 `@tool applicant_list()` — 표(`table`) 렌더링까지 조립, `subscription_status`로의 후속 조회는 프롬프트로만 안내(§ 위 "입력 없는 목록 조회" 절) |

## 신규 서비스 추가 시 손대는 파일 (엔진 불변성 체크)

두 카테고리가 있다 — 어느 쪽이든 `framework/`도 `main.py`도 손대지 않는 게 목표이고, `discover_services()`(auto-discovery) 덕분에 실제로 그렇게 됐다. `services/<name>/`에 파일을 놓기만 하면 다음 실행 때 `registry.validate()`가 등록/참조 무결성까지 자동으로 확인해준다.

**레거시/외부 어댑터 서비스** (`subscription_status`, `weather`, `applicant_list`) — `guides/legacy_adapter_guide.md` 체크리스트 기준, 아래 4개 파일만 새로 만든다. `workflow.py`의 모양은 분기/재시도/판단 노드가 있느냐에 따라 갈린다(§ 위 "언제 WorkflowRegistry/StateMachine을 아예 생략하는가").
- `services/<name>/adapter.py` (`BaseAdapter` 상속)
- `services/<name>/mapping.json`
- `services/<name>/workflow.py`
  - 분기/재시도/판단 노드가 하나도 없으면(`weather`, `applicant_list`): `WorkflowRegistry` 없이 최상위 `@tool` 함수 안에서 어댑터를 직접 호출
  - 하나라도 있으면(`subscription_status`): `steps = WorkflowRegistry()` + `steps.step()`/`steps.judged()`(모델 판단) 또는 `steps.human_action()`(사람 판단) + 최상위 `@tool`
- `services/<name>/prompts/<tool_name>.md`

**조합 서비스** (`subscription_weather_flow`) — 자신만의 외부 연동이 없으므로 `adapter.py`/`mapping.json`은 만들지 않는다.
- `services/<name>/workflow.py` (다른 tool은 `registry.tool_for("<name>")`로 이름만 알고 스텝 본문 안에서 조회해 호출 — 직접 import 금지, § 위 "서비스를 조합하는 서비스" 절, 자기 전용 `steps = WorkflowRegistry()`의 `steps.step()`으로 연결 + 최상위 `@tool`)
- `services/<name>/prompts/<tool_name>.md`

두 카테고리 모두 `services/<name>/workflow.py`라는 파일명은 고정이다 — `discover_services()`가 정확히 이 이름을 import하기 때문(§ `registry/discovery.py`).

## 현재 스캐폴드의 한계 (다음 작업 후보)

- `SubscriptionStatusAdapter.call()`은 여전히 실제 레거시 연동 전 스텁(고정 응답, `region`도 항상 `"Seoul"`로 고정) — 청약 시스템 실 연동 시 교체 필요. 실제 레거시가 지역 정보를 안 주면 `subscription_weather_flow`의 데이터 연결 지점 자체를 다시 설계해야 함.
- `WeatherAdapter`는 Open-Meteo(무료, 인증 불필요)를 쓰므로 `weather` 서비스는 `.env`에 키를 넣지 않아도 바로 호출 가능 — 처음에 RapidAPI "yahoo-weather5"(키 필요)로 만들었다가 인증 없는 샘플 테스트에 맞춰 교체함.
- `requirements.txt`(openai/python-dotenv/requests)가 아직 이 환경에 설치되지 않음 — `pip install -r requirements.txt` 필요.
- `OpenAIRunner`(tool 라우팅)는 `OPENAI_MODEL` 미지정 시 `gpt-4o-mini`로 기본 동작 — 실제 사용 가능한 모델명으로 `.env`에서 확정해야 함. `manual_review`는 더 이상 OpenAI를 호출하지 않으므로(사람 판단으로 전환) 이 항목과 무관해졌다.
- `steps.judged()`(모델이 판단하는 judged branch)는 메서드·`WorkflowRegistry.validate()` 검사·문서까지 다 갖춰져 있지만, `manual_review`가 `steps.human_action()`(사람 판단)으로 전환되면서 지금 `services/` 전체에서 실제로 이 메서드를 쓰는 서비스가 하나도 없다 — `framework/prompts/store.py`의 `compose()` + `framework/llm/openai_client.py`의 `complete()` 조합도 같이 orphan됨. **정리 여부**: 이 조합에 실제로 종속돼 있던 서비스별 산출물, 즉 `services/subscription_status/prompts/manual_review.md`(당시 OpenAI에게 자동승인/수동검토를 판단시키던 프롬프트)는 완전히 죽은 파일이라 삭제했다. 반면 `steps.judged()`·`WorkflowRegistry.validate()`의 judged 검사·`PromptStore.compose()`·`framework/llm/openai_client.py`는 특정 서비스에 종속된 게 아니라 재사용 가능한 프레임워크 능력이라 그대로 남겨뒀다 — 다음에 "사람이 아니라 모델이 판단해야 하는" judged 노드가 생기면 그때 다시 살아있는 예시가 생긴다.
- `steps.human_action()`/`AwaitingHumanAction`/`Orchestrator.resume()`으로 만든 human-in-the-loop 일시정지/재개는 `subscription_status`라는 단일 사례로만 검증됐다. `Orchestrator.resume()`은 tool이 `context["last_result"]`를 그대로 반환한다는 관례에 기대므로 `subscription_weather_flow`처럼 자체적으로 반환값을 조립하는 tool에는 아직 쓸 수 없고, 세션 영속화 계층이 없어 paused response의 `context`를 호출자가 프로세스 메모리 안에서 직접 들고 있다가 넘겨야 한다(재시작하면 유실).
- **미해결 논의 — LangGraph의 checkpointer식 영속화가 필요한가.** 위 항목의 근본 원인은 "멈춘 상태를 프로세스 메모리 밖(DB 등)에 저장했다가, 나중에 다른 프로세스/다른 시점에서도 정확히 그 지점부터 재개한다"는 기능 자체가 없다는 것이다. LangGraph의 checkpointer가 하는 일과 비교하며 논의했는데, `manual_review`가 대표하는 실제 업무(사람이 서류를 몇 시간~며칠 걸려 검토)를 생각하면 이 갭은 실재한다는 데는 동의했다. **아직 구현하지 않음** — 세션 저장소 종류(파일/Redis/DB)와 배포 형태(단일 프로세스 유지 vs 여러 워커로 분산)가 안 정해진 채로 먼저 만들면 나중에 실제 요구사항이 드러났을 때 다시 뜯어고칠 위험이 크다는 판단. 실제로 필요해지는 신호는 (1) 사람이 몇 시간/며칠 뒤에 승인·반려하는 실제(모의가 아닌) 시나리오가 생기는가, (2) 그 사이 서버 재시작이나 여러 인스턴스 분산 배포가 실제로 필요한가 — 이 둘 중 하나라도 나타나면 그때 checkpointer 스타일 영속화를 설계한다.
- **미해결 논의 — 병렬 분기(fan-out/join)가 필요한가.** `StateMachine.run()`(`framework/workflow/state_machine.py:51-94`)은 `current` 변수 하나로 추적하는 순수 순차 루프라 `next`의 outcome이 항상 다음 스텝 "하나"로만 resolve된다 — 여러 스텝을 동시에 실행하고 결과를 합치는 fan-out/join 개념 자체가 없다. "두 서비스의 결과를 같이 들고 다음 지점으로 넘어가야 하는" 요구는 이미 지금 방식(공유 `context`에 각자 순차적으로 결과를 채우는 것 — `subscription_weather_flow`가 실제 사례)으로 충분하다는 데는 합의했다. 진짜 동시 실행(두 호출 사이에 데이터 의존관계가 없어서 지연시간을 줄이려고 병렬로 부르는 것)은 `next`가 여러 타겟을 가리키게 하고 join 지점을 새로 설계해야 하는, 지금 없는 기능이다. **아직 구현하지 않음** — 지금 4개 서비스 중 "의존관계 없는 두 호출을 동시에 불러야 할 만큼 느린" 실제 사례가 없어서, 그런 필요가 실제로 발생할 때까지 보류.
- **미해결 논의 — tool 본문 안에 `complete()`를 직접 박아넣으면 어떻게 되는가.** 지금 이 프로그램 전체에서 AI가 실제로 결정에 참여하는 지점은 `OpenAIRunner.choose_tool()`(tool 선택) 단 한 곳뿐이다(`grep`으로 확인 — `complete()` 호출부가 `main.py:59`에만 있음). `judged`/`human_action`이 감사 가능성을 위해 bounded choices를 강제하는 것과 달리, tool 함수 본문에서 `framework.llm.openai_client.complete()`를 직접 호출하는 건 파이썬 문법상 막을 방법이 없다 — 다만 그러면 반환값의 형태를 코드 어디에도 선언할 수 없어 `guardrail`/`registry.validate()`/`WorkflowRegistry.validate()`가 검증할 대상 자체가 사라지고, 로그에도 "왜 이 결과가 나왔는지"가 `judged '...' -> '...'` 같은 명확한 라인이 아니라 자유 텍스트 생성으로만 남는다. 즉 "선택은 자유롭되 감사는 가능해야 한다"는 이 프레임워크의 핵심 제약을 그 tool 안에서는 포기하는 트레이드오프다. **아직 구현하지 않음** — 정형화가 원천적으로 불가능한 자유 텍스트 생성이 목적 자체인 tool이 실제로 필요해지기 전까지는 열어둔 질문으로만 남겨둔다.
- **미해결 논의 — `manual_review` 앞에 AI 기반 중요도 분류(triage)를 넣을지.** 지금은 `fetch_status`가 `status_confidence != "confirmed"`면 무조건(예외 없이) `manual_review`(사람 판단)로 보낸다. "덜 중요한 판단은 AI에게 위임하고 싶어질 수도 있다"는 논의가 나왔는데, 이건 사실 이 프로젝트가 이미 한 번 시도했다가 되돌린 구조와 같다 — 외부 커밋으로 처음 들어왔을 때 이 지점은 `@judged`가 "자동승인"/"수동검토" 중 뭘 고를지 AI가 판단하는 구조였고, "`manual_review`라는 이름의 노드 안에서 AI가 자동으로 판단한다"는 게 이름과 행동이 모순돼 지금의 `human_action`(사람이 직접 승인/반려)으로 바꿨다(§ "human-in-the-loop" 절). 다시 넣는다면 그 모순을 반복하지 않도록 **역할을 분리**해야 한다는 데는 논의 중 합의했다 — 예: 새 `judged()` 노드 `triage`를 하나 더 두어 bounded choices를 "경미"/"중요" 같은 **중요도 분류로만** 한정하고(승인/반려를 직접 고르게 하지 않음), "경미"는 별도 자동 처리 경로로, "중요"는 지금처럼 `manual_review`로 보낸다 — 이러면 `triage`(AI가 함)와 `manual_review`(사람이 함)가 이름과 실제 행동이 어긋나지 않는다. **아직 구현하지 않음** — "누군가 원할 수도 있겠다"는 가정 단계일 뿐 구체적인 need가 아직 없어서, 실제로 사람에게 넘어가는 케이스 중 "이건 AI가 걸러줬어도 됐을 텐데"라는 구체적 사례가 쌓이기 전까지는 보류.
- human_action의 action은 여전히 "라벨 + payload"로만 끝난다 — action이 실제로 다른 capability를 호출·연결하는 것(예: `"서류추가요청"`이 서류 재제출 처리 tool로 실제 핸드오프하는 것)은 의도적으로 미룬 범위다. 실제로 연결할 대상 capability가 생기면 그때 실행 로직을 얹기로 함(YAGNI로 미룬 것이지 빠뜨린 게 아님).
- `main.py`의 `FirstMatchRunner`는 이름이 긴 tool부터 substring 매칭하도록 고쳤지만(한 tool 이름이 다른 tool 이름을 포함하는 경우 대비, 예: `weather` ⊂ `subscription_weather_flow`), 여전히 순수 문자열 포함 검사라 실제 자연어 요청 라우팅에는 쓸 수 없다 — 오프라인 샘플 테스트 전용 스텁이라는 원래 성격은 그대로.
- `ToolRegistry.validate()`(tool/guardrail 카탈로그)와 `WorkflowRegistry.validate()`(파일별 step/next/judged/human_action) 둘 다 참조 무결성만 본다 — "adapter.py가 BaseAdapter를 상속했는가", "mapping.json이 실제로 존재하는가" 같은 파일 시스템/클래스 계층 검사나, "새 tool description이 기존 tool과 의미가 안 겹치는가" 같은 의미적 검사(`guides/legacy_adapter_guide.md` 체크리스트 항목)는 하지 않는다 — 이런 건 코드로 자동 판별하기 어려워 사람 리뷰 영역으로 남겨둠.
- **(해결됨, 참고로 남김)** 원래 `workflow_step`/`next`/`order`가 전역 `ToolRegistry`에 이름만으로 등록돼 있었다 — 다른 파일과 스텝 이름이 겹치면 조용히 덮어써지고, `next` 참조가 다른 서비스로 새는 것도 막을 방법이 없었고, `order`가 "이 workflow 안에서 몇 번째"라는 걸 전역에서는 표현할 수 없었다(같은 스텝이 여러 workflow에 다른 순서로 조합될 수 있으므로). `workflow/registry.py`의 `WorkflowRegistry`로 분리해 각 파일이 자기 전용 인스턴스를 갖게 하면서 세 문제 모두 구조적으로 해소됨(§ 위 `workflow/registry.py` 절). 다만 `WorkflowStepSpec.order`/`.source`는 지금도 여전히 저장만 되고 `StateMachine.run()`을 포함해 어디에서도 읽히지 않는 죽은 필드다 — 실행 순서는 순전히 `entry` + `next` 체인만으로 결정된다. 지금은 사람이 읽을 때(코드 리뷰) 실행 순서를 가늠하는 문서화 용도로만 쓰이며, 실제로 강제되는 값이 아니라는 점에 주의.
- `steps.judged(choices=..., confidence_required="confirmed")`의 `confidence_required`는 `workflow.registry.JudgedSpec`에 저장만 되고 실제로 어디서도 읽거나 검사하지 않는다 — "inferred 값은 judged 판단에 넘기면 안 된다"는 규칙은 지금 `fetch_status`가 `status_confidence != "confirmed"`를 직접 체크해서 우회 진입시키는 방식으로만 지켜지고, `judged()` 자체는 이 제약을 강제하지 않는 미완성 지점이다.
- `subscription_weather_flow`의 중첩 guardrail(§ 위 절)은 **output 내용물**만 boundary에서 검증한다 — 내부에서 직접 호출하는 `subscription_status()`/`weather()` 각각의 `GuardrailChain.run()`(input 검증 포함)은 여전히 우회된다. 지금은 두 tool 모두 input_schema를 선언하지 않아 우연히 gap이 드러나지 않을 뿐이므로, 나중에 어느 한쪽이 input_schema를 추가하면 조합 서비스 경로에서는 그 input 검증이 적용 안 된다는 점을 잊기 쉽다.
- `subscription_weather_flow`가 다른 서비스를 호출할 때 함수는 registry 조회로 바꿨지만(§ 위 절), **output 스키마 상수는 여전히 직접 import한다**(`SUBSCRIPTION_STATUS_OUTPUT_SCHEMA`/`WEATHER_OUTPUT_SCHEMA`) — 정확한 모듈 경로와 상수 이름을 알아야 한다는 점에서 같은 종류의 결합이 남아있다. `@guardrail(output_schema=...)`가 모듈 로드 시점(데코레이터 적용 시점)에 그 값을 필요로 하는데, 그 시점엔 `discover_services()`가 아직 모든 서비스를 등록하지 못했을 수 있어(`subscription_weather_flow`는 알파벳 순서상 `weather`보다 먼저 import됨) `registry.guardrail_for("weather").output_schema`로 바꾸면 `None`을 가져오는 실제 버그가 난다 — 함수 호출과 달리 스텝 본문 안으로 늦출 수 없는 자리라 그대로 뒀다. 스키마를 `GuardrailSpec`에서 지연 평가(callable)로 받도록 `harness/guardrail.py`를 고치면 해결되지만, 그건 별도의 더 큰 변경이라 미룸.
- `ApplicantListAdapter.call()`은 20명 고정 스텁(하드코딩된 리스트) — 실제 레거시 목록 조회 API 연동 시 교체 필요. `applicant_list`와 `subscription_status`가 값은 동일하지만 서로 다른 `mapping.json`을 갖고 있어서(§ 위 "입력 없는 목록 조회" 절 — 의도적 설계), 실제로 상태 체계가 바뀌면 두 파일을 각각 갱신해야 한다는 걸 잊기 쉽다.
- **미해결 논의 — 서비스 간 "겹치는 필드"를 어떻게 다룰지.** 위 항목의 근본 원인은 두 서비스의 output이 스키마 전체가 겹치는 것도 완전히 독립적인 것도 아니라, 일부 필드만 겹친다는 데 있다(`applicant_id`/`status`/`status_confidence`는 같은 도메인 개념이라 일치해야 하고, `region`/`manual_review_decision`/`name`은 각 서비스 고유). 스키마 전체를 합치거나 완전히 분리하는 이분법 대신, 겹치는 조각만 뽑아 공유 자산으로 만들고(예: 도메인을 대표하는 서비스가 `MAPPING_PATH`/상태 enum 상수를 export하고 다른 서비스가 그 조각만 import) 안 겹치는 필드는 각자 스키마에 남기는 방향으로 논의했다. 프레임워크 차원 규약(`"confirmed"/"inferred"` 같은 `SemanticMapping` 자체의 값)과 도메인 차원 지식(청약 상태 5종 같은 특정 서비스의 값)은 공유 주체가 다르다는 점(전자는 `framework/semantic/mapping.py`, 후자는 그 도메인을 대표하는 서비스)도 같이 짚었다. **아직 구현하지 않음** — 실제 use case(파라미터가 여럿이고 그중 일부만 겹치는 상황이 정확히 어떻게 발생할지)가 명확해지기 전까지는 의도적으로 보류.
- "목록에서 이름을 보고 다음 요청에 applicant_id를 넣는" 연결은 프롬프트 문구(`prompts/applicant_list.md`)로만 안내할 뿐, 실제로 이름→ID를 찾아 다음 tool 호출의 인자를 채우는 로직은 어디에도 없다 — `AgentRunner`는 tool 이름만 고르고 인자는 여전히 호출자가 직접 채워야 하므로(§ `orchestrator.py`), 이 흐름이 실제로 자동으로 이어지려면 인자까지 추출하는 `AgentRunner` 구현체가 필요하다.
- `applicant_list`의 `_render_table()`이 만드는 표 포맷(지금은 마크다운 파이프 표)은 **미확정 상태로 남겨둔 것**이다 — "예쁘게 보여주는" 방법은 이 결과를 최종적으로 어디서 보여주느냐(마크다운 렌더링 채팅 UI / raw text 전용 뷰 / 자체 웹 프론트엔드의 테이블 컴포넌트 / 다른 서비스의 프로그램적 소비)에 따라 완전히 달라지는데, 그 실행 환경 자체가 아직 정해지지 않았다. 환경이 정해지기 전까지는 raw text 정렬 로직(한글 폭 계산 등) 같은 특정 방향으로 미리 구현하지 않기로 함 — 다음 작업은 환경이 확정된 뒤 그에 맞는 포맷으로 `_render_table()`을 바꾸는 것.
