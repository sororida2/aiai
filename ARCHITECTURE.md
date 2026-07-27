# Agent Loop 프레임워크 — 코드 구성

`README.md`(왜 이 구조가 필요한가)와 `ai_framework_2.md`(설계 철학)의 논의가 실제로 어떤 파일·클래스로 구현됐는지 매핑한 문서다. `services/` 아래 세 서비스가 각기 다른 절의 살아있는 예시다 — `subscription_status`(레거시 어댑터 + judged 노드 + OpenAI 연동), `weather`(인증 없는 외부 실 API 어댑터), `subscription_weather_flow`(서비스를 조합하는 서비스). `main.py`가 실행 진입점이다.

## 디렉토리 구조

```
framework/                  ← 엔진. 새 서비스를 추가해도 손대지 않는 것이 목표.
├── registry/decorators.py  ← @tool·@workflow_step·@judged·@guardrail 데코레이터 + ToolRegistry(+ validate())
├── registry/discovery.py    ← services/<name>/workflow.py 자동 스캔·import (discover_services)
├── orchestrator.py          ← Triage 라우팅 (Orchestrator, AgentRunner Protocol)
├── harness/
│   ├── guardrail.py          ← Input/Output 검증 체인 (GuardrailChain)
│   ├── tracing.py            ← Trace/Span 중첩 기록 + 그 자리에서 로그로도 출력 (Tracer)
│   └── logging_setup.py      ← LOG_LEVEL 환경변수 기반 로깅 설정 (configure_logging, get_logger)
├── prompts/store.py         ← 공통/도메인 프롬프트 계층 조립 (PromptStore)
├── prompts/common/          ← 공통 오케스트레이터 프롬프트 (orchestrator.md)
├── semantic/mapping.py      ← 레거시 원시값→정규화값 (SemanticMapping, MappedValue)
├── adapters/base.py         ← 양면 어댑터 추상 (BaseAdapter: call / normalize / execute)
├── llm/openai_client.py     ← OpenAI 호출 얇은 wrapper (complete()) — 엔진이 아니라 필요한 지점에서 opt-in으로 import
└── workflow/state_machine.py← 고정 파이프라인 실행기 (StateMachine)

services/                   ← 설정. 새 서비스 추가 시 여기만 늘어난다 (main.py도 안 건드림 — auto-discovery).
├── subscription_status/
│   ├── adapter.py           ← SubscriptionStatusAdapter(BaseAdapter)
│   ├── mapping.json          ← 상태코드 confirmed/inferred 매핑 테이블
│   ├── workflow.py           ← @workflow_step 파이프라인 + @judged 노드(manual_review, OpenAI 연동) + 최상위 @tool
│   └── prompts/
│       ├── subscription_status.md  ← 이 tool 전용 프롬프트
│       └── manual_review.md        ← manual_review judged 노드 전용 프롬프트
├── weather/                  ← 두 번째 살아있는 예시 (외부 실 API 연동 케이스, 인증 불필요)
│   ├── adapter.py           ← WeatherAdapter(BaseAdapter), Open-Meteo 지오코딩 + 현재 날씨 호출
│   ├── mapping.json          ← WMO weather code(공식 문서화 표) → 한국어 정규화 테이블
│   ├── workflow.py           ← 단일 스텝 파이프라인(fetch_weather) + 최상위 @tool
│   └── prompts/weather.md    ← 이 tool 전용 프롬프트
└── subscription_weather_flow/← 세 번째 예시: 어댑터 서비스가 아니라 "서비스를 조합하는 서비스"
    ├── workflow.py           ← adapter.py/mapping.json 없음 — subscription_status()/weather() tool 함수를
    │                            그대로 호출해 조합하는 @workflow_step 2단계 + 최상위 @tool
    └── prompts/subscription_weather_flow.md

main.py                     ← 조립 지점 (discover_services + registry.validate(), build_orchestrator,
                                OpenAIRunner/FirstMatchRunner) + 실행 예시. 서비스 추가 시 더 이상 손대지 않아도 됨.
guides/legacy_adapter_guide.md ← 신규 서비스 추가 가이드
.env / .env.example         ← OPENAI_API_KEY, OPENAI_MODEL, LOG_LEVEL (.env는 커밋 안 함; weather는 키 불필요)
```

## 컴포넌트별 역할

