# 합성 실행·위험·복구 계약 v1 — Q27

상태: root 구현 기준. EXEC-DEC-001의 Q27 로컬 범위, Q26 독립 판정 이후 적용한다. [설계 자문](../research/execution-design-input-2026-10-25.md)의 실제 사실과 제안은 구분하며 아래 선택·보완을 적용한다. frozen baseline7·Q26 fixture·기존 migration0001/0002는 불변이다.

## 범위·타입·권위

환경은 synthetic 고정, 현금계좌·정규장·Q24 정확 지정가 후보만 사용한다. 실제 인증·API·자금·계좌·취소·환전·외부 전송은 활성화하지 않는다. 별도 합성 broker에서 submit/cancel 상태만 검증하며 실제 write adapter·credential loader를 추가하지 않는다. 기존 Q14의 synthetic binding은 실제 권한이 아니다.

자문의 타입 표를 구현 기준으로 채택한다: ExecutionRef, ExecutionAccountState, ExecutionSourceSet, ExecutionRiskDecision, OrderIntent, ReservationSlice, DispatchAttempt, SyntheticBrokerReceipt, SyntheticOrderEvent, SyntheticExecutionQuery, CancelCommand, ExecutionReconciliation, ExecutionCommandReceipt. SyntheticExecutionPolicy는 기존 target 정책 refs와 gross turnover 상한·합성 한도 manifest·권한/세대·유효기간을 추가한다. 작은 중첩 타입으로 합칠 수 있으나 표의 필수 결속·closed field·nullable·state/version·현재 권리·원천 해소를 생략하지 않는다. 기존 TargetRef/OrderTerms/Q26 승인 타입의 의미·enum은 보존한다. 취소 권한을 Q26 enum에 몰래 추가하지 않는다.

합성 broker receipt/event/query는 실제 issuer가 수신·발급한 journal에서 해소해야 한다. canonical/hash/fixture 문자열·final/complete/unsent bool은 증거가 아니다. 발급 한도와 scope가 있는 독립 broker 사실을 사용하며 로컬 원장 값을 복사해 matched를 만들지 않는다. Q19 조회 배치의 미확인 금액 의미를 실행 사실로 승격하지 않는다.

## 단일 DB 권위와 원자성

Q27 composition은 최초 present부터 승인 상태를 DB repository에 둔다. 메모리 승인 import·JSON 권한 복원은 비활성이다. ApprovalApplication은 기존 합성 adapter와 명시 DB adapter의 닫힌 구성만 허용하며 임의 duck typing을 인증으로 받아들이지 않는다. 메모리 Q26 simulation의 admit/dispatch/record_risk는 DB composition에서 호출하지 않는다. 불변 원천 검증·순수 전이 계산의 코드 재사용은 허용하되 임시 메모리 소비를 실제 권위로 취급하지 않는다.

현재 opaque handle의 identity는 실제 살아 있는 issuer registry에서 확인하고 session·permissions·nonce·approval head·mode는 DB에서 해소한다. 같은 계좌 source/권한/세대 변경도 동일 registry gate와 DB 직렬화 경계를 사용한다. 코드 hash는 버전 식별이며 인증이 아니다. 하나의 실제 PostgreSQL 연결·transaction과 고정 잠금 순서 ledger_stream→execution account→head를 사용한다. 기존 Q20 Python append는 별도 commit이므로 공통 transaction에서 SQL ledger_append를 직접 재사용한다.

admission은 현재 원천/승인/세션/시각/위험을 검사하고 승인 consumed+candidate claim+prepared intent+현금/수량/위험 예약+outbox+nonce/receipt+history를 한 번에 commit한다. 독립 consume commit은 없다. 단계별 failure는 전체 rollback, commit 응답 유실은 동일 command 결과 조회이며 새 의도를 만들지 않는다. candidate 고유키는 environment/account/id/version이며 approval ID·generation/fence로 완화하지 않는다. aborted_unsent 뒤에도 claim을 보존한다.

