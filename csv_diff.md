# CSV 대조 — 의뢰측 스켈레톤(SFA list) vs 현재 프로젝트(`aiai`)

`인공지능에이전트_SFA_list.csv`(의뢰측이 만든 "청약진행상황 AI Agent" 설계서, OpenAI Agents SDK + Qwen 기준 22개 서브시스템 분해)와 이 저장소(범용 Agent Loop 프레임워크, `subscription_status`가 첫 사례)를 대조한 기록이다. 이 저장소는 **OpenAI Agents SDK를 쓰지 않는다** — `openai` 원시 SDK로 `complete()` 하나만 얇게 쓰고, 나머지(레지스트리·가드레일·트레이싱·상태기계·오케스트레이터 라우팅)는 전부 자체 구현이다. 이 차이가 아래 모든 대조의 근본 원인이다.

## 1. 22개 서브시스템 대조

### 강하게 대응됨 (이미 있음)

| No | CSV 서브시스템 | 이 프로젝트의 대응물 |
|---|---|---|
| 10 | Service Registry | `ToolRegistry` + `discover_services()` + `@tool` — 폴더 1개=서비스 1개, 선언만으로 등록되는 구조가 거의 동일 |
| 11 | Legacy Adapter | `BaseAdapter`(call/normalize 분리) + 서비스별 `adapter.py` — 원칙까지 똑같음 |
| 17 | Function Tools | `@tool` + `_infer_schema()`(타입힌트로 인자 스키마 자동생성) — 정확히 같은 패턴 |
| 19 | Triage Agent | `AgentRunner.choose_tool()` — `common/orchestrator.md`에서도 스스로 "Triage Agent"라고 부름 |
| 15 | Flow Harness (FlowSpec + Hooks) | `WorkflowRegistry`/`StateMachine`의 `next` dict — "정해진 절차를 상태기계로 선언하고 매 시점 허용 전이만 대조"라는 설명이 거의 그대로 일치 |
| 7 | Observability | `Tracer`(Trace/Span 중첩) + `configure_logging()`(LOG_LEVEL) — 자체 구축 방향까지 일치(CSV도 Qwen 전환 시 "자체 프로세서 구축" 필요하다고 적음) |

### 부분적으로만 대응 (개념은 있는데 스코프가 다름)

| No | CSV 서브시스템 | 이 프로젝트 상태 |
|---|---|---|
| 5 | Output Guardrail | `GuardrailChain` — 이름까지 같지만 스코프가 좁음. CSV는 "버튼 id 중복, sent_to 화이트리스트, 위험 액션 confirm, 주민번호 노출"까지 보는 **정책 게이트**인데, 이 프로젝트는 **스키마 형태 검증**(필드 존재/enum)만 함 — 의미론적 정책 검사는 없음 |
| 4 | UI Schema (UIResponse) | `@guardrail(output_schema=...)`가 출력 형태를 강제하는 원리는 같지만, UI 렌더링 계약(agent-ui protocol)이라는 목적은 없음 — 이 프로젝트엔 프론트엔드 자체가 없음(§18) |
| 2 | Agent Loop (Runner) | `Orchestrator._handle()` — 결정적으로 다른 점: CSV의 Runner는 "LLM 호출→툴 실행→재투입"을 **여러 번 반복**하는 진짜 agentic loop인데, 이 프로젝트는 **tool 하나를 딱 한 번** 고르고 끝남(`_resolve_missing_via_other_tool()`이 재귀 재시도를 일부 도입했지만 "누락된 인자 하나 메우기" 용도지 범용 반복 루프가 아님) |
| 6 | Model Provider 추상화 | `framework/llm/openai_client.py`의 `complete()` — 얇은 wrapper는 있지만 OpenAI 전용, Qwen/vLLM 스위치 추상화는 없음 |
| 16 | Service Agent | `subscription_status` tool이 도메인 구현체 역할은 하지만, **LLM이 자유롭게 tool을 골라 부르는 게 아니라 완전히 결정론적인 StateMachine**이라 "instructions+tools를 들고 알아서 업무를 수행하는 에이전트"라는 CSV 정의와는 성격이 다름 |

### 아예 없음

| No | CSV 서브시스템 |
|---|---|
| 1 | Session Store (멀티턴 대화 저장/복원) |
| 8 | Chat Gateway (FastAPI `/chat` 엔드포인트) |
| 9 | 인증·개인정보 경계 (customer_id 확정, PII 마스킹) |
| 12 | API Handler Registry (LLM 없이 결정적 실행 액션) |
| 13 | 에러/폴백 UX (표준 에러 화면) |
| 14 | 구조화 출력 폴백·검증 래퍼 |
| 18 | Frontend Renderer |
| 20 | Eval Runner (골든 시나리오 자동 회귀 테스트) |
| 21 | LLM Judge (사후 품질 채점 — `judged()`와는 다름, 그건 런타임 판단 노드) |
| 22 | 프롬프트·정책 버전 관리 |

### 요약

이 프로젝트는 CSV의 22개 중 **"core 엔진 배선"에 해당하는 부분(Registry/Adapter/Tool/Triage/Flow Harness/Observability)은 상당히 탄탄하게 대응**되지만, **"실제 서비스로 배포하는 데 필요한 주변부"(세션 저장, HTTP 게이트웨이, 인증/PII, 에러 UX, 프론트엔드, 자동 평가)는 거의 다 없다** — 이 프로젝트가 처음부터 "프레임워크 스캐폴드"로 설계됐지 실제 서비스 배포체가 아니었기 때문으로 보인다.

