# 신규 서비스 추가 가이드

`services/subscription_status`(레거시 어댑터 + 분기 + human-in-the-loop), `services/weather`(단순 어댑터, 분기 없음), `services/subscription_weather_flow`(조합 서비스), `services/applicant_list`(입력 없는 단순 어댑터)가 아래 각 절의 살아있는 예시다. `ARCHITECTURE.md`가 "왜 이렇게 됐는가"를 설명하는 문서라면, 이 가이드는 "새 서비스를 만들 때 뭘 어떻게 쓰면 되는가"에 집중한다.

**(2026-08-07 업데이트)** `@tool`이 이제 OpenAI Agents SDK의 `function_tool()`을 감싼다 — `@guardrail`이라는 별도 데코레이터는 더 이상 없다(제거됨), `output_schema`는 `@tool(...)`의 키워드 인자로 합쳐졌다. tool 라우팅·인자 추출·다중 tool 체이닝은 이제 `main.py`의 `Runner.run_sync()`(SDK)가 처리한다. 자세한 배경은 `ARCHITECTURE.md`의 "SDK 마이그레이션" 절 참고 — 이 가이드는 그 결과로 바뀐 실무 절차만 반영한다.

## 1. 새 서비스 추가 시 만들 파일

| 파일 | 필수 여부 |
|---|---|
| `services/<name>/workflow.py` | **항상 필수** — 파일명 고정. `discover_services()`가 정확히 이 이름을 스캔하므로 다르면 그냥 무시된다(등록 자체가 안 됨) |
| `services/<name>/prompts/<tool_name>.md` | 항상 필수 — 이 tool 전용 프롬프트 |
| `services/<name>/adapter.py` + `services/<name>/mapping.json` | **레거시/외부 연동이 있는 서비스만.** 다른 이미 등록된 tool을 조합하는 서비스는 만들지 않는다(§4) |

`main.py`/`framework/`는 손대지 않는다 — `discover_services()`가 자동으로 찾아 import하고, `registry.validate()`가 기동 시점에 등록/참조 무결성을 검사한다.

## 2. 첫 갈림길 — `WorkflowRegistry`가 필요한가

기준은 딱 하나다: **분기(`next`가 outcome에 따라 갈리는가)·재시도(`max_retries`)·판단 노드(`judged`/`human_action`)가 하나라도 있는가.** "스텝이 몇 개인가"가 아니라 "이 스텝들 사이에 실제로 코드가 결정할 게 있는가"로 판단한다.

**없으면 — `WorkflowRegistry`/`StateMachine`을 아예 안 쓴다.** `@tool` 함수 본문에서 어댑터를 직접 호출하면 끝이다.
```python
WEATHER_OUTPUT_SCHEMA = {...}

@tool(name="weather", description="...", output_schema=WEATHER_OUTPUT_SCHEMA)
def weather(location: str) -> dict[str, Any]:
    result = WeatherAdapter().execute(location=location)
    return validate_tool_output("weather", result)
```
(`weather`, `applicant_list`가 이 패턴 — `applicant_list`는 어댑터 호출 뒤 `_render_table()`로 표현까지 조립한다.) `validate_tool_output(name, result)`(`framework/harness/guardrail.py`)은 선택이지만, tool의 output에 enum/optional 같은 세부 규칙이 있으면 반드시 부른다 — guardrail이 SDK 관례대로 tool 단위가 아니라 **Agent 단위**(`@output_guardrail`)로 옮겨가면서, 이제 어떤 tool이 결과를 만들었는지 그 자리에서 알 수 없어 tool별 세부 검증을 못 하기 때문이다(§ `ARCHITECTURE.md`의 "SDK 마이그레이션" 절, `harness/guardrail.py`의 `output_schema_guardrail` docstring).

