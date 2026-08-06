# Tool: exchange_rate

기준 통화(base)에 대한 다른 통화들(symbols)의 최신 환율을 조회하는 capability다.

- base/symbols 모두 ISO 4217 통화 코드(예: USD, KRW, EUR)를 써야 한다 — 통화 이름이나 기호("달러", "$")를
  그대로 넣지 마라.
- symbols는 쉼표로 구분된 문자열 하나로 받는다(예: "KRW,EUR,JPY") — 리스트가 아니다.
- 반환된 rates는 base 1단위당 환율이다. 실시간 시세가 아니라 하루 단위로 갱신되는 참고용 값이라는 점을
  사용자에게 알려라.
