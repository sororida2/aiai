# 레거시 어댑터 작성 가이드 (skeleton)

> 우선순위 1(청약진행상황 어댑터 인터페이스 확정)이 끝나면 이 문서를 채운다.
> `services/subscription_status/`가 아래 각 절의 살아있는 예시다.

## 1. 새 서비스 추가 시 만들 파일
- `services/<name>/adapter.py` — `BaseAdapter` 상속, `call()`/`normalize()` 구현
- `services/<name>/mapping.json` — 코드값 매핑, confidence: confirmed/inferred
- `services/<name>/workflow.py` — `@tool`로 최상위 capability 등록. 분기/재시도/판단 노드가 하나도 없으면(단순 단일 호출) `WorkflowRegistry` 없이 `@tool` 함수 안에서 어댑터를 직접 호출한다(`weather`/`applicant_list` 참고). 하나라도 있으면 `steps = WorkflowRegistry()`를 만들고 `steps.step()`/`steps.judged()`(모델 판단)/`steps.human_action()`(사람 판단)으로 고정 파이프라인을 선언한다(`subscription_status` 참고) — 판단 기준은 "스텝이 몇 개인가"가 아니라 "이 스텝들 사이에 실제로 코드가 결정할 게 있는가"다.
- `services/<name>/prompts/<tool_name>.md` — tool 프롬프트

`main.py`는 건드리지 않는다 — `framework/registry/discovery.py`의 `discover_services()`가 `services/` 아래를 스캔해서 `workflow.py`를 자동으로 import한다. 파일명이 정확히 `workflow.py`가 아니면 스캔에서 안 잡히니 주의.

## 2. 함수 시그니처 규약

- `adapter.call(self, **kwargs) -> dict[str, Any]` — 인자는 전부 keyword-only, 반환값은 레거시 원시 필드명을 그대로 쓴 dict (예: `status_code`). 프로토콜 세부사항(REST/DB/인증)은 이 함수 안에 갇혀야 한다.
- `adapter.normalize(self, raw_response: dict[str, Any]) -> dict[str, Any]` — 반환 dict의 키는 `@guardrail(output_schema=...)`에 선언한 키와 1:1로 맞춘다. `self.mapping.normalize(...)`로 얻은 `MappedValue`에서 `.value`/`.confidence`를 꺼내 채운다.
- `steps.step()` 함수는 항상 `func(context: dict[str, Any]) -> str` 형태. 반환 문자열은 그 스텝의 `next={...}` 맵의 키와 정확히 일치해야 한다 — 안 맞으면 (함수 반환 즉시) `ValueError`, `StateMachine.run()`까지 갈 필요도 없다.
- `steps.judged()`/`steps.human_action()` 함수도 시그니처는 동일하게 `func(context) -> str`(또는 `human_action`은 `dict`)이지만, 반환값이 `choices=(...)` 밖이면 데코레이터가 `ValueError`를 던진다. `steps.step()`과 이중으로 씌워 state machine에는 보통 노드와 구분 없이 등록한다 — 모델이 판단하면 `judged`, 사람이 판단하면 `human_action`(`manual_review` 참고, 사람이 승인/반려/서류추가요청 중 고름).
- 최상위 `@tool` 함수는 `input_schema`가 `inspect.signature`로 자동 추론되므로, 파라미터에 타입 힌트를 반드시 붙인다 (예: `def subscription_status(applicant_id: str) -> dict[str, Any]`). `self`는 자동 제외된다.

## 3. 에러 포맷