**(2026-08-07 추가) `input_schema`/`validate_tool_input(name, kwargs)`는 output과 대칭이지만 기본은 선언 안 하는 쪽이다.** SDK가 함수 시그니처(타입 힌트)로 하는 형태(shape) 체크는 자동이라 신경 쓸 필요 없다 — `input_schema`를 쓰는 건 그 이상의 **의미** 검증(값이 실제 유효한 닫힌 집합 안에 있는가)이 필요할 때만이다. 판단 기준: 이 인자를 사용자가 매번 직접 타이핑하는가, 아니면 다른 tool의 출력에서 모델이 그때그때 합성해서 채우는가 — 후자(다단계 tool 체이닝의 중간 인자)일수록 검증 없이는 잘못된 값이 그대로 다음 API 호출로 흘러갈 위험이 크다(`public_holiday`/`university_search`의 `country_code`가 실제 사례, `shared/countries.py`의 `ISO_3166_1_ALPHA2`를 재사용). 닫힌 집합이 자연스럽지 않은 자유 텍스트 인자(예: `weather`의 `location`)에는 굳이 선언하지 않는다.
```python
from shared.countries import ISO_3166_1_ALPHA2

MY_TOOL_INPUT_SCHEMA = {"country_code": {"choices": sorted(ISO_3166_1_ALPHA2)}}

@tool(name="...", description="...", output_schema=..., input_schema=MY_TOOL_INPUT_SCHEMA)
def my_tool(country_code: str) -> dict[str, Any]:
    validate_tool_input("...", {"country_code": country_code})  # 함수 본문 맨 앞
    ...
```

**하나라도 있으면 — 파일 전용 `WorkflowRegistry` 인스턴스를 만든다.**
```python
steps = WorkflowRegistry()          # 이 파일 전용 — 다른 서비스와 이름 겹쳐도 충돌 없음

@steps.step(order=1, next={"완료": "DONE"})
def fetch_status(context: dict[str, Any]) -> str:
    ...

steps.validate()                    # 파일 하단에 반드시 — 이 파일만으로 즉시 검증됨

def build_state_machine() -> StateMachine:
    return StateMachine(registry=steps, entry="fetch_status")

MY_TOOL_OUTPUT_SCHEMA = {...}

@tool(
    name="...",
    description="...",
    output_schema=MY_TOOL_OUTPUT_SCHEMA,
    workflow_registry=steps,   # human_action 쓰면 필수
    pausable=True,             # human_action 쓰면 필수 — 아래 설명
)
def my_tool(...) -> dict[str, Any]:
    context: dict[str, Any] = {...}
    build_state_machine().run(context)
    return validate_tool_output("...", context["last_result"])
```
`workflow_registry=steps`와 `pausable=True`는 **`human_action`(pause 가능)을 쓸 때만** 둘 다 필요하다.
- `workflow_registry=steps` — `main.py`의 `resume()`이 멈췄던 지점을 재개하려면 그 tool 전용 `WorkflowRegistry`를 찾아야 하기 때문. 안 넘기면 `resume()` 호출 시 `ValueError`로 막힌다.
- `pausable=True` — SDK의 `function_tool()`은 기본적으로 tool 함수가 던진 예외를 모델에게 보여줄 에러 메시지로 바꿔버린다. `AwaitingHumanAction`이 "일시정지 신호"라는 의미를 유지하려면 이 기본값을 꺼야 한다(`function_tool(failure_error_function=None)`) — `@tool(pausable=True)`가 이 옵트아웃을 자동으로 적용한다. `subscription_status`가 실제 사례.

**`@guardrail`이라는 별도 데코레이터는 이제 없다.** 예전엔 `@tool` 밑에 `@guardrail(output_schema=...)`를 따로 붙였는데, 지금은 `output_schema`가 `@tool(...)`의 키워드 인자로 합쳐졌다.

## 3. 레거시/외부 어댑터 서비스라면

