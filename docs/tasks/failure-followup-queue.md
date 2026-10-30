# 실패 후속 작업 큐

2026-10-30 · 정본 [JSON](failure-followup-queue.json). 원래계획우선·영향받는통합/완료관문유지.

현재 16개: awaiting_retest1·queued2·resolved13.

| ID | 종류 | 상태 | 작업 | 차단 범위 |
|---|---|---|---|---|
| FUP-Q27-001 | product_defect | resolved | source 교체 시 미완료 명령 hold 누락 | 개별해결·최종판정별도 |
| FUP-Q27-002 | test_fixture | resolved | financial 시험의 process/policy 준비 불일치 | 개별해결·최종판정별도 |
| FUP-Q27-003 | product_defect | resolved | 소수 numeric fingerprint의 JSON 판독 실패 | 개별해결·최종판정별도 |
| FUP-Q27-004 | test_oracle | resolved | 독립 공통 예약 oracle의 prepared byte 단위 누락 | 개별해결·최종판정별도 |
| FUP-Q27-005 | validation_execution | awaiting_retest | 최종 동일 입력의 전체 제품/actualDB 판정 수거 | Q27:local, P29-01:integration, P29-02:completion |
| FUP-Q27-006 | research_reconciliation | queued | 고정40 대응 초안의 누락/범위 과장 재대조 | Q27:local |
| FUP-P28-001 | execution_timeout | resolved | 설계 자문 시간 제한으로 최종 초안 미반환 | 개별해결·최종판정별도 |
| FUP-Q27-007 | validation_failure | resolved | actualDB84 24번 daily-risk invalid_contract 실패 | 개별해결·최종판정별도 |
| FUP-P28-002 | verification_capability | queued | 브라우저 표시·키보드·좁은 화면 검수 미실행 | P28-01:completion, P29-01:UX_acceptance |
| FUP-P28-003 | security_design_gap | resolved | 조회 cookie 포트·응답세대·잔존수명 계약 보완 | 개별해결·최종판정별도 |
| FUP-P28-004 | test_fixture | resolved | DB수명관리 모의시험의 초기명령/label fixture 불일치 | 개별해결·최종판정별도 |
| FUP-P28-005 | product_adapter_representation | resolved | 실제Docker namedvolume의 Binds표기를호스트bind로오판 | 개별해결·최종판정별도 |
| FUP-Q27-008 | test_fixture | resolved | SQLAUTH의 수동 context header에 current_validation 누락 | 개별해결·최종판정별도 |
| FUP-P28-006 | test_fixture | resolved | 실제저장검사의 용량 예외·봉인된 target ID 준비 불일치 | 개별해결·최종판정별도 |
| FUP-P28-007 | product_defect | resolved | COMMIT 이후 확인쿼리 오류의 rollback 오분류 | 개별해결·최종판정별도 |
| FUP-P28-008 | product_defect | resolved | 설치 저장함수 본문 손상의 재연결 검증 누락 | 개별해결·최종판정별도 |

실제검증/독립검토/해당납품으로개별해결,전체관문은별도다. 자동배정없음.
