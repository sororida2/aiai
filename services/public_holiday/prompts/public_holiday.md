# Tool: public_holiday

지정한 연도(year)와 국가 코드(country_code)의 공휴일 목록을 조회하는 capability다.

- country_code는 ISO 3166-1 alpha-2(예: KR, US, JP) 형식이어야 한다 — 국가명을 그대로 넣지 마라.
- 데이터셋에 없는 country_code나 너무 먼 미래/과거 연도는 빈 목록이 올 수 있다 — 결과가 비어 있으면
  "그 해/국가엔 공휴일이 없다"고 단정하지 말고 조회 범위를 사용자에게 확인하라.
