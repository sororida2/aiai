# Tool: applicant_list

현재 청약 신청자 전원의 목록과 각자의 진행 단계를 표 형식으로 보여주는 capability다.

- 입력을 받지 않는다 (전체 목록 고정 조회).
- 사용자가 이 결과를 보고 "그 중 OOO 상태를 자세히 봐줘"처럼 특정 신청자를 지목하면,
  그 사람의 applicant_id를 이 목록에서 찾아 subscription_status(applicant_id=...)로
  이어서 조회해야 한다 — applicant_list 자체는 상세 조회 기능이 없다.
- status_confidence가 "inferred"인 행은 아직 확정된 상태가 아니라는 걸 사용자에게 알려라.
