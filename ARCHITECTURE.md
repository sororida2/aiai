# Agent Loop 프레임워크 — 코드 구성

`README.md`(왜 이 구조가 필요한가)와 `ai_framework_2.md`(설계 철학)의 논의가 실제로 어떤 파일·클래스로 구현됐는지 매핑한 문서다. `services/` 아래 네 서비스가 각기 다른 절의 살아있는 예시다 — `subscription_status`(레거시 어댑터 + human-in-the-loop 판단 노드), `weather`(인증 없는 외부 실 API 어댑터), `subscription_weather_flow`(서비스를 조합하는 서비스), `applicant_list`(입력 없는 목록 조회 + 표 형식 렌더링). `main.py`가 실행 진입점이고, `examples/human_action_demo.py`가 human-in-the-loop 일시정지/재개를 터미널에서 직접 확인해보는 실행 가능한 예시다.

## 디렉토리 구조

```
framework/                  ← 엔진. 새 서비스를 추가해도 손대지 않는 것이 목표.
├── registry/decorators.py  ← @tool·@workflow_step·@judged·@human_action·@guardrail 데코레이터 + ToolRegistry(+ validate())
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
└── workflow/state_machine.py← 고정 파이프라인 실행기 (StateMachine) + AwaitingHumanAction(사람의 답 대기 신호)

services/                   ← 설정. 새 서비스 추가 시 여기만 늘어난다 (main.py도 안 건드림 — auto-discovery).
├── subscription_status/
│   ├── adapter.py           ← SubscriptionStatusAdapter(BaseAdapter)
│   ├── mapping.json          ← 상태코드 confirmed/inferred 매핑 테이블
│   ├── workflow.py           ← @workflow_step 파이프라인 + @human_action 노드(manual_review, 사람의
│   │                            action 선택을 기다렸다가 이어서 실행) + 최상위 @tool
│   └── prompts/subscription_status.md  ← 이 tool 전용 프롬프트
├── weather/                  ← 두 번째 살아있는 예시 (외부 실 API 연동 케이스, 인증 불필요)
│   ├── adapter.py           ← WeatherAdapter(BaseAdapter), Open-Meteo 지오코딩 + 현재 날씨 호출
│   ├── mapping.json          ← WMO weather code(공식 문서화 표) → 한국어 정규화 테이블
│   ├── workflow.py           ← 단일 스텝 파이프라인(fetch_weather) + 최상위 @tool
│   └── prompts/weather.md    ← 이 tool 전용 프롬프트
├── subscription_weather_flow/← 세 번째 예시: 어댑터 서비스가 아니라 "서비스를 조합하는 서비스"
│   ├── workflow.py           ← adapter.py/mapping.json 없음 — subscription_status()/weather() tool 함수를
│   │                            그대로 호출해 조합하는 @workflow_step 2단계 + 최상위 @tool
│   └── prompts/subscription_weather_flow.md
└── applicant_list/            ← 네 번째 예시: 입력 없는 tool + 표 형식 렌더링
    ├── adapter.py           ← ApplicantListAdapter(BaseAdapter), 20명 스텁 목록 + subscription_status와
    │                            같은 5단계 상태 체계(별도 mapping.json, 값은 동일)로 정규화
    ├── mapping.json
    ├── workflow.py           ← 단일 스텝(fetch_applicants) + 최상위 @tool이 마크다운 표(`table`)까지 조립
    └── prompts/applicant_list.md

main.py                     ← 조립 지점 (discover_services + registry.validate(), build_orchestrator,
                                OpenAIRunner/FirstMatchRunner) + 실행 예시. 서비스 추가 시 더 이상 손대지 않아도 됨.
examples/human_action_demo.py ← human-in-the-loop 일시정지/재개를 터미널에서 직접 확인하는 실행 가능한 예시
                                (main.py의 build_orchestrator()를 그대로 재사용)
guides/legacy_adapter_guide.md ← 신규 서비스 추가 가이드
.env / .env.example         ← OPENAI_API_KEY, OPENAI_MODEL, LOG_LEVEL (.env는 커밋 안 함; weather는 키 불필요)
```

## 컴포넌트별 역할

### `registry/decorators.py` — 등록 규약의 단일 지점
전역 `registry = ToolRegistry()` 하나에 다섯 종류 스펙이 모인다.
- `@tool(name, description)` → `ToolSpec` (오케스트레이터가 유일하게 커플링되는 표면)
- `@workflow_step(order, next=..., max_retries=...)` → `WorkflowStepSpec` (결정론적 분기/순환을 `next` dict로 고정) + 실행 시 반환값이 `next`의 키 밖이면 즉시 `ValueError` (`@judged`/`@human_action`과 같은 방식의 즉시 검증)
- `@judged(choices=...)` → `JudgedSpec` + 실행 시 `choices` 밖 값이면 즉시 `ValueError` (bounded 강제, 판단 주체는 모델)
- `@human_action(choices=..., payload_schemas=...)` → `HumanActionSpec` + 실행 시 action이 `choices` 밖이거나 payload가 선언된 스키마를 어기면 즉시 `ValueError` (bounded 강제, 판단 주체는 사람) — § 아래 "human-in-the-loop" 절
- `@guardrail(input_schema=..., output_schema=...)` → `GuardrailSpec`

모듈을 import하는 순간 데코레이터가 실행되며 등록된다. 예전에는 `main.py`에 서비스마다 `from services.<name> import workflow as _`를 나열해 이 import를 직접 트리거했지만, 지금은 `framework/registry/discovery.py`의 `discover_services()`가 `services/` 아래를 스캔해서 대신 트리거한다 (§ 아래 `registry/discovery.py` 절).