한 연결에서 잠금/조회→typed 계산→read-set/version·clock 재검사→쓰기/commit을 수행한다. SQL timeout·framing·출력 상한을 강제한다. 별도 연결에서 읽고 allow만 가져오는 방식은 금지한다. 예상 버전/전체 read-set을 같은 SQL transaction에서 재확인하는 동등 구현은 가능하되 권한·현재 시각·원천 변경의 원자적 경계가 시험으로 입증돼야 한다.

## 현재 원천·금융 계산

원래 Q24 candidate/plan/result는 Q26 validate_source로 실제 원본 inputs/repository에서 재현한다. 현재 실행 위험은 별도 ExecutionSourceSet으로 전체 계좌·DB 활성 의도·예약·현재 Q20 원장 cursor·독립 broker 조회와 inclusion/cutoff·현재 가격/FX/권리/분류/달력/정책·성과를 해소한다. 현재 입력을 원래 빈 active-intents facts로 대체하지 않는다. 전체 scope·자료 시점·누락/정정·원천 identity가 미확인이면 unknown/차단이다.

실제 Q20 replay, Q21 value_projection/reconcile, Q23 bound performance/cost 계산을 연결한다. Q24의 available_cash/cost_bounds/정확 수치·노출 계산은 재사용하거나 순수 계산을 명시 추출한다. Q24 활성 주문 거부를 끄는 플래그와 새 원천 없이 allow를 만드는 길은 금지한다. 추출 후 기존 Q24 동작·금융 의미는 그대로 유지한다.

A=min(L-H-F,B-U-D), 신규 R=q*pmax+fee/tax bound≤A. H/U/D는 obligation ID와 principal/cost component·이행 부분으로 구분한다. 같은 부분을 U와 D에 중복 배치하지 않는다. fill로 예약을 줄일 때 원장 지급채무/사용량/D를 같은 transaction에서 늘린다. settlement는 L 감소와 H 해제를 결속하고, D는 새 B의 실제 반영 근거까지 유지한다. query 교체는 B·inclusion·U/D·sellable cutoffs를 같은 버전으로 갱신한다. postquery 입금·미결제 매도대금·예상 매수 수량을 임의 가용금/매도가능량에 더하지 않는다.

매도 상한은 min(ledger sellable-all sell holds, broker sellable-unreflected holds-postquery fills), 비용 상한도 확보한다. 노출은 활성 매수만/활성 매도만 체결된 두 방향의 최악값이며 상계하지 않는다. 기존 모든 통화 funding·종목/업종/시장/통화·수량/금액·거래량 참여·일간 한도에 prepared/dispatching/unknown을 포함한다. gross turnover는 Q23 시간가중 NAV를 분모로 사용하고 합성 상한1을 채택한다. 손실/낙폭은 현재 관측값+승인 경계 내 최악 비용/불리한 체결 영향을 검사한다. 필요한 계산값/정정/비용 미확정은 신규 제출을 막는다. dispatch에서 자기 예약은 새 부담으로 이중 차감하지 않는다.

## 전송·사건·취소·복구

자문의 상태 표를 채택한다. prepared→dispatching 직전과 handoff 직전 현재 session/principal의 승인 권한·generation/fence·정규장·정책·원천·위험·예약·중단/철회를 다시 검사한다. 외부 handoff는 DB transaction 밖이며 같은 계좌의 단일 합성 egress gate가 최종 검사부터 handoff까지와 stop/withdraw/generation 변경을 직렬화한다. egress 인자는 action과 대상 ID뿐이고 요청 금융조건을 덮어쓰지 못한다. 이 경계는 실제 OS/network 격리 증명이 아니다.

attempt를 먼저 영속하고 broker 수신 후 기록 실패/timeout/restart는 unknown·예약 유지·재전송0이다. outbox는 상태 조회를 깨우며 자동 주문 재생 기능이 아니다. lease/fence만 새로 얻어 자동 failover하지 않는다. unknown이 완전 조회에 없거나 거래일이 지나도 예약을 해제하지 않는다. 정확 request에 대한 실제 issuer 최종 거절 또는 handoff 권한을 폐기한 egress 미전송 증거만 종료 근거다.

