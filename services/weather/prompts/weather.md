# Tool: weather

지정한 location(도시명)의 현재 날씨를 조회하는 capability.

- location 하나만 입력받는다. 도시명이 모호하면 임의로 국가/지역을 추측하지 마라.
- condition_confidence가 "inferred"인 결과는 알 수 없는 상태 코드(3200 등)에서 온 것이며,
  확정된 날씨 정보처럼 사용자에게 전달하지 마라.