### `registry/decorators.py` — 등록 규약의 단일 지점
전역 `registry = ToolRegistry()` 하나에 네 종류 스펙이 모인다.
- `@tool(name, description)` → `ToolSpec` (오케스트레이터가 유일하게 커플링되는 표면)
- `@workflow_step(order, next=..., max_retries=...)` → `WorkflowStepSpec` (결정론적 분기/순환을 `next` dict로 고정)
- `@judged(choices=...)` → `JudgedSpec` + 실행 시 `choices` 밖 값이면 즉시 `ValueError` (bounded 강제)
- `@guardrail(input_schema=..., output_schema=...)` → `GuardrailSpec`

모듈을 import하는 순간 데코레이터가 실행되며 등록된다. 예전에는 `main.py`에 서비스마다 `from services.<name> import workflow as _`를 나열해 이 import를 직접 트리거했지만, 지금은 `framework/registry/discovery.py`의 `discover_services()`가 `services/` 아래를 스캔해서 대신 트리거한다 (§ 아래 `registry/discovery.py` 절).

### `registry/discovery.py` + `ToolRegistry.validate()` — auto-discovery와 일관성 검사
`main.py`가 서비스를 일일이 알 필요가 없게 만드는 지점. Python은 모듈을 실제로 import하기 전까진 그 안의 데코레이터를 실행하지 않으므로, 등록이 일어나려면 누군가는 각 `services/<name>/workflow.py`를 import해야 한다 — `discover_services(services)`가 `pkgutil.iter_modules(services.__path__)`로 하위 패키지를 전부 찾아 그 `workflow.py`를 대신 import해준다.

이렇게 등록을 "자동"으로 만들면 반쯤 구현된 서비스 폴더가 조용히 무시되거나(예: `@tool`을 하나도 등록 안 함), 다른 모듈이 등록한 step 이름을 가리키다 오타난 `next` 참조가 `StateMachine.run()` 시점(즉 실제 요청이 들어올 때)까지 숨어있을 위험이 커진다. 그래서 `main.py`는 `discover_services()` 직후 `registry.validate()`를 호출해 기동 시점에 바로 fail-fast한다. `ToolRegistry.validate()`가 검사하는 것:
- 등록된 tool이 하나도 없으면 즉시 실패 (서비스 폴더는 있는데 아무것도 안 잡힌 상태)
- 모든 `workflow_step.next`의 target이 `"DONE"`이거나 등록된 다른 step 이름이어야 함 (오타 탐지)
- 모든 `@judged` 노드는 반드시 같은 이름으로 `@workflow_step`에도 등록돼 있어야 함 (이중 데코레이터 누락 탐지)
- 모든 `@guardrail`은 실제로 그 tool의 함수 자체에 등록돼야 함 — `@guardrail`을 `@tool`보다 위(나중에 적용되게)에 잘못 쓰거나 함수 이름이 tool name과 다르면, `guardrail()` 데코레이터가 `func.__name__`으로 fallback하면서 엉뚱한 키에 등록되는 조용한 버그가 생기는데 이걸 잡아낸다

`discover_services()`도 자체적으로 한 단계 fail-fast한다: `services/<name>/`에 `workflow.py` 자체가 없으면 `ServiceConsistencyError`로 명확히 실패하고, `workflow.py`는 있지만 그 안에서 다른 import가 실패한 "진짜 버그"는 오진하지 않고 원래 예외 그대로 전파한다(`ModuleNotFoundError.name`으로 구분).

### `orchestrator.py` — 라우팅
`Orchestrator.handle()`이 요청 하나의 진입점이다.
1. `tracer.start_trace("orchestrator")`로 Trace 시작
2. `PromptStore.common_prompt()` + `registry.tools()`를 카탈로그로 넘겨 `AgentRunner.choose_tool()` 호출 — 실제 라우팅 판단은 SDK 몫이며, 엔진은 `AgentRunner` Protocol에만 의존해 SDK에 비커플링
3. 선택된 tool을 `GuardrailChain.run()`으로 감싸 실행, 그 안에서 `tracer.span()`으로 Tool Span 기록

