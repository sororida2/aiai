# Agent Loop 프레임워크 — 코드 구성

`README.md`(왜 이 구조가 필요한가)와 `ai_framework_2.md`(설계 철학)의 논의가 실제로 어떤 파일·클래스로 구현됐는지 매핑한 문서다. `services/` 아래 8개 서비스가 각기 다른 절의 살아있는 예시다 — `subscription_status`(레거시 어댑터 + human-in-the-loop 판단 노드), `weather`(인증 없는 외부 실 API 어댑터), `subscription_weather_flow`(고정 조합으로 묶은 조합 서비스), `applicant_list`(입력 없는 목록 조회 + 표 형식 렌더링), `public_holiday`/`exchange_rate`/`ip_geolocation`/`university_search`(외부 API 4종 추가 — `mapping.json` 없이 값을 그대로 쓰는 패턴, `university_search`만 국가명↔alpha-2 변환용 매핑을 씀). `main.py`가 실행 진입점이고, `examples/human_action_demo.py`가 human-in-the-loop 일시정지/재개를 터미널에서 직접 확인해보는 실행 가능한 예시다. 라우팅/인자 채우기/tool 간 동적 연결은 이제 `main.py`의 `build_triage_agent()`가 조립한 SDK `Agent`와 `Runner.run_sync()`가 담당한다(§ SDK 마이그레이션) — 고정 조합이 없는 tool도 모델이 필요하면 알아서 이어 부른다. 이 확장이 드러낸 구조적 한계는 `limitation.md`에 별도로 정리했다.

## 열린 질문 요약

아직 구현하지 않고 의도적으로 열어둔 논의들 — 전부 "실제 use case/환경이 아직 안 정해졌다"는 같은 이유로 보류 중이다. 각 항목의 전체 맥락은 § 아래 "현재 스캐폴드의 한계"에 있다.

- **서비스 간 겹치는 필드를 어떻게 공유할지** — `applicant_list`/`subscription_status`처럼 일부 필드만 겹치는 두 서비스의 스키마를 어디까지 공유 자산으로 뽑아낼지. 파라미터가 여럿이고 일부만 겹치는 실제 use case가 나오기 전까진 보류.
- **`applicant_list`의 표(`table`) 렌더링 포맷** — 마크다운 파이프 표가 최종 형태인지 여부는 이 결과를 어디서 보여줄지(실행/렌더링 환경)에 달려 있는데 그 환경 자체가 아직 안 정해짐.
- **LangGraph의 checkpointer식 영속화가 필요한가** — `main.py`의 `resume()`이 멈춘 상태를 프로세스 메모리로만 들고 있는 한계. 사람이 몇 시간~며칠 뒤에 판단하는 실제 시나리오나 분산 배포가 실제로 필요해지기 전까진 보류.
- **병렬 분기(fan-out/join)가 필요한가** — `StateMachine`은 순차 실행만 지원. 의존관계 없는 두 호출을 동시에 불러야 할 만큼 느린 실제 사례가 나오기 전까진 보류.
- **tool 본문에 `complete()`를 직접 호출하는 것의 트레이드오프** — bounded choices(감사 가능)를 포기하는 대신 완전히 자유로운 생성을 얻는 선택. 정형화가 원천적으로 불가능한 자유 텍스트 생성이 목적인 tool이 실제로 필요해지기 전까진 열어만 둠.
- **`manual_review` 앞에 AI 기반 중요도 분류(triage)를 넣을지** — "덜 중요한 판단은 AI에게 위임"은 예전에 시도했다가 이름-행동 모순으로 되돌린 구조와 같아서, 다시 하려면 `triage`(AI, 중요도만 분류)와 `manual_review`(사람, 실제 결정)를 역할 분리해야 함. 사람에게 넘어가는 케이스 중 "AI가 걸러줬어도 됐을" 구체적 사례가 쌓이기 전까진 보류.
- **main.py 경계의 일반 예외 처리(구조화된 에러 응답)** — 지금은 `AwaitingHumanAction`(및 그걸 감싼 SDK `UserError`) 하나만 특별 취급하고 나머지 예외(`GuardrailViolation`/`UnmappedValueError`/`MaxRetriesExceeded`/버그 등)는 전부 그대로 터진다. 초기 단계에서는 이렇게 안 막아야 버그가 바로 드러난다는 판단으로 **의도적으로 보류** — 채팅 UI 등에서 tool 하나의 실패로 전체 대화가 끊기면 안 되는 실제 배포 상황이 생기기 전까진 지금처럼 둔다.
- **복합 의도(compound intent) 요청 — 한 요청이 여러 tool의 최종 결과를 동시에 원하는 경우** — SDK `Runner`가 여러 tool을 이어 부르더라도, `main.py`의 `_extract_last_tool_output()`은 `result.new_items` 중 **마지막** `ToolCallOutputItem` 하나만 취한다. "143.248.1.1이 속한 나라의 휴일과 대학 5개를 알려줘"처럼 두 tool의 결과가 다 필요한 요청은 그중 하나만 반환되고 나머지는 **에러 없이 조용히 사라진다**(실측 확인됨, § `limitation.md`의 "증거 3"). 다중 tool 체이닝 자체(§ 아래 SDK 마이그레이션 절)는 이미 일반해로 고쳤지만, 이건 그것과 별개로 "여러 tool의 결과를 동시에 반환"하는 문제라 여전히 미해결이고 우선순위가 높은 항목이다. 지금 규모에서 구체적 need가 쌓이기 전까진 보류.

## 근본적 한계 — 질문의 방법론은 사전에 결정된다

위 "열린 질문"들이 전부 같은 뿌리를 공유한다는 게 4개 서비스(`public_holiday`/`exchange_rate`/`ip_geolocation`/`university_search`)를 추가하면서 드러났다. `registry.tools()`(tool 카탈로그), `WorkflowRegistry`의 `choices=(...)`(judged/human_action), 각 tool의 `output_schema`, `SemanticMapping`(`mapping.json`) — 이 넷은 전부 **코드 작성 시점에 사람이 닫아두는 자산**이고, `main.py`의 `handle(request)`로 들어오는 자연어가 실제로 착지할 수 있는 자리는 이 자산들뿐이다.

실측으로 확인된 두 가지:

1. **tool 선택(라우팅)은 이 구조의 강점과 정확히 일치한다.** SDK `Agent`+`Runner.run_sync()`로 자연어 요청 9개(tool 이름을 언급하지 않은 문장)로 직접 실험했을 때 전부 정확히 골랐다 — 등록된 카탈로그 중 분류하는 문제라서다. "상태+날씨" 복합 요청도 `common/orchestrator.md`의 "고정 서브 workflow부터 확인하라" 규칙대로 `subscription_weather_flow`를 정확히 찾아냈다.
2. **인자 채우기(argument filling)는 SDK로 옮긴 뒤로 모델이 기본으로 잘 처리한다.** `public_holiday(year, country_code)`나 `exchange_rate(base, symbols)`처럼 문장만으론 모호한 경우도, SDK가 tool 스키마(함수 시그니처에서 자동 추론)를 보고 모델이 직접 채운다 — 예전에 이 프로젝트가 직접 구현했던 `extract_arguments()`류 메서드가 통째로 사라졌다. 다만 추출된 값이 맞는지 감사할 방법이 없다는 문제 자체는 그대로 남아 있고, `limitation.md`에 그 구체적 한계가 기록돼 있다.

`services/university_search/mapping.json`(alpha-2 코드 200개)이 만들어질 수 있었던 것도, Hipolabs API 자신의 응답 레코드 안에 `alpha_two_code`와 `country`가 이미 같이 있었기 때문이다 — 다리를 새로 놓은 게 아니라 데이터 안에 있던 다리를 찾아 꺼낸 것이다.

**(업데이트) 이 다리를 "그때그때" 놓는 것은 이제 SDK의 기본 동작이다.** "143.248.1.1이 위치한 나라의 대학교 5개를 알려줘"처럼 한 요청이 다른 tool의 결과를 필요로 하는 경우, SDK `Runner`가 `tool_use_behavior`(기본값 `run_llm_again`)에 따라 모델이 필요한 만큼 tool을 이어 부르게 둔다(§ 아래 SDK 마이그레이션 절) — `ip_geolocation` 결과를 보고 모델이 알아서 `university_search`를 이어서 부르는 식이다. 예전엔 이 프로젝트가 `_resolve_missing_via_other_tool()`/`rewrite_request()`를 직접 구현해서 "부족한 필드를 다른 tool로 알아낸 뒤 요청을 자연어로 다시 써서 재시도"하는 조건적 해법을 만들었지만, 그 역할이 통째로 SDK 기본 루프로 흡수됐다 — 적당한 tool을 못 찾거나 그 tool 호출도 실패하면 여전히 원래대로 정직하게 실패한다.

즉 이 시스템이 실시간으로 잘 하는 일은 "이미 있는 선택지 중 맞는 걸 고르는 것"(bounded classification)이고, "선택지 자체가 없는 곳에 새 선택지를 만들어내는 것"은 못 한다 — 위 열린 질문 목록의 "서비스 간 겹치는 필드 공유", "`manual_review` 앞 triage", "`complete()` 직접 호출" 세 항목은 전부 이 한 가지 한계의 다른 표현이다. 결함이 아니라 `ai_framework_2.md`가 처음부터 선택한 트레이드오프(judged branch는 반드시 bounded여야 감사 가능하다)의 필연적 귀결이며, 실증 근거와 상세 논의는 `limitation.md` 참고.

```
framework/                  ← 엔진. 새 서비스를 추가해도 손대지 않는 것이 목표.
├── registry/decorators.py  ← @tool 데코레이터(SDK function_tool()을 감싸는 얇은 wrapper) + 전역 ToolRegistry
│                              (+ validate()) — tool 카탈로그(라우팅 표면) + FunctionTool 조립을 관리
├── registry/discovery.py    ← services/<name>/workflow.py 자동 스캔·import (discover_services)
├── harness/
│   ├── schema.py             ← 스키마 검증 원시 요소 (OptionalField/optional/validate_schema) — output_schema와
│   │                            human_action의 payload 검증이 공유
│   ├── guardrail.py          ← Agent 단위 SDK @output_guardrail(관찰만, 차단 안 함) + tool 본문에서 opt-in으로
│   │                            부르는 validate_tool_output()(schema.py 위에 얹힘, 실제 차단은 여기서)
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

main.py                     ← 조립 지점 (discover_services + registry.validate(), build_triage_agent() —
                                SDK Agent + Runner.run_sync()) + handle()/resume() + 실행 예시.
                                서비스 추가 시 더 이상 손대지 않아도 됨.
examples/human_action_demo.py ← human-in-the-loop 일시정지/재개를 터미널에서 직접 확인하는 실행 가능한 예시
                                (main.py의 handle()/resume()을 그대로 재사용)
guides/legacy_adapter_guide.md ← 신규 서비스 추가 가이드
.env / .env.example         ← OPENAI_API_KEY, OPENAI_MODEL, LOG_LEVEL (.env는 커밋 안 함; weather는 키 불필요)
```

## SDK 마이그레이션 — OpenAI Agents SDK 도입

`csv_diff.md`에서 이 프로젝트가 OpenAI Agents SDK를 전혀 안 쓰고(`openai` 원시 SDK로 `complete()`만 씀) 6개 핵심 조각을 손으로 재구현했다는 걸 확인한 뒤, 실제로 대체 작업을 진행했다(계획 문서는 세션 로컬 plan 파일에 있었고, 이 절이 결과를 as-built로 정리한 것). 아래 "컴포넌트별 역할" 절도 이 마이그레이션 결과에 맞춰 갱신되어 있다 — `Orchestrator`/`GuardrailChain`/`@guardrail`은 더 이상 존재하지 않는다.

### 바뀐 것

| 예전 | 지금 |
|---|---|
| `registry/decorators.py`의 `@tool`+`_infer_schema()` | SDK `function_tool()` — `ToolSpec.func`(원본, 서비스 간 합성용)와 `ToolSpec.function_tool`(SDK `FunctionTool`, `Agent(tools=...)`용)을 둘 다 들고 있음 |
| `harness/guardrail.py`의 `GuardrailChain`(tool 단위 검증) | `output_schema_guardrail`(SDK `@output_guardrail`, **Agent 단위** — 최종 출력이 dict인지만 구조적으로 확인) + `validate_tool_output(name, output)`(tool별 세부 스키마가 필요하면 각 서비스가 함수 본문에서 직접 부르는 opt-in 헬퍼) |
| `orchestrator.py`의 `Orchestrator`/`AgentRunner`(`choose_tool`/`extract_arguments`/`rewrite_request`/`_resolve_missing_via_other_tool`) | 파일 자체를 삭제. `main.py`의 `build_triage_agent()`(flat `Agent(tools=registry.function_tools())`) + `Runner.run_sync()`가 tool 선택·인자 추출·동적 연결을 전부 대신함 |
| `main.py`의 `FirstMatchRunner`/`OpenAIRunner` | 삭제. **트레이드오프**: `FirstMatchRunner`가 제공하던 "API 키 없이 오프라인으로 라우팅 테스트" 능력이 사라졌다 — SDK는 항상 실제 모델 호출이 전제라 `OPENAI_API_KEY` 없이는 아예 못 돈다 |

### 안 바뀐 것 (의도적으로)