**`@workflow_step` vs `@judged`/`@human_action` — 헷갈리기 쉬운 지점.** 기준은 단 하나, "이 스텝의 결과값이 코드 로직으로 나오는가, 판단(모델 또는 사람)으로 나오는가"뿐이다.

| | `@workflow_step` | `@judged` | `@human_action` |
|---|---|---|---|
| 필수 여부 | 모든 스텝에 필수 — 없으면 state machine이 이 함수를 아예 모른다 | 선택 — "이 스텝은 모델이 결정한다"는 표시일 때만 추가로 얹는다 | 선택 — "이 스텝은 사람이 결정한다"는 표시일 때만 추가로 얹는다 |
| 하는 일 | `next={...}`로 다음 스텝(라우팅) 결정 | 반환값이 `choices` 밖이면 즉시 차단 (라우팅은 모름) | 반환값의 `action`이 `choices` 밖이거나 그 action의 payload가 스키마를 어기면 즉시 차단 |
| 등록 위치 | `registry._workflow_steps` | `registry._judged` (별도) | `registry._human_actions` (별도) |
| 왜 필요한가 | 파이프라인 그래프 자체를 코드로 고정하기 위해 | 모델 출력은 예측 불가능하므로 bounded 안전망이 필요해서 | 사람의 선택도 bounded해야 감사 가능하고, payload가 붙는 action은 그 구조까지 검증해야 해서 |

코드가 직접 결정하는 스텝(`fetch_status`)은 `@workflow_step` 단독, 판단이 필요한 스텝은 `@workflow_step` + (`@judged` 또는 `@human_action`) 이중으로 붙는다 — 판단 데코레이터가 라우팅을 대신하는 게 아니라, `@workflow_step`의 라우팅 계약 위에 "이 값은 모델/사람이 만든 것"이라는 제약을 얹는 것뿐이다. `registry.validate()`가 "judged/human_action인데 workflow_step이 없는" 반쪽짜리 선언을 기동 시점에 바로 잡아내는 것도 이 관계(둘 다 workflow_step에 종속) 때문이다. 지금 `services/` 전체에서 실제로 쓰이는 건 `@human_action`(`manual_review`)뿐이고 `@judged`는 코드로는 남아있지만 등록된 서비스가 하나도 없다 — § 아래 "현재 스캐폴드의 한계" 참고.

### `registry/discovery.py` + `ToolRegistry.validate()` — auto-discovery와 일관성 검사
`main.py`가 서비스를 일일이 알 필요가 없게 만드는 지점. Python은 모듈을 실제로 import하기 전까진 그 안의 데코레이터를 실행하지 않으므로, 등록이 일어나려면 누군가는 각 `services/<name>/workflow.py`를 import해야 한다 — `discover_services(services)`가 `pkgutil.iter_modules(services.__path__)`로 하위 패키지를 전부 찾아 그 `workflow.py`를 대신 import해준다.

이렇게 등록을 "자동"으로 만들면 반쯤 구현된 서비스 폴더가 조용히 무시되거나(예: `@tool`을 하나도 등록 안 함), 다른 모듈이 등록한 step 이름을 가리키다 오타난 `next` 참조가 `StateMachine.run()` 시점(즉 실제 요청이 들어올 때)까지 숨어있을 위험이 커진다. 그래서 `main.py`는 `discover_services()` 직후 `registry.validate()`를 호출해 기동 시점에 바로 fail-fast한다. `ToolRegistry.validate()`가 검사하는 것:
- 등록된 tool이 하나도 없으면 즉시 실패 (서비스 폴더는 있는데 아무것도 안 잡힌 상태)
- 모든 `workflow_step.next`의 target이 `"DONE"`이거나 등록된 다른 step 이름이어야 함 (오타 탐지)
- 모든 `@judged` 노드는 반드시 같은 이름으로 `@workflow_step`에도 등록돼 있어야 함 (이중 데코레이터 누락 탐지)
- 모든 `@human_action` 노드도 같은 이유로 `@workflow_step`에 등록돼 있어야 하고, `payload_schemas`에 선언된 action 키는 전부 `choices` 안에 있어야 함 (payload_schemas 쪽 오탈자 탐지 — choices에 없는 action에 스키마를 선언해봐야 절대 검증되지 않는 죽은 선언이 되므로)
- 모든 `@guardrail`은 실제로 그 tool의 함수 자체에 등록돼야 함 — `@guardrail`을 `@tool`보다 위(나중에 적용되게)에 잘못 쓰거나 함수 이름이 tool name과 다르면, `guardrail()` 데코레이터가 `func.__name__`으로 fallback하면서 엉뚱한 키에 등록되는 조용한 버그가 생기는데 이걸 잡아낸다

`discover_services()`도 자체적으로 한 단계 fail-fast한다: `services/<name>/`에 `workflow.py` 자체가 없으면 `ServiceConsistencyError`로 명확히 실패하고, `workflow.py`는 있지만 그 안에서 다른 import가 실패한 "진짜 버그"는 오진하지 않고 원래 예외 그대로 전파한다(`ModuleNotFoundError.name`으로 구분).

### `orchestrator.py` — 라우팅 + 일시정지/재개
`Orchestrator.handle()`이 요청 하나의 진입점이다.
1. `tracer.start_trace("orchestrator")`로 Trace 시작
2. `PromptStore.common_prompt()` + `registry.tools()`를 카탈로그로 넘겨 `AgentRunner.choose_tool()` 호출 — 실제 라우팅 판단은 SDK 몫이며, 엔진은 `AgentRunner` Protocol에만 의존해 SDK에 비커플링
3. 선택된 tool을 `GuardrailChain.run()`으로 감싸 실행, 그 안에서 `tracer.span()`으로 Tool Span 기록