`main.py`의 `build_orchestrator()`는 `OPENAI_API_KEY`가 있으면 `OpenAIRunner`(실제 모델에 tool 카탈로그를 주고 name 하나만 고르게 함)를, 없으면 `FirstMatchRunner`(요청 문자열에 tool 이름이 포함되는지만 검사하는 오프라인 스텁)를 `agent_runner`로 선택한다. 두 클래스 모두 `AgentRunner` Protocol만 구현하므로 `orchestrator.py` 자체는 어느 쪽을 쓰든 안 바뀐다 — 이 스위칭도 `main.py`(조립 지점)의 책임이다.

### `harness/guardrail.py` — 개입 권한을 가진 검증
`GuardrailChain.run()`은 `registry.guardrail_for(tool_name)`으로 선언을 읽어 input → 호출 → output 순으로 검증한다. **엔진 코드 어디에도 tool 이름이 하드코딩되지 않는다** — `if tool_name == ...` 분기가 생기면 안티패턴이라는 설계 원칙(`ai_framework_2.md`)이 그대로 구현된 지점. `output_schema`에 `{"choices": [...]}` 형태를 넣으면 enum 제약으로 동작한다 (`subscription_status.workflow`의 `status`/`status_confidence` 필드 참고). 스키마 없음/통과는 `DEBUG`로, 위반은 예외를 던지기 직전 `ERROR`로 로깅한다.

### `harness/logging_setup.py` — 로그 레벨 설정
`configure_logging()`이 `LOG_LEVEL` 환경변수(기본 `INFO`)로 표준 `logging`을 한 번 설정한다. `main.py`가 `load_dotenv()` 직후, `discover_services()`보다 먼저 호출해야 discovery/validate 단계 로그도 같은 레벨로 잡힌다(`main.py` 참고). `get_logger(name)`은 전부 `agent_loop.<name>` 네임스페이스 아래 로거를 돌려주므로, 특정 모듈만 레벨을 따로 올리고 싶으면(예: `logging.getLogger("agent_loop.adapter").setLevel(logging.DEBUG)`) 표준 `logging` API를 그대로 쓰면 된다.

### `harness/tracing.py` — 관측이자 로깅의 뼈대
`Tracer`는 스택 기반으로 `Span`을 중첩시킨다. `start_trace`가 루트(kind="orchestrator")를 열고, `span()` 호출마다 현재 스택 최상단의 자식으로 붙는다. Tool이 늘어나도 상위 구조(Trace → Orchestrator Span → Tool Span*)는 그대로 유지된다는 설계가 스택 구현으로 자연히 보장됨.

각 `start_trace`/`span` 진입·종료 시점에 `INFO` 레벨로 로그를 찍고, 중첩 깊이(`len(self._stack)`)만큼 들여쓰기를 붙인다 — `Trace`/`Span` 객체(`tracer.current_trace`)는 원래도 만들어지고 있었지만 그걸 읽어서 보여주는 코드가 어디에도 없었던 게 실제 gap이었다(§ 로깅 절 참고). `workflow/state_machine.py`가 각 `@workflow_step` 실행을 `tracer.span(kind="step")`으로 감싸면서, tool 단위보다 한 단계 더 세밀한 "이 tool 안에서 지금 어느 스텝을 도는지"까지 같은 메커니즘으로 로그에 잡힌다.

`span()`은 활성 trace가 없는 상태(예: 오케스트레이터를 거치지 않고 `weather(location=...)`처럼 tool 함수를 직접 호출·테스트하는 경우)에도 안전하게 동작한다 — 스택이 비어 있으면 이름 없는 암묵적 루트를 하나 열어서 쓰고, 빠져나갈 때 다시 비운다. `StateMachine.run()`이 항상 `span()`을 쓰게 되면서 이 케이스를 처음부터 고려해야 했다.

### `prompts/store.py` — 프롬프트 계층
`common_prompt()` (공통) + `tool_prompt()` (도메인별, `services/<name>/prompts/<tool_name>.md`) + 선택적 few-shot을 `compose()`가 `---`로 이어붙인다. 오케스트레이터는 `common_prompt()`만 써서 `OpenAIRunner.choose_tool()`에 넘기고, 개별 tool 실행 단계는 `compose()`로 조립한 프롬프트를 `framework.llm.openai_client.complete()`에 넘긴다 — `subscription_status.workflow`의 `manual_review`가 이 배선의 살아있는 예시(`tool_dir=services/subscription_status/prompts`, `tool_name="manual_review"`). `complete()`는 모델/프롬프트 길이·응답 미리보기를 `INFO`로, system/user 프롬프트 원문 전체를 `DEBUG`로 로깅한다 — 프롬프트에 개인정보가 실릴 수 있는 서비스라면 운영 환경에서 `LOG_LEVEL=DEBUG`를 켜지 않도록 주의.