- `workflow/registry.py`(`WorkflowRegistry`) + `workflow/state_machine.py`(`StateMachine`) — 결정론적 그래프 자체. SDK의 `Agent`는 기본적으로 LLM이 매 턴 자유롭게 tool을 고르는 루프라 이 프로젝트의 "그래프는 코드로 고정" 원칙과 반대 방향이라서, 각 tool **내부**의 sub-flow(`subscription_status`의 fetch_status→manual_review)는 그대로 이 엔진이 담당하고 SDK는 그 안을 모른다(하나의 `@function_tool` 호출로만 봄).
- `adapters/base.py`(`BaseAdapter`), `semantic/mapping.py`(`SemanticMapping`) — 도메인 고유 로직, SDK 스코프 밖.
- `AwaitingHumanAction`/`MaxRetriesExceeded`, `context["_step_retry_counts"]` 재시도 안전장치 — 그대로.

### human_action(pause/resume) — 새 설계

SDK의 `@function_tool`은 기본적으로 tool 함수가 던진 예외를 모델에게 보여줄 에러 메시지로 바꿔버린다(`failure_error_function`). `AwaitingHumanAction`이 "일시정지 신호"라는 의미를 유지하려면 이 기본값을 꺼야 한다 — `@tool(pausable=True)`가 `function_tool(failure_error_function=None)`으로 이 옵트아웃을 자동으로 적용한다(`subscription_status`가 실제 사례).

`resume()`은 `Runner.run()`(SDK 루프)을 다시 타지 않는다 — 어떤 tool의 어떤 step에서 멈췄는지 이미 알고 있으므로 모델의 라우팅 판단이 다시 필요 없고, SDK의 Session이 "죽었던 tool 호출을 정확히 그 지점부터 재개"하는 걸 보장해주는지도 검증 안 된 영역이라 그 불확실성 자체를 피했다. 예전 `Orchestrator.resume()`과 완전히 같은 방식으로 `StateMachine(registry=tool_spec.workflow_registry, entry=step).run(context)`를 직접 호출한다(`main.py`의 `resume()`).

`AwaitingHumanAction`에 `tool_name` 필드가 새로 생겼다 — `@tool(pausable=True)`의 래퍼가 예외를 잡아 자동으로 채운다(스텝 함수는 여전히 자기가 어느 tool에 속하는지 몰라도 됨). `main.py`의 `resume()`이 어떤 `workflow_registry`를 찾을지 이 값으로 안다.

### 알려진 한계 / Windows 실측으로 확인·수정된 것

이 환경(WSL)엔 `openai-agents`가 설치돼 있지 않아(`pip show openai-agents` → not found) 여기서는 코드만 SDK 문서 지식으로 작성했고, 실제 동작 확인은 Windows에서 했다. 실측으로 드러난 것:

1. **`failure_error_function=None` 가정 — Windows 실측으로 확인·수정됨.** 예외를 삼키지 않고 밖으로 전파시키긴 하는데(그 부분은 가정대로 맞았음), SDK가 원본 `AwaitingHumanAction`을 그대로 주지 않고 자기 `agents.exceptions.UserError`로 한 번 감싸서 던졌다(`Error running tool subscription_status: awaiting human action from (...)`, `raise ... from` 체이닝이라 `__cause__`에 원본이 그대로 남아있음). `main.py`의 `handle()`이 `UserError`를 잡아 `e.__cause__`가 `AwaitingHumanAction`이면 풀어서 처리하고, 아니면(진짜 tool 버그 등) 다시 던지도록 고쳐서 해결. `resume()`은 SDK를 아예 안 거치고(`StateMachine`을 직접 호출) 이 문제와 무관하다.
2. **`tool_use_behavior="stop_on_first_tool"`이어도 `result.final_output`은 tool의 원본 dict가 아니라 그 dict를 문자열로 바꾼 것이었다.** 실제로 `applicant_list` 호출 시 처음엔 `TypeError: string indices must be integers`로 재현됨. 그런데 그 문자열이 JSON(큰따옴표)이 아니라 **파이썬 `repr()`(작은따옴표, 예: `"{'a': 'b'}"`)**이었다 — `json.loads()`로 고쳤더니 이번엔 `JSONDecodeError: Expecting property name enclosed in double quotes`로 재현됨. `main.py`의 `handle()`이 `json.loads()` 실패 시 `ast.literal_eval()`로 재시도하도록 고쳐서 최종 해결.
3. **처음 만든 `output_schema_guardrail`(`isinstance(output, dict)` 체크)이 위 2번과 같은 이유로 유효한 응답을 `OutputGuardrailTripwireTriggered`로 막는 실제 버그를 냈다.** `output`이 이 자리에서 정확히 어떤 타입/모양인지 확신할 수 없다는 게 근본 원인이라, 타입을 단정해서 막는 대신 **관찰만 하고 통과시키도록** 되돌렸다(§ `harness/guardrail.py`) — 진짜 검증은 이미 `validate_tool_output()`이 tool 함수 본문 안에서 끝낸다.
4. **guardrail 단위가 tool→Agent로 넓어진 트레이드오프** — `subscription_weather_flow`처럼 한 tool이 다른 tool을 내부에서 부르는 경우, 내부 호출의 output은 더 이상 boundary에서 개별 검증되지 않는다(이미 input 검증도 우회됐던 것과 같은 종류의 gap이 output까지 넓어짐).
5. **`stop_on_first_tool`이 다중 tool 체이닝을 막는다는 게 Windows 실측으로 확인되고, 수정됨.** `"143.248.1.1이 위치한 나라의 대학교 5개를 알려줘"`(`ip_geolocation` → `university_search` 순으로 이어야 함)를 돌려봤더니, `ip_geolocation`은 성공했는데 `university_search`는 아예 호출되지도 않았다 — `main.py`의 `_log_run_items()`(`result.new_items`의 항목 타입을 전부 로깅)로 확인하니 `run items (2): ['ToolCallItem', 'ToolCallOutputItem']`, 즉 tool 호출이 딱 1번뿐이었다. 원인은 `tool_use_behavior="stop_on_first_tool"`이 이름 그대로 **첫 번째 tool 호출이 끝나는 순간 바로 멈추기 때문**이었다.
   - **처음 시도한 땜빵(폐기됨)**: `ip_geolocation`→`university_search` 전용 고정 composition tool을 만듦. 사용자가 "질문을 '통화는 어쩌고'로 바꾸면 또 새로 만들어야 하지 않냐"고 지적해서 즉시 폐기 — 페어마다 고정 tool을 만드는 건 확장이 안 되는 근본적으로 잘못된 방향이었다.
   - **실제로 적용한 수정 — Windows 재실측으로 확인됨.** `tool_use_behavior`를 기본값(`run_llm_again`)으로 되돌려서 모델이 필요한 만큼 tool을 이어 부를 수 있게 하고, 대신 "구조화된 dict를 모델이 재요약하지 않고 그대로 받는다"는 요구는 `main.py`의 `_extract_last_tool_output()`이 책임진다 — `result.final_output`(모델이 생성한 텍스트) 대신 `result.new_items`에서 **마지막 `ToolCallOutputItem`**을 직접 찾아 그 안의 원본 반환값을 쓴다. 이러면 tool을 몇 번 체이닝하든(1번이든 여러 번이든) 항상 마지막 tool의 원본 dict를 얻는다 — 페어별 특별 처리가 필요 없는 일반해다. 같은 요청을 다시 돌려서 이번엔 `university_search`까지 실제로 호출되는 것을 확인했다.
   - **덤으로 발견**: `ip_geolocation`의 원시 응답(`ip-api.com`)에 이미 ISO 3166-1 alpha-2(`countryCode`)가 들어있었는데 `normalize()`가 버리고 있었다 — `country_code` 필드로 노출하도록 고쳤다. 이 프로젝트의 국가 정준 표현(alpha-2, `public_holiday`/`university_search`가 이미 따름)과 이름 변환 없이 바로 맞아떨어진다.
   - **여전히 안 풀리는 것**: `limitation.md`의 "증거 3"(휴일 목록 **그리고** 대학 목록처럼 서로 다른 두 tool의 최종 결과를 **동시에** 원하는 진짜 복합 의도)은 "마지막 tool 하나의 결과만 취한다"는 `_extract_last_tool_output()`의 전제상 여전히 못 푼다 — 이건 순차 체이닝이 아니라 애초에 다른 문제(§ 위 열린 질문, `_extract_last_tool_output()`이 여러 tool 결과를 동시에 반환하지 못하는 것)라서 별개로 남는다.

**종합 — 마이그레이션의 핵심 위험 구간은 Windows 실측으로 전부 검증 완료됐다.** 단일 tool 호출(`applicant_list`), 동적 다중 tool 체이닝(`ip_geolocation`→`university_search`), human-in-the-loop 일시정지/재개 전체 사이클(`subscription_status`의 `manual_review` — pause 후 "승인" 입력으로 정상 완료 확인, `examples/human_action_demo.py`) 세 경로 모두 실제로 끝까지 돌아갔다. 남은 미해결 항목(guardrail granularity 트레이드오프, 복합 의도 요청)은 이 마이그레이션이 새로 만든 문제가 아니라 원래도 있었거나(전자) 별개 층의 문제(후자)다.

관련 문서: `csv_diff.md`(대체 대상 분석의 원본), `requirements.txt`(`openai-agents` 추가됨).

## 컴포넌트별 역할

### `registry/decorators.py` — 전역 tool 카탈로그 (SDK `function_tool()`을 감싸는 지점)

**(2026-08-07 SDK 마이그레이션 이후 갱신)** 전역 `registry = ToolRegistry()`에는 이제 `ToolSpec` 한 종류만 모인다 — `@guardrail`/`GuardrailSpec`은 완전히 없어졌다(guardrail이 Agent 단위로 옮겨감, § 아래 `harness/guardrail.py` 절).

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    func: Callable                    # 원본(undecorated) 함수 — 서비스 간 직접 호출·resume 경로용
    function_tool: FunctionTool       # Agent(tools=[...])에 그대로 넣을 SDK 객체
    output_schema: dict[str, Any] | None = None
    workflow_registry: WorkflowRegistry | None = None

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)
```

`@tool(name, description, *, output_schema=None, workflow_registry=None, pausable=False)`가 하는 일:
1. SDK의 `function_tool(name_override=name, description_override=description)`을 원본 함수에 적용해 `FunctionTool` 객체를 만든다 — `Agent(tools=registry.function_tools())`에 그대로 들어갈 것.
2. **원본 함수는 그대로 보존**해서 `ToolSpec.func`에 둔다 — SDK가 데코레이트한 함수를 `FunctionTool`(JSON 문자열 인자를 받는 `on_invoke_tool`만 남음)로 통째로 바꿔버려서, 서비스가 다른 서비스를 파이썬 함수처럼 직접 호출하는 패턴(`registry.tool_for(name)`)이 SDK 객체만으로는 불가능하기 때문.
3. `pausable=True`면 `function_tool(..., failure_error_function=None)`을 써서 tool 함수의 예외를 SDK가 모델용 에러 메시지로 바꿔버리는 기본 동작을 끈다 — `human_action`의 `AwaitingHumanAction`이 "일시정지 신호"라는 의미를 유지하려면 필수(§ 아래 "human-in-the-loop" 절). 이때 원본 함수를 한 번 더 감싸서, 잡은 `AwaitingHumanAction`에 `e.tool_name = name`을 자동으로 찍어준다(스텝 함수는 여전히 자기가 어느 tool에 속하는지 몰라도 됨).
4. `output_schema`는 검증에 즉시 쓰이지 않는다 — `harness/guardrail.py`의 `validate_tool_output(name, output)`이 필요할 때 `registry.tool_for(name).output_schema`로 찾아 쓰는 참고 자료로만 저장해둔다.

`workflow_registry`는 이 tool 내부에 `human_action`(pause 가능) 노드가 있을 때만 넘긴다 — `main.py`의 `resume()`이 멈췄던 지점을 재개하려면 그 tool 전용 `WorkflowRegistry`를 찾아야 하기 때문(§ 아래 "human-in-the-loop" 절).

`ToolRegistry.tool_for(name)`은 이름 하나로 등록된 tool을 바로 찾는다(`tools()`처럼 전체 dict를 복사하지 않고, 없으면 `KeyError`로 명확히 실패). 돌려주는 `ToolSpec`은 `__call__`을 구현해서 그 자체가 호출 가능하다 — 호출부가 `.func`라는 내부 속성 이름을 몰라도 `registry.tool_for(name)(**kwargs)`로 바로 쓸 수 있다. 이건 서비스가 다른 서비스를 부를 때 쓰는 방식이다(§ 아래 "서비스를 조합하는 서비스" 절). `ToolRegistry.function_tools()`는 `Agent(tools=...)`에 그대로 넣을 SDK `FunctionTool` 목록을 돌려준다 — `main.py`의 `build_triage_agent()`가 이걸 쓴다.

모듈을 import하는 순간 `@tool` 데코레이터가 실행되며 등록된다. 예전에는 `main.py`에 서비스마다 `from services.<name> import workflow as _`를 나열해 이 import를 직접 트리거했지만, 지금은 `framework/registry/discovery.py`의 `discover_services()`가 `services/` 아래를 스캔해서 대신 트리거한다 (§ 아래 `registry/discovery.py` 절).

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
WEATHER_OUTPUT_SCHEMA = {...}

@tool(name="weather", description="...", output_schema=WEATHER_OUTPUT_SCHEMA)
def weather(location: str) -> dict[str, Any]:
    result = WeatherAdapter().execute(location=location)
    return validate_tool_output("weather", result)
```
기준은 **분기(`next`가 outcome에 따라 갈리는가)·재시도(`max_retries`)·판단 노드(`judged`/`human_action`)가 하나라도 있는가**다. 하나라도 있으면 `WorkflowRegistry`가 실제로 일(그래프 고정, bounded 강제)을 하므로 그대로 쓴다(`subscription_status`가 셋 다 있음). 셋 다 없으면 `StateMachine`은 "step 하나 부르고 바로 DONE"만 반복하는 빈 껍데기이므로 안 쓴다. `subscription_weather_flow`는 분기/재시도/판단은 없지만 **두 tool 호출 사이의 순서와 데이터 의존관계**(region → location) 자체가 코드 로직이라 `WorkflowRegistry`를 유지했다 — 이 기준은 "스텝이 몇 개인가"가 아니라 "그 사이에 실제로 코드가 결정할 게 있는가"임에 유의.