- `adapter.py` — `BaseAdapter` 상속. `call(self, **kwargs) -> dict[str, Any]`(프로토콜적 면 — REST/DB/인증이 이 함수 안에 갇혀야 함, 인자는 전부 keyword-only)와 `normalize(self, raw_response) -> dict[str, Any]`(의미론적 면 — `self.mapping.normalize(...)`로 얻은 `MappedValue`에서 `.value`/`.confidence`를 꺼내 `@tool(output_schema=...)`에 선언한 키와 1:1로 채움)를 분리 구현한다. 원시 코드값 정규화가 필요 없는 외부 API(이미 사람이 읽을 수 있는 값을 주는 경우, `ip_geolocation`이 실제 사례)는 `mapping.json`/`SemanticMapping` 없이 `normalize()`에서 dict 형태만 맞추면 된다.
- `mapping.json` — **정규화할 원시 코드값이 있는 서비스만 만든다** (`BaseAdapter.__init__`은 이걸 요구하지 않는다 — 필요한 어댑터가 자기 `__init__`에서 `self.mapping = SemanticMapping.from_json(...)`으로 직접 든다). 만들 땐 이 서비스 전용으로 새로 만든다 — 값이 다른 서비스와 우연히 같아도(예: `applicant_list`와 `subscription_status`의 상태 5종) import로 공유하지 않는다("서비스는 자기 매핑 자산을 스스로 갖는다"는 원칙). 각 엔트리는 `{"value": <정규화 문자열>, "confidence": "confirmed" | "inferred"}` 형태다.
  - `confirmed`는 사람이 레거시 명세나 실측으로 검증을 마친 매핑, `inferred`는 코드만 보고 추정했지만 아직 검증되지 않은 매핑이다.
  - 매핑에 아예 없는 raw 코드값은 `inferred`로 대충 채우지 않는다 — `UnmappedValueError`로 fail-fast하게 두고 그대로 전파시킨다("모르는 값은 모른다고 실패").
- **`inferred` 값은 판단 분기(`judged`/`human_action` 이외의 곳)에서 그대로 쓰면 안 된다.** `fetch_status`가 `result["status_confidence"] != "confirmed"`를 직접 체크해 `"미확인"` outcome으로 `manual_review`(human_action)에 위임하는 게 표준 패턴이다.
- 승격(promotion): `inferred` 값이 반복 관측되면 사람이 실제 레거시 스펙을 확인해 `mapping.json`의 `confidence`를 `"confirmed"`로 바꿔야 한다는 신호다 — 이 확인은 코드가 자동으로 하지 않는다.
- **다른 tool과 개념이 겹치는지 먼저 확인한다.** 새 어댑터가 다루는 값(국가/통화/날짜/ID 등)을 이미 등록된 다른 tool도 다룬다면, 그 tool이 어떤 표현 규약을 쓰는지 먼저 확인하고 같은 규약을 따른다 — `registry.validate()`/`WorkflowRegistry.validate()`는 이런 의미적 중복·불일치를 검사하지 않으므로 사람이 직접 확인해야 한다(`limitation.md`의 핵심 논지 — "질문의 방법론은 사전에 결정된다"는 것을 여기서 실무적으로 만난다).
  - 외부 API 자체가 그 규약과 다른 형식을 요구하면(예: `country_code`를 쓰는 `public_holiday`와 달리 Hipolabs Universities API는 자유 국가명 문자열만 받음), 변환은 어댑터 내부에 가둔다 — `services/university_search/adapter.py`가 실제 예시다. 공개 입력은 다른 tool과 같은 규약(`country_code`)으로 받고, `call()` 안에서 `SemanticMapping`(여기선 출력이 아니라 **입력값 정규화** 용도로 재사용)으로 그 API가 실제로 원하는 문자열로 변환한다.
  - 이 변환을 코드로 자동화하려면, 두 표현이 동시에 나타나는 **공통 데이터(다리)**가 실제로 있는지부터 확인한다 — `university_search/mapping.json`은 Hipolabs API 자신의 응답에 `alpha_two_code`와 `country`가 같이 오길래 거기서 뽑아낸 것이지, 손으로 지어낸 게 아니다. 그런 다리가 없으면 억지로 맞추지 말고, 파라미터 이름 자체를 다르게 지어(`country_code` vs `country`처럼) 최소한 그 차이가 겉으로 드러나게 한다.

