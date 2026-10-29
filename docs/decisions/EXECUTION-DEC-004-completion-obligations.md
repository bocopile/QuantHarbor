# EXECUTION-DEC-004 — 복구 완료 의무와 완료 명령 조회 회수

- 날짜: 2026-10-27
- 관련 작업: Q27 / EXECUTION-local, EXECUTION-DEC-003
- 상태: 채택 — 구현·실제 검증 전
- 결정 담당·요청 근거: root; 사용자 전체 순차 구현·검증 요청과 Astra/high 읽기 전용 설계 자문

## 사실·추론·미확인

root가 자문 입력 소유28개 SHA가 현재와 동일함을 대조했다. 자문은 실제 시험을 수행하지 않았다. 현18행 공유 복구 capsule은 두 세션 발급·rebind에서 controller stop 의무와 resume 의무가 겹쳐 1controller 경로19행, 2controller 경로20행이 되는 코드상 반례가 있다. 재대사 후 새 세션/source 변경은 resume 준비를 무효화하지만 재대사 예약이 이미 해제되는 경로도 있다. 미완료 공통 command 계산의 mutable lookup 의존도 보완 대상이다.

기존 실제 DB 4시나리오/9검사 증거는 당시 버전 partial로 보존한다. 그 포화 검사는 restart 후 controller 발급까지이며 rebind/resume 전체 충분성을 입증하지 않는다. `85+48=133>128`은 이미 세대를 교체해 map이 빈 경로의 음성이다. 같은 세대에서 완료 명령8개의 중복 map24행 회수 후 세 번째 presentation이 125/128이 될 수 있다는 산식은 설계 추론이며 실제 양성 증거가 아니다.

## 선택

1. 고정 한도·fixture·baseline7·migration0001/0002를 유지한다. 복구 의무를 단계별로 계산하고 필수 완료 전이에 대해 rows와 bytes 각각 `Δactual + Δremaining ≤ 0`을 검증한다. 새로운 선택 작업은 미래 의무까지 확보한 뒤 들어오게 한다. 18을19/20으로 바꾸는 것만으로 충분성 증명을 대신하지 않는다.
2. 공동 충족 가능한 계좌 복구 의무와 intent별/기존 미완료 보호 의무를 구분한다. 같은 복구로 여러 intent를 충족하는 조건을 명시하고 증명되지 않은 의무는 상계하지 않는다. session/role/head/stop/resume/reconciliation/index/copy의 최악 비용을 함께 계산한다.
3. 새 session/source/보호 전이가 현재 reconciliation을 무효화하면 필요한 재대사 예약을 변경의 사전 검사에 포함하거나 해당 선택 변경을 부작용 없이 거절한다. 무효화된 준비를 현재 유효한 resume 근거로 재사용하지 않는다.
4. 미완료 명령 의무는 current-generation 불변 challenge/receipt evidence에서 계산한다. mutable command/nonce/receipt lookup을 지워 의무를 없애지 못하도록 SQL commit 경계를 검사한다.
5. 완료 명령의 세 중복 lookup은 정확한 불변 challenge/receipt로 재구성 가능한 경우 원자적으로 회수할 수 있다. 원본·UNIQUE·history·consumed·claim·금융 예약은 보존한다. 이 회수는 이력 삭제나 한도 확장이 아니다. 최소 additive 경로로 구현하고 실제 절감 rows/bytes를 독립 대조한다.
6. 회수 후 동일 요청은 현재 권리·actor/session/generation·action/target/nonce/hash를 검증한 뒤 기존 결과를 반환한다. 과거 세대 실행은 거절하며 권한 있는 과거 결과 조회만 유지한다. SQL map 존재 검사를 제거하는 대신 기존 또는 동일 transaction의 정확한 evidence 결속을 검사한다. raw payload hash와 domain reference hash를 혼동하지 않는다.
7. 회수로 줄어든 usage가 다른 owner의 새 기록 비용 또는 완료 예약 소비를 상쇄하지 않도록 회계 경계를 분리한다. 미완료 명령은 회수하지 않는다. 실패·충돌·COMMIT 실패 때 업무 변경과 회수가 함께 rollback되고 응답 유실은 기존 결과 관측으로 처리한다.
8. 같은 세대의 두 실제 의도 종료→보호 철회→완료 lookup 회수→현재 source/query·유효 controller·필요한 명시 대사/resume→세 번째 승인/admission/dispatch 양성을 검증한다. active2와 누적2를 혼동하지 않는다. 세 활성 의도 거절은 presentation 용량이 아니라 실제 admission의 active2 검사까지 도달해 입증한다.

## 영향·대안·소유권