## 2. SDK로 대체 가능했을 자체 구현 분석

이 프로젝트가 OpenAI Agents SDK를 아예 안 쓰기로 한 결정 때문에, CSV가 "SDK 제공"이라 표시한 기능들을 전부 손으로 다시 만들게 됐다. CSV의 "대응 SDK 기능" 열과 이 프로젝트의 자체 구현물을 맞대보면:

### 진짜 SDK로 대체 가능한 것 (군더더기 재구현)

**(업데이트) 아래 표의 항목 중 위 3개는 실제로 마이그레이션 완료** — `ARCHITECTURE.md`의 "SDK 마이그레이션" 절 참고. 나머지 2개(Triage handoff, Tracing)는 flat 구조로 시작하기로 해서(handoff 트리는 도메인이 늘면 나중에) 이번 1차 이관 범위에서 뺐다.

| 이 프로젝트의 자체 구현 | CSV가 말하는 SDK 대응 기능 | 평가 | 상태 |
|---|---|---|---|
| `ToolSpec`/`_infer_schema()` (`@tool`) | `@function_tool`(스키마 자동생성 + Pydantic 검증) | 거의 클론 수준. 타입힌트→스키마 자동생성이라는 동일한 아이디어를 처음부터 다시 짠 것 | ✅ 완료 |
| `GuardrailChain` | `@output_guardrail` + tripwire (훅 기반 차단) | SDK가 이미 "검사→차단" 훅 포인트를 제공하는데, 그 위에 얹는 대신 검증 체인 전체를 새로 만듦 | ✅ 완료(단, tool 단위→Agent 단위로 검증 granularity가 넓어지는 트레이드오프 수용) |
| `AgentRunner.choose_tool()`(+`extract_arguments`/`rewrite_request`/`_resolve_missing_via_other_tool`) | `Agent(tools=[...])` + `Runner.run()`의 기본 멀티턴 tool-calling 루프 | Triage 패턴+동적 인자추출+동적 tool 연결까지 전부 손으로 재구현 — SDK가 기본으로 다 함 | ✅ 완료(flat 구조, handoff 트리는 보류) |
| `context: dict[str, Any]`를 손으로 여기저기 넘기는 것 | `RunContextWrapper[T]` | SDK가 실행 중 context를 자동으로 들고 다니는 그릇을 제공하는데, 매 함수 시그니처마다 `context` dict를 수동으로 전달 | 보류 — 지금 어떤 tool도 실행 전체에 걸쳐 공유되는 context가 실제로 필요하지 않아서(각 tool이 자기 내부 context를 스스로 만듦), 굳이 SDK 개념을 끌어올 이유가 아직 없음(YAGNI) |
| `Tracer`/`Span` | `TracingProcessor` + `set_trace_processors` 훅 | OpenAI를 계속 쓴다면(이 프로젝트가 그럼) 이 훅에 얹으면 됐는데 완전 별도 구현을 만듦 | 보류 — 우선순위 낮음, 지금 `Tracer`는 `StateMachine` 내부 스텝 단위까지 로깅해서 SDK 레벨 트레이싱과 완전 대체는 아님 |
| `WorkflowRegistry`/`StateMachine`의 "허용된 전이만 통과" 부분 | `AgentHooks.on_tool_start`/`on_tool_end` | 툴 호출 시점마다 가로채는 훅이 SDK에 이미 있는데, 그 감시 로직 전체를 별도 상태기계로 새로 만듦 | 유지 — 아래 "자체 구현이 오히려 정당한 것" 참고, 애초에 대체 대상 아님 |

### 자체 구현이 오히려 정당한 것

- **`StateMachine`의 결정론적 그래프 자체** — SDK의 `Agent`는 기본적으로 "LLM이 매 턴 자유롭게 다음 tool을 고르는" 루프다. 이 프로젝트가 원하는 "그래프 위상은 코드로 고정, 판단은 bounded choices 안에서만"이라는 목표는 SDK의 기본 동작과 **정반대 방향**이라, 훅으로 감싼다 해도 SDK의 자유 루프 위에 억지로 제약을 씌우는 셈이 된다 — 처음부터 별도로 만든 게 오히려 자연스러운 선택.
- **Model Provider 추상화를 안 만든 것** — CSV는 Qwen 전환 때문에 이게 꼭 필요했지만, 이 프로젝트는 OpenAI 하나만 쓰므로 지금 당장은 필요 없다(추상화 안 만든 게 미비가 아니라 아직 그 need가 없는 것).

### 핵심 결론

이 프로젝트가 "OpenAI Agents SDK를 아예 안 쓰기로 한 결정" 자체가, 위 표의 자체 구현물 대부분을 파생시킨 근본 원인이다. SDK를 실제로 도입하면 왼쪽 열 대부분을 걷어내고 SDK 호출로 대체할 수 있는데, 대신 `StateMachine`이 강제하는 "그래프 고정 + bounded 판단"이라는 이 프로젝트의 핵심 설계 원칙을 SDK의 자유 Agent 루프 위에 어떻게 다시 강제할지를 새로 풀어야 한다 — 이게 SDK 도입 여부를 결정할 때 진짜 트레이드오프다.

---
관련 문서:
- `ARCHITECTURE.md` — 이 프로젝트의 as-built 구현 근거
- `ai_framework_2.md` — 이 프로젝트가 처음에 고른 설계 철학(왜 SDK를 안 쓰고 bounded choices를 강제하는 자체 엔진을 택했는지)
- `limitation.md` — 이 설계가 만드는 구조적 한계(자연어→정준 표현 변환, 복합 의도 요청 등)