`main.py`의 `build_orchestrator()`는 `OPENAI_API_KEY`가 있으면 `OpenAIRunner`(실제 모델에 tool 카탈로그를 주고 name 하나만 고르게 함)를, 없으면 `FirstMatchRunner`(요청 문자열에 tool 이름이 포함되는지만 검사하는 오프라인 스텁)를 `agent_runner`로 선택한다. 두 클래스 모두 `AgentRunner` Protocol만 구현하므로 `orchestrator.py` 자체는 어느 쪽을 쓰든 안 바뀐다 — 이 스위칭도 `main.py`(조립 지점)의 책임이다.

**일시정지/재개.** `spec.func(**kwargs)` 실행 중 내부의 `@human_action` 노드가 `AwaitingHumanAction`을 던지면(§ 아래 "human-in-the-loop" 절), `handle()`은 이 예외를 그대로 죽게 두지 않고 `{"status": "awaiting_human_action", "tool": ..., "step": ..., "choices": [...], "context": ...}`를 정상 반환값으로 돌려준다 — 대화가 여기서 사람의 답을 기다리며 멈춘다는 뜻이다. 호출자가 사람의 답을 받으면 `Orchestrator.resume(tool_name, context, step, action)`을 불러 멈췄던 `step`부터 이어서 실행한다: `context["human_action"] = action`을 채운 뒤 `StateMachine(registry=self.registry, entry=step).run(context)`를 다시 돌린다 — `registry._workflow_steps`가 tool 구분 없이 하나의 전역 이름공간이라, entry만 바꿔서 아무 지점부터나 재진입할 수 있다는 점을 이용한다. `resume()`도 같은 `GuardrailChain`을 거치므로 최종 완료 시 output guardrail은 그대로 적용된다.

### `harness/schema.py` — 스키마 검증 원시 요소
`OptionalField`/`optional()`/`SchemaViolation`/`validate_schema()`가 여기 산다. 원래 `harness/guardrail.py` 안에 있던 걸, `@human_action`의 payload 검증(§ 아래 "human-in-the-loop" 절)이 똑같은 재귀 검증 로직을 필요로 하면서 공유 모듈로 뺐다 — guardrail도 human_action도 이 모듈에만 의존하고 서로는 모른다. `validate_schema(value, schema, path="")`가 스키마 값의 형태로 세 가지를 구분한다.
- `Any` → 필드 존재 여부만 확인
- `{"choices": [...]}` → enum 제약
- `{"choices": ...}`가 없는 순수 dict → **중첩 스키마**로 간주해 재귀 검증. 실패 시 `path`가 `subscription.status`처럼 점(dot) 경로로 어느 중첩 레벨에서 깨졌는지 보여준다.

기본적으로 스키마에 선언된 키는 전부 필수지만, 조건부 경로에만 채워지는 필드는 `optional(schema)`(`OptionalField` wrapper)로 감싸 선언한다 — 필드가 없으면 통과, 있으면 `inner` 규칙으로 그대로 검증한다. 위반 시 `SchemaViolation(detail)`을 던지며, 호출자(`guardrail.py`/`registry.decorators.human_action`)가 각자의 맥락(`stage`/`tool_name` 또는 `human_action 이름`/`action`)을 붙여 자기 예외 타입(`GuardrailViolation`/`ValueError`)으로 다시 던진다.

### `harness/guardrail.py` — 개입 권한을 가진 검증
`GuardrailChain.run()`은 `registry.guardrail_for(tool_name)`으로 선언을 읽어 input → 호출 → output 순으로 검증한다. **엔진 코드 어디에도 tool 이름이 하드코딩되지 않는다** — `if tool_name == ...` 분기가 생기면 안티패턴이라는 설계 원칙(`ai_framework_2.md`)이 그대로 구현된 지점. 실제 검증은 `harness/schema.py`의 `validate_schema()`에 위임하고, `_validate()`는 그 결과에 `stage`(input/output)·`tool_name`을 붙여 `GuardrailViolation`으로 감싸고 로깅만 담당한다(`subscription_status.workflow`의 `status`/`status_confidence`/`manual_review_decision` 필드, `subscription_weather_flow`의 중첩 검증이 실제 예시). 스키마 없음/통과는 `DEBUG`로, 위반은 예외를 던지기 직전 `ERROR`로 로깅한다.

### `harness/logging_setup.py` — 로그 레벨 설정
`configure_logging()`이 `LOG_LEVEL` 환경변수(기본 `INFO`)로 표준 `logging`을 한 번 설정한다. `main.py`가 `load_dotenv()` 직후, `discover_services()`보다 먼저 호출해야 discovery/validate 단계 로그도 같은 레벨로 잡힌다(`main.py` 참고). `get_logger(name)`은 전부 `agent_loop.<name>` 네임스페이스 아래 로거를 돌려주므로, 특정 모듈만 레벨을 따로 올리고 싶으면(예: `logging.getLogger("agent_loop.adapter").setLevel(logging.DEBUG)`) 표준 `logging` API를 그대로 쓰면 된다.

### `harness/tracing.py` — 관측이자 로깅의 뼈대
`Tracer`는 스택 기반으로 `Span`을 중첩시킨다. `start_trace`가 루트(kind="orchestrator")를 열고, `span()` 호출마다 현재 스택 최상단의 자식으로 붙는다. Tool이 늘어나도 상위 구조(Trace → Orchestrator Span → Tool Span*)는 그대로 유지된다는 설계가 스택 구현으로 자연히 보장됨.