- `UnmappedValueError` (`framework/semantic/mapping.py`) — 두 지점에서 발생: (1) `mapping.json`에 없는 raw 코드값을 `normalize()`할 때, (2) `MappedValue.require_confirmed()`를 `confidence != "confirmed"`인 값에 호출할 때. 메시지에 `raw` 값을 그대로 포함시켜, 이 예외를 잡아 조사 큐(로그)로 흘려보내는 것이 지속적 발굴 파이프라인의 입구가 된다. 새 어댑터도 이 예외를 삼키지 말고 그대로 전파시킨다.
- `GuardrailViolation(stage, tool_name, detail)` (`framework/harness/guardrail.py`) — `GuardrailChain.run()`이 input/output 스키마 검증 실패 시 던진다. 메시지 포맷은 `"[{stage}] '{tool_name}' guardrail failed: {detail}"`로 고정되어 있으며, `stage`는 `"input"` 또는 `"output"`. 필드 누락과 enum(`choices`) 위반 두 케이스만 현재 지원된다.
- `MaxRetriesExceeded` (`framework/workflow/state_machine.py`) — 어떤 스텝이 `next` 맵에서 자기 자신으로 순환(`next_step == current`)하는 횟수가 `max_retries`를 넘으면 발생. 재조회처럼 유한 재시도가 필요한 스텝(`fetch_status`)에는 반드시 `max_retries`를 명시한다.
- `judged`/`human_action` 위반은 별도 클래스 없이 평범한 `ValueError`다 — 다른 세 예외와 달리 커스텀 타입이 아니므로, 호출부에서 구분해서 잡아야 한다면 메시지 프리픽스(`"judged node '...' returned"` / `"human_action '...' returned action"`)로 식별한다.
- 새 서비스에서 자체 예외를 추가할 경우, 이 네 가지 패턴(원인 그대로 전파 / 구조화된 메시지 / 카운터 기반 / 일반 ValueError) 중 성격이 가장 가까운 걸 따른다 — 새 예외 클래스를 함부로 늘리지 않는다.

## 4. 상태 정규화 규칙

- `mapping.json`의 각 엔트리는 `{"value": <정규화 문자열>, "confidence": "confirmed" | "inferred"}` 형태다. `confirmed`는 사람이 레거시 명세나 실측으로 검증을 마친 매핑, `inferred`는 코드만 보고 추정했지만 아직 검증되지 않은 매핑이다 (예: `subscription_status/mapping.json`의 `"99": {"value": "보류", "confidence": "inferred"}`).
- `inferred` 값은 판단 분기(**`judged`/`human_action` 이외의 곳**)에서 그대로 쓰면 안 된다 — `require_confirmed()`를 거치지 않고 코드 로직에서 `confidence`를 확인하지 않은 채 분기하면 안티패턴. `fetch_status`는 `result["status_confidence"] != "confirmed"`를 직접 체크해 `"미확인"` outcome으로 `manual_review`(human_action 노드 — 판단 주체가 사람)에 위임하는 걸 표준 패턴으로 삼는다.
- 승격(promotion) 프로세스: `inferred` 값이 `manual_review` 등에서 반복적으로 관측되면, 이는 사람이 실제 레거시 스펙을 확인해 `mapping.json`의 `confidence`를 `"confirmed"`로 바꿔야 한다는 신호다. 이 확인은 코드가 자동으로 하지 않는다 — 사람이 매핑을 갱신하는 것 자체가 "확정된 자산"의 갱신이며, `SemanticMapping`은 이 파일을 신뢰 가능한 단일 소스로만 취급한다.
- 매핑에 아예 없는 raw 코드값은 `inferred`로 대충 채우지 않는다. `UnmappedValueError`로 fail-fast하게 두고 조사 큐로 흘려보내, "모르는 값은 모른다고 실패"하는 게 원칙이다 (§3 참고).

## 5. 체크리스트
- [ ] 오케스트레이터/`main.py` 코드를 한 줄도 고치지 않았는가
- [ ] 신규 tool description이 기존 tool과 의미가 겹치지 않는가 (이건 `registry.validate()`가 못 잡는다 — 사람이 확인)
- [ ] inferred 매핑이 판단 분기(judged/human_action 이외)에 쓰이지 않는가
- [ ] 미확인 코드값이 guardrail에서 fail-fast로 차단되는가
- [ ] (`WorkflowRegistry`를 쓰는 경우) `workflow.py` import 시점에 `steps.validate()`가 오류 없이 통과하는가
- [ ] `python main.py` (또는 `registry.validate()`)가 등록/참조 무결성 오류 없이 통과하는가
