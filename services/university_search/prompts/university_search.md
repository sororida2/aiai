# Tool: university_search

지정한 국가 코드(country_code)에 속한 대학 목록을 조회하는 capability다.

- country_code는 ISO 3166-1 alpha-2(예: KR, US, MY) 형식이어야 한다 — public_holiday와 같은 형식이다.
  국가명을 그대로 넣지 마라.
- 커뮤니티가 관리하는 비공식 데이터셋이라 최신 대학이나 소규모 기관이 누락될 수 있다.
- 베트남(VN)은 데이터셋 안에 국가명 표기가 "Viet Nam"/"Vietnam" 두 가지로 섞여 있어, 이 조회는 그중
  다수 표기만 잡는다 — 결과가 예상보다 적으면 이 한계를 사용자에게 알려라.