이 변경으로 로그의 `state machine start`/`span(kind="step")` 한 단계가 `weather`/`applicant_list`에서는 더 이상 안 찍힌다 — 어차피 tool 단위 span(`span(kind="tool")`)과 1:1이었던 정보라 손실은 없다(§ 아래 "로깅" 절).

### `registry/discovery.py` + 두 단계 일관성 검사 — auto-discovery
`main.py`가 서비스를 일일이 알 필요가 없게 만드는 지점. Python은 모듈을 실제로 import하기 전까진 그 안의 데코레이터를 실행하지 않으므로, 등록이 일어나려면 누군가는 각 `services/<name>/workflow.py`를 import해야 한다 — `discover_services(services)`가 `pkgutil.iter_modules(services.__path__)`로 하위 패키지를 전부 찾아 그 `workflow.py`를 대신 import해준다.

일관성 검사는 이제 두 단계로 나뉜다.
- **파일 단위, import 시점 즉시** — 각 `workflow.py` 하단의 `steps.validate()`(`WorkflowRegistry.validate()`)가 그 파일의 `next`/`judged`/`human_action` 참조 무결성을 검사한다. 이 파일 하나로 판단 가능한 검사라 다른 서비스를 기다릴 필요가 없다.
- **전역 카탈로그 단위, discovery 이후 한 번** — `main.py`가 `discover_services()` 직후 `registry.validate()`(`ToolRegistry.validate()`)를 호출해 tool 카탈로그를 검사한다: 등록된 tool이 하나도 없으면 즉시 실패(서비스 폴더는 있는데 아무것도 안 잡힌 상태). `@guardrail`이 별도 데코레이터로 있던 시절엔 여기서 guardrail-tool 매칭도 같이 검사했는데, guardrail이 Agent 단위로 옮겨가면서(§ 아래 `harness/guardrail.py` 절) 그 검사 자체가 없어졌다 — 지금은 tool 카탈로그가 비어있지 않은지만 본다.

`discover_services()`도 자체적으로 한 단계 fail-fast한다: `services/<name>/`에 `workflow.py` 자체가 없으면 `ServiceConsistencyError`로 명확히 실패하고, `workflow.py`는 있지만 그 안에서 다른 import가 실패한 "진짜 버그"는 오진하지 않고 원래 예외 그대로 전파한다(`ModuleNotFoundError.name`으로 구분).

### `main.py` — 라우팅 + 인자 추출 + 일시정지/재개 (SDK `Agent`/`Runner`가 담당)

**(2026-08-07 SDK 마이그레이션으로 전면 교체)** `framework/orchestrator.py`(`Orchestrator`/`AgentRunner` Protocol/`FirstMatchRunner`/`OpenAIRunner`)는 삭제됐다. tool 선택·인자 추출·고정 조합 없는 tool 간 동적 연결을 전부 손으로 구현했던 그 파일 대신, 이제 SDK의 `Agent`+`Runner`가 이 세 가지를 전부 기본 동작으로 처리한다. `main.py`의 세 함수가 그 자리를 대신한다.

**`build_triage_agent()`** — 매 요청마다 새 `Agent`를 하나 만든다.
```python
def build_triage_agent() -> Agent:
    prompt_store = PromptStore(base_dir=FRAMEWORK_DIR / "prompts")
    return Agent(
        name="triage",
        instructions=prompt_store.common_prompt(),
        tools=registry.function_tools(),
        output_guardrails=[output_schema_guardrail],
    )
```
`instructions=`는 예전 `AgentRunner.choose_tool()`에 넘기던 것과 같은 `common/orchestrator.md`를 그대로 재사용한다(§ 아래 "실제 운영 환경에서 발견한 라우팅 버그" — 이 프롬프트 파일에 넣은 수정이 여전히 유효하다). `tools=registry.function_tools()`가 8개 서비스의 `FunctionTool`을 전부 한 Agent에 넣는다 — flat 구조로 시작(§ 위 "SDK 마이그레이션" 절, handoff 트리는 도메인이 늘면 나중에). `tool_use_behavior`는 **기본값**(`run_llm_again`)을 그대로 쓴다 — 처음엔 `"stop_on_first_tool"`로 시작했는데 다중 tool 체이닝을 막아버린다는 걸 실측으로 확인하고 되돌렸다(§ 위 "SDK 마이그레이션" 절에 상세 경위).

**`handle(request)`** — 요청 하나의 진입점.
```python
def handle(request: str) -> dict[str, Any]:
    agent = build_triage_agent()
    try:
        result = Runner.run_sync(agent, request)
    except AwaitingHumanAction as e:
        return _paused_response(e)
    except UserError as e:
        if isinstance(e.__cause__, AwaitingHumanAction):
            return _paused_response(e.__cause__)
        raise
    _log_run_items(result)
    return _extract_last_tool_output(result)
```
`Runner.run_sync(agent, request)` 한 줄이 예전 `choose_tool()`+`extract_arguments()`+(필요하면) `_resolve_missing_via_other_tool()`을 전부 대신한다 — 모델이 tool을 고르고, 인자를 자연어에서 추측해 채우고, 필요하면 다른 tool을 이어서 부르는 것까지 SDK 내부 루프가 기본으로 처리한다(§ 아래 "SDK는 flow를 어떻게 다루는가"). 구조화된 dict를 정확히 돌려받는 건 `result.final_output`(모델이 생성한 텍스트, 신뢰 안 함) 대신 `_extract_last_tool_output()`이 `result.new_items`에서 마지막 `ToolCallOutputItem`을 직접 꺼내서 보장한다.

**`resume(tool_name, context, step, action)`** — 예전 `Orchestrator.resume()`과 똑같은 방식이다. `Runner.run()`(SDK 루프)을 다시 안 탄다 — 어떤 tool의 어떤 step에서 멈췄는지 이미 알고 있으므로 모델의 라우팅 판단이 다시 필요 없고, SDK의 Session이 "죽었던 tool 호출을 정확히 그 지점부터 재개"하는 걸 보장해주는지도 검증 안 된 영역이라 그 불확실성 자체를 피했다.
```python
def resume(tool_name, context, step, action):
    tool_spec = registry.tool_for(tool_name)
    if tool_spec.workflow_registry is None:
        raise ValueError(...)
    context["human_action"] = action
    StateMachine(registry=tool_spec.workflow_registry, entry=step).run(context)
    return context["last_result"]
```
`registry.tool_for(tool_name).workflow_registry`로 그 tool 전용 `WorkflowRegistry`를 찾는다(§ `workflow/registry.py` 절 — `@tool(workflow_registry=steps)`로 연결해둔 것). `workflow_registry`가 없는 tool(`weather`처럼 pause가 없는 tool)에 `resume()`을 부르면 즉시 `ValueError`로 막는다.

**예외 처리 — SDK가 예외를 `UserError`로 감싼다.** `@tool(pausable=True)`(`function_tool(failure_error_function=None)`)는 예외를 삼키지 않고 밖으로 전파시키지만, SDK가 원본 예외를 그대로 주지 않고 자기 `agents.exceptions.UserError`로 한 번 감싸서 던진다(Windows 실측으로 확인, `raise ... from` 체이닝이라 `__cause__`에 원본이 그대로 남아있음). `handle()`이 `UserError`를 잡아 `e.__cause__`가 `AwaitingHumanAction`이면 풀어서 처리하고, 아니면(진짜 tool 버그 등) 다시 던진다.

**`_extract_last_tool_output(result)`** — 모델이 마지막으로 부른 tool의 원본 반환값을 그대로 돌려준다. `tool_outputs = [item for item in result.new_items if type(item).__name__ == "ToolCallOutputItem"]`로 찾아 그 마지막 항목의 `.output`을 쓴다 — 이 값이 문자열(JSON 또는 파이썬 `repr()`, 둘 다 실측으로 확인됨)이면 `json.loads()`를 먼저 시도하고 실패하면 `ast.literal_eval()`로 재시도한다. tool을 하나도 안 불렀으면(`tool_outputs`가 비어있으면) 이 프로젝트의 "모든 tool은 구조화된 dict를 반환한다"는 계약을 못 지킨 것이므로 조용히 넘어가지 않고 `ValueError`로 명확히 실패시킨다. "가장 마지막에 부른 tool의 결과가 사용자가 원한 답"이라는 전제인데, 순차 체이닝에는 맞지만 진짜 복합 의도(여러 tool의 결과를 동시에 원하는 것, `limitation.md`의 "증거 3")는 여전히 못 푼다.

**`_log_run_items(result)`** — `result.new_items`의 각 항목 타입을 그대로 로깅한다(`run items (2): ['ToolCallItem', 'ToolCallOutputItem']`). `tool_use_behavior="stop_on_first_tool"`이 두 번째 tool 호출 자체를 막아버렸을 때, "다음 tool의 `Invoking tool` 로그가 안 보인다"는 **부재**로만 알아채야 했던 걸 명시적으로 확인 가능하게 만든 디버깅 도구다.

**실제 운영 환경에서 발견한 라우팅 프롬프트 버그(SDK 마이그레이션 이전부터 유효, 지금도 그대로 씀).** `"weather 조회해줘"`(location은 별도 전달) 요청이 모델의 `'NONE'` 응답으로 라우팅 실패했다. `DEBUG` 로그로 실제 프롬프트를 확인해보니, `weather`/`subscription_weather_flow`처럼 description에 "location 하나만 입력받는다" 식으로 필수 입력을 명시한 tool만 실패하고, 그런 문구가 없는 `subscription_status`/`applicant_list`는 정상 라우팅됐다 — 원인은 `common/orchestrator.md`의 "*description에 명시된 입력 스키마 밖의 것을 추측하지 마라*"/"*적합한 tool이 없으면 억지로 고르지 마라*" 규칙이, "요청 텍스트에 인자 값이 없다"를 "적합한 tool이 없다"로 모델이 오판하게 만든 것이었다. `common/orchestrator.md`에 "요청 텍스트에 tool의 입력 인자 값이 구체적으로 적혀 있지 않아도 된다 — 그 값은 호출자가 별도로 채워 넣는다"는 규칙을 한 줄 추가해 해결했다 — 이 프롬프트 파일은 SDK 마이그레이션 이후에도 `Agent(instructions=...)`로 그대로 재사용되므로 이 수정은 지금도 유효하다.

### `harness/schema.py` — 스키마 검증 원시 요소
`OptionalField`/`optional()`/`SchemaViolation`/`validate_schema()`가 여기 산다. 원래 `harness/guardrail.py` 안에 있던 걸, `@human_action`의 payload 검증(§ 아래 "human-in-the-loop" 절)이 똑같은 재귀 검증 로직을 필요로 하면서 공유 모듈로 뺐다 — guardrail도 human_action도 이 모듈에만 의존하고 서로는 모른다. `validate_schema(value, schema, path="")`가 스키마 값의 형태로 세 가지를 구분한다.
- `Any` → 필드 존재 여부만 확인
- `{"choices": [...]}` → enum 제약
- `{"choices": ...}`가 없는 순수 dict → **중첩 스키마**로 간주해 재귀 검증. 실패 시 `path`가 `subscription.status`처럼 점(dot) 경로로 어느 중첩 레벨에서 깨졌는지 보여준다.

기본적으로 스키마에 선언된 키는 전부 필수지만, 조건부 경로에만 채워지는 필드는 `optional(schema)`(`OptionalField` wrapper)로 감싸 선언한다 — 필드가 없으면 통과, 있으면 `inner` 규칙으로 그대로 검증한다. 위반 시 `SchemaViolation(detail)`을 던지며, 호출자(`guardrail.py`/`workflow.registry.WorkflowRegistry.human_action`)가 각자의 맥락(`stage`/`tool_name` 또는 `human_action 이름`/`action`)을 붙여 자기 예외 타입(`GuardrailViolation`/`ValueError`)으로 다시 던진다.

### `harness/guardrail.py` — 검증 (SDK 마이그레이션 이후 Agent 단위 관찰 + opt-in tool 단위 차단)

**(2026-08-07 SDK 마이그레이션 이후 갱신)** 예전 `GuardrailChain`(tool마다 input→호출→output을 직접 검증하고 위반 시 즉시 차단)은 없어졌다. 지금은 두 층으로 나뉜다.

1. **`output_schema_guardrail`** — SDK `@output_guardrail`, `Agent(output_guardrails=[...])`로 Agent 단위에 붙인다(`main.py`의 `build_triage_agent()`). 어떤 tool이 출력을 만들었는지 이 자리에선 구분이 안 되므로 **차단하지 않고 관찰만 한다** — `GuardrailFunctionOutput(output_info={"observed_type": type(output).__name__}, tripwire_triggered=False)`을 항상 반환한다. 처음엔 `isinstance(output, dict)`로 막으려다가 SDK가 tool 결과를 문자열로 감싸 넘기는 경우(§ 위 "SDK 마이그레이션" 절)에 유효한 응답까지 `OutputGuardrailTripwireTriggered`로 막는 실제 버그를 냈다 — 그래서 관찰 전용으로 되돌렸다.
2. **`validate_tool_output(tool_name, output)`** — 실제 차단은 여기서 한다. `registry.tool_for(tool_name).output_schema`로 그 tool의 스키마를 찾아 `harness/schema.py`의 `validate_schema()`에 위임하고, 위반 시 `SchemaViolation`을 `GuardrailViolation(stage="output", tool_name, detail)`로 감싸 다시 던진다. **opt-in이다** — 각 tool 함수 본문이 `return`하기 직전에 직접 불러야 한다(`subscription_status.workflow`의 `status`/`status_confidence`/`manual_review_decision` 필드, `subscription_weather_flow`의 중첩 검증이 실제 예시). 안 부르면 그 tool은 검증 없이 그대로 반환된다.