## 4. 조합 서비스(다른 tool을 부르는 서비스)라면

**먼저 확인할 것 — 정말 고정 조합(`WorkflowRegistry` 기반)으로 만들어야 하는가?** SDK로 옮긴 뒤로는 `main.py`의 triage `Agent`가 필요하면 tool을 여러 번 동적으로 이어서 부르는 걸 기본으로 처리한다(`tool_use_behavior` 기본값 + `_extract_last_tool_output()`, § `ARCHITECTURE.md`의 SDK 마이그레이션 절 — `ip_geolocation`→`university_search`를 이렇게 실측 확인함). 그래서 **A의 결과가 B의 입력이 되는 관계라고 해서 무조건 고정 composition tool을 새로 만들 필요는 없다** — 대부분은 그냥 두 tool을 각자 등록해두면 모델이 알아서 이어 부른다. 아래처럼 이미 만들어져 있는 `subscription_weather_flow`는 "이 조합이 항상 함께 요청된다"는 게 명확해서 하나의 capability로 미리 묶어둔 사례이지, 데이터 의존관계가 있다고 자동으로 이렇게 만들어야 하는 건 아니다. **페어마다 고정 tool을 만드는 걸 습관화하지 말 것** — 조합이 늘어날 때마다 새로 만들어야 하는 확장 안 되는 패턴이다(실제로 이 문제로 한 번 되돌린 적 있음).

그래도 고정 조합이 맞다고 판단되면(사용자가 매번 함께 요청하는 게 확실할 때), 아래 패턴을 따른다.

`adapter.py`/`mapping.json`은 만들지 않는다 — 자기만의 레거시/외부 연동이 없다.

**다른 서비스의 함수를 절대 직접 import하지 않는다.** `from services.<other>.workflow import <func>`처럼 정확한 모듈 경로와 함수 이름을 아는 건, `discover_services()`가 없애려던 결합(오케스트레이터가 서비스 목록을 몰라도 됨)을 서비스 간 호출에서 다시 만드는 것이다. 대신 스텝 함수 **본문 안에서**(모듈 로드 시점이 아니라 호출 시점에) 이름 하나로 조회한다:
```python
@steps.step(order=1, next={"완료": "query_weather"})
def query_subscription(context: dict[str, Any]) -> str:
    subscription_status = registry.tool_for("subscription_status")  # .func 없이 바로 호출 가능
    context["subscription_result"] = subscription_status(applicant_id=context["applicant_id"])
    return "완료"
```
호출을 스텝 본문 안에 두는 이유: `discover_services()`가 서비스를 알파벳 순으로 import하므로, 모듈 최상단에서 조회하면 아직 등록 안 된 서비스를 못 찾을 수 있다. 스텝 본문 안이면 실제 호출 시점엔 모든 서비스 등록이 끝나 있어 안전하다.

**두 tool 호출 사이에 진짜 데이터 의존관계가 있을 때만** 하나의 capability로 묶는다(A의 결과가 B의 입력이 되는 경우, `subscription_weather_flow`의 region→location). 사람이 매번 다르게 고르는 관계(`applicant_list`가 보여준 목록에서 사람이 특정 신청자를 골라 `subscription_status`로 이어가는 것)라면 묶지 말고 개별 tool로 남긴 채 프롬프트로만 안내한다.

**output 스키마도 직접 import하지 않는다.** 최상위 tool 함수 본문 안에서(호출 시점에) `registry.tool_for("<name>").output_schema`로 조회해 중첩 스키마를 조립하고 `validate_schema()`로 검증한다 — `discover_services()`의 import 순서와 무관하게 안전하다(스키마 상수를 즉시 조립해야 하는 데코레이터 인자 자리가 아니라 함수 본문 안이라서 가능하다). 실제 예시(`services/subscription_weather_flow/workflow.py`):
```python
@tool(name="subscription_weather_flow", description="...")
def subscription_weather_flow(applicant_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {"applicant_id": applicant_id}
    build_state_machine().run(context)
    result = {"subscription": context["subscription_result"], "weather": context["weather_result"]}

    nested_schema = {
        "subscription": registry.tool_for("subscription_status").output_schema,
        "weather": registry.tool_for("weather").output_schema,
    }
    try:
        validate_schema(result, nested_schema)
    except SchemaViolation as e:
        raise GuardrailViolation("output", "subscription_weather_flow", e.detail) from e
    return result
```