금융 산식·주문 조건·실제 인증/연결·자금 정책은 바꾸지 않는다. Q26 synthetic API 의미를 유지한 additive lookup/회계 seam과 Q27 DB 제약 변경이다. 합성 DB의 0003 변경은 새 임시 DB 재현에 한정하며 실제 운영 migration 완료를 주장하지 않는다. Q28 이후는 보완된 예약·조회 계약을 소비한다.

root는 본 결정·execution-local-v1 추가 설명·상태·증거를 통합한다. 단독 구현자 소유는 postgres_execution.py, 필요한 synthetic_approval.py seam, 0003, tests의 execution_storage/control/sql, scripts/check_execution.py, docs/development/execution.md다. execution_uow.py는 delta 결속에 필요한 경우만 허용하며 나머지 기존28파일은 읽기/회귀 대상으로 유지한다. 불가피한 소유 확대는 root에게 근거를 반환한다.

한도 확대·과거 원본 삭제·금융 의미 생략·불명 주문 예약 해제·실패 검사 완화는 대안으로 채택하지 않는다. 옛133 음성 증거는 보존하되 새 회수 동작으로 같은 경로 결과가 달라지면 새 기대값을 이유와 함께 기록한다. 기존 결과를 새 버전 증거로 덮어쓰지 않는다.

## 완료 증거·재검토

복구 순서/복수controller/무효화·미완료map손실·완료map회수·replay/권한·원자성/COMMIT유실·terminal-third/active3를 실제 합성 DB에서 확인한다. bytes 전체 저장 위치 상계와 타 owner 예약 보존이 필요하다. focused red/green→root actual DB→독립 보안/일반 검토→최신 전체 판정 순서다. 현재는 구현/새 검증 미실행, Q27 진행 중이다.

## 실제 DB 반례에 따른 구현 상계 보정 — 2026-10-27

초기25행 구현은 재대사 때 기존 query를 재사용한다는 가정으로 미래1행만 남겼다. 실제 새 query identity가 발급되면 query와 reconciliation2행이 생겨 합계72→73행으로 완료 guard가 거절했다. root 진단에서는 업무 조건을 그대로 두고 임시 DB 예외 DETAIL만 추가했으며 rollback/ownDB정리를 확인했다. 따라서 mandatory repair는 새 query까지2행/393216bytes를 확보한다. stop과repair는3행/458752bytes, 세션은 실제5+종료2+두stop/repair6=13행/1376256bytes, 두세션의 다음 공동복구는29행/3211264bytes다. 한도 증액이나 guard 제거는 하지 않는다. 이는 구현 상계이며 실제 모든 필수 전이 충분성은 아직 검증 중이다. 기존25행 당시의 단위 통과를 새 SQL 증거로 쓰지 않는다.

## 보안 반례 수정 범위 — 2026-10-27

실제DB SEC1은 matched rebind 후 approver 종료가 actual+remaining 73→74행 및 bytes 증가로 rollback됨을 확인했다. 비controller 종료가 현재 대사를 무효화할 때 필요한 새 query+대사 비용도 종료 전에 예약한다. 단순 상수 증액·guard 제거 대신 각 필수 전이의 행/bytes 비증가를 검증한다. SEC2는 최종 DB검사가 끝난 뒤 시간이 경과하면 submit/cancel이 만료되어도 전송되는 반례다. 같은 lock 아래 신뢰된 검증 근거에 결속한 유효시간을 실제 전송 직전 현재 시각으로 재검사한다. 모든 DB I/O 이후여야 하며 공개 bool/callback 권한 대체·자동재전송·armed hold 조기해제를 허용하지 않는다. 기존 계약을 충족하는 결함 보완이며 실제 계좌/API/금융 권한 확장이 아니다.

## 종료 예약의 수명주기 보정 — 2026-10-27

실제 보안수정 DB에서 SEC1/SEC2 및 recovery3/terminal-third가 통과했으나 running 상태의 noncontroller에도 재대사2행을 항상 남겨 active3 명령발급이 한도에 먼저 걸렸다. 재대사는 이미 약속한 resume 단계와 결속한다. resume 의무가 없을 때 불필요한 추가분을 유지하지 않고, 복구 준비에 진입할 때 각 세션/명령의 후속 무효화 의무를 먼저 확보한다. 필수 복구 전이의 비증가·선택적 재대사 준비의 사전용량 검사를 유지한다. 별도 actual revoke 관측은 90→91행 증가여서 미소비 승인 보호 명령의 terminal+repair 예약도 보완한다. 행/bytes 충분성은 새 actual DB와 독립 검토 전에는 확정하지 않는다.