각 `start_trace`/`span` 진입·종료 시점에 `INFO` 레벨로 로그를 찍고, 중첩 깊이(`len(self._stack)`)만큼 들여쓰기를 붙인다 — `Trace`/`Span` 객체(`tracer.current_trace`)는 원래도 만들어지고 있었지만 그걸 읽어서 보여주는 코드가 어디에도 없었던 게 실제 gap이었다(§ 로깅 절 참고). `workflow/state_machine.py`가 각 `@workflow_step` 실행을 `tracer.span(kind="step")`으로 감싸면서, tool 단위보다 한 단계 더 세밀한 "이 tool 안에서 지금 어느 스텝을 도는지"까지 같은 메커니즘으로 로그에 잡힌다.

`span()`은 활성 trace가 없는 상태(예: 오케스트레이터를 거치지 않고 `weather(location=...)`처럼 tool 함수를 직접 호출·테스트하는 경우)에도 안전하게 동작한다 — 스택이 비어 있으면 이름 없는 암묵적 루트를 하나 열어서 쓰고, 빠져나갈 때 다시 비운다. `StateMachine.run()`이 항상 `span()`을 쓰게 되면서 이 케이스를 처음부터 고려해야 했다.

### `prompts/store.py` — 프롬프트 계층
`common_prompt()` (공통) + `tool_prompt()` (도메인별, `services/<name>/prompts/<tool_name>.md`) + 선택적 few-shot을 `compose()`가 `---`로 이어붙인다. 오케스트레이터는 `common_prompt()`만 써서 `OpenAIRunner.choose_tool()`에 넘긴다. `compose()` + `framework.llm.openai_client.complete()` 조합(도메인별 judged 노드가 실제로 모델을 호출하는 배선)은 원래 `manual_review`가 살아있는 예시였는데, `manual_review`가 사람 판단(`@human_action`)으로 바뀌면서 지금은 이 조합을 실제로 쓰는 서비스가 없다 — 당시 전용이던 `services/subscription_status/prompts/manual_review.md`는 완전히 죽은 파일이라 삭제했고, `compose()`/`complete()` 자체는 재사용 가능한 프레임워크 능력이라 남겨뒀다 (§ 아래 "현재 스캐폴드의 한계" 참고). `complete()` 자체는 모델/프롬프트 길이·응답 미리보기를 `INFO`로, system/user 프롬프트 원문 전체를 `DEBUG`로 로깅한다 — 프롬프트에 개인정보가 실릴 수 있는 서비스라면 운영 환경에서 `LOG_LEVEL=DEBUG`를 켜지 않도록 주의.

### `semantic/mapping.py` — 레거시 의미 정규화
`SemanticMapping.normalize(raw_value)`가 `mapping.json`을 찾아 `MappedValue(raw, value, confidence)`를 반환. 매핑에 없으면 `UnmappedValueError`로 즉시 실패 (fail-fast). `MappedValue.require_confirmed()`는 `confidence != "confirmed"`면 예외를 던져, `inferred` 값이 판단 분기에 잘못 쓰이는 걸 타입 수준에서 막는다.

### `adapters/base.py` — 양면 어댑터
`BaseAdapter`는 `call()`(프로토콜적 면 — 레거시 스펙에 종속)과 `normalize()`(의미론적 면 — `SemanticMapping`에 종속)를 분리해 각각 독립적으로 오버라이드하게 강제한다. `execute()`는 `normalize(call())`로 둘을 합성만 한다 — 이 한 곳에서 `call()`/`normalize()` 각각의 입출력을 `DEBUG`로 로깅하므로, 어떤 어댑터를 새로 만들어도(레거시 원시값 로깅을) 따로 구현할 필요가 없다.

### `workflow/state_machine.py` — 고정 파이프라인 실행기
`StateMachine.run()`은 `entry`부터 시작해 `WorkflowStepSpec.func(context)`가 반환한 outcome 문자열을 `next` dict에서 찾아 다음 단계로 이동한다. `next_step == current`(자기 자신으로 순환)면 `retries` 카운터를 올리고 `max_retries` 초과 시 `MaxRetriesExceeded`. `next`가 없거나 `TERMINAL("DONE")`이면 종료. 판단 노드도 그냥 하나의 `workflow_step`으로 등록되며(`@judged`/`@human_action` + `@workflow_step` 이중 데코레이터), state machine 입장에서는 outcome이 code-driven이든 model-driven이든 human-driven이든 구분하지 않는다 — bounded choices라는 계약만 `@judged`/`@human_action`이 보장한다. 각 스텝 실행을 `tracer.span(name=현재_step, kind="step")`으로 감싸고, 진입("state machine start")·전이("step 'X' -> outcome=... -> next='Y'")·종료를 `INFO`로 로깅한다.

`outcome`이 `next`의 키 밖인지 확인하는 검증은 여기 없다 — `@workflow_step`의 wrapper(`registry/decorators.py`)가 함수 반환 즉시 검사해서 `ValueError`를 던지므로, `run()`이 `spec.next[outcome]`을 인덱싱하는 시점엔 `outcome`이 항상 유효한 키임이 보장된다(`@judged`/`@human_action`이 각자의 bounded 값 밖을 함수 반환 즉시 막는 것과 동일한 위치·방식). 이 즉시 검증 덕분에 `services/subscription_status/workflow.py`의 실제 버그(`mapping.json`의 `"10"→"접수완료"`가 `fetch_status`의 `next`에는 빠져 있던 것)를 테스트 중 바로 잡아낼 수 있었다.

**`AwaitingHumanAction` — 일시정지.** `spec.func(context)` 호출이 이 예외를 던지면(§ 아래 "human-in-the-loop" 절), `run()`은 이를 에러가 아니라 정상적인 일시정지 신호로 취급한다: 예외 객체에 `step`(현재 step 이름)과 `context`(그 시점까지의 실행 상태)를 채워 넣고 그대로 다시 던진다 — raise한 쪽(예: `manual_review`)은 자기 step 이름을 몰라도 되고, `StateMachine`이 그 자리에서 알아서 채워준다. `retries`/`max_retries` 카운터는 건드리지 않으므로, 나중에 사람의 답을 받아 같은 step에 재진입해도 재시도 횟수로 잘못 소모되지 않는다.