### `semantic/mapping.py` — 레거시 의미 정규화
`SemanticMapping.normalize(raw_value)`가 `mapping.json`을 찾아 `MappedValue(raw, value, confidence)`를 반환. 매핑에 없으면 `UnmappedValueError`로 즉시 실패 (fail-fast). `MappedValue.require_confirmed()`는 `confidence != "confirmed"`면 예외를 던져, `inferred` 값이 판단 분기에 잘못 쓰이는 걸 타입 수준에서 막는다.

### `adapters/base.py` — 양면 어댑터
`BaseAdapter`는 `call()`(프로토콜적 면 — 레거시 스펙에 종속)과 `normalize()`(의미론적 면 — `SemanticMapping`에 종속)를 분리해 각각 독립적으로 오버라이드하게 강제한다. `execute()`는 `normalize(call())`로 둘을 합성만 한다 — 이 한 곳에서 `call()`/`normalize()` 각각의 입출력을 `DEBUG`로 로깅하므로, 어떤 어댑터를 새로 만들어도(레거시 원시값 로깅을) 따로 구현할 필요가 없다.

### `workflow/state_machine.py` — 고정 파이프라인 실행기
`StateMachine.run()`은 `entry`부터 시작해 `WorkflowStepSpec.func(context)`가 반환한 outcome 문자열을 `next` dict에서 찾아 다음 단계로 이동한다. `next_step == current`(자기 자신으로 순환)면 `retries` 카운터를 올리고 `max_retries` 초과 시 `MaxRetriesExceeded`. `next`가 없거나 `TERMINAL("DONE")`이면 종료. 판단(judged) 노드도 그냥 하나의 `workflow_step`으로 등록되며(`@judged` + `@workflow_step` 이중 데코레이터), state machine 입장에서는 outcome이 code-driven이든 model-driven이든 구분하지 않는다 — bounded choices라는 계약만 `@judged`가 보장한다. 각 스텝 실행을 `tracer.span(name=현재_step, kind="step")`으로 감싸고, 진입("state machine start")·전이("step 'X' -> outcome=... -> next='Y'")·종료를 `INFO`로 로깅한다.

### 서비스를 조합하는 서비스 — `services/subscription_weather_flow/workflow.py`
`common/orchestrator.md`가 "하나의 요청이 여러 tool을 필요로 하면 ... 고정 서브 workflow(capability)로 등록되어 있는지 먼저 확인하라"고 지시하는 지점의 구현체. `Orchestrator.handle()`은 요청당 tool 하나만 고르므로(§`orchestrator.py`), 두 tool을 함께 써야 하는 요청은 에이전트가 즉석에서 두 번 호출하게 두지 않고 이렇게 **상위 capability 하나로 미리 고정**한다.

- `registry`에 등록되는 다른 서비스와 달리 `adapter.py`/`mapping.json`이 없다 — 자신만의 레거시/외부 연동이 없고, 이미 등록된 `subscription_status()`/`weather()` **tool 함수를 그대로 호출**해서 결과를 합성만 한다.
- `query_subscription` → `query_weather` 두 `@workflow_step`이 `next`로 고정 연결되며, `query_subscription`이 채운 `subscription_result["region"]`을 `query_weather`가 그대로 `weather(location=...)`의 입력으로 넘긴다 — 이게 두 서비스 사이의 실제 데이터 의존관계다.
- 내부에서 `subscription_status()`/`weather()`를 직접 호출하는 건 `GuardrailChain.run()`을 거치지 않는다는 뜻이다 — 즉 두 tool 각각의 output guardrail은 검증되지 않고, 오직 `subscription_weather_flow` 자신의 guardrail(`{"subscription": Any, "weather": Any}`)만 오케스트레이터를 통해 검증된다. `subscription_status.workflow`가 내부적으로 `SubscriptionStatusAdapter`를 직접 호출하고 오케스트레이터의 개입 없이 결과를 합성하는 것과 동일한 "capability가 capability를 감싼다" 패턴이다.

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
                   └─ (manual_review 진입 시) prompt_store.compose("manual_review", ...) → complete()로 OpenAI 호출
                        → @judged(choices=("자동승인","수동검토"))가 반환값을 bounded set으로 강제 (밖이면 ValueError)
              → context["last_result"] 반환
           └─ output 검증: status/status_confidence가 선언된 enum 안에 있는지 확인
     └─ tracer: Trace 안에 subscription_status Tool Span 기록하고 종료