`input_schema`/thunk(`output_schema_for`/`input_schema_for`) 메커니즘은 guardrail이 Agent 단위(호출 전 input을 가로챌 지점이 없음)로 바뀌면서 함께 사라졌다 — 지금 `output_schema`는 `@tool(output_schema=...)`에 진짜 dict로 직접 넘기고, `registry.tool_for(name).output_schema`로 바로 읽는다(늦은 평가가 필요 없다, `discover_services()`가 이미 이 시점엔 등록을 끝냈으므로).

### `harness/logging_setup.py` — 로그 레벨 설정
`configure_logging()`이 `LOG_LEVEL` 환경변수(기본 `INFO`)로 표준 `logging`을 한 번 설정한다. `main.py`가 `load_dotenv()` 직후, `discover_services()`보다 먼저 호출해야 discovery/validate 단계 로그도 같은 레벨로 잡힌다(`main.py` 참고). `get_logger(name)`은 전부 `agent_loop.<name>` 네임스페이스 아래 로거를 돌려주므로, 특정 모듈만 레벨을 따로 올리고 싶으면(예: `logging.getLogger("agent_loop.adapter").setLevel(logging.DEBUG)`) 표준 `logging` API를 그대로 쓰면 된다.

### `harness/tracing.py` — 관측이자 로깅의 뼈대
`Tracer`는 스택 기반으로 `Span`을 중첩시킨다. `start_trace`가 루트(kind="orchestrator")를 열고, `span()` 호출마다 현재 스택 최상단의 자식으로 붙는다. Tool이 늘어나도 상위 구조(Trace → Orchestrator Span → Tool Span*)는 그대로 유지된다는 설계가 스택 구현으로 자연히 보장됨.

각 `start_trace`/`span` 진입·종료 시점에 `INFO` 레벨로 로그를 찍고, 중첩 깊이(`len(self._stack)`)만큼 들여쓰기를 붙인다 — `Trace`/`Span` 객체(`tracer.current_trace`)는 원래도 만들어지고 있었지만 그걸 읽어서 보여주는 코드가 어디에도 없었던 게 실제 gap이었다(§ 로깅 절 참고). `workflow/state_machine.py`가 각 `steps.step()` 실행을 `tracer.span(kind="step")`으로 감싸면서, tool 단위보다 한 단계 더 세밀한 "이 tool 안에서 지금 어느 스텝을 도는지"까지 같은 메커니즘으로 로그에 잡힌다 — 단, `weather`/`applicant_list`처럼 `StateMachine`을 아예 안 쓰는 tool은 이 "step" span 없이 tool 단위 span까지만 찍힌다(§ 위 "언제 WorkflowRegistry를 생략하는가" 참고).

`span()`은 활성 trace가 없는 상태(예: 오케스트레이터를 거치지 않고 `subscription_status(applicant_id=...)`처럼 `StateMachine`을 쓰는 tool 함수를 직접 호출·테스트하는 경우)에도 안전하게 동작한다 — 스택이 비어 있으면 이름 없는 암묵적 루트를 하나 열어서 쓰고, 빠져나갈 때 다시 비운다. `StateMachine.run()`이 항상 `span()`을 쓰게 되면서 이 케이스를 처음부터 고려해야 했다.

### `prompts/store.py` — 프롬프트 계층
`common_prompt()` (공통) + `tool_prompt()` (도메인별, `services/<name>/prompts/<tool_name>.md`) + 선택적 few-shot을 `compose()`가 `---`로 이어붙인다. `main.py`의 `build_triage_agent()`는 `common_prompt()`만 써서 SDK `Agent(instructions=...)`에 넘긴다. `compose()` + `framework.llm.openai_client.complete()` 조합(도메인별 judged 노드가 실제로 모델을 호출하는 배선)은 원래 `manual_review`가 살아있는 예시였는데, `manual_review`가 사람 판단(`@human_action`)으로 바뀌면서 지금은 이 조합을 실제로 쓰는 서비스가 없다 — 당시 전용이던 `services/subscription_status/prompts/manual_review.md`는 완전히 죽은 파일이라 삭제했고, `compose()`/`complete()` 자체는 재사용 가능한 프레임워크 능력이라 남겨뒀다 (§ 아래 "현재 스캐폴드의 한계" 참고). `complete()` 자체는 모델/프롬프트 길이·응답 미리보기를 `INFO`로, system/user 프롬프트 원문 전체를 `DEBUG`로 로깅한다 — 프롬프트에 개인정보가 실릴 수 있는 서비스라면 운영 환경에서 `LOG_LEVEL=DEBUG`를 켜지 않도록 주의.

### `semantic/mapping.py` — 레거시 의미 정규화
`SemanticMapping.normalize(raw_value)`가 `mapping.json`을 찾아 `MappedValue(raw, value, confidence)`를 반환. 매핑에 없으면 `UnmappedValueError`로 즉시 실패 (fail-fast). `MappedValue.require_confirmed()`는 `confidence != "confirmed"`면 예외를 던져, `inferred` 값이 판단 분기에 잘못 쓰이는 걸 타입 수준에서 막는다.

### `adapters/base.py` — 양면 어댑터
`BaseAdapter`는 `call()`(프로토콜적 면 — 레거시 스펙에 종속)과 `normalize()`(의미론적 면 — `SemanticMapping`에 종속)를 분리해 각각 독립적으로 오버라이드하게 강제한다. `execute()`는 `normalize(call())`로 둘을 합성만 한다 — 이 한 곳에서 `call()`/`normalize()` 각각의 입출력을 `DEBUG`로 로깅하므로, 어떤 어댑터를 새로 만들어도(레거시 원시값 로깅을) 따로 구현할 필요가 없다.

### `workflow/state_machine.py` — 고정 파이프라인 실행기
`StateMachine.run()`은 `entry`부터 시작해 `WorkflowStepSpec.func(context)`가 반환한 outcome 문자열을 `next` dict에서 찾아 다음 단계로 이동한다. `next`가 없거나 `TERMINAL("DONE")`이면 종료. 판단 노드도 그냥 하나의 step으로 등록되며(`steps.judged()`/`steps.human_action()` + `steps.step()` 이중 데코레이터), state machine 입장에서는 outcome이 code-driven이든 model-driven이든 human-driven이든 구분하지 않는다 — bounded choices라는 계약만 `judged()`/`human_action()`이 보장한다. 각 스텝 실행을 `tracer.span(name=현재_step, kind="step")`으로 감싸고, 진입("state machine start")·전이("step 'X' -> outcome=... -> next='Y'")·종료를 `INFO`로 로깅한다.

`StateMachine.registry`는 전역 `ToolRegistry`가 아니라 `workflow.registry.WorkflowRegistry` 인스턴스다 — 각 서비스의 `build_state_machine()`이 자기 파일 전용 `steps`를 넘긴다(§ `workflow/registry.py` 절). 그래서 `steps()` 메서드가 보는 스텝 집합은 그 파일에 등록된 것으로 자연히 한정된다.

`outcome`이 `next`의 키 밖인지 확인하는 검증은 여기 없다 — `steps.step()`의 wrapper(`workflow/registry.py`)가 함수 반환 즉시 검사해서 `ValueError`를 던지므로, `run()`이 `spec.next[outcome]`을 인덱싱하는 시점엔 `outcome`이 항상 유효한 키임이 보장된다(`judged()`/`human_action()`이 각자의 bounded 값 밖을 함수 반환 즉시 막는 것과 동일한 위치·방식). 이 즉시 검증 덕분에 `services/subscription_status/workflow.py`의 실제 버그(`mapping.json`의 `"10"→"접수완료"`가 `fetch_status`의 `next`에는 빠져 있던 것)를 테스트 중 바로 잡아낼 수 있었다.

**순환 방지(`max_retries`) — self-loop뿐 아니라 여러 스텝을 왕복하는 순환까지.** `context[RETRY_COUNTS_KEY]`(`"_step_retry_counts"`, 프레임워크 예약 키)에 스텝별로 "완료된" 실행 횟수를 기록한다 — `spec.func(context)`가 예외 없이 outcome을 반환했을 때만 카운트가 올라간다. 어떤 스텝이든 다시 진입하려는 시점에 이미 완료된 횟수가 `max_retries + 1`(기본 5+1=6)에 도달했으면 실행 전에 `MaxRetriesExceeded`로 막는다. 예전엔 `next_step == current`(자기 자신으로 도는 것)일 때만 카운트했는데, 그러면 `evaluate → generate → evaluate → ...`처럼 **서로 다른 두 스텝 이상을 왕복하는 순환은 전혀 감지하지 못했다** — 지금은 스텝 이름 기준으로 재진입 자체를 세므로 몇 개 스텝을 거치는 순환이든 막힌다.

이 카운트를 `StateMachine.run()`의 로컬 변수가 아니라 **`context` 안에** 두는 이유는 `main.py`의 `resume()`이 멈출 때마다 새 `StateMachine` 인스턴스로 `run()`을 다시 호출하기 때문이다(그때그때 로컬 변수는 초기화됨) — 순환이 `human_action`처럼 멈추는 노드를 거치면 카운트가 resume 경계를 넘어 살아남아야 실제로 보호가 된다. `context`는 resume()에 그대로 전달되는 유일한 것이라 여기 둔다. 스텝 작성자는 이 키를 직접 건드릴 필요가 없다.

"완료된" 실행만 센다는 게 핵심이다 — 사람이 `human_action`의 bounded choices 밖의 값을 입력해 `ValueError`가 나거나 아직 답이 없어 `AwaitingHumanAction`으로 멈춘 시도는 카운트되지 않는다. 사람이 입력을 몇 번 틀렸는지는 자동 순환 폭주와 무관한 문제라 같은 예산을 쓰면 안 된다는 판단(§ 아래 "human-in-the-loop" 절과도 연결).

**`AwaitingHumanAction` — 일시정지.** `spec.func(context)` 호출이 이 예외를 던지면(§ 아래 "human-in-the-loop" 절), `run()`은 이를 에러가 아니라 정상적인 일시정지 신호로 취급한다: 예외 객체에 `step`(현재 step 이름)과 `context`(그 시점까지의 실행 상태)를 채워 넣고 그대로 다시 던진다 — raise한 쪽(예: `manual_review`)은 자기 step 이름을 몰라도 되고, `StateMachine`이 그 자리에서 알아서 채워준다.

### human-in-the-loop — `steps.human_action()` + `AwaitingHumanAction` + `main.py`의 `resume()`
"사람의 의사결정이 필요하면 action 목록을 보여주고 고르게 해야 한다"는 요구가 `manual_review`에 실제로 배선된 지점이다. 세 조각으로 나뉜다.

- **`WorkflowRegistry.human_action(choices, payload_schemas=None)`** — `judged()`와 계약(bounded choices)은 같지만 판단 주체가 모델이 아니라 사람이다. 함수는 `context`에 사람의 답이 이미 있으면(`context.get("human_action")`) `{"action": <choices 중 하나>, **payload}` 형태의 dict를 반환하고, 없으면 `AwaitingHumanAction(choices=...)`을 던진다. `action`은 여전히 유한 집합(bounded)이어야 감사 가능하다는 원칙(`ai_framework_2.md`의 judged branch 정의)을 그대로 유지하면서, action별로 다른 payload가 필요한 경우(예: `manual_review`의 `"서류추가요청"`이 어떤 서류가 더 필요한지 담아야 하는 것)는 `payload_schemas={"서류추가요청": {"field": Any}}`처럼 action에 종속된 스키마를 따로 선언해 `harness.schema.validate_schema()`로 검증한다. 이 분리가 핵심이다 — **action의 종류는 닫혀 있고(bounded), 그 안의 세부 데이터만 구조화**되므로 자유 라우팅과 구분되는 judged branch의 안전성이 그대로 유지된다. 검증을 통과하면 래퍼가 `context["human_action"]`을 지운다(관례상 `func(context: dict[str, Any])`로 호출되므로 `args[0]`가 context) — 안 지우면 같은 human_action 노드가 순환 안에서(예: evaluator가 이전 스텝으로 되돌리는 구조) 다시 방문될 때 새 결정을 기다리지 않고 예전 답을 그대로 재사용해버리는 버그가 있었다(발견 즉시 수정).
- **`workflow.state_machine.AwaitingHumanAction`** — 위에서 설명한 일시정지 신호. `manual_review`는 raise만 하고, `StateMachine.run()`이 `step`/`context`를 채워 넣는다.
- **`main.py`의 `handle()`/`resume()`** — `handle()`은 이 예외를(SDK가 `UserError`로 감싸 던지는 경우까지 포함, § 위 "SDK 마이그레이션" 절) 받으면 크래시 대신 `{"status": "awaiting_human_action", "tool": ..., "step": ..., "choices": [...], "context": ...}`를 반환한다. 사람의 답이 오면 호출자가 `resume(tool_name, context, step, action)`을 불러 `context["human_action"] = action`을 채우고, `tool_spec.workflow_registry`(`@tool(workflow_registry=steps)`로 연결된 이 tool 전용 `WorkflowRegistry`)를 써서 `StateMachine(registry=tool_spec.workflow_registry, entry=step).run(context)`로 멈췄던 지점부터 재개한다.

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

