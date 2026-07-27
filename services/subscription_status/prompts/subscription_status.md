# Tool: subscription_status

청약 신청자의 진행상황을 조회하는 capability. applicant_id 하나만 입력받는다.

- 이 tool은 내부적으로 상태 재조회/재제출대기/수동검토까지 이어지는 고정
  서브 workflow를 실행한다. 오케스트레이터는 중간 단계를 몰라도 된다.
- status_confidence가 "inferred"인 결과는 수동검토를 거친 것이며,
  사용자에게 확정된 사실처럼 전달하지 마라.