### human-in-the-loop — `@human_action` + `AwaitingHumanAction` + `Orchestrator.resume()`
"사람의 의사결정이 필요하면 action 목록을 보여주고 고르게 해야 한다"는 요구가 `manual_review`에 실제로 배선된 지점이다. 세 조각으로 나뉜다.

- **`registry.decorators.human_action(choices, payload_schemas=None)`** — `@judged`와 계약(bounded choices)은 같지만 판단 주체가 모델이 아니라 사람이다. 함수는 `context`에 사람의 답이 이미 있으면(`context.get("human_action")`) `{"action": <choices 중 하나>, **payload}` 형태의 dict를 반환하고, 없으면 `AwaitingHumanAction(choices=...)`을 던진다. `action`은 여전히 유한 집합(bounded)이어야 감사 가능하다는 원칙(`ai_framework_2.md`의 judged branch 정의)을 그대로 유지하면서, action별로 다른 payload가 필요한 경우(예: `manual_review`의 `"서류추가요청"`이 어떤 서류가 더 필요한지 담아야 하는 것)는 `payload_schemas={"서류추가요청": {"field": Any}}`처럼 action에 종속된 스키마를 따로 선언해 `harness.schema.validate_schema()`로 검증한다. 이 분리가 핵심이다 — **action의 종류는 닫혀 있고(bounded), 그 안의 세부 데이터만 구조화**되므로 자유 라우팅과 구분되는 judged branch의 안전성이 그대로 유지된다.
- **`workflow.state_machine.AwaitingHumanAction`** — 위에서 설명한 일시정지 신호. `manual_review`는 raise만 하고, `StateMachine.run()`이 `step`/`context`를 채워 넣는다.
- **`orchestrator.Orchestrator.handle()`/`resume()`** — `handle()`은 이 예외를 받으면 크래시 대신 `{"status": "awaiting_human_action", "tool": ..., "step": ..., "choices": [...], "context": ...}`를 반환한다. 사람의 답이 오면 호출자가 `resume(tool_name, context, step, action)`을 불러 `context["human_action"] = action`을 채우고 `StateMachine(registry=self.registry, entry=step).run(context)`로 멈췄던 지점부터 재개한다.