# ... 최상위 @tool(subscription_status, workflow_registry=steps)가 이 steps를 main.py의 resume()에 연결한다
```
전에는 이 지점에서 OpenAI에게 "자동승인/수동검토 중 뭘 고를지"를 대신 판단시켰다(`@judged` + `complete()`). "manual_review"라는 이름 자체가 "사람이 검토해야 하는 케이스"라는 뜻인데 정작 모델이 그 판단을 대신하고 있었던 게 원래의 모순이었고, 지금은 이름 그대로 실제 사람의 답을 기다린다.

choices 이름도 그 흔적을 정리했다 — "자동승인"(모순: 사람이 고르는데 "자동"?)/"수동검토"(모순: 이미 `manual_review` 안인데 또 "수동검토"로?)는 AI가 "사람에게 넘길지 말지"를 판단하던 시절의 이분법이 그대로 남은 것이었다. 지금은 이 노드 자체가 사람이 보고 있는 지점이므로, 사람이 실제로 내리는 결정(승인/반려)으로 바꿨다.

**실행 가능한 예시 — `examples/human_action_demo.py`.** 위 배선이 실제로 pause → 사람 입력 → resume까지 도는 걸 터미널에서 직접 확인할 수 있다(Windows 실측으로 확인 완료, § 위 "SDK 마이그레이션" 절). `main.py`의 `handle()`/`resume()`을 그대로 재사용하고, 레거시 어댑터가 아직 스텁이라(`SubscriptionStatusAdapter.call()`이 항상 confirmed 응답만 반환) `manual_review`까지 못 가는 문제는 이 스크립트 안에서만 어댑터를 몽키패치해 `status_code="99"`(inferred)를 강제하는 방식으로 우회한다 — 실제 레거시 연동이 붙으면 이 몽키패치는 필요 없다. 흐름:
```
$ python examples/human_action_demo.py
[사람 확인 필요] tool=subscription_status step=manual_review
가능한 action: 승인, 반려, 서류추가요청
고를 action을 입력하세요: 서류추가요청
어떤 서류가 더 필요한가요?: 소득증빙서류

최종 결과: {'applicant_id': 'A123', 'status': '보류', 'status_confidence': 'inferred',
            'region': 'Seoul', 'manual_review_decision': {'action': '서류추가요청', 'field': '소득증빙서류'}}
```
bounded choices 밖의 값을 입력하면(`@human_action`이 던지는 `ValueError`) 크래시 대신 "다시 골라주세요"로 재입력을 받는다 — `resume()` 호출이 실패해도 대화 자체는 안 끊어진다는 걸 보여준다.

**알려진 한계** (자세한 건 § 아래 "현재 스캐폴드의 한계"): `main.py`의 `resume()`은 tool이 `context["last_result"]`를 그대로 반환하는 관례에 기대므로 `subscription_status`에서만 쓸 수 있고(`subscription_weather_flow`처럼 자체적으로 반환값을 조립하는 tool은 대상이 아님), 세션 영속화 계층이 없어 호출자가 paused response의 `context`를 직접 들고 있다가 넘겨야 하며, "action이 실제로 다른 capability를 호출·연결한다"(예: `"서류추가요청"`이 서류 재제출 처리 tool로 실제 핸드오프하는 것)는 아직 구현하지 않았다 — 지금은 action + payload까지만 만들고, 실제로 연결할 대상 capability가 생겼을 때 그 실행 로직을 얹기로 결정했다.

### 서비스를 조합하는 서비스 — `services/subscription_weather_flow/workflow.py`
`common/orchestrator.md`가 "하나의 요청이 여러 tool을 필요로 하면 ... 고정 서브 workflow(capability)로 등록되어 있는지 먼저 확인하라"고 지시하는 지점의 구현체. SDK `Runner`는 이제 요청 하나 안에서 여러 tool을 모델이 알아서 이어 부르게 둘 수 있지만(§ 위 "SDK 마이그레이션" 절, `ip_geolocation`→`university_search`로 실측 확인된 일반적 다중 tool 체이닝), `subscription_status`→`weather`처럼 다음 tool의 입력(`location`)이 이전 tool 출력(`region`)에 **항상 결정론적으로** 의존하는 조합은 그때그때 모델의 판단에 맡기지 않고 이렇게 **상위 capability 하나로 미리 고정**한다 — 이 기준은 § 위 "언제 `WorkflowRegistry`/`StateMachine`을 아예 생략하는가"의 "데이터 의존관계가 매 호출마다 결정론적으로 이어지면 묶는다" 기준과 같다.

- `registry`에 등록되는 다른 서비스와 달리 `adapter.py`/`mapping.json`이 없다 — 자신만의 레거시/외부 연동이 없고, 이미 등록된 `subscription_status`/`weather` **tool을 그대로 호출**해서 결과를 합성만 한다.
- **다른 서비스의 함수를 직접 import하지 않는다.** `query_subscription`/`query_weather` 스텝 본문 안에서 `registry.tool_for("subscription_status")`처럼 전역 `ToolRegistry`를 이름(문자열)으로 조회해 호출한다 — `from services.subscription_status.workflow import subscription_status`처럼 정확한 모듈 경로와 함수 이름을 직접 아는 게 아니다. Triage Agent가 tool을 고를 때 이름 문자열에만 커플링되는 것과 같은 원칙을 서비스 간 호출에도 적용한 것 — 원래는 직접 import였는데, "조합 서비스가 다른 서비스의 내부 구현(정확한 함수 이름)까지 알아야 하는 건 `discover_services()`가 없애려던 결합을 다시 만드는 것"이라는 지적으로 고쳤다. 조회를 **스텝 함수 본문 안에서(모듈 로드 시점이 아니라 호출 시점에)** 하기 때문에 `discover_services()`가 서비스를 어떤 순서로 import하든 안전하다(`subscription_weather_flow`가 알파벳 순서상 `weather`보다 먼저 import돼도, 실제 함수가 호출되는 시점엔 이미 전부 등록이 끝나 있음). `ToolRegistry.tool_for(name)`은 `tools()`처럼 전체 dict를 복사하지 않고 이름 하나만 찾으며(없으면 `KeyError`로 명확히 실패), 반환하는 `ToolSpec`이 `__call__`을 구현해서(spec 자체가 호출 가능) 호출부가 `.func`를 몰라도 되게 했다 — "몇 단계를 거치든 상관없지만 `.func`라는 내부 속성 이름은 안 보였으면 좋겠다"는 요청으로 다듬은 형태. `registry.tool_for(name)()`은 SDK `FunctionTool`(JSON 문자열 인자만 받는 `on_invoke_tool`)이 아니라 `ToolSpec.func`(원본 파이썬 함수)를 호출하므로, 키워드 인자를 그대로 넘길 수 있다(§ `registry/decorators.py` 절).
- output 스키마도 직접 import하지 않는다: `subscription_status()`/`weather()`를 호출한 뒤, `registry.tool_for("subscription_status").output_schema`/`registry.tool_for("weather").output_schema`로 각 tool에 이미 등록된 스키마를 그대로 가져와 `{"subscription": ..., "weather": ...}`로 중첩 선언하고 `harness.schema.validate_schema()`에 넘긴다 — 위반 시 `GuardrailViolation`으로 감싸 던진다. 이 조회도 호출 시점(함수 본문 안)에 일어나므로 import 순서와 무관하게 안전하다.
- 내부에서 `subscription_status()`/`weather()`를 (registry를 통해) 직접 호출하는 건 SDK `Runner`를 거치지 않는다는 뜻이다 — 즉 Agent 단위 `output_schema_guardrail`(§ `harness/guardrail.py` 절, 어차피 관찰만 함)의 대상이 안 된다. 다만 각 tool 함수 본문 안의 `validate_tool_output()` 호출은 그대로 실행되므로, 개별 tool의 출력 검증 자체는 우회되지 않는다 — `subscription_status.workflow`가 내부적으로 `SubscriptionStatusAdapter`를 직접 호출하고 Runner의 개입 없이 결과를 합성하는 것과 동일한 "capability가 capability를 감싼다" 패턴이다.
- `subscription_weather_flow` 자기 자신의 output(중첩된 `{"subscription": ..., "weather": ...}`)도 위에서 설명한 대로 `validate_schema()`로 명시적으로 검증한다 — 각 서비스의 `output_schema`를 재사용하므로 중복 선언 없이 단일 소스로 유지된다.

### 입력 없는 목록 조회 + 표 렌더링 — `services/applicant_list/workflow.py`
청약 신청자 20명(스텁)과 각자의 진행 단계를 한 번에 보여주는 tool. 구조적으로는 `weather`와 같은 "단순 어댑터 서비스"(`adapter.py`/`mapping.json`, 분기 없어 `WorkflowRegistry` 생략)이지만 두 가지가 다르다.

- **입력이 없다.** `@tool` 함수가 `applicant_list()`로 파라미터 0개 — SDK `function_tool()`이 함수 시그니처에서 tool의 입력 스키마를 자동 추론하므로(이 프로젝트가 따로 `input_schema`를 선언하거나 추론할 필요가 없다), 파라미터가 0개면 그 자체로 빈 입력 스키마가 된다. 목록 전체를 고정 조회하는 tool은 라우팅에 필요한 인자가 없어도 된다는 걸 보여준다.
- **`mapping.json`을 `subscription_status`와 공유하지 않고 따로 둔다.** 두 서비스가 같은 레거시 청약 시스템의 다른 API(목록 vs 상세)를 표현한다는 설정이라 값(코드→상태 5종)은 우연히 동일하지만, "서비스는 자기 매핑 자산을 스스로 갖는다"는 원칙(§ 신규 서비스 추가 가이드)을 그대로 따른다 — import로 공유하면 결합이 생기고, 두 API가 실제로는 다른 속도로 바뀔 수 있는 별개의 레거시 엔드포인트라는 전제와 맞지 않는다.
- **최상위 `@tool` 함수가 표현(presentation)까지 조립한다.** `adapter.normalize()`는 의미 정규화(코드→값+confidence)까지만 하고, `applicant_list()`가 그 위에서 `_render_table()`로 마크다운 표 문자열을 만들어 `{"applicants": [...], "table": "..."}`로 반환한다 — 구조화된 데이터와 표 문자열을 같이 주는 이유는, 채팅 인터페이스에 그대로 얹었을 때 20행짜리 표가 실제로 읽을 만한지(이번 서비스를 추가한 실험 목적)를 그 자리에서 확인할 수 있게 하기 위해서다.
- **"목록 → 상세" 두 단계는 하나의 capability로 묶지 않았다.** `subscription_weather_flow`(region 데이터를 다음 tool 입력으로 자동 전달)와 달리, `applicant_list`의 tool description은 "사용자가 특정 신청자를 지목하면 `subscription_status(applicant_id=...)`로 이어서 조회하라"고만 안내하고 실제 연결은 만들지 않았다 — 두 호출이 같은 요청 안에서 항상 함께 일어나는 게 아니라(목록만 보고 끝낼 수도 있음), 별개의 대화 턴에서 사용자가 고른 이름을 사람(또는 그 위의 agent 판단)이 applicant_id로 옮겨서 다음 요청을 만드는 구조이기 때문이다 — 이게 **고정 서브 workflow로 묶어야 하는 경우(subscription_weather_flow)와 개별 tool로 남겨야 하는 경우(applicant_list → subscription_status)를 가르는 기준**이다: 데이터 의존관계가 매 호출마다 결정론적으로 이어지면 묶고, 사람이 매번 다르게 골라야 하면 개별 tool로 남긴다.

## 서비스-프레임워크 연결도

지금 구현된 4개 서비스가 프레임워크의 어떤 조각에 실제로 연결되는지를 시각화한 다이어그램은 `agent_loop_architecture_diagrams.html`의 "8. 현재 구현된 서비스 ↔ 프레임워크 연결도" 절에 있다(SVG로 직접 그려서 마크다운 뷰어의 mermaid 렌더링 품질에 의존하지 않음 — 브라우저로 그 HTML 파일을 열어서 확인). 읽는 법은 아래와 같다.

읽는 법:
- **`main.py`의 triage Agent는 전역 `ToolRegistry`가 조립한 `FunctionTool` 목록만 안다** — 어떤 서비스가 몇 개 있는지, 내부 구조가 뭔지는 모른다.
- **`WorkflowRegistry`는 서비스마다 쓰거나 안 쓰거나다** — `subscription_status`/`subscription_weather_flow`만 실제로 쓰고(분기/재시도/판단 노드가 있어서), `weather`/`applicant_list`는 아예 안 쓴다(§ "언제 WorkflowRegistry를 생략하는가").
- **`subscription_weather_flow`의 두 점선(직접 호출)**: `subscription_status`/`weather`의 tool 함수를 **직접** 호출한다는 뜻 — 이 경로는 SDK `Runner`를 거치지 않으므로 Agent 단위 `output_schema_guardrail`의 대상이 안 된다(다만 각 tool 본문 안의 `validate_tool_output()`은 그대로 실행됨, § "서비스를 조합하는 서비스" 절).
- **`applicant_list`의 라벨 붙은 점선(prompt만)**: `subscription_status`로 이어지는 걸 tool description 문구로만 안내하고 코드로 연결하지 않았다 — 사람이 매번 다른 신청자를 고르는 시나리오라 고정 서브 workflow로 안 묶은 결과다(§ "입력 없는 목록 조회" 절).

## 요청 하나의 전체 흐름 (`main.py` 예시 기준, SDK 마이그레이션 이후)

```
handle("A123 신청자의 subscription_status 조회해줘")
  └─ agent = build_triage_agent()   — Agent(tools=registry.function_tools(), output_guardrails=[...])
  └─ Runner.run_sync(agent, request)
     ├─ 모델이 tools 목록(스키마는 함수 시그니처에서 SDK가 자동 추론)을 보고
     │    "subscription_status"를 고르고 "A123"에서 applicant_id를 직접 추출
     └─ FunctionTool.on_invoke_tool 호출 → subscription_status(applicant_id="A123")
        [services/subscription_status/workflow.py]
          └─ StateMachine(entry="fetch_status").run(context)
             ├─ fetch_status: SubscriptionStatusAdapter().execute(applicant_id=...)
             │    ├─ call()      → 레거시 원시 응답 {"status_code": "20"} (현재 스텁)
             │    └─ normalize() → mapping.json 조회 → {"status": "서류미비", "status_confidence": "confirmed"}
             │    outcome = "서류미비" → next 맵에 따라 종료(DONE)
             │    (만약 confidence != confirmed였다면 outcome="미확인" → manual_review로 진입)
          → context["last_result"] 반환
          └─ validate_tool_output("subscription_status", result) — status/status_confidence가
               선언된 enum 안에 있는지 확인(tool 함수 본문이 opt-in으로 직접 부름)
     └─ output_schema_guardrail — Agent 단위, 관찰만 하고 차단 안 함(§ 위 "SDK 마이그레이션" 절)
  └─ _log_run_items(result) — new_items 타입을 로깅
  └─ _extract_last_tool_output(result) — new_items의 마지막 ToolCallOutputItem에서 원본 dict를 꺼냄
