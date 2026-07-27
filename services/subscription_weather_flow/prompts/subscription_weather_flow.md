# Tool: subscription_weather_flow

청약 신청자의 진행상황과, 그 신청자 소재 지역의 현재 날씨를 함께 조회하는 복합 capability다.

- applicant_id 하나만 입력받는다. location을 별도로 요구하지 마라 — 지역은 청약 조회 결과에서 자동으로 얻는다.
- "청약 상태랑 날씨 같이/함께 알려줘"처럼 두 정보를 동시에 요구하는 요청에만 이 tool을 골라라.
  단순히 청약 상태만 묻거나 날씨만 묻는 요청에는 각각 subscription_status / weather를 골라야 한다.
- weather 결과의 condition_confidence가 "inferred"면 확정된 날씨 정보처럼 전달하지 마라.