ACK 전 fill을 지원하고 늦은 ACK가 체결 상태를 되돌리지 않는다. delta execution ID와 cumulative stream/sequence를 구분한다. 누계1→3의 유효량은3, revision1→2는 대체2이며 더해3으로 만들지 않는다. 누락 predecessor·의미 혼합·payload collision·overfill·최종 종료 후 늦은 fill은 근거를 보존하고 신규 주문을 차단한다. 과거 revision은 현재 상태를 되돌리지 않는다. 상위 revision 선도착은 격리 후 명시 재처리한다.

broker inbox/event+intent 상태+reservation→used/D+Q20 ledger_append의 원장/projection/outbox+mapping/history는 한 transaction이다. broker inbox를 Q20 ledger inbox와 혼용하지 않는다. ledger outbox 소비는 ledger_consume와 execution cursor를 함께 갱신하며 이미 반영한 체결을 재기장하지 않는다. 매수/매도 principal·settlement·fee/tax는 기존 Q20 경제 의미와 correction/dependency를 그대로 사용한다.

EX06의 execution fee0은 해당 execution에서 확인된 값이며 order-level 미청구 비용 bound2는 별도 hold로 남긴다. 이를 비용 미확인 사례와 혼동하지 않는다. 비용 자체가 unknown인 EX26은 Q20 costs_known을 true로 조작하지 않고 관측 체결·보수적 사용량·미확정 비용을 저장하고 incomplete/차단한다. 완전 근거가 도착하면 기존 멱등 identity로 한 번만 확정한다.

withdraw는 Q26 원자적 보호 API와 현재권한 규칙을 유지한다. approved는 revoked, consumed는 consumed 유지+별도 요청이다. 확정 미전송만 aborted_unsent/해제, handoff 이후는 requested/unknown/예약 유지다. 현재 report/risk 거부로 적법한 보호 철회를 막지 않는다. cancel은 별도 권한/nonce/target/version·attempt를 가진다. cancelACK는 종료가 아니며 cancel unknown 중 fill을 반영한다. 확정 잔량만 해제하고 자동 retry/replace/환전/청산은 없다.

resume는 현재 DB의 완전 합성 대사+명시 권한을 요구한다. complete bool은 권한이 아니다. 재시작/복원은 stopped/reconciling, DB snapshot 밖에서 새 generation을 발급하고 옛 egress·handle·session·nonce·pending/approved를 차단한다. consumed/claim/unknown/예약/체결은 보존한다. Q27은 현재 DB 재시작·세대/fence 복구와 restore seam을 검증하고, 과거 파일/DB 백업의 전체 복원은 Q28에서 별도 수행한다. 근거 없는 missing event 복구·자동 제출은 금지한다.

## 저장 예산·DB 권한

root는 자문의 256records/16MiB 제안 대신 **실행이 유발한 원장 행까지 포함하는1024 logical records/64MiB**로 한도를 확정한다. Q26의128records/8MiB 제한은 별도로 보존한다. source는 총8MiB/128refs, 객체 canonical64KiB, 문자열2KiB, 조회1~20, active intent2, intent별 issuer broker event8·cancel command2·withdraw command2다. 원천 한도는 서로 다른 후보 사이에서도 전체 해소 집합을 기준으로 한다.

admission 전 intent당 종료 예산384records/24MiB를 예약한다. 고정 상한의 배분은 다음과 같다. 기본 intent/claim/attempt/outbox/reservation/head/history32, broker8사건의 event/inbox/receipt/전이/정정64, 해당 사건이 유발하는 Q20 event/journal/decision/projection/outbox/consumer 행192, 취소·철회·명령완료64, 늦은 근거/종료여유32. 합계384다. 전체 제어/복구 보호128records/8MiB와 source8MiB를 남겨 두 active intent의 보호 몫이 다른 발급에 소진되지 않게 한다. 예산 예약 자체·indexes·immutable history도 계상하며 예약과 실제 사용을 이중 가산하지 않는다. 더 필요한 실제 행 수가 발견되면 완료로 숨기지 말고 root에 근거를 반환한다.

