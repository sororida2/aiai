from __future__ import annotations

# ISO 3166-1 alpha-2 국가 코드 — 이 프로젝트가 "국가"라는 겹치는 개념의 정준(canonical)
# 표현으로 이미 통일시킨 표준(§ limitation.md의 "업계 비교" 절, public_holiday/university_search
# 추가 당시 사용자가 직접 결정). 특정 서비스의 레거시 지식(청약 상태 5종 같은)은 아니지만,
# 그렇다고 framework/(엔진 자체, 새 서비스를 추가해도 손대지 않는 게 목표)에 넣을 물건도
# 아니다 — 여러 서비스가 공유하는 순수 참조 데이터(도메인 로직도 어댑터도 아님)라 `shared/`에
# 둔다. `framework/`는 이 디렉토리의 존재조차 모른다 — services/의 개별 파일이 필요하면
# 직접 import한다.
#
# 목록 출처: services/university_search/mapping.json(Hipolabs Universities API 실제 응답
# 데이터셋에서 도출된 200개 코드, 2026-08-06 스냅샷) — 이미 이 프로젝트가 검증해둔 alpha-2
# 코드 집합을 그대로 재사용한다. 완전한 ISO 3166-1 목록(249개)의 부분집합이지만, 이 목록에
# 없는 코드는 university_search가 어차피 지원하지 못하므로 지금 이 프로젝트의 실용적 경계와
# 일치한다.
ISO_3166_1_ALPHA2 = frozenset({
    'AD', 'AE', 'AF', 'AG', 'AL', 'AM', 'AO', 'AR', 'AT', 'AU', 'AZ', 'BA', 'BB', 'BD', 'BE', 'BF',
    'BG', 'BH', 'BI', 'BJ', 'BM', 'BN', 'BO', 'BR', 'BS', 'BT', 'BW', 'BY', 'BZ', 'CA', 'CD', 'CF',
    'CG', 'CH', 'CI', 'CL', 'CM', 'CN', 'CO', 'CR', 'CU', 'CV', 'CY', 'CZ', 'DE', 'DJ', 'DK', 'DM',
    'DO', 'DZ', 'EC', 'EE', 'EG', 'ER', 'ES', 'ET', 'FI', 'FJ', 'FO', 'FR', 'GA', 'GB', 'GD', 'GE',
    'GF', 'GH', 'GL', 'GM', 'GN', 'GP', 'GQ', 'GR', 'GT', 'GU', 'GY', 'HK', 'HN', 'HR', 'HT', 'HU',
    'ID', 'IE', 'IL', 'IN', 'IQ', 'IR', 'IS', 'IT', 'JM', 'JO', 'JP', 'KE', 'KG', 'KH', 'KN', 'KP',
    'KR', 'KW', 'KY', 'KZ', 'LA', 'LB', 'LC', 'LI', 'LK', 'LR', 'LS', 'LT', 'LU', 'LV', 'LY', 'MA',
    'MD', 'ME', 'MG', 'MK', 'ML', 'MM', 'MN', 'MO', 'MR', 'MS', 'MT', 'MU', 'MV', 'MW', 'MX', 'MY',
    'MZ', 'NA', 'NC', 'NE', 'NG', 'NI', 'NL', 'NO', 'NP', 'NU', 'NZ', 'OM', 'PA', 'PE', 'PF', 'PG',
    'PH', 'PK', 'PL', 'PR', 'PS', 'PT', 'PY', 'QA', 'RE', 'RO', 'RS', 'RU', 'RW', 'SA', 'SC', 'SD',
    'SE', 'SG', 'SI', 'SK', 'SL', 'SM', 'SN', 'SO', 'SR', 'SS', 'SV', 'SY', 'SZ', 'TC', 'TD', 'TG',
    'TH', 'TJ', 'TM', 'TN', 'TR', 'TT', 'TW', 'TZ', 'UA', 'UG', 'US', 'UY', 'UZ', 'VA', 'VC', 'VE',
    'VG', 'VN', 'WS', 'XK', 'YE', 'ZA', 'ZM', 'ZW',
})
