# 실패 후속 작업 큐

2026-10-30 · 정본 [JSON](failure-followup-queue.json). 원래계획우선·영향받는통합/완료관문유지.

현재 28개: diagnosing1·queued7·resolved20.

| ID | 종류 | 상태 | 작업 | 차단 범위 |
|---|---|---|---|---|
| FUP-Q27-001 | product_defect | resolved | source 교체 시 미완료 명령 hold 누락 | 개별해결·최종판정별도 |
| FUP-Q27-002 | test_fixture | resolved | financial 시험의 process/policy 준비 불일치 | 개별해결·최종판정별도 |
| FUP-Q27-003 | product_defect | resolved | 소수 numeric fingerprint의 JSON 판독 실패 | 개별해결·최종판정별도 |
| FUP-Q27-004 | test_oracle | resolved | 독립 공통 예약 oracle의 prepared byte 단위 누락 | 개별해결·최종판정별도 |
| FUP-Q27-005 | validation_execution | resolved | 최종 동일 입력의 전체 제품/actualDB 판정 수거 | 개별해결·최종판정별도 |
| FUP-Q27-006 | research_reconciliation | diagnosing | 고정40 대응 초안의 누락/범위 과장 재대조 | Q27:local |
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
| FUP-P28-009 | execution_timeout | resolved | AI 저장 기반 구현 시간 상한 후 부분 인계 수용 | 개별해결·최종판정별도 |
| FUP-P28-010 | product_defect | resolved | AI 체크포인트 processed revision의 bool-as-int 허용 | 개별해결·최종판정별도 |
| FUP-P28-011 | product_defect | resolved | ai_state CHECK 의미 손상 검출 누락 | 개별해결·최종판정별도 |
| FUP-P28-012 | product_defect | resolved | 60초 전체 deadline 잠금 대기/최종검증 제외 | 개별해결·최종판정별도 |
| FUP-P28-013 | product_defect | resolved | 완료 result receipt 시각/원천관계 검증 누락 | 개별해결·최종판정별도 |
| FUP-P28-014 | product_defect | resolved | 상속 저장 테이블의 단일 book 훼손 미검출 | 개별해결·최종판정별도 |
| FUP-Q27-009 | validation_gap | queued | 매도 미수금500의 실제금액·fresh query 전 가용금불증가 관측 | Q27:local, P29-01:integration |
| FUP-Q27-010 | validation_gap | queued | 실제 발급 mixed semantics 사건의 격리·근거보존·경제량 불변 | Q27:local, P29-01:integration |
| FUP-Q27-011 | validation_gap | queued | cancel foreign account·다른 target 거부와 송신/금융 불변 | Q27:local, P29-01:integration |
| FUP-Q27-012 | validation_gap | queued | 만료 cost rule·classification의 실제 시간가드 거부 근거 | Q27:local, P29-01:integration |
| FUP-Q27-013 | validation_gap | queued | owner SQL cross-account/FK·enum·negative·행version 독립 거부 | Q27:local, P29-01:integration |
| FUP-Q27-014 | validation_gap | queued | 8MiB 이내 서로다른 전체 해소refs129개의 실제 count 가드 | Q27:local, P29-01:integration |

고정40관측보강6건은제품결함재현과구분한다. 전체836/86 수거는완료했으나Q27최종수용은별도다. 자동배정없음.