```

나머지 두 tool은 같은 골격(라우팅 → guardrail → tool 함수 → StateMachine)을 훨씬 짧게 탄다.

```
orchestrator.handle("weather 조회해줘", location="Seoul")
  → weather(location="Seoul")   [services/weather/workflow.py]
     └─ StateMachine(entry="fetch_weather").run(context)  — 분기/재시도 없음, 단일 스텝
        └─ fetch_weather: WeatherAdapter().execute(location="Seoul")
             ├─ call()      → 지오코딩(도시명→좌표) + Open-Meteo 현재 날씨 실 호출
             └─ normalize() → mapping.json(WMO code) 조회 → {"condition": "대체로 맑음", ...}

orchestrator.handle("subscription_weather_flow 조회해줘", applicant_id="A123")
  → subscription_weather_flow(applicant_id="A123")   [services/subscription_weather_flow/workflow.py]
     └─ StateMachine(entry="query_subscription").run(context)
        ├─ query_subscription: subscription_status(applicant_id="A123") 직접 호출 (guardrail 안 거침)
        │    → context["subscription_result"] = {..., "region": "Seoul"}
        └─ query_weather: weather(location=subscription_result["region"]) 직접 호출
             → context["weather_result"] = {...}
     → {"subscription": ..., "weather": ...} 반환, 이 반환값만 오케스트레이터의 guardrail 검증 대상
