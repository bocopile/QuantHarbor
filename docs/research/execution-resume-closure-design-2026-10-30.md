# Q27 잔여 완료조건 독립 설계 자문

**분류: (a) 2개, (b) 5개, (c) 1개입니다.** 새 runtime 결함을 확정하지는 않았지만, 미지원 경계의 직접 검증과 저장 계상의 독립 증명이 부족합니다. actualDB84·최신 전체 제품 재실행은 **INCOMPLETE**, Q27 완료 판정은 보류합니다.

아래 번호는 [REMAINING 선언 순서](../../scripts/check_execution.py#L33)입니다. (a)는 의도적 미지원, (b)는 구현·assertion 존재/최신 증거 대기, (c)는 미충족 계약 의무입니다.

| # / 잔여 항목 | 분류 | 구현·assertion 근거와 종료에 필요한 증거 |
|---|---|---|
| **1. control actual DB / independent reviews** | **b** | [계약 65행](../../docs/contracts/execution-local-v1.md#L65)은 실제DB·독립검토·최종 제품/품질을 요구합니다. 제공된 집중3·DB3·검토·financial21·품질87 결과는 해당 범위의 증거입니다. **최종 동일 입력의 DB84·전체 제품 결과와 검토 적용 범위**를 합쳐야 합니다. 최초 783개 중 2 ERROR는 후속 모듈 PASS로 전체 PASS가 되지 않습니다. |
| **2. EX21 earlier cumulative successor reinterpretation** | **a** | [DEC002 선택4](../../docs/decisions/EXECUTION-DEC-002-correction-performance-scope.md#L21)의 명시적 미지원입니다. [`_receive`](../../src/quantharbor/adapters/postgres_execution.py#L1231)는 successor 존재 시 quarantine합니다. 그러나 [`cumulative`](../../scripts/check_execution.py#L361)는 **최신 sequence 정정**을 검사합니다. 앞선 sequence 정정에서 원본·hold 보존, incomplete, 신규 위험/재개 차단, 후속 정상 revision으로 충돌이 사라지지 않는 직접 증거가 필요합니다. 자동 재해석 구현은 요구하지 않습니다. |
| **3. EX26 zero-cost / settled-trade dependency corrections** | **a** | [`_receive`](../../src/quantharbor/adapters/postgres_execution.py#L1284)는 양수→0을, [projection 검사](../../src/quantharbor/adapters/postgres_execution.py#L1301)는 미해결 dependency를 차단합니다. [settled-trade 단위시험](../../tests/product/test_execution_financial.py#L174)은 존재하지만, runner의 unknown-cost 정상 확정·일반 quarantine은 두 경계의 직접 증명이 아닙니다. **양수→0 및 결제후 정정 각각의 실제DB 증거·보수적 예약·신규 위험 차단**을 확인해야 합니다. |
| **4. EX27/28 cancel handoff** | **b** | [`control_cancel`](../../scripts/check_execution.py#L612)는 ACK 해제0, timeout 재전송 거부, fill 반영, 확정 잔량만 해제를 검사합니다. [`control_cancel_conflict`](../../scripts/check_execution.py#L645)는 역순 충돌의 hold/incomplete 보존을 검사합니다. 실제84의 해당 경로와 handoff fault·SEC2 결과가 필요합니다. `authored…pending`은 결과 확인 후 갱신할 메타데이터입니다. |
| **5. EX31 restart/rebind/manual resume** | **b** | [`control_restart`](../../scripts/check_execution.py#L714)는 세대 교체·옛 handle 거부·claim/원장/예약 보존·unknown 재개 거부를 검사합니다. [`recovery_validity`](../../scripts/check_execution.py#L1751)는 DEC005의 과거 TTL 분리·새 자료·현재 권리·명시재개를 다룹니다. 해당 실제DB 결과와 rollback/COMMIT 유실·registry 결속 결과가 필요합니다. |
| **6. EX32/37 exact row/index-byte accounting** | **c — 독립 검증 의무 부족** | [`execution_storage_rows`](../../migrations/0003_synthetic_execution.sql#L541)·[`execution_check_budget`](../../migrations/0003_synthetic_execution.sql#L1224)에 실제 계상 구현은 있습니다. 하지만 [`storage_independent`](../../scripts/check_execution.py#L922)의 수기 독립 대조는 **Q20 7개 테이블**에 한정됩니다. Q27 evidence/history/reservation/budget·Q26 map 복사본·owner 배분까지 독립 대조한 증명은 이 runner로 성립하지 않습니다. 전 저장 위치의 행·내용·PK/UNIQUE key bytes와 owner별 actual+remaining을 별도 산출해 비교해야 합니다. 이는 계상 오류 확정이 아니라 **증명 범위의 결손**입니다. |
| **7. EX34 SQL auth/nonce/closed schema** | **b** | [`sql_auth_closed`](../../scripts/check_execution.py#L965)는 product 권한 거부와 owner 구조 음성을 분리하고, orphan이 COMMIT까지 도달한 후 rollback되는지 검사합니다. [`sql_atomic_withdraw_binding`](../../scripts/check_execution.py#L1058)는 actor/session/generation/nonce/receipt 변조와 정상 replay를 검사합니다. 실제84의 각 음성·양성 결과, staging0·fingerprint 불변을 확인해야 합니다. |
| **8. EX32 active3/terminal3/Q26 history/common reserve** | **b** | [`completion_same_generation_third`](../../scripts/check_execution.py#L1499)는 불변 evidence 보존·lookup24행 회수·**실제 active3 admission 거절 및 terminal-third admission/dispatch**를 검사합니다. [`completion_step`](../../scripts/check_execution.py#L1326)은 rows/bytes 각각 actual+remaining 비증가를 검사합니다. 포화 발급사실 완료·타 owner 예약 보존·pending 예약 수정의 실제 결과까지 필요합니다. 과거 [`storage_terminal_third`](../../scripts/check_execution.py#L1217)의 허용된 용량 거절은 세 번째 성공 증거가 아닙니다. |

root의 다음 작업은 다음과 같습니다.

1. **현재 실행 결과를 먼저 수거**하고, 최종 입력 hash·84개 종료·자기 자원 cleanup·전체 제품 결과를 보존합니다. runner는 [초기 partial/false](../../scripts/check_execution.py#L1942)를 성공 후에도 바꾸지 않으므로 문자열이나 exit0으로 판정하지 않습니다.
2. **DEC002 미지원 세 경계의 직접 실제DB 검증을 보완**합니다. 안전 차단을 검증하는 작업이며 자동 지원으로 범위를 확대하지 않습니다.
3. **저장 계상의 독립 대조 범위를 완성**합니다. production 계상 helper 결과끼리의 비교나 순수 helper 단위시험으로 대체하지 않습니다.
4. fixed40의 **각 기대 문장→실제 assertion→최종 실행 결과**를 연결합니다. 우선 미확립 가능성이 큰 항목은 **EX21·EX26·EX32·EX37**, 실행 종료·정리 전인 **EX40**입니다.

이번 자문은 읽기 전용입니다. 파일 변경·시험·Docker·외부 도구 실행 및 진행 중 DB 작업 개입은 하지 않았습니다.

[실제 실행 근거](../evidence/execution-resume-closure-design-2026-10-30.json).