한도 내 이미 발급된 사건은 보존/처리할 몫이 있어야 한다. issuer는 허용 event8을 넘어 추가 근거를 발급하지 않고 신규 작업을 차단하며 이미 발급한 증거를 버리지 않는다. 중복은 추가 경제기록을 만들지 않는다. 미처리 명령의 완료비용·stop/withdraw·정정·취소 완료를 신규 명령이 소진하지 못하게 한다. terminal session의 사용 불가능한 hold만 원자적으로 회수하고 금융/승인 hold는 결속된 최종성 전까지 유지한다. 자동 eviction·무한 이벤트 처리/보존을 주장하지 않는다.

DB는 synthetic-only, closed schema/exact numeric/UTC, account/environment FK, candidate/nonce/command uniqueness, immutable evidence/history, version/previous hash/허용전이, reservation 보존식, consumed↔intent/outbox commit 결속을 강제한다. 제품 SQL role은 직접 financial table mutation 권한 없이 고정 함수/view를 사용하고 migration/관리 runner와 구분한다. trusted host/DB admin에 대한 공격 방지는 주장하지 않는다. 오류는 고정 code로 반환하며 rawSQL/DSN/nonce/handle/예외/개인정보를 조회·로그에 반사하지 않는다.

## 구현·검증 순서와 소유권

고정40사례 JSON은 production 계산기로 기대값을 생성하지 않았다. EX38은 Q24 `fixture(obligations=True)` 의미를 명시 채택한 경우이며 helper 주석의 ‘기본’ 표현을 근거로 다른 입력의 A를800으로 단정하지 않는다. EX03은 새로 구성한 현재 독립 broker/계좌 사실에서 A600을 실제 계산해야 한다. 입력 합계나 caller risk_allow를 모의 반환해 통과시키지 않는다.

단독 구현자: 새 domain/application/ports execution.py, adapters/postgres_execution.py, adapters/synthetic_execution_broker.py, 필요한 새 execution_uow.py, tests/product/synthetic_execution.py 및 test_execution*.py, scripts/check_execution.py, docs/development/execution.md, migration0003_synthetic_execution.sql. 통합 seam: application/ports approval.py와 synthetic_approval.py의 authority 결속(기존Q26동작 보존), additive serialization 등록, application/target.py의 공통 순수 계산 추출 및 새 domain/execution_math.py, postgres_ledger.py의 같은 transaction 참여용 제한 지원(기존API/0001/2 보존). 새 외부 패키지·framework·실제연결 설정은 추가하지 않는다. 파일을 더 나누면 정확한 소유목록을 인계한다.

root가 공통 계약/fixture/decision/task/evidence/status/queue를 통합하고 migration 변경을 검토한다. 작성자는 한 명, 재귀 위임 없음. 구현자는 관련 단위·합성 통합 시험과 serializer/Q26/Q24 영향 회귀를 수행한다. Docker를 역할에게 주지 않는다. root가 고정 기존 이미지·network none·host mount/port 없음·pullnever·own UUID project의 actual PostgreSQL runner를 검토·실행하고 자기 자원만 정리한다. DB rollback·경쟁연결·응답유실·체결/원장 원자성·복구·보호용량은 실제DB에서 확인해야 한다. 일반/보안 독립 검토와 최종 전체 제품/품질 실행까지 통과해야 Q27 로컬 완료다.

실제 API/키/비밀번호·PG01/PG03·지원/권리·운영 격리·실제 주문/취소 승인은 미완료로 남긴다. AP05 실제 조회는 사용하지 않는다. 합성 고정값은 사용자 운용정책이 아니다.

## 정정 이력의 성과 연결 보완 — EXECUTION-DEC-002