## 5. 함수 시그니처 규약

- `steps.step()` 함수는 항상 `func(context: dict[str, Any]) -> str`. 반환 문자열이 그 스텝의 `next={...}` 키 밖이면 함수 반환 즉시 `ValueError`(`StateMachine.run()`까지 갈 필요도 없음).
- `steps.judged()`/`steps.human_action()` 함수도 시그니처는 동일(`human_action`은 `dict`를 반환)하지만, 반환값이 `choices=(...)` 밖이면 데코레이터가 즉시 `ValueError`. 모델이 판단하면 `judged`, 사람이 판단하면 `human_action`(`manual_review` 참고 — 사람이 승인/반려/서류추가요청 중 고름). `human_action`은 유효한 action을 확인하면 `context["human_action"]`을 자동으로 지운다 — 같은 노드가 순환 안에서 다시 방문돼도 예전 답을 재사용하지 않고 새로 멈춘다.
- 최상위 `@tool` 함수는 파라미터에 타입 힌트를 반드시 붙인다(예: `def subscription_status(applicant_id: str) -> dict[str, Any]`) — SDK `function_tool()`이 이 시그니처에서 모델에게 노출할 JSON 스키마를 자동 추론한다. 이건 **형태(shape)** 체크(str/int 등)만 하는 것으로, 이 프로젝트가 별도로 선언하는 `@tool(input_schema=...)`(§2, 의미 검증)와는 다른 층이다 — 이름이 같아 헷갈리기 쉬우니 주의.

## 6. 순환/재시도 안전장치 (자동, 신경 안 써도 됨)

`steps.step(..., max_retries=N)`을 선언 안 해도 **기본 5**가 적용된다 — self-loop든 여러 스텝을 왕복하는 순환(evaluator 패턴 등)이든, 어떤 스텝이 완료된 실행 횟수가 `max_retries + 1`을 넘으면 `MaxRetriesExceeded`. 카운트는 `context["_step_retry_counts"]`에 저장돼 `main.py`의 `resume()`을 여러 번 거쳐도 살아남는다. "완료된" 실행만 세므로, 사람이 `human_action`의 bounded choices 밖의 값을 입력해 재시도하는 것은 이 예산을 안 쓴다 — 자동 순환 폭주 방지와 사람의 입력 실수는 별개 문제라서다.

## 7. 에러 포맷

- `UnmappedValueError`(`framework/semantic/mapping.py`) — `mapping.json`에 없는 raw 코드값을 `normalize()`할 때, 또는 `MappedValue.require_confirmed()`를 `confidence != "confirmed"`인 값에 호출할 때. 삼키지 말고 그대로 전파시킨다.
- `GuardrailViolation(stage, tool_name, detail)`(`framework/harness/guardrail.py`) — `validate_tool_output()`/`validate_tool_input()`을 불렀는데 스키마 검증에 실패했을 때(선택적으로 부르는 fine-grained 검증, § 2/4). Agent 단위 `output_schema_guardrail`은 이제 막지 않고 관찰만 하고, input 쪽은 애초에 boundary에서 가로챌 지점 자체가 없으므로, 실제로 막고 싶으면 이 두 헬퍼를 직접 불러야 한다.
- `MaxRetriesExceeded`(`framework/workflow/state_machine.py`) — §6 참고.
- `judged`/`human_action`/`next` 위반은 별도 클래스 없이 평범한 `ValueError`다 — 메시지 프리픽스(`"judged node '...' returned"` / `"human_action '...' returned action"` / `"step '...' returned outcome"`)로 식별한다. `pausable=True` tool 안에서 이 `ValueError`가 나면(예: human_action의 bounded choices 위반) SDK가 삼키지 않고 밖으로 던지되 자기 `agents.exceptions.UserError`로 한 번 감싼다 — `main.py`의 `handle()`이 이미 이 언래핑을 처리하므로 새 pausable tool을 추가해도 신경 쓸 필요 없다.
- 새 서비스에서 자체 예외를 추가할 경우, 이 네 가지 패턴(원인 그대로 전파 / 구조화된 메시지 / 카운터 기반 / 일반 ValueError) 중 성격이 가장 가까운 걸 따른다 — 새 예외 클래스를 함부로 늘리지 않는다.