```

`applicant_id="A123"`처럼 요청 텍스트 안에 값이 있으면 모델이 tool 스키마를 보고 직접 채운다 — 예전 `extract_arguments()` 같은 별도 단계가 없다. 값이 요청 텍스트 자체엔 없고 다른 tool의 결과로만 알아낼 수 있는 경우, SDK `Runner`가 `tool_use_behavior`(기본값 `run_llm_again`)에 따라 모델이 필요한 만큼 tool을 이어 부르게 둔다 — Windows 실측으로 확인된 실제 사례:

```
handle("143.248.1.1이 위치한 나라의 대학교 5개를 알려줘")
  └─ Runner.run_sync(agent, request)
     ├─ 1번째 tool 호출: ip_geolocation(ip="143.248.1.1")
     │    → {"country": "United States", "country_code": "US", ...}
     ├─ 모델이 그 결과를 보고 university_search에 필요한 country_code="US"를 스스로 채워
     │    이어서 2번째 tool을 호출(같은 run 안에서, 요청을 다시 쓰지 않음)
     └─ 2번째 tool 호출: university_search(country_code="US")
          → {"universities": [...]}
  └─ _log_run_items(result) → run items (4): ['ToolCallItem', 'ToolCallOutputItem',
                                                'ToolCallItem', 'ToolCallOutputItem']
  └─ _extract_last_tool_output(result) → university_search의 결과(마지막 ToolCallOutputItem)
```
지원할 만한 tool을 모델이 못 찾거나 그 tool 호출 자체가 실패하면 SDK가 알아서 실패를 모델에게 보여주고, 모델은 그 사실을 반영한 텍스트로 마무리한다 — `_extract_last_tool_output()`이 tool을 하나도 못 찾으면(`tool_outputs`가 비어있으면) `ValueError`로 명확히 실패시킨다(§ 위 `main.py` 절).

`fetch_status`의 outcome이 `"미확인"`이면(confidence가 `inferred`) `manual_review`로 진입하는데, 이 노드는 사람의 답이 필요해 여기서 한 번 더 갈린다.

```
StateMachine.run() 계속 (entry 이후 manual_review 진입)
  └─ manual_review(context) 호출 — context에 아직 "human_action" 없음
       └─ raise AwaitingHumanAction(choices=("승인","반려","서류추가요청"))
            → StateMachine.run()이 잡아 step="manual_review", context=현재 context를 채워 다시 던짐
       → @tool(pausable=True) 래퍼가 tool_name을 찍고 다시 던짐 → SDK가 이걸 UserError로
          한 번 감싸서 Runner.run_sync() 밖으로 전파(§ 위 "SDK 마이그레이션" 절)
       → handle()이 UserError를 잡아 e.__cause__가 AwaitingHumanAction이면 풀어서 반환:
            {"status": "awaiting_human_action", "tool": "subscription_status",
             "step": "manual_review", "choices": ["승인","반려","서류추가요청"], "context": {...}}
  ⋯ (사람이 다음 턴에 답을 고름: 예 {"action": "서류추가요청", "field": "소득증빙서류"}) ⋯
resume("subscription_status", context, "manual_review", {"action": "서류추가요청", "field": "소득증빙서류"})
  └─ tool_spec = registry.tool_for("subscription_status")  → tool_spec.workflow_registry (= subscription_status.workflow.steps)
     context["human_action"] = {"action": "서류추가요청", "field": "소득증빙서류"}
     └─ StateMachine(registry=tool_spec.workflow_registry, entry="manual_review").run(context)  — 멈췄던 지점부터 재개
          (Runner.run()을 다시 안 탐 — § 위 "SDK 마이그레이션" 절의 human_action 설계)
          └─ manual_review(context) 재호출 — 이번엔 context["human_action"]이 있음
               → @human_action이 action("서류추가요청")을 choices로, payload({"field":...})를
                 payload_schemas["서류추가요청"]으로 검증 (밖이면 ValueError)
               → context["last_result"]["manual_review_decision"] = {"action": "서류추가요청", "field": "소득증빙서류"}
               outcome = "서류추가요청" → next 맵에 따라 종료(DONE)
     → context["last_result"] 반환
```

나머지 두 tool은 같은 골격(모델이 tool 선택 → tool 함수 실행)을 훨씬 짧게 탄다.

```
handle("서울 날씨 알려줘")
  → weather(location="Seoul")   [services/weather/workflow.py]
     └─ WeatherAdapter().execute(location="Seoul")  — 분기/재시도가 없어 WorkflowRegistry/StateMachine 없이 직접 호출
          ├─ call()      → 지오코딩(도시명→좌표) + Open-Meteo 현재 날씨 실 호출
          └─ normalize() → mapping.json(WMO code) 조회 → {"condition": "대체로 맑음", ...}

handle("A123 신청자의 진행상황과 그 지역 날씨를 알려줘")
  → subscription_weather_flow(applicant_id="A123")   [services/subscription_weather_flow/workflow.py]
     └─ StateMachine(entry="query_subscription").run(context)
        ├─ query_subscription: registry.tool_for("subscription_status")(applicant_id="A123") 직접 호출
        │    (SDK Runner를 안 거침 — output_schema_guardrail의 대상 아님, 다만 validate_tool_output()은
        │    subscription_status() 본문 안에서 그대로 실행됨)
        │    → context["subscription_result"] = {..., "region": "Seoul"}
        └─ query_weather: registry.tool_for("weather")(location=subscription_result["region"]) 직접 호출
             → context["weather_result"] = {...}
     → {"subscription": ..., "weather": ...} 반환
        └─ validate_schema(result, {"subscription": ..., "weather": ...}) — 각 tool의 output_schema를
           registry에서 가져와 중첩 검증, 위반 시 GuardrailViolation