[추가 결정](../decisions/EXECUTION-DEC-002-correction-performance-scope.md)에 따라 정상 Q20 정정 전체 이력을 재생하는 합성 실행용 성과 경로를 추가한다. 기존 Q23 public v1·고정 비교와 원래 Q24 후보의 의미를 보존하며, 필요 helper 추출용 application/research.py·새 application/execution_research.py·관련 시험을 구현 소유 범위에 추가한다. 고정40사례·baseline7·0001/0002는 불변이다. Q20 미지원 정정은 EX26의 증거 보존·incomplete·신규 주문 차단 경로로 명시하고 자동 해소 완료로 표시하지 않는다. 정상 정정 이후 현재 위험 계산을 연결하지 못하는 결함과 이 미지원 경계를 구별한다.

## 저장·SQL 경계 후속 결정 — 2026-10-25

[EXECUTION-DEC-003](../decisions/EXECUTION-DEC-003-storage-sql-boundary.md)를 적용한다. 기존 한도는 유지하되 logical record/index key byte의 의미, owner별 완료 예약, 발급 전 manifest 비용 검사, 중복 archive 제거, 동일 transaction의 신뢰된 권한 전달과 고정 SQL 전이, 제한된 paging/chunk 전송을 명시한다. 최대8사건은 모든 조합의 수용 보장이 아니며192행을 넘는255행 조합은 발급 전에 거절한다. 이미 발급된 사실은 보호 예약으로 보존·처리한다. 추가 소유 파일/seam과 실제 검증 조건은 해당 결정에 명시한다.

### 저장 구현 인계의 호환성·검증 구분

Q27 미출시 합성 `BrokerQuantity`에 issuer가 발급한 `hold_reflections`(기본 빈 tuple)를 추가해 부분 반영을 표현한다. canonical wire hash는 달라지므로 이전 Q27 wire/snapshot을 자동 채택하지 않는다. 이번 검증은 고정 이전 migration을 유지한 새 임시 synthetic DB를 사용하며 migration checksum 불일치를 우회하지 않는다. Q28 복원은 판정된 schema/code/manifest 버전을 요구한다.

EX11의 기존400+활성매수100+신규50과 반대매도 상계 금지는 각각 실제 DB 사례로 검증할 수 있다. 세 번째 승인 제시의 Q26 저장 거절은 별도 용량 결과이며 금융550>500의 증명을 대신하지 않는다. active2와 저장128 한도를 완화하지 않는다.

## 2026-10-27 완료 의무·조회 회수 보완

[EXECUTION-DEC-004](../decisions/EXECUTION-DEC-004-completion-obligations.md)를 따른다. 복구 예약은 최종 상태뿐 아니라 session 발급·rebind·수동 resume 및 그 사이 허용된 보호 전이의 최대 잔여 비용을 포함한다. 입장 시 새 복구 의무와 기존 미해결 보호 의무를 함께 검사하며 공동 충족이 입증되지 않은 의무를 상계하지 않는다. 필수 전이의 actual 증가가 remaining 감소를 넘지 않는지 rows/bytes별로 확인한다.

완료 명령의 중복 lookup은 정확한 불변 challenge/receipt로 재구성 가능한 경우에만 원자적으로 회수한다. 원본·UNIQUE index·consumed·claim·history는 보존하며 미완료 의무는 lookup 존재 여부와 독립적으로 계산한다. 회수량으로 다른 owner의 완료 예약 소비를 상쇄하지 않는다. 현재 권리/세션/세대/nonce/hash·SQL 결속과 실패 rollback은 유지한다. 이전133 음성은 당시 버전 증거이며 신규 같은 세대 누적 세 번째 실제 admission/dispatch와 active3 거절은 별도 확인한다.

## 2026-10-27 현재 계좌 복구 유효성

[EXECUTION-DEC-005](../decisions/EXECUTION-DEC-005-recovery-validity.md)를 적용한다. 현재 계좌 검증은 과거 approval/request TTL과 분리하지만 현재 정책·자료·권리·전 계좌 원장/broker 의무 검사는 유지한다. 새자료는 동일 gate/DB CAS에 결속하고 새대사·명시재개를 요구한다. 복구로 과거 승인 실행권한·unknown hold를 되살리거나 해제하지 않는다. typed 결속·SQL·원자성·용량과 실제 수용행렬을 함께 검증하며 옛 matched 결과를 새 근거로 자동 채택하지 않는다.