## 8. 체크리스트

- [ ] `main.py`/`framework/` 코드를 한 줄도 고치지 않았는가
- [ ] 다른 서비스를 부른다면 직접 import 대신 `registry.tool_for("<name>")`를 스텝(또는 최상위 tool) 본문 안에서 썼는가(§4)
- [ ] **정말 고정 composition tool이 필요한가부터 확인했는가** — SDK가 동적 tool 체이닝을 기본으로 처리하므로, 페어 전용 tool을 습관적으로 만들지 않았는가(§4)
- [ ] 신규 tool description이 기존 tool과 의미가 겹치지 않는가 (`registry.validate()`가 못 잡는다 — 사람이 확인)
- [ ] 새 tool이 다루는 개념(국가/통화/날짜 등)이 이미 등록된 다른 tool과 겹친다면, 같은 표현 규약을 쓰거나 최소한 파라미터 이름으로 그 차이가 드러나는가(§3, `limitation.md`)
- [ ] inferred 매핑이 판단 분기(judged/human_action 이외)에 쓰이지 않는가
- [ ] tool output에 enum/optional 같은 세부 규칙이 있다면 `validate_tool_output()`을 함수 본문에서 불렀는가(§2) — 안 부르면 Agent 단위 guardrail은 그 세부 규칙을 못 본다
- [ ] tool의 인자 중 다른 tool의 출력에서 모델이 그때그때 합성해 채울 만한 것(다단계 체이닝의 중간 인자)이 있고, 그 값이 닫힌 집합(국가 코드 등)이라면 `input_schema`+`validate_tool_input()`을 붙였는가(§2) — 자유 텍스트 인자까지 굳이 다 붙일 필요는 없다
- [ ] `human_action`을 쓰면 `@tool`에 `workflow_registry=steps`와 `pausable=True` 둘 다 넣었는가(§2)
- [ ] (`WorkflowRegistry`를 쓰는 경우) `workflow.py` import 시점에 `steps.validate()`가 오류 없이 통과하는가
- [ ] `python main.py`(또는 `registry.validate()`)가 등록/참조 무결성 오류 없이 통과하는가

## 9. 테스트 권장 사항 (프레임워크가 강제하지 않음, TDD 관점)

프레임워크가 자동으로 검사해주는 것(위 §6, `registry.validate()`, `steps.validate()`)은 구조/참조 무결성뿐이다 — 아래는 값과 행동을 다루므로 사람이 직접 테스트를 써야 한다.
- `adapter.normalize()`의 값 매핑 — `call()`을 스텁으로 고정하고 각 코드값이 기대한 `(value, confidence)`로 정규화되는지, 매핑에 없는 코드값이 `UnmappedValueError`를 내는지.
- 각 `next` 분기가 실제로 도달 가능한지 — 선언한 outcome마다 그걸 만들어내는 입력 시나리오가 있는지("죽은 분기" 탐지).
- `validate_tool_output()`을 부르는 tool이라면 그 실패 케이스 — 정상 입력 통과뿐 아니라 깨진 입력에서 `GuardrailViolation`이 나는지.
- `human_action`의 pause→resume 전체 사이클 — bounded choices 밖 action, `payload_schemas` 위반, 정상 케이스 각각.
- 조합 서비스는 내부에서 부르는 tool을 mock으로 격리하고 배선 로직(데이터가 올바르게 넘어가는가)만 검증.