```

## 로깅

`LOG_LEVEL` 환경변수(`.env`, 기본 `INFO`)로 전체 로깅 레벨을 정한다. `main.py`가 기동 직후 `configure_logging()`을 한 번 호출해 표준 `logging`을 설정하므로, 이후 `discover_services()`부터 `handle()`까지 전 과정이 같은 스트림에 시간순으로 찍힌다 — 요청 하나가 SDK Runner의 tool 선택부터 state machine의 스텝 전이, 어댑터 호출, (있다면) 사람의 판단 대기/재개까지 어떻게 흘렀는지 콘솔 출력 하나로 전부 볼 수 있다(§ 위 "요청 하나의 전체 흐름"과 대응).

- **INFO** (기본값): "지금 어떤 단계를 지나는지"만 보여주는 요약 라인 — `main.py`의 요청 수신/완료, `_log_run_items()`의 tool 호출 순서, trace/span 시작·종료(들여쓰기로 중첩 깊이 표현), state machine 스텝 전이, judged/human_action 노드의 최종 선택("state machine paused: ... awaiting human action from (...)" 포함), (judged 노드가 실제로 모델을 호출하면) OpenAI 호출의 모델명·길이·응답 미리보기.
- **DEBUG**: 위에 더해 어댑터 `call()`/`normalize()`의 실제 payload, guardrail 관찰/검증 상세, OpenAI system/user 프롬프트 원문까지 — 로컬 디버깅 전용. 레거시 원시값이나 프롬프트에 개인정보가 실릴 수 있으므로 운영 환경에서는 켜지 않는다.
- **WARNING 이상**: 정상 흐름은 거의 안 찍히고 예외 직전 `ERROR` 로그만 남는다.

`LOG_LEVEL=INFO`로 `subscription_status` 하나를 조회하면 이런 식으로 찍힌다(시간은 매번 다름):

```
INFO  agent_loop.main              | request received: 'A123 신청자의 subscription_status 조회해줘'
INFO  agent_loop.tracing           | span start [step] fetch_status
INFO  agent_loop.tracing           | span end   [step] fetch_status duration=0.000s
INFO  agent_loop.state_machine     | step 'fetch_status' -> outcome='서류미비' -> next='DONE'
INFO  agent_loop.state_machine     | state machine done: step='fetch_status'
INFO  agent_loop.main              | run items (2): ['ToolCallItem', 'ToolCallOutputItem']
INFO  agent_loop.main              | request done: result={...}
```
**SDK 마이그레이션으로 바뀐 부분(실제 코드 확인).** `harness/tracing.py`의 `Tracer.start_trace()`(`kind="orchestrator"` 루트를 여는 메서드)는 예전엔 `Orchestrator.handle()`이 요청마다 호출했는데, 지금은 어디서도 호출되지 않는다(`main.py`에 이 호출이 없음, grep으로 확인) — 그래서 `"trace ... start/end [orchestrator]"` 로그 줄 자체가 더 이상 안 찍힌다. `StateMachine.run()`이 여전히 `tracer.span(kind="step")`을 쓰기 때문에, 활성 trace가 없는 이 상태에서는 `span()`의 fallback 경로(스택이 비어있으면 이름 없는 암묵적 루트를 열었다가 빠져나갈 때 바로 정리, § 아래 `harness/tracing.py` 절)가 항상 켜진 채로 동작한다 — 요청 하나 안에서 열고 닫히는 span 자체는 그대로지만, 그걸 감싸던 최상위 "trace" 로그 줄만 사라졌다. "누가 이 tool을 골랐는가"는 이제 `Tracer`가 아니라 `_log_run_items()`가 보여준다.

`subscription_weather_flow`처럼 tool이 다른 tool을 직접 호출하는 경우, 안쪽 `subscription_status`가 여는 `state machine start`/`span`이 바깥쪽 `query_subscription` 스텝 span 밑에 한 단계 더 들여써져서 나온다 — 합성 관계가 로그 들여쓰기 그대로 드러난다. `weather`는 이제 자체 `StateMachine`이 없어 `query_weather` 스텝 span 밑에 별도 "state machine start" 없이 어댑터 호출 로그만 바로 붙는다.

**알려진 한계**: `Tracer._stack`은 `Tracer` 싱글턴 하나가 공유하는 상태라 스레드 세이프하지 않다 — 지금 스캐폴드는 요청을 동기적으로 하나씩 처리하는 걸 전제로 하며, 나중에 요청을 동시에(멀티스레드/비동기) 처리하게 되면 이 부분을 `contextvars` 기반으로 바꿔야 한다.

## 설계축 ↔ 코드 매핑

| 설계 문서의 개념 | 코드 |
|---|---|
| 오케스트레이터 (인터페이스에만 커플링) | SDK `Agent`+`Runner.run_sync()` (`main.py`의 `build_triage_agent()`/`handle()`) |
| Tool Registry (양면 어댑터의 의미론적 면 등록 + SDK `FunctionTool` 조립) | `registry.decorators.ToolRegistry` / `@tool` |
| 프로토콜적 면 vs 의미론적 면 분리 | `adapters.base.BaseAdapter.call()` vs `.normalize()` |
| Prompt Store (공통/도메인/few-shot 계층) | `prompts.store.PromptStore` |
| 공통 하네스 — Output 검증 (Agent 단위 관찰 + tool 단위 opt-in 차단) | `harness.guardrail.output_schema_guardrail`(SDK `@output_guardrail`) + `harness.guardrail.validate_tool_output()` |
| 공통 하네스 — Tracing | `harness.tracing.Tracer` |
| 결정론적 분기/순환 | `workflow.registry.WorkflowRegistry.step(next=...)`(파일마다 로컬 인스턴스) + `workflow.state_machine.StateMachine` |
| Judged branch (bounded choices, 판단 주체=모델) | `workflow.registry.WorkflowRegistry.judged(choices=...)` — 현재 등록된 서비스는 없음(§ 아래 한계) |
| Human-in-the-loop judged branch (bounded choices + payload, 판단 주체=사람) | `workflow.registry.WorkflowRegistry.human_action(choices=..., payload_schemas=...)` + `workflow.state_machine.AwaitingHumanAction` + `main.py`의 `resume()`(tool별 `workflow_registry`로 재개) |
| confirmed/inferred 매핑 관리 | `semantic.mapping.SemanticMapping` / `MappedValue` |
| 미확인 값 fail-fast | `semantic.mapping.UnmappedValueError` |
| 도메인 흐름 전체를 하나의 capability로 등록 | `services/subscription_status/workflow.py`의 최상위 `@tool subscription_status` (내부 state machine을 감싸 단일 tool로 노출) |
| 외부 실 API를 가진 서비스 (프로토콜적 면 = 실제 HTTP 호출, 인증 불필요) | `services/weather/adapter.WeatherAdapter.call()` (Open-Meteo 지오코딩 + 현재 날씨) |
| 사람에게 action 목록을 보여주고 고르게 하는 실제 배선 | `services/subscription_status/workflow.py`의 `manual_review()` — `@human_action` + `AwaitingHumanAction`으로 일시정지, `main.py`의 `resume()`으로 재개 |
| 여러 tool을 고정 서브 workflow로 미리 묶기 (결정론적 데이터 의존관계를 모델 판단에 맡기지 않음) | `services/subscription_weather_flow/workflow.py`의 최상위 `@tool subscription_weather_flow` — `subscription_status()` → `weather()` 순차 호출, `region` 필드로 데이터 연결 |
| 고정 조합 없는 tool 간 동적 다중 호출 | SDK `Runner`의 기본 `tool_use_behavior`(`run_llm_again`) + `main.py`의 `_extract_last_tool_output()` |
| 서비스 auto-discovery + 기동 시점 일관성 검사 | `registry.discovery.discover_services()` + `registry.decorators.ToolRegistry.validate()` |
| Optional 필드 + 중첩 스키마 검증 (조합 서비스의 하위 tool 결과까지 명시적으로 검증) | `harness.schema.optional()`(`OptionalField`) + `validate_schema()`의 재귀 검증 — `harness.guardrail`과 `workflow.registry.WorkflowRegistry.human_action`이 공유, `services/subscription_weather_flow/workflow.py`가 `registry.tool_for(name).output_schema`로 각 tool의 스키마를 재사용 |
| 레벨 조절 가능한 단계별 로깅 | `harness.logging_setup.configure_logging()`(`LOG_LEVEL`) + `harness.tracing.Tracer`(span을 로그로도 출력) + `main.py`의 `_log_run_items()`(SDK Runner의 tool 호출 순서) |
| 입력 없는 tool + 결정론적 데이터 의존관계가 없어 별도 tool로 남긴 "목록 → 상세" 패턴 | `services/applicant_list/workflow.py`의 최상위 `@tool applicant_list()` — 표(`table`) 렌더링까지 조립, `subscription_status`로의 후속 조회는 프롬프트로만 안내(§ 위 "입력 없는 목록 조회" 절) |

## 신규 서비스 추가 시 손대는 파일 (엔진 불변성 체크)

두 카테고리가 있다 — 어느 쪽이든 `framework/`도 `main.py`도 손대지 않는 게 목표이고, `discover_services()`(auto-discovery) 덕분에 실제로 그렇게 됐다. `services/<name>/`에 파일을 놓기만 하면 다음 실행 때 `registry.validate()`가 등록/참조 무결성까지 자동으로 확인해준다.

**레거시/외부 어댑터 서비스** (`subscription_status`, `weather`, `applicant_list`, `public_holiday`, `exchange_rate`, `ip_geolocation`, `university_search`) — `guides/legacy_adapter_guide.md`가 최신 체크리스트를 갖고 있으니 그쪽을 우선 참고(중복 유지 방지를 위해 여기선 개요만). 아래 파일을 만든다. `workflow.py`의 모양은 분기/재시도/판단 노드가 있느냐에 따라 갈린다(§ 위 "언제 WorkflowRegistry/StateMachine을 아예 생략하는가").
- `services/<name>/adapter.py` (`BaseAdapter` 상속)
- `services/<name>/mapping.json` — **정규화할 원시 코드값이 있을 때만** 만든다. 외부 API가 이미 사람이 읽을 수 있는 값을 돌려주면(`ip_geolocation`처럼) `SemanticMapping` 없이 `normalize()`에서 dict 형태만 맞추면 된다.
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
- `main.py`의 `build_triage_agent()`는 `Agent(model=...)`를 지정하지 않는다 — SDK 자체의 기본 모델로 동작한다(`OPENAI_MODEL` 환경변수는 이제 tool 라우팅과 무관, 아래 참고). 실제로 어떤 모델을 쓸지 명시적으로 고정하고 싶으면 `Agent(model=...)`를 추가해야 함.
- `OPENAI_MODEL` 환경변수는 `framework/llm/openai_client.py`의 `complete()`(judged 노드가 직접 모델을 호출할 때 쓰는 별도 경로, § 아래 `judged()` 관련 한계)에서만 읽힌다 — 미지정 시 `gpt-4o-mini`로 기본 동작. `manual_review`는 더 이상 이 경로를 쓰지 않으므로(사람 판단으로 전환) 이 항목과 무관해졌다.
- `steps.judged()`(모델이 판단하는 judged branch)는 메서드·`WorkflowRegistry.validate()` 검사·문서까지 다 갖춰져 있지만, `manual_review`가 `steps.human_action()`(사람 판단)으로 전환되면서 지금 `services/` 전체에서 실제로 이 메서드를 쓰는 서비스가 하나도 없다 — `framework/prompts/store.py`의 `compose()` + `framework/llm/openai_client.py`의 `complete()` 조합도 같이 orphan됨. **정리 여부**: 이 조합에 실제로 종속돼 있던 서비스별 산출물, 즉 `services/subscription_status/prompts/manual_review.md`(당시 OpenAI에게 자동승인/수동검토를 판단시키던 프롬프트)는 완전히 죽은 파일이라 삭제했다. 반면 `steps.judged()`·`WorkflowRegistry.validate()`의 judged 검사·`PromptStore.compose()`·`framework/llm/openai_client.py`는 특정 서비스에 종속된 게 아니라 재사용 가능한 프레임워크 능력이라 그대로 남겨뒀다 — 다음에 "사람이 아니라 모델이 판단해야 하는" judged 노드가 생기면 그때 다시 살아있는 예시가 생긴다.
- `steps.human_action()`/`AwaitingHumanAction`/`main.py`의 `resume()`으로 만든 human-in-the-loop 일시정지/재개는 `subscription_status`라는 단일 사례로 검증됐다(Windows 실측 포함, § 위 "SDK 마이그레이션" 절). `resume()`은 tool이 `context["last_result"]`를 그대로 반환한다는 관례에 기대므로 `subscription_weather_flow`처럼 자체적으로 반환값을 조립하는 tool에는 아직 쓸 수 없고, 세션 영속화 계층이 없어 paused response의 `context`를 호출자가 프로세스 메모리 안에서 직접 들고 있다가 넘겨야 한다(재시작하면 유실).
- **미해결 논의 — LangGraph의 checkpointer식 영속화가 필요한가.** 위 항목의 근본 원인은 "멈춘 상태를 프로세스 메모리 밖(DB 등)에 저장했다가, 나중에 다른 프로세스/다른 시점에서도 정확히 그 지점부터 재개한다"는 기능 자체가 없다는 것이다. LangGraph의 checkpointer가 하는 일과 비교하며 논의했는데, `manual_review`가 대표하는 실제 업무(사람이 서류를 몇 시간~며칠 걸려 검토)를 생각하면 이 갭은 실재한다는 데는 동의했다. **아직 구현하지 않음** — 세션 저장소 종류(파일/Redis/DB)와 배포 형태(단일 프로세스 유지 vs 여러 워커로 분산)가 안 정해진 채로 먼저 만들면 나중에 실제 요구사항이 드러났을 때 다시 뜯어고칠 위험이 크다는 판단. 실제로 필요해지는 신호는 (1) 사람이 몇 시간/며칠 뒤에 승인·반려하는 실제(모의가 아닌) 시나리오가 생기는가, (2) 그 사이 서버 재시작이나 여러 인스턴스 분산 배포가 실제로 필요한가 — 이 둘 중 하나라도 나타나면 그때 checkpointer 스타일 영속화를 설계한다.
- **미해결 논의 — 병렬 분기(fan-out/join)가 필요한가.** `StateMachine.run()`(`framework/workflow/state_machine.py:51-94`)은 `current` 변수 하나로 추적하는 순수 순차 루프라 `next`의 outcome이 항상 다음 스텝 "하나"로만 resolve된다 — 여러 스텝을 동시에 실행하고 결과를 합치는 fan-out/join 개념 자체가 없다. "두 서비스의 결과를 같이 들고 다음 지점으로 넘어가야 하는" 요구는 이미 지금 방식(공유 `context`에 각자 순차적으로 결과를 채우는 것 — `subscription_weather_flow`가 실제 사례)으로 충분하다는 데는 합의했다. 진짜 동시 실행(두 호출 사이에 데이터 의존관계가 없어서 지연시간을 줄이려고 병렬로 부르는 것)은 `next`가 여러 타겟을 가리키게 하고 join 지점을 새로 설계해야 하는, 지금 없는 기능이다. **아직 구현하지 않음** — 지금 4개 서비스 중 "의존관계 없는 두 호출을 동시에 불러야 할 만큼 느린" 실제 사례가 없어서, 그런 필요가 실제로 발생할 때까지 보류.
- **미해결 논의 — tool 본문 안에 `complete()`를 직접 박아넣으면 어떻게 되는가.** (이 항목을 처음 적었을 땐 "AI가 결정에 참여하는 지점은 tool 선택뿐"이었지만, SDK 마이그레이션 이후 인자 채우기·다중 tool 체이닝까지 전부 모델의 판단 영역이 됐다(§ 위 "SDK 마이그레이션" 절) — 이 논의 자체(tool 본문에 직접 `complete()` 박기)는 여전히 미구현.) `judged`/`human_action`이 감사 가능성을 위해 bounded choices를 강제하는 것과 달리, tool 함수 본문에서 `framework.llm.openai_client.complete()`를 직접 호출하는 건 파이썬 문법상 막을 방법이 없다 — 다만 그러면 반환값의 형태를 코드 어디에도 선언할 수 없어 `guardrail`/`registry.validate()`/`WorkflowRegistry.validate()`가 검증할 대상 자체가 사라지고, 로그에도 "왜 이 결과가 나왔는지"가 `judged '...' -> '...'` 같은 명확한 라인이 아니라 자유 텍스트 생성으로만 남는다. 즉 "선택은 자유롭되 감사는 가능해야 한다"는 이 프레임워크의 핵심 제약을 그 tool 안에서는 포기하는 트레이드오프다. **아직 구현하지 않음** — 정형화가 원천적으로 불가능한 자유 텍스트 생성이 목적 자체인 tool이 실제로 필요해지기 전까지는 열어둔 질문으로만 남겨둔다.
- **(해결됨, 이제는 역사적 기록 — 아래 두 항목은 SDK 마이그레이션으로 완전히 대체됨) "자연어에서 인자를 추출할 방법이 없다"/"고정 조합 없는 두 tool을 그때그때 이을 방법이 없다"는 두 gap을 이 프로젝트가 손수 구현한 `AgentRunner.extract_arguments()`/`rewrite_request()`/`Orchestrator._resolve_missing_via_other_tool()`(`framework/orchestrator.py`)로 한 번 메웠던 적이 있다.** 두 gap 모두 SDK 마이그레이션 이후엔 그 손수-구현 코드 자체가 통째로 삭제되고, SDK `Agent`+`Runner`의 기본 tool-calling 루프(모델이 스키마 보고 인자를 직접 채우고, 필요하면 여러 tool을 이어서 부름)로 흡수됐다(§ 위 "SDK 마이그레이션" 절, § 위 "근본적 한계" 절의 "(업데이트)" 문단). **다만 두 gap의 근본적인 한계는 여전히 남아있다** — 채워지거나 이어진 값이 맞는지 감사할 방법이 없다는 문제(`limitation.md`), "직전 turn의 결과를 참조"하는 건 여전히 안 풀린다는 점(§ 아래 "목록에서 이름을 보고..." 항목)은 구현 수단이 바뀌었다고 사라지지 않았다.
- **미해결(우선순위 높음) — 복합 의도(compound intent) 요청은 조용히 반쪽만 처리된다.** "143.248.1.1이 속한 나라의 휴일과 대학 5개를 알려줘"처럼 한 요청이 서로 다른 두 tool의 최종 결과(휴일 목록 + 대학 목록)를 동시에 원하는 경우를 실제로 흉내내 실행해봤다. SDK `Runner`가 여러 tool을 이어 부르는 것 자체는 문제없이 되지만(§ 위 "SDK 마이그레이션" 절), `main.py`의 `_extract_last_tool_output()`이 `result.new_items`에서 **마지막** `ToolCallOutputItem` 하나만 취하므로, 최종 응답은 먼저(또는 나중에) 처리된 tool 하나의 결과뿐이고 다른 하나의 요청은 에러·로그 없이 그냥 사라진다 — 예를 들어 `{"universities": [...]}`가 완전히 정상적인 응답 모양으로 돌아온다. 원인은 "요청 하나에 응답 하나"라는 `handle()`의 반환 계약 자체가 여러 tool의 결과를 동시에 담을 자리가 없다는 것 — 인자 채우기(§ 위 항목)는 "선택된 tool 하나의 스키마를 채우는" 문제라 SDK가 그대로 흡수했지만, 이건 "결과 자체가 여러 개여야 하는" 문제라 지금 구조엔 대응할 자리가 아예 없다. **지금까지 실측한 어떤 실패보다 심각하다** — 나머지는 최소한 명확하게 실패하는데, 이건 "확신 없으면 명확히 실패한다"는 이 프레임워크 전체 원칙을 벗어나 정상 응답처럼 보이는 부분 성공을 돌려준다. `StateMachine`의 fan-out/join 부재(§ 아래 "병렬 분기" 항목)와 겉보기엔 비슷하지만 그건 **한 tool 내부 workflow**의 순차 제약이고 이건 **`_extract_last_tool_output()`이 tool 결과를 하나만 반환**하는 층의 제약이라 서로 다른 지점이다. **아직 구현하지 않음** — 해법 후보(여러 `ToolCallOutputItem`을 전부 모아 반환하도록 바꾸기 / `subscription_weather_flow`처럼 조합마다 고정 서비스를 미리 만들기) 둘 다 논의했으나, 지금 규모(서비스 8개)에서 구체적 need가 쌓이기 전까진 열어둔 질문으로만 남긴다(§ `limitation.md`의 "증거 3"에 실측 상세).
- **미해결 논의 — `manual_review` 앞에 AI 기반 중요도 분류(triage)를 넣을지.** 지금은 `fetch_status`가 `status_confidence != "confirmed"`면 무조건(예외 없이) `manual_review`(사람 판단)로 보낸다. "덜 중요한 판단은 AI에게 위임하고 싶어질 수도 있다"는 논의가 나왔는데, 이건 사실 이 프로젝트가 이미 한 번 시도했다가 되돌린 구조와 같다 — 외부 커밋으로 처음 들어왔을 때 이 지점은 `@judged`가 "자동승인"/"수동검토" 중 뭘 고를지 AI가 판단하는 구조였고, "`manual_review`라는 이름의 노드 안에서 AI가 자동으로 판단한다"는 게 이름과 행동이 모순돼 지금의 `human_action`(사람이 직접 승인/반려)으로 바꿨다(§ "human-in-the-loop" 절). 다시 넣는다면 그 모순을 반복하지 않도록 **역할을 분리**해야 한다는 데는 논의 중 합의했다 — 예: 새 `judged()` 노드 `triage`를 하나 더 두어 bounded choices를 "경미"/"중요" 같은 **중요도 분류로만** 한정하고(승인/반려를 직접 고르게 하지 않음), "경미"는 별도 자동 처리 경로로, "중요"는 지금처럼 `manual_review`로 보낸다 — 이러면 `triage`(AI가 함)와 `manual_review`(사람이 함)가 이름과 실제 행동이 어긋나지 않는다. **아직 구현하지 않음** — "누군가 원할 수도 있겠다"는 가정 단계일 뿐 구체적인 need가 아직 없어서, 실제로 사람에게 넘어가는 케이스 중 "이건 AI가 걸러줬어도 됐을 텐데"라는 구체적 사례가 쌓이기 전까지는 보류.
- human_action의 action은 여전히 "라벨 + payload"로만 끝난다 — action이 실제로 다른 capability를 호출·연결하는 것(예: `"서류추가요청"`이 서류 재제출 처리 tool로 실제 핸드오프하는 것)은 의도적으로 미룬 범위다. 실제로 연결할 대상 capability가 생기면 그때 실행 로직을 얹기로 함(YAGNI로 미룬 것이지 빠뜨린 게 아님).
- **미해결 논의 — `main.py` 경계에 일반 예외 처리(구조화된 에러 응답)가 필요한가.** 지금 `handle()`/`resume()`은 `AwaitingHumanAction`(및 그걸 감싼 SDK `UserError`) 하나만 특별 취급해서 `{"status": "awaiting_human_action", ...}`로 바꿔준다. 그 외 예외 — `GuardrailViolation`, `UnmappedValueError`, `MaxRetriesExceeded`, `judged`/`human_action`/`next` 위반의 `ValueError`, 어댑터 내부의 버그나 네트워크 에러까지 — 는 전부 어디서도 안 잡히고 호출자까지 그대로 터진다. 확인 중에 관련 gap도 하나 찾았다: `Tracer.span()`/`start_trace()`(`framework/harness/tracing.py`)가 `try/finally`만 써서, 예외로 끝나든 정상 종료든 "span end" 로그 줄이 똑같다 — 로그만 보고는 그 tool 호출이 성공했는지 터졌는지 구분이 안 된다. **아직 구현하지 않음** — 초기 단계에서는 안 막아야 버그가 바로(크래시로) 드러난다는 판단으로 의도적으로 보류했다. 채팅 UI 등에서 tool 하나의 실패로 전체 대화가 끊기면 안 되는 실제 배포 상황이 생기면, 그때 `AwaitingHumanAction`과 같은 패턴(`{"status": "error", "tool": ..., "error_type": ..., "detail": ...}`)으로 경계에서 잡아 구조화하고, tracing의 실패 표시 gap도 같이 고친다.
- `ToolRegistry.validate()`(tool 카탈로그)와 `WorkflowRegistry.validate()`(파일별 step/next/judged/human_action) 둘 다 참조 무결성만 본다 — "adapter.py가 BaseAdapter를 상속했는가", "mapping.json이 실제로 존재하는가" 같은 파일 시스템/클래스 계층 검사나, "새 tool description이 기존 tool과 의미가 안 겹치는가" 같은 의미적 검사(`guides/legacy_adapter_guide.md` 체크리스트 항목)는 하지 않는다 — 이런 건 코드로 자동 판별하기 어려워 사람 리뷰 영역으로 남겨둠.
- **(해결됨, 참고로 남김)** 원래 `workflow_step`/`next`/`order`가 전역 `ToolRegistry`에 이름만으로 등록돼 있었다 — 다른 파일과 스텝 이름이 겹치면 조용히 덮어써지고, `next` 참조가 다른 서비스로 새는 것도 막을 방법이 없었고, `order`가 "이 workflow 안에서 몇 번째"라는 걸 전역에서는 표현할 수 없었다(같은 스텝이 여러 workflow에 다른 순서로 조합될 수 있으므로). `workflow/registry.py`의 `WorkflowRegistry`로 분리해 각 파일이 자기 전용 인스턴스를 갖게 하면서 세 문제 모두 구조적으로 해소됨(§ 위 `workflow/registry.py` 절). 다만 `WorkflowStepSpec.order`/`.source`는 지금도 여전히 저장만 되고 `StateMachine.run()`을 포함해 어디에서도 읽히지 않는 죽은 필드다 — 실행 순서는 순전히 `entry` + `next` 체인만으로 결정된다. 지금은 사람이 읽을 때(코드 리뷰) 실행 순서를 가늠하는 문서화 용도로만 쓰이며, 실제로 강제되는 값이 아니라는 점에 주의.
- `steps.judged(choices=..., confidence_required="confirmed")`의 `confidence_required`는 `workflow.registry.JudgedSpec`에 저장만 되고 실제로 어디서도 읽거나 검사하지 않는다 — "inferred 값은 judged 판단에 넘기면 안 된다"는 규칙은 지금 `fetch_status`가 `status_confidence != "confirmed"`를 직접 체크해서 우회 진입시키는 방식으로만 지켜지고, `judged()` 자체는 이 제약을 강제하지 않는 미완성 지점이다.
- `subscription_weather_flow`가 내부에서 직접 호출하는 `subscription_status()`/`weather()`는 SDK `Runner`를 거치지 않으므로 Agent 단위 `output_schema_guardrail`의 대상이 안 된다(§ "서비스를 조합하는 서비스" 절) — 다만 각 tool 본문 안의 `validate_tool_output()`은 그대로 실행되므로 output 검증 자체가 우회되는 건 아니다. SDK 마이그레이션으로 guardrail이 tool 단위에서 Agent 단위로 넘어가면서 "input을 boundary에서 검증한다"는 개념 자체가 없어졌다(§ 위 "SDK 마이그레이션" 절 4번 항목) — 지금은 input 검증이 SDK가 함수 시그니처로 하는 타입 체크뿐이라, 예전의 "input_schema 우회" 걱정은 그 형태로는 더 이상 유효하지 않다.
- **(해결됨, 완전히 폐기됨 — 참고로 남김)** `subscription_weather_flow`가 다른 서비스의 output 스키마를 참조할 때 한동안 `output_schema=lambda: {...}` 형태의 thunk(그리고 그걸 감춘 `ToolRegistry.output_schema_for(name)`/`input_schema_for(name)` 헬퍼)를 썼다 — guardrail이 tool 단위였던 시절, `@guardrail(output_schema=...)`가 모듈 로드 시점에 그 값을 필요로 했는데 `discover_services()`가 아직 모든 서비스를 등록 못 했을 수 있어서(알파벳 순서상 `subscription_weather_flow`가 `weather`보다 먼저 import됨) 즉시 읽으면 `None`을 가져오는 버그를 우회하기 위한 설계였다. **SDK 마이그레이션으로 이 메커니즘 자체가 완전히 없어졌다** — 지금은 `output_schema`를 tool 함수 **호출 시점**(모듈 로드 시점이 아니라)에 `registry.tool_for(name).output_schema`로 바로 읽으므로(§ "서비스를 조합하는 서비스" 절), 늦은 평가를 위한 thunk/lambda가 애초에 필요 없다.
- `ApplicantListAdapter.call()`은 20명 고정 스텁(하드코딩된 리스트) — 실제 레거시 목록 조회 API 연동 시 교체 필요. `applicant_list`와 `subscription_status`가 값은 동일하지만 서로 다른 `mapping.json`을 갖고 있어서(§ 위 "입력 없는 목록 조회" 절 — 의도적 설계), 실제로 상태 체계가 바뀌면 두 파일을 각각 갱신해야 한다는 걸 잊기 쉽다.
- **미해결 논의 — 서비스 간 "겹치는 필드"를 어떻게 다룰지.** 위 항목의 근본 원인은 두 서비스의 output이 스키마 전체가 겹치는 것도 완전히 독립적인 것도 아니라, 일부 필드만 겹친다는 데 있다(`applicant_id`/`status`/`status_confidence`는 같은 도메인 개념이라 일치해야 하고, `region`/`manual_review_decision`/`name`은 각 서비스 고유). 스키마 전체를 합치거나 완전히 분리하는 이분법 대신, 겹치는 조각만 뽑아 공유 자산으로 만들고(예: 도메인을 대표하는 서비스가 `MAPPING_PATH`/상태 enum 상수를 export하고 다른 서비스가 그 조각만 import) 안 겹치는 필드는 각자 스키마에 남기는 방향으로 논의했다. 프레임워크 차원 규약(`"confirmed"/"inferred"` 같은 `SemanticMapping` 자체의 값)과 도메인 차원 지식(청약 상태 5종 같은 특정 서비스의 값)은 공유 주체가 다르다는 점(전자는 `framework/semantic/mapping.py`, 후자는 그 도메인을 대표하는 서비스)도 같이 짚었다. **당시엔 아직 구현하지 않음** — 실제 use case가 명확해지기 전까지는 의도적으로 보류했었다.
  - **이후 실제 사례로 확인됨.** `public_holiday`/`university_search`를 추가할 때 "국가"라는 겹치는 개념을 alpha-2로 통일시키기로 사람이 직접 결정했다(우연이 아니라 의도적 지시) — 가정이었던 "파라미터가 여럿이고 일부만 겹치는 상황"이 실제로 발생한 사례다. 다만 이 결정은 지금도 코드/문서에 **명시적으로 선언**돼 있지 않다 — `guides/legacy_adapter_guide.md` §3가 실무적으로 이 결정을 따르고는 있지만 "이 프로젝트의 국가 정준 표현은 alpha-2다"라고 못박아 둔 자리는 없다(§ `limitation.md`의 "업계 비교" 절에 상세). 이걸 명문화하는 작업 자체는 아직 안 함.
- "목록에서 이름을 보고 다음 요청에 applicant_id를 넣는" 연결은 프롬프트 문구(`prompts/applicant_list.md`)로만 안내할 뿐, 실제로 이름→ID를 찾아 다음 tool 호출의 인자를 채우는 로직은 어디에도 없다. SDK가 인자 채우기 자체는 기본으로 처리하지만(§ 위 "SDK 마이그레이션" 절), 이 특정 시나리오는 여전히 안 풀린다 — `handle(request)`가 매 호출마다 새 `Agent`/새 `Runner.run_sync()`를 돌리므로, 그 turn의 `request` 텍스트 밖에 있는 정보(직전 turn에 `applicant_list`가 보여준 표에서 김민준이 A101이었다는 사실)를 모델이 알 방법이 없다(대화 히스토리/이전 결과를 이어주는 경로가 없음). 이걸 풀려면 이전 turn의 결과를 다음 요청에 컨텍스트로 넘기는 별도 배선(SDK의 `Session`/대화 히스토리 기능을 쓰거나 직접 구현)이 필요하다 — 아직 안 함.
- `applicant_list`의 `_render_table()`이 만드는 표 포맷(지금은 마크다운 파이프 표)은 **미확정 상태로 남겨둔 것**이다 — "예쁘게 보여주는" 방법은 이 결과를 최종적으로 어디서 보여주느냐(마크다운 렌더링 채팅 UI / raw text 전용 뷰 / 자체 웹 프론트엔드의 테이블 컴포넌트 / 다른 서비스의 프로그램적 소비)에 따라 완전히 달라지는데, 그 실행 환경 자체가 아직 정해지지 않았다. 환경이 정해지기 전까지는 raw text 정렬 로직(한글 폭 계산 등) 같은 특정 방향으로 미리 구현하지 않기로 함 — 다음 작업은 환경이 확정된 뒤 그에 맞는 포맷으로 `_render_table()`을 바꾸는 것.