`manual_review`의 실제 배선(`services/subscription_status/workflow.py`):
```python
MANUAL_REVIEW_CHOICES = ("승인", "반려", "서류추가요청")


@workflow_step(order=2, next={"승인": "DONE", "반려": "DONE", "서류추가요청": "DONE"})
@human_action(
    choices=MANUAL_REVIEW_CHOICES,
    payload_schemas={"서류추가요청": {"field": Any}},
)
def manual_review(context: dict[str, Any]) -> dict[str, Any]:
    human_action_input = context.get("human_action")
    if human_action_input is None:
        raise AwaitingHumanAction(choices=MANUAL_REVIEW_CHOICES)
    context["last_result"]["manual_review_decision"] = human_action_input
    return human_action_input
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

- `registry`에 등록되는 다른 서비스와 달리 `adapter.py`/`mapping.json`이 없다 — 자신만의 레거시/외부 연동이 없고, 이미 등록된 `subscription_status()`/`weather()` **tool 함수를 그대로 호출**해서 결과를 합성만 한다.
- `query_subscription` → `query_weather` 두 `@workflow_step`이 `next`로 고정 연결되며, `query_subscription`이 채운 `subscription_result["region"]`을 `query_weather`가 그대로 `weather(location=...)`의 입력으로 넘긴다 — 이게 두 서비스 사이의 실제 데이터 의존관계다.
- 내부에서 `subscription_status()`/`weather()`를 직접 호출하는 건 그 두 tool 각각의 `GuardrailChain.run()`(input 검증 포함)을 거치지 않는다는 뜻이다 — `subscription_status.workflow`가 내부적으로 `SubscriptionStatusAdapter`를 직접 호출하고 오케스트레이터의 개입 없이 결과를 합성하는 것과 동일한 "capability가 capability를 감싼다" 패턴이다.
- 다만 output 쪽 **내용물 검증**은 우회되지 않는다. `subscription_weather_flow`의 guardrail은 `{"subscription": Any, "weather": Any}`처럼 존재 여부만 보는 대신, 각 서비스의 `workflow.py`가 노출하는 `SUBSCRIPTION_STATUS_OUTPUT_SCHEMA` / `WEATHER_OUTPUT_SCHEMA` 상수를 그대로 import해 `{"subscription": SUBSCRIPTION_STATUS_OUTPUT_SCHEMA, "weather": WEATHER_OUTPUT_SCHEMA}`로 중첩 선언한다(§ `harness/guardrail.py`의 중첩 스키마 검증). `_validate()`가 재귀적으로 내려가 `subscription.status`/`weather.condition` 같은 중첩 필드까지 enum·optional 규칙을 그대로 적용하므로, 조합 서비스를 오케스트레이터로 호출하는 경로에서는 결과적으로 내용 검증이 이뤄진다. 스키마를 두 tool 모듈에서 재사용하기 때문에 중복 선언 없이 단일 소스로 유지된다.

### 입력 없는 목록 조회 + 표 렌더링 — `services/applicant_list/workflow.py`
청약 신청자 20명(스텁)과 각자의 진행 단계를 한 번에 보여주는 tool. 구조적으로는 `weather`와 같은 "단순 어댑터 서비스"(`adapter.py`/`mapping.json`/단일 스텝)이지만 두 가지가 다르다.

- **입력이 없다.** `@tool` 함수가 `applicant_list()`로 파라미터 0개 — `_infer_schema()`(`registry/decorators.py`)가 빈 `input_schema`를 추론하는 첫 사례다. 목록 전체를 고정 조회하는 tool은 라우팅에 필요한 인자가 없어도 된다는 걸 보여준다.
- **`mapping.json`을 `subscription_status`와 공유하지 않고 따로 둔다.** 두 서비스가 같은 레거시 청약 시스템의 다른 API(목록 vs 상세)를 표현한다는 설정이라 값(코드→상태 5종)은 우연히 동일하지만, "서비스는 자기 매핑 자산을 스스로 갖는다"는 원칙(§ 신규 서비스 추가 가이드)을 그대로 따른다 — import로 공유하면 결합이 생기고, 두 API가 실제로는 다른 속도로 바뀔 수 있는 별개의 레거시 엔드포인트라는 전제와 맞지 않는다.
- **최상위 `@tool` 함수가 표현(presentation)까지 조립한다.** `adapter.normalize()`는 의미 정규화(코드→값+confidence)까지만 하고, `applicant_list()`가 그 위에서 `_render_table()`로 마크다운 표 문자열을 만들어 `{"applicants": [...], "table": "..."}`로 반환한다 — 구조화된 데이터와 표 문자열을 같이 주는 이유는, 채팅 인터페이스에 그대로 얹었을 때 20행짜리 표가 실제로 읽을 만한지(이번 서비스를 추가한 실험 목적)를 그 자리에서 확인할 수 있게 하기 위해서다.
- **"목록 → 상세" 두 단계는 하나의 capability로 묶지 않았다.** `subscription_weather_flow`(region 데이터를 다음 tool 입력으로 자동 전달)와 달리, `applicant_list`의 tool description은 "사용자가 특정 신청자를 지목하면 `subscription_status(applicant_id=...)`로 이어서 조회하라"고만 안내하고 실제 연결은 만들지 않았다 — 두 호출이 같은 요청 안에서 항상 함께 일어나는 게 아니라(목록만 보고 끝낼 수도 있음), 별개의 대화 턴에서 사용자가 고른 이름을 사람(또는 그 위의 agent 판단)이 applicant_id로 옮겨서 다음 요청을 만드는 구조이기 때문이다 — 이게 **고정 서브 workflow로 묶어야 하는 경우(subscription_weather_flow)와 개별 tool로 남겨야 하는 경우(applicant_list → subscription_status)를 가르는 기준**이다: 데이터 의존관계가 매 호출마다 결정론적으로 이어지면 묶고, 사람이 매번 다르게 골라야 하면 개별 tool로 남긴다.

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
  └─ context["human_action"] = {"action": "서류추가요청", "field": "소득증빙서류"}
     └─ StateMachine(registry=registry, entry="manual_review").run(context)  — 멈췄던 지점부터 재개
          └─ manual_review(context) 재호출 — 이번엔 context["human_action"]이 있음
               → @human_action이 action("서류추가요청")을 choices로, payload({"field":...})를
                 payload_schemas["서류추가요청"]으로 검증 (밖이면 ValueError)
               → context["last_result"]["manual_review_decision"] = {"action": "서류추가요청", "field": "소득증빙서류"}
               outcome = "서류추가요청" → next 맵에 따라 종료(DONE)
     → context["last_result"] 반환
  └─ output 검증: status/status_confidence가 enum 안에 있는지, manual_review_decision(optional)이
     있다면 존재만 확인(Any — 세부 검증은 이미 @human_action이 끝냄)
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
| Judged branch (bounded choices, 판단 주체=모델) | `registry.decorators.judged(choices=...)` — 현재 등록된 서비스는 없음(§ 아래 한계) |
| Human-in-the-loop judged branch (bounded choices + payload, 판단 주체=사람) | `registry.decorators.human_action(choices=..., payload_schemas=...)` + `workflow.state_machine.AwaitingHumanAction` + `orchestrator.Orchestrator.resume()` |
| confirmed/inferred 매핑 관리 | `semantic.mapping.SemanticMapping` / `MappedValue` |
| 미확인 값 fail-fast | `semantic.mapping.UnmappedValueError` |
| 도메인 흐름 전체를 하나의 capability로 등록 | `services/subscription_status/workflow.py`의 최상위 `@tool subscription_status` (내부 state machine을 감싸 단일 tool로 노출) |
| 외부 실 API를 가진 서비스 (프로토콜적 면 = 실제 HTTP 호출, 인증 불필요) | `services/weather/adapter.WeatherAdapter.call()` (Open-Meteo 지오코딩 + 현재 날씨) |
| 사람에게 action 목록을 보여주고 고르게 하는 실제 배선 | `services/subscription_status/workflow.py`의 `manual_review()` — `@human_action` + `AwaitingHumanAction`으로 일시정지, `Orchestrator.resume()`으로 재개 |
| 여러 tool을 고정 서브 workflow로 미리 묶기 (에이전트가 즉석에서 여러 tool을 잇지 않게) | `services/subscription_weather_flow/workflow.py`의 최상위 `@tool subscription_weather_flow` — `subscription_status()` → `weather()` 순차 호출, `region` 필드로 데이터 연결 |
| 서비스 auto-discovery + 기동 시점 일관성 검사 | `registry.discovery.discover_services()` + `registry.decorators.ToolRegistry.validate()` |
| Optional 필드 + 중첩 스키마 검증 (조합 서비스의 하위 tool 결과까지 boundary에서 검증) | `harness.schema.optional()`(`OptionalField`) + `validate_schema()`의 재귀 검증 — `harness.guardrail`과 `registry.decorators.human_action`이 공유, `services/subscription_weather_flow/workflow.py`가 `SUBSCRIPTION_STATUS_OUTPUT_SCHEMA`/`WEATHER_OUTPUT_SCHEMA`를 재사용 |
| 레벨 조절 가능한 단계별 로깅 | `harness.logging_setup.configure_logging()`(`LOG_LEVEL`) + `harness.tracing.Tracer`(trace/span을 로그로도 출력) |
| 입력 없는 tool + 결정론적 데이터 의존관계가 없어 별도 tool로 남긴 "목록 → 상세" 패턴 | `services/applicant_list/workflow.py`의 최상위 `@tool applicant_list()` — 표(`table`) 렌더링까지 조립, `subscription_status`로의 후속 조회는 프롬프트로만 안내(§ 위 "입력 없는 목록 조회" 절) |

## 신규 서비스 추가 시 손대는 파일 (엔진 불변성 체크)

두 카테고리가 있다 — 어느 쪽이든 `framework/`도 `main.py`도 손대지 않는 게 목표이고, `discover_services()`(auto-discovery) 덕분에 실제로 그렇게 됐다. `services/<name>/`에 파일을 놓기만 하면 다음 실행 때 `registry.validate()`가 등록/참조 무결성까지 자동으로 확인해준다.

**레거시/외부 어댑터 서비스** (`subscription_status`, `weather`, `applicant_list`) — `guides/legacy_adapter_guide.md` 체크리스트 기준, 아래 4개 파일만 새로 만든다.
- `services/<name>/adapter.py` (`BaseAdapter` 상속)
- `services/<name>/mapping.json`
- `services/<name>/workflow.py` (`@workflow_step`/`@judged`(모델 판단) 또는 `@human_action`(사람 판단)/`@tool`)
- `services/<name>/prompts/<tool_name>.md`

**조합 서비스** (`subscription_weather_flow`) — 자신만의 외부 연동이 없으므로 `adapter.py`/`mapping.json`은 만들지 않는다.
- `services/<name>/workflow.py` (이미 등록된 다른 tool 함수를 직접 호출해 `@workflow_step`으로 연결 + 최상위 `@tool`)
- `services/<name>/prompts/<tool_name>.md`

두 카테고리 모두 `services/<name>/workflow.py`라는 파일명은 고정이다 — `discover_services()`가 정확히 이 이름을 import하기 때문(§ `registry/discovery.py`).

## 현재 스캐폴드의 한계 (다음 작업 후보)

- `SubscriptionStatusAdapter.call()`은 여전히 실제 레거시 연동 전 스텁(고정 응답, `region`도 항상 `"Seoul"`로 고정) — 청약 시스템 실 연동 시 교체 필요. 실제 레거시가 지역 정보를 안 주면 `subscription_weather_flow`의 데이터 연결 지점 자체를 다시 설계해야 함.
- `WeatherAdapter`는 Open-Meteo(무료, 인증 불필요)를 쓰므로 `weather` 서비스는 `.env`에 키를 넣지 않아도 바로 호출 가능 — 처음에 RapidAPI "yahoo-weather5"(키 필요)로 만들었다가 인증 없는 샘플 테스트에 맞춰 교체함.
- `requirements.txt`(openai/python-dotenv/requests)가 아직 이 환경에 설치되지 않음 — `pip install -r requirements.txt` 필요.
- `OpenAIRunner`(tool 라우팅)는 `OPENAI_MODEL` 미지정 시 `gpt-4o-mini`로 기본 동작 — 실제 사용 가능한 모델명으로 `.env`에서 확정해야 함. `manual_review`는 더 이상 OpenAI를 호출하지 않으므로(사람 판단으로 전환) 이 항목과 무관해졌다.
- `@judged`(모델이 판단하는 judged branch)는 데코레이터·`registry.validate()` 검사·문서까지 다 갖춰져 있지만, `manual_review`가 `@human_action`(사람 판단)으로 전환되면서 지금 `services/` 전체에서 실제로 이 데코레이터를 쓰는 서비스가 하나도 없다 — `framework/prompts/store.py`의 `compose()` + `framework/llm/openai_client.py`의 `complete()` 조합도 같이 orphan됨. **정리 여부**: 이 조합에 실제로 종속돼 있던 서비스별 산출물, 즉 `services/subscription_status/prompts/manual_review.md`(당시 OpenAI에게 자동승인/수동검토를 판단시키던 프롬프트)는 완전히 죽은 파일이라 삭제했다. 반면 `@judged` 데코레이터·`registry.validate()`의 judged 검사·`PromptStore.compose()`·`framework/llm/openai_client.py`는 특정 서비스에 종속된 게 아니라 재사용 가능한 프레임워크 능력이라 그대로 남겨뒀다 — 다음에 "사람이 아니라 모델이 판단해야 하는" judged 노드가 생기면 그때 다시 살아있는 예시가 생긴다.
- `@human_action`/`AwaitingHumanAction`/`Orchestrator.resume()`으로 만든 human-in-the-loop 일시정지/재개는 `subscription_status`라는 단일 사례로만 검증됐다. `Orchestrator.resume()`은 tool이 `context["last_result"]`를 그대로 반환한다는 관례에 기대므로 `subscription_weather_flow`처럼 자체적으로 반환값을 조립하는 tool에는 아직 쓸 수 없고, 세션 영속화 계층이 없어 paused response의 `context`를 호출자가 프로세스 메모리 안에서 직접 들고 있다가 넘겨야 한다(재시작하면 유실).
- human_action의 action은 여전히 "라벨 + payload"로만 끝난다 — action이 실제로 다른 capability를 호출·연결하는 것(예: `"서류추가요청"`이 서류 재제출 처리 tool로 실제 핸드오프하는 것)은 의도적으로 미룬 범위다. 실제로 연결할 대상 capability가 생기면 그때 실행 로직을 얹기로 함(YAGNI로 미룬 것이지 빠뜨린 게 아님).
- `main.py`의 `FirstMatchRunner`는 이름이 긴 tool부터 substring 매칭하도록 고쳤지만(한 tool 이름이 다른 tool 이름을 포함하는 경우 대비, 예: `weather` ⊂ `subscription_weather_flow`), 여전히 순수 문자열 포함 검사라 실제 자연어 요청 라우팅에는 쓸 수 없다 — 오프라인 샘플 테스트 전용 스텁이라는 원래 성격은 그대로.
- `ToolRegistry.validate()`는 registry 내부 참조 무결성(step/judged/human_action/guardrail 연결)만 본다 — "adapter.py가 BaseAdapter를 상속했는가", "mapping.json이 실제로 존재하는가" 같은 파일 시스템/클래스 계층 검사나, "새 tool description이 기존 tool과 의미가 안 겹치는가" 같은 의미적 검사(`guides/legacy_adapter_guide.md` 체크리스트 항목)는 하지 않는다 — 이런 건 코드로 자동 판별하기 어려워 사람 리뷰 영역으로 남겨둠.
- `@judged(choices=..., confidence_required="confirmed")`의 `confidence_required`는 `JudgedSpec`에 저장만 되고 실제로 어디서도 읽거나 검사하지 않는다 — "inferred 값은 judged 판단에 넘기면 안 된다"는 규칙은 지금 `fetch_status`가 `status_confidence != "confirmed"`를 직접 체크해서 우회 진입시키는 방식으로만 지켜지고, `@judged` 데코레이터 자체는 이 제약을 강제하지 않는 미완성 지점이다.
- `subscription_weather_flow`의 중첩 guardrail(§ 위 절)은 **output 내용물**만 boundary에서 검증한다 — 내부에서 직접 호출하는 `subscription_status()`/`weather()` 각각의 `GuardrailChain.run()`(input 검증 포함)은 여전히 우회된다. 지금은 두 tool 모두 input_schema를 선언하지 않아 우연히 gap이 드러나지 않을 뿐이므로, 나중에 어느 한쪽이 input_schema를 추가하면 조합 서비스 경로에서는 그 input 검증이 적용 안 된다는 점을 잊기 쉽다.
- `ApplicantListAdapter.call()`은 20명 고정 스텁(하드코딩된 리스트) — 실제 레거시 목록 조회 API 연동 시 교체 필요. `applicant_list`와 `subscription_status`가 값은 동일하지만 서로 다른 `mapping.json`을 갖고 있어서(§ 위 "입력 없는 목록 조회" 절 — 의도적 설계), 실제로 상태 체계가 바뀌면 두 파일을 각각 갱신해야 한다는 걸 잊기 쉽다.
- **미해결 논의 — 서비스 간 "겹치는 필드"를 어떻게 다룰지.** 위 항목의 근본 원인은 두 서비스의 output이 스키마 전체가 겹치는 것도 완전히 독립적인 것도 아니라, 일부 필드만 겹친다는 데 있다(`applicant_id`/`status`/`status_confidence`는 같은 도메인 개념이라 일치해야 하고, `region`/`manual_review_decision`/`name`은 각 서비스 고유). 스키마 전체를 합치거나 완전히 분리하는 이분법 대신, 겹치는 조각만 뽑아 공유 자산으로 만들고(예: 도메인을 대표하는 서비스가 `MAPPING_PATH`/상태 enum 상수를 export하고 다른 서비스가 그 조각만 import) 안 겹치는 필드는 각자 스키마에 남기는 방향으로 논의했다. 프레임워크 차원 규약(`"confirmed"/"inferred"` 같은 `SemanticMapping` 자체의 값)과 도메인 차원 지식(청약 상태 5종 같은 특정 서비스의 값)은 공유 주체가 다르다는 점(전자는 `framework/semantic/mapping.py`, 후자는 그 도메인을 대표하는 서비스)도 같이 짚었다. **아직 구현하지 않음** — 실제 use case(파라미터가 여럿이고 그중 일부만 겹치는 상황이 정확히 어떻게 발생할지)가 명확해지기 전까지는 의도적으로 보류.
- "목록에서 이름을 보고 다음 요청에 applicant_id를 넣는" 연결은 프롬프트 문구(`prompts/applicant_list.md`)로만 안내할 뿐, 실제로 이름→ID를 찾아 다음 tool 호출의 인자를 채우는 로직은 어디에도 없다 — `AgentRunner`는 tool 이름만 고르고 인자는 여전히 호출자가 직접 채워야 하므로(§ `orchestrator.py`), 이 흐름이 실제로 자동으로 이어지려면 인자까지 추출하는 `AgentRunner` 구현체가 필요하다.
- `applicant_list`의 `_render_table()`이 만드는 표 포맷(지금은 마크다운 파이프 표)은 **미확정 상태로 남겨둔 것**이다 — "예쁘게 보여주는" 방법은 이 결과를 최종적으로 어디서 보여주느냐(마크다운 렌더링 채팅 UI / raw text 전용 뷰 / 자체 웹 프론트엔드의 테이블 컴포넌트 / 다른 서비스의 프로그램적 소비)에 따라 완전히 달라지는데, 그 실행 환경 자체가 아직 정해지지 않았다. 환경이 정해지기 전까지는 raw text 정렬 로직(한글 폭 계산 등) 같은 특정 방향으로 미리 구현하지 않기로 함 — 다음 작업은 환경이 확정된 뒤 그에 맞는 포맷으로 `_render_table()`을 바꾸는 것.