```

## 로깅

`LOG_LEVEL` 환경변수(`.env`, 기본 `INFO`)로 전체 로깅 레벨을 정한다. `main.py`가 기동 직후 `configure_logging()`을 한 번 호출해 표준 `logging`을 설정하므로, 이후 `discover_services()`부터 `orchestrator.handle()`까지 전 과정이 같은 스트림에 시간순으로 찍힌다 — 요청 하나가 오케스트레이터 라우팅부터 state machine의 스텝 전이, 어댑터 호출, OpenAI 판단까지 어떻게 흘렀는지 콘솔 출력 하나로 전부 볼 수 있다(§ 위 "요청 하나의 전체 흐름"과 대응).

- **INFO** (기본값): "지금 어떤 단계를 지나는지"만 보여주는 요약 라인 — trace/span 시작·종료(들여쓰기로 중첩 깊이 표현), state machine 스텝 전이, guardrail 통과 여부, judged 노드의 최종 선택, OpenAI 호출의 모델명·길이·응답 미리보기.
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

`subscription_weather_flow`처럼 tool이 다른 tool을 직접 호출하는 경우, 안쪽 `subscription_status`/`weather`가 각자 여는 `state machine start`/`span`이 바깥쪽 `query_subscription`/`query_weather` 스텝 span 밑에 한 단계 더 들여써져서 나온다 — 합성 관계가 로그 들여쓰기 그대로 드러난다.

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
| 결정론적 분기/순환 | `registry.decorators.workflow_step(next=...)` + `workflow.state_machine.StateMachine` |
| Judged branch (bounded choices) | `registry.decorators.judged(choices=...)` |
| confirmed/inferred 매핑 관리 | `semantic.mapping.SemanticMapping` / `MappedValue` |
| 미확인 값 fail-fast | `semantic.mapping.UnmappedValueError` |
| 도메인 흐름 전체를 하나의 capability로 등록 | `services/subscription_status/workflow.py`의 최상위 `@tool subscription_status` (내부 state machine을 감싸 단일 tool로 노출) |
| 외부 실 API를 가진 서비스 (프로토콜적 면 = 실제 HTTP 호출, 인증 불필요) | `services/weather/adapter.WeatherAdapter.call()` (Open-Meteo 지오코딩 + 현재 날씨) |
| judged 노드의 실제 모델 판단 배선 | `services/subscription_status/workflow.py`의 `manual_review()` — `PromptStore.compose()` + `framework.llm.openai_client.complete()` |
| 여러 tool을 고정 서브 workflow로 미리 묶기 (에이전트가 즉석에서 여러 tool을 잇지 않게) | `services/subscription_weather_flow/workflow.py`의 최상위 `@tool subscription_weather_flow` — `subscription_status()` → `weather()` 순차 호출, `region` 필드로 데이터 연결 |
| 서비스 auto-discovery + 기동 시점 일관성 검사 | `registry.discovery.discover_services()` + `registry.decorators.ToolRegistry.validate()` |
| 레벨 조절 가능한 단계별 로깅 | `harness.logging_setup.configure_logging()`(`LOG_LEVEL`) + `harness.tracing.Tracer`(trace/span을 로그로도 출력) |

## 신규 서비스 추가 시 손대는 파일 (엔진 불변성 체크)

두 카테고리가 있다 — 어느 쪽이든 `framework/`도 `main.py`도 손대지 않는 게 목표이고, `discover_services()`(auto-discovery) 덕분에 실제로 그렇게 됐다. `services/<name>/`에 파일을 놓기만 하면 다음 실행 때 `registry.validate()`가 등록/참조 무결성까지 자동으로 확인해준다.

**레거시/외부 어댑터 서비스** (`subscription_status`, `weather`) — `guides/legacy_adapter_guide.md` 체크리스트 기준, 아래 4개 파일만 새로 만든다.
- `services/<name>/adapter.py` (`BaseAdapter` 상속)
- `services/<name>/mapping.json`
- `services/<name>/workflow.py` (`@workflow_step`/`@judged`/`@tool`)
- `services/<name>/prompts/<tool_name>.md`

**조합 서비스** (`subscription_weather_flow`) — 자신만의 외부 연동이 없으므로 `adapter.py`/`mapping.json`은 만들지 않는다.
- `services/<name>/workflow.py` (이미 등록된 다른 tool 함수를 직접 호출해 `@workflow_step`으로 연결 + 최상위 `@tool`)
- `services/<name>/prompts/<tool_name>.md`

두 카테고리 모두 `services/<name>/workflow.py`라는 파일명은 고정이다 — `discover_services()`가 정확히 이 이름을 import하기 때문(§ `registry/discovery.py`).

## 현재 스캐폴드의 한계 (다음 작업 후보)

- `SubscriptionStatusAdapter.call()`은 여전히 실제 레거시 연동 전 스텁(고정 응답, `region`도 항상 `"Seoul"`로 고정) — 청약 시스템 실 연동 시 교체 필요. 실제 레거시가 지역 정보를 안 주면 `subscription_weather_flow`의 데이터 연결 지점 자체를 다시 설계해야 함.
- `WeatherAdapter`는 Open-Meteo(무료, 인증 불필요)를 쓰므로 `weather` 서비스는 `.env`에 키를 넣지 않아도 바로 호출 가능 — 처음에 RapidAPI "yahoo-weather5"(키 필요)로 만들었다가 인증 없는 샘플 테스트에 맞춰 교체함.
- `requirements.txt`(openai/python-dotenv/requests)가 아직 이 환경에 설치되지 않음 — `pip install -r requirements.txt` 필요.
- `OpenAIRunner`/`manual_review`는 `OPENAI_MODEL` 미지정 시 `gpt-4o-mini`로 기본 동작 — 실제 사용 가능한 모델명으로 `.env`에서 확정해야 함.
- `main.py`의 `FirstMatchRunner`는 이름이 긴 tool부터 substring 매칭하도록 고쳤지만(한 tool 이름이 다른 tool 이름을 포함하는 경우 대비, 예: `weather` ⊂ `subscription_weather_flow`), 여전히 순수 문자열 포함 검사라 실제 자연어 요청 라우팅에는 쓸 수 없다 — 오프라인 샘플 테스트 전용 스텁이라는 원래 성격은 그대로.
- `ToolRegistry.validate()`는 registry 내부 참조 무결성(step/judged/guardrail 연결)만 본다 — "adapter.py가 BaseAdapter를 상속했는가", "mapping.json이 실제로 존재하는가" 같은 파일 시스템/클래스 계층 검사나, "새 tool description이 기존 tool과 의미가 안 겹치는가" 같은 의미적 검사(`guides/legacy_adapter_guide.md` 체크리스트 항목)는 하지 않는다 — 이런 건 코드로 자동 판별하기 어려워 사람 리뷰 영역으로 남겨둠.
