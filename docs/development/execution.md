# Q27 합성 실행 개발 인계

Q27-local의 금융 후속 부분 구현이다. `execution-local-v1`·EXECUTION-DEC-001·고정40사례를 입력으로 사용한다. fixture SHA256은 `41756164ab565c611458d0d3dfeed236aaefa5d98973a76e04b04766c7ff46a1`이다. 최신 입력 root DB 판정은 정정 버전의 27시나리오·42검사묶음·1032.689초·cleanup27·소유22hash 불변·exit0다(`execution-database-correction-2026-10-25.json`). EX03 양쪽 winner와 EX05 COMMIT 응답 유실도 그 버전에서 확인했다. 이 결과는 이번 제어 변경의 실행 증거나 독립 검토가 아니다. **이번 수정본의 실제 DB runner는 구현자가 실행하지 않았다.**

## 이번 금융 변경

원본 Q24 `ApprovalSource`는 계속 `validate_source`로 재현한다. `refresh_current(handle, query, market_inputs=...)`는 현재 issuer가 실제 발급한 query를 받고, 공유 gate와 하나의 SQL transaction 안에서 Q20 실제 사건 전체·projection을 읽어 Q21 snapshot/독립 statement 대사와 Q23 cost/performance를 구성한다. 임의 current-ref·allow·complete bool은 받지 않는다. 현재 권리와 원본 권리를 모두 검증하고 source hash·query/inclusion·cutoff·DB CAS와 reservation별 반영 사용량·source cutoff를 함께 저장한다. 하나의 원금 예약에서 일부 execution만 결제·broker 반영된 경우에도 execution별 포함 ID로 정확한 금액을 식별한다. 다른 facade는 공유 registry의 최신 현재 입력을 읽는다. 현재 DB에 대한 새 issuer 재결속은 아래 명시 restart/rebind 경로를 사용한다.

`current_risk`는 실제 DB 사건과 공급된 사건 전체를 대조한다. Q24의 활성 주문 거부를 끄는 flag는 추가하지 않았다. 실행 원금 채무를 Q24 전체 의무 검증에 포함한 뒤, reservation으로 대표되는 부분만 식별해서 한 번 계산한다. 남은 주문 수량과 비용만 prospective exposure에 넣고 이미 Q20 holdings에 반영된 체결량을 다시 더하지 않는다. funding에서는 이미 holdings가 된 미결제 매수 원금과 현금 hold를 구분한다. 자기 reservation 제외는 held 부분에 한정하며 이미 사용한 금액과 다른 intent 예약은 보존한다. 일간·gross turnover/시간가중 NAV·손실·낙폭·모든 통화/분류/시장 한도를 유지한다.

체결 head를 execution ID와 cumulative sequence별로 보존하고 **각 유효 execution의 원금·비용을 합산**한다. delta revision은 이전 head를 대체하며 cumulative는 이전 issuer 누계와의 차이를 기장한다. 최신 cumulative sequence 정정을 지원한다. 누락 predecessor는 원래 격리 증거를 남긴 뒤 `reprocess(event)`로 명시 재처리한다. 과거 revision은 현재 경제를 되돌리지 않는다. payload collision·overfill·late final conflict는 보존·중단한다. 원래 broker inbox와 추가 immutable 처리 결과 기록으로 격리와 재처리 이력을 함께 남긴다.

비용 unknown인 체결은 quantity/보수적 principal usage/비용 hold를 보존하고 accounting incomplete로 차단한다. Q20에 `costs_known=true`나 확인된 비용0을 만들지 않는다. fee만 확인되고 tax가 unknown이면 확인된 하한을 cost used에 보존하고, 실제 기장 전에는 settled로 표시하지 않는다. 같은 execution identity의 실제 complete revision이 도착하면 Q20 trade와 별도 fee/tax expense를 같은 transaction에서 한 번 기장한다. 확인된 execution fee0과 남은 주문 비용 hold2는 별개다. 비용은 cost reservation의 held에서 used로 이동하므로 중복 hold하지 않는다. 비용이 승인 bound를 넘으면 실제 원장과 초과 금액을 보존하고 중단하며 기존 bound 보존식을 훼손하지 않는다. 이때 초과값은 aggregate의 `financial_excess`에 있고 정규 reservation에 사용량 전부를 수용하지 못한다는 한계를 남긴다.

매수·매도 settlement는 실제 trade dependency를 사용한다. 미결제 매도 채권은 가용금에 더하지 않는다. 매도 결제 후에도 오래된 독립 B가 증가하지 않는다. 이미 결제한 체결의 정정은 Q20 reversal/dependency 결과를 그대로 보존하고 unresolved이면 중단한다. 부분 체결 후 늦은 ACK는 상태를 되돌리지 않는다.

UoW는 단일 psql 연결에서 ledger stream→execution account→head를 잠그고 조회·계산·저장한다. nonblocking selector로 부분 pipe write를 끝까지 전송하고 stdout을 동시에 배출한다. 쓰기·읽기 공통20초 deadline, 입력/출력8MiB 상한, SQL statement15초/lock10초를 사용하며 stderr/raw SQL/raw 예외를 출력하지 않는다.

## 검증 실행 구분

제품 unit discovery는 Docker를 호출하지 않는다. 다음 focused 명령은 실제 Q20 reducer·Q24/Q26 source·Q21/Q23·issuer·pipe 경계를 검사한다. SQL 원자성·실제 DB 성공 증거로 집계하지 않는다.

```sh
PYTHONPATH=src:tests/product python3.13 -B -m unittest discover -s tests/product -p 'test_execution*.py' -v
```

root만 검토 후 인자 없이 `python3.13 -B scripts/check_execution.py`를 실행한다. 기존 PostgresLedger의 고정 image·pullnever·local unix daemon·network none·no ports·no host mount·자기 UUID project cleanup을 유지한다. runner는 migration0001/0002를 바꾸지 않고 0003의 선행 checksum·순서·idempotence를 검사한다.

runner에 다음 실제 DB 시나리오를 작성했다. 새 수정본의 실행 성공을 뜻하지 않는다.

- EX06/07/08: A598→A598→B900/U202/D0/A598, 실제 다음 후보 admission 후196.
- EX03/35: 서로 다른 facade의 두 admission 요청을 함께 시작하고, DB 잠금 경합을 별도로 확인하며302·402 양쪽 winner를 각각 검사.
- EX05: 실제 COMMIT 후 psql이 응답 frame 전에 종료되는 유실과 같은 command lookup, EX02 다른 approval 거절·세대 변경 후 SQL claim 고유성.
- EX20/21/22/23/26/39: fill-before-ACK, 다중 가격 원금190→정정290, cumulative 역순 명시 재처리·최신 정정, unknown→fee1/tax0.5→settlement, 매도 채권/결제, 중복 무변화·예약 보존·정정 및 trade/fee/tax 개별 기장 단계의 모든 fault fingerprint, collision·overfill·Q20 quarantine·비용 상한 초과 보존.
- EX38: 실제 obligations 입력의800→498→96 두 admission.

runner는 `phase`와 고정 `reason`을 출력하며 `status=partial`, `q27_complete=false`를 유지한다. 최초 root 증거와 새 runner의 작성/실행/통과를 구분한다. 전체 제품630·품질87·독립 검토는 이번 구현자 범위에서 실행하지 않는다. 실제 명령·실패/수정·SHA·시간·미실행 항목은 `/private/tmp/q27-financial-handoff.json`을 따른다.

## 잔여와 다음 순차 단계

- 앞선 cumulative sequence를 정정해 이미 기장된 successor까지 바꾸는 경우는 `cumulative_successor_dependency`로 보존·차단한다. 최신 sequence 정정과 predecessor 명시 재처리만 지원한다.
- Q23 public v1은 원본 사건만 받는 기존 의미를 유지한다. Q27의 정상 정정 성과 연결은 아래 추가 경로를 사용한다. 양수 비용→0, 결제 후 trade dependency, 앞선 누계 sequence 정정 후 이미 기장된 successor 재해석은 원래 미지원 실패 경로다. 관측·원장 근거와 보수적 hold를 보존하고 incomplete/신규 주문 차단을 유지하며 자동 해소 완료로 표시하지 않는다.
- 이번 제어 경로의 실제 DB 시나리오는 root가 실행한다. 구현자의 메모리 participant 결과는 SQL 내구성·DB 원자성·독립 검토 통과가 아니다.
- 정확한 intent별 Q20 행·index·실제 bytes·완료 용량 증명은 미완료다.1024/64MiB·384/24MiB 보호 예약의 기존 추산을 정확 계상으로 표현하지 않는다.
- SQL 제품 role은 금융 table 직접 mutation을 허용하지 않는다. 그러나 공용 `execution_save`에 대한 DB 단독 닫힌 인증/session/nonce/read-set/전이 검증은 미완료다. aggregate JSON의 NULL·잘못된 enum·정당한 hash만으로 Python 의도 경계를 우회할 수 있는 잔여를 완전히 배제하지 못한다. 새 금융 transition과 immutable 처리 결과 table을 추가한 사실을 전체 SQL 인증 증명으로 승격하지 않는다.
- root 수정본 actual DB 검사, 독립 일반/보안 검토, 이후 전체 제품/품질 검증이 필요하다. 실제 API·계좌·키·비밀번호·주문·운영 격리는 활성화하지 않았다.

## 소유 파일

이전 인계17파일 중 이번 변경 대상은 application/execution.py, adapters/postgres_execution.py, adapters/synthetic_execution_broker.py, adapters/execution_uow.py, domain/serialization.py, domain/execution_math.py, migration0003, scripts/check_execution.py, tests/product/synthetic_execution.py, test_execution_financial.py, 이 개발 안내다. 정확한 경로·변경 전/후 SHA는 인계 JSON에 기록한다. 기존 domain/ports/math·application/approval seam의 변경 전 내용은 보존한다. baseline7·공통 계약/fixture/decision/status/evidence/queue·Q26 fixture·migration0001/0002는 수정하지 않는다.


## 정상 정정 성과 추가 연결 — EXECUTION-DEC-002

`application/execution_research.py`는 공급된 전체 사건을 실제 Q20 `SyntheticLedger.append`로 재생한다. 정정은 replacement submission 한 번에서 생성된 reversal+replacement 전체를 공급된 연속 bundle과 exact 대조한다. 이전 submission을 reversal 대신 다시 append하거나 reversal을 버린 별도 가짜 원장을 만들지 않는다. 계좌·cursor·source/hash·bundle·predecessor·recorded/effective 시각·경제 값은 reducer가 생성한 객체 전체 비교에 포함된다. 현재 조회에는 동일 transaction에서 읽은 실제 DB 사건 전체와 projection이 추가 결속된다. decision 이력 없이 quarantine cursor gap을 건너뛰거나 재구성하지 않으며 fail closed한다. 이 구현은 gap 해소용 DB decision reader를 추가하지 않았다.

완전 재생 후 현재 cutoff에서 유효한 replacement head만 비용·수량·채무·일간 사용량·sellability 집계에 넣는다. 원본·inactive·reversal·미래 revision은 `ExecutionInputs.current.events`에서 보존한다. Q21 snapshot은 실제 projection과 독립 issuer statement로 재구성하며 Q23의 snapshot 재검증·flow 경계 검사·`calculate_performance`를 재사용한다. 비용은 유효 trade 및 fee/tax head의 정확한 dependency·금액·revision·배분을 공통 경제 검사로 검증한다. Q24 v1 채무 검사는 전체 재생을 마친 내부 head view에만 적용하며 원래 source와 Q23 public API는 보존한다. 임의 NAV 배열·검증 callback·allow/proof/complete bool은 추가 경로의 권위 입력이 아니다.

`build_current_inputs`와 `validate_current/current_risk`가 이 경로를 함께 사용한다. 최신 current query의 전체 scope·cutoff·Q20 cursor, Q21 평가/독립 대사, Q23 성과·비용, 현재 권리, 기존 정책·일간 사용·과거 FX를 연결한다. `refresh_current`는 기존 하나의 transaction에서 source binding과 예약별 U/D·반영 사용량·cutoff를 함께 갱신하고 다른 facade는 같은 registry의 최신 binding을 읽는다. 가격 개선으로 남은 원금 hold는 보수적으로 유지할 수 있다.

독립 literal manifest는 `tests/product/synthetic_execution.py`에 추가했다. delta1→2의 유효량2·원금190, 누계 최신 정정의190, 90/100/95 다중 가격의190→290, 비용0.5/0.25→1/0.5와 NAV998.5를 선언한다. 원장 결과를 복사해 broker 현금/수량/상태를 맞추지 않는다. 비용 차감의 query 포함 component는 원래 주문조건 hash에 결속하며 실제 issuer/예약 검사에서 소비한다. `test_execution_correction.py`와 `test_research_execution.py`의 순수/undecorated repository 시험은 local test다.

root 전용 runner에는 정상 정정4종의 fresh query→실제 Q20/Q21/Q23→다른 facade의 다음 실제 admission, EX09 실제 typed/DB 7 허용·8 거절, EX11 계좌 전체550>500(반대 매도 상계 금지), EX12 사용400+활성350+신규300=1050/시간가중NAV1000, EX13 실제 손실40+최악비용15>50 및 낙폭, EX19 실제 issuer 최종 거절만 해제·위조 hash/다른 issuer/bool 거절을 추가했다. EX12의 매수→실제 결제→매도는 미결제 매수 수량을 매도 가능량으로 승격하지 않는다. 해당 runner 추가 시나리오는 **작성했으며 이 역할에서는 Docker/DB 실행하지 않았다**. EX09 고정식의 상세 분해 `min(12-4,10-2-1)`는 별도 순수 literal 시험이며 새 DB7/8 경계를 그 상세 분해 전체의 DB 증명으로 승격하지 않는다.

최신 source freeze·시험별 실제 counts/실패/수정/시간/log·소유 SHA·보호 hash·EX별 증거와 미실행은 `/private/tmp/q27-correction-handoff.json`에 남긴다. 이전 focused47+추가7+회귀14와 root DB30은 각 당시 버전의 증거다. 새 최종 고정본의 결과와 합산하지 않는다. 전체 product/quality87은 독립 최종 단계에 남긴다. 취소/재시작·storage/SQL 후속 및 알려진 미지원 정정 경계는 그대로 남으며 runner는 partial/q27_complete=false다.


## 제어 후속 — 취소·보호 철회·현재 DB 재시작

작업 ID는 Q27-control(EX15/17/27~31/35)이다. 선행조건은 EXECUTION-DEC-002, 정정 소유22개 최종 hash, root 실제 PostgreSQL27시나리오 판정이다. 변경 전/최종 hash, 정확한 변경 목록·명령·시간·counts·미실행·고정40 mapping은 `/private/tmp/q27-control-handoff.json`에 기록한다. root 공통 문서는 이 역할이 수정하지 않는다.

`cancel(handle,intent_id,command_id=...,expected_version=...)`은 현재 controller의 별도 취소 권한, 세션·세대·독립 nonce, broker order/intent version·최대 잔량·10초 TTL을 저장한다. Q26 approve 권한은 취소 권한이 아니다. `change_cancel_permissions`는 현재 runtime controller만 호출하며 Q26 action enum에 cancel을 추가하지 않는다. `dispatch_cancel(handle,command_id)`는 금융조건을 인자로 받지 않는다. DB에서 명령/대상을 읽어 attempt를 commit한 다음, 같은 gate 안에서 새 DB transaction으로 권한·세션·nonce·세대/fence·TTL·대상 버전/잔량을 다시 검사하고 broker handoff를 한 번 수행한 뒤 receipt를 저장한다. durable attempt 뒤 fault는 자동 재전송하지 않는다. ACK는 종료나 해제가 아니며 timeout/unknown 중에도 기존 submit receipt의 실제 fill을 받는다.

취소 확인은 실제 issuer의 cancel request journal에 있는 `cancel_ack` receipt에 결속된 사건만 허용한다. submit receipt나 로컬 issued 명령으로 취소 확인을 발급할 수 없다. 확인 수량과 현재 잔량이 정확히 일치해야 하며, 확인된 미체결 수량에 해당하는 principal/quantity/risk 부분만 해제한다. 주문 전체 비용과 가격 개선 잔여 쿠션은 별도 금융 근거까지 보수적으로 보유한다. 역순 확인이 아직 반영되지 않은 fill과 충돌하거나 확인량이 다르면 사건·원장·예약을 보존하고 incomplete/faulted로 차단한다. 뒤늦은 fill이 도착해도 충돌을 자동 해소하지 않는다. 중복은 무변화이며 terminal 이후 late fill은 근거를 보존하고 중단한다. 자동 retry/replace/FX/청산 경로는 없다.

submit에도 attempt commit 뒤 새 DB 최종 검사(`_handoff_ready`)를 추가했다. stop·withdraw·세대·권한·source/policy 변경은 같은 broker/account gate를 사용한다. `replace_source`는 명시 runtime 권한으로 DB hash를 갱신하고 다른 facade는 공유 registry의 source/current inputs를 다시 읽는다. 보호 withdraw는 현재 report/risk 소비 권리와 분리하며 독립 controller 새 세션에서도 가능하다. consumed/claim은 보존하고 withdrawal만 별도 기록한다. durable dispatch attempt가 남은 경우 before_handoff fault라는 이유만으로 미전송을 추정하지 않는다.

`PostgresExecutionRepository.restart(database,new_authority,source,approval_policy,inputs,broker,expected_generation=...)`는 root의 합성 composition용 명시 API다. 기존 DB load·ledger/account/head lock·현재 generation CAS·원본/current input hash 확인 후 DB 밖 UUID 세대를 발급해 stopped/restored로 시작한다. JSON snapshot import는 받지 않는다. 새 authority는 실제 opaque handle을 새로 발급하며 old handle/session/pending/approved/nonces는 실행 권한으로 재사용하지 않는다. consumed/claim/prepared/unknown/예약/원장·사건 이력은 보존하고 dispatching은 unknown으로 바꾼다. 세대 변경 후 원본 source는 원래 세대로 재현하며, 새 DB 실행 세대는 `ExecutionInputs.runtime_generation`의 저장 hash로 별도 결속한다.

새 issuer는 기존 독립 broker journal이 실제 보존된 경우만 금융 근거를 확인한다. 새 broker issuer에 old facts 파일을 주어 권위로 승격하지 않는다. journal을 잃으면 확인 못한 outstanding은 unknown이며 관찰만 가능하다. 이전 executor의 실행 권한은 최신 세대 검사로 거절한다. 이미 실제 journal에 발급된 receipt/fill은 새 runtime의 결과 저장 경로에서 보존·반영할 수 있으며, 이 금융 사실의 수신은 자동 resume를 의미하지 않는다. rollback/응답 오류 시 새 issuer의 authority publish는 성공 commit 이후에만 수행한다.

`rebind(new_controller,actual_query)`는 stopped/reconciling 상태에서만 실행한다. 실제 full-scope query의 request/order attempts·receipts·fills·cash/qty·journal sequence/반영 cutoff를 독립 issuer journal과 대조하고 Q20 전체 이력·현재 projection, Q21 독립 대사, 정정 대응 Q23 성과·현재 source 권리를 갱신한다. unknown cost·미처리 receipt/event·quarantine·claims/consumed/예약 manifest를 검사한 저장 reconciliation이 matched여야 한다. `control(controller,'resume')`는 별도 명시 호출이며 DB account version·ledger cursor·현재 generation/fence와 source/권리를 다시 검사한다. 새 세션 발급 등으로 DB/readset이 바뀌면 reconcile을 다시 해야 한다. complete bool·빈 조회·날짜/세대 변경·matched 보고서 복사로 unknown을 해제하지 않는다. 미지원 Q20 정정과 quarantine는 자동 해소하지 않는다. 과거 backup 복원은 Q28 범위다.

제어 unit 시험은 실제 승인/위험/reducer/broker와 공개 API를 사용하되 SQL 대신 명시 메모리 transaction participant를 둔다. allow/risk를 mock하지 않으며 제품 unit discovery는 Docker를 호출하지 않는다. root runner에는 별도 실제 DB 취소 ACK/unknown/확인 충돌, 양방향 stop/withdraw barrier/thread 경합, 권리 회수 후 보호 철회, 정상 정정 후 새 issuer rebind/resume/새 후보 승인, quarantine·unknown·before_handoff·late completion 보존 시나리오를 추가했다. 두 thread 시험은 공유 Python gate 검증이며 여러 DB 프로세스의 강제 격리 증명이 아니다. SQL 자체 닫힌 인증/정확 저장 용량 증명은 여전히 남으므로 partial/q27_complete=false를 유지한다. EX09의 순수 `min(12-4,10-2-1)=7`과 이전 실제 DB의 단순 B7/qty7·8 경계를 상세 분해 전체의 DB 증거로 합치지 않는다. nonzero sell hold/postquery fill/부분 반영을 모두 함께 재현하는 상세 DB 증거는 잔여다.

세대 교체에서는 이전 commands/nonces/receipts의 live lookup을 `retired_commands` 이력으로 원자 이동하고 immutable evidence는 계속 저장한다. 새 세대는 이 인덱스를 권한으로 읽지 않는다. 옛 세대에서 완료할 수 없는 명령 몫을 회수하고 consumed 승인에는 남은 보호 철회 횟수당8records(발급3+완료5)를 남긴다. 금융 principal/cost/quantity/risk 예약과 intent의 보호 몫은 변경하지 않는다. 이 조정은 Q26의128records 상한을 올리지 않으며, 옛 세대 전체 이력은 Q27 aggregate/SQL 저장 한도 안에 계속 남는다. 이력/index/실제 bytes의 정확 계상 증명은 잔여다. `current_runtime(database,account)`는 commit 응답 유실 후 현재 DB 세대/version/mode/fence만 관측해 다음 명시 CAS를 가능하게 하며, 반환값 자체로 session/복원 권한을 얻을 수 없다.


마지막 복구 경계 보완: reconciliation 자체에 현재 controller session ID와 current source hash를 저장하고 resume에서 일치 여부를 검사한다. ledger 값이 같아도 독립 query의 cash/qty·statement·반영 cutoff·request/receipt/event manifest가 현재 typed source와 다르면 refresh_current와 reconcile을 다시 해야 한다. 다른 기존 controller session의 matched 결과를 복사해 resume하지 않는다.

`resolve_unsent(current_controller,intent_id)`는 stopped/reconciling의 durable submit attempt에 대한 명시 수동 복구다. 동일한 실제 broker issuer의 request journal이 미수신을 확인하고 해당 attempt를 폐기해 발급한 `proven_unsent` receipt만 aborted_unsent/해제를 허용한다. 실제 수신 후 timeout인 요청이나 journal을 잃은 새 broker issuer는 해제할 수 없다. 자동 recover/withdraw는 이 증거를 추정하지 않는다. 성공해도 consumed/claim은 남고 resume는 별도다. 0003에는 이 사실에 필요한 dispatching/unknown→aborted_unsent 전이만 추가했다. 기존0001/0002와 SQL 인증 미완료 판정은 보존한다. 이 마지막 보완은 새 시험과 영향을 받는 경계만 추가 확인하며 앞선 고정본의 녹색 시험 전체를 반복하지 않는다.


## 저장·SQL 후속 구현 — EXECUTION-DEC-003, 2026-10-25

이번 후속은 부분 구현이며 실제 PostgreSQL 실행·최신 전체 제품·독립 검토를 통과한 상태가 아니다. root quarantine restart의 원본 typed event_id/receipt_id 검증을 보존한다. 과거 제어 final1 집중15+영향39, final2 경계7, root 수정 후 DB11은 각각 당시 버전의 증거다.

`execution_budget.py`는 최초 Q20 append8행·정정11행(미래 consumer inbox 포함), 실제 canonical/index key byte 계상의 순수 경계를 제공한다. 고정 manifest의 trade/fee/tax 최초24+정정7×33=255행은 broker journal 생성 전에 거절한다. SQL meter는 실제 event/reversal/journal/decision/projection/outbox/delivery/inbox와 PK/UNIQUE key를 읽고, 복제된 state bytes도 소유자에게 분배한다. owner별 actual+remaining과 32/64/192/64/32, 384/24MiB·공통128/8MiB·source8MiB·총1024/64MiB를 유지한다. 이것은 PG disk/WAL/MVCC/RSS 한도가 아니다. Q26의 원래 map별128/8MiB 검사는 별도로 남는다.

`retired_commands` archive는 만들지 않는다. 세대 변경 시 사용 불가능해진 commands/nonces/receipts/cancel_nonces 인덱스를 퇴역시킨다. 원본 불변 ActionChallenge/ActionReceipt는 계속 Q26에서 계상하고 과거 결과는 `command_result`가 임시 조회로 재구성한다. 남아 있는 map의 행당 계상은 그대로이며 SQL의 실제 UNIQUE key bytes도 센다. 옛 session/generation의 실행 권한은 복구하지 않는다. consumed 이후 approve/deny/admit의 불가능해진 미래 몫만 회수하고 남은 withdrawal 두 슬롯과 발급된 미완료 명령의 완료비용을 보존한다. active2는 미종료 의도 수로 센다. terminal의 미래 슬롯이 모두 소진됐거나 확정 미전송/거절인 경우에만 저장 예약을 줄이며, claim/consumed/history/금융 reservation은 남긴다. 동일 quarantine 결과·같은 query/read-set의 reconciliation은 재기록하지 않는다. issuer event ID는 intent와 고정 fact label로 결속해 두 의도의 같은 fixture label이 영속 UNIQUE에서 충돌하지 않게 한다.

제품 SQL 역할은 generic save/event/ledger_append 및 context 생성/청크 발급을 실행할 수 없다. trusted Python이 opaque registry·현재 actor·issuer fact를 검증한 연결에서 owner 구간으로 context를 발급하고, 제품 역할은 backend/transaction/action/버전/read-set에 결속된 일회성 context만 소비한다. SQL은 현재 session/permission·command nonce·대상 버전·고정 전이·이전 hash·불변 terms·closed field/type/NULL/decimal/UTC와 deferred consumed↔claim↔intent↔outbox를 검사한다. ledger append는 저장된 terms와 검증된 fact에서 다시 도출한다. owner가 RESET/SET LOCAL ROLE을 할 수 있는 신뢰된 host 구성이다. hostile owner 격리, 실제 인증/실전 거래 권한을 뜻하지 않는다. 실제 AUTH와 구조 음성은 root가 별도로 실행해야 한다.

UoW는 전체 snapshot을 다시 쓰지 않고 변경된 map entry/evidence/head/의도·예약·attempt만 전달한다. 같은 연결에서 byte paging·청크 staging을 사용한다. raw chunk65536/header4096/직렬화 후 hex frame135168/최종 frame8MiB, 누적 I/O256MiB·전체 transaction120초·교환20초·SQL statement15초/lock10초·금융 자동 retry0이다. 잘못된 sequence/JSON/UTF8/추가 출력/EOF/timeout은 transaction을 폐기하며 staging/context/read-buffer가 COMMIT 때 남을 수 없게 한다. 전체 typed state와 JSON은 여전히 메모리에 물질화한다. 이를 RSS 한도나64MiB 저장 전체의 PG 실측 증명으로 표현하지 않는다.

EX09의 `min(12-4,10-2-1)=7` 양성과 qty8 거절, EX11 기존400+활성매수100+신규50=550>500 및 반대 매도 미상계는 root의 `execution-database-storage-focused-initial-2026-10-26.json`에서 실제 DB 통과했다. EX11을 세 번째 presentation 용량 검사와 합산하지 않는다. 해당 증거는 그때의 고정본이며 이번 SQL 수정 후 실제 DB 재실행은 root 담당이다.

2026-10-27 후속은 `/private/tmp/q27-storage-followup-handoff.json`에 별도 인계한다. `execution_check_command`는 기존 영속 challenge 검사를 유지하면서, 같은 TX의 신규 challenge는 withdraw/save에 한해 허용한다. 현재 issuer/principal/session/action/generation/nonce/target/version과 같은 delta의 정확한 challenge·receipt·withdrawal 결과 및 commands/nonces/receipts map 참조를 결속한다. 이미 영속 receipt가 있는 command의 새 SQL 실행은 거절하며 공개 replay는 원본 결과만 관측한다. DB runner AUTH 음성은 PL/pgSQL에서 정확히 `execution_auth`만 수용하여 구문·권한·구조 실패로 성공을 대신하지 않는다.

공통 예약은 실제 공통 행/index/copy bytes에 `execution_common_remaining`의 필수 미래 몫을 더해128/8MiB 안에서 검사한다. session terminal·stop, 발급된 미완료 명령, 남은 보호 withdraw의 runtime, prepared dispatch의 source/risk, 최초 consumer cursor/workstate와 유한 복구 capsule을 포함한다. SQL이 `execution_account.common_plan`을 관리하며 제품 state JSON에는 해제 권한이 없다. capsule18행은 두 session의 principal/event/session/head/hold 각5+종료 제어 각2, query/reconciliation2, resume와 stop2다. 초기 bootstrap와 다음 복구는 별도 몫이다. 생성 시 실제 행/현재 종료 예약으로 옮기며 generation에서 다음 capsule을 bootstrap으로 옮긴다. 새 admission은 다음 복구를 예약하고, 추가 선택적 generation은 실제 남은 공간에 들어야 한다. 작은 evidence 실제 행8192, index 합4096, escaped state copy20480; 큰 wire65536와 copy147456의 강제 상계를 사용한다. SQL 상계의 실제 PostgreSQL 실행·독립 검토는 미실행이며 전체 필수 경로의 완료 보장이 입증됐다고 표시하지 않는다.

종료 owner의 control 예약도 무조건64를 유지하지 않고, 실제 남은 withdraw 슬롯 각8과 현재 generation의 미완료 명령 각6을 보존한다. 미처리 consumer inbox는 계속 보호하며 claim/consumed/원본 history/예약 원장은 삭제하지 않는다. category/owner/total 한도는 늘리지 않는다.

세 번째 admission 양성은 잔여다. root와 같은 두 principal 구성에서 두 intent 종료, 각 보호 withdraw 두 슬롯 완료, 새 generation/session, 실제 rebind/resume 및 controller disconnect 뒤에도 세 번째 presentation은 실제85+미래48=133>128로 거절됐다. 원본 이력·claim은 그대로다. 이 구체 경로에서는5행 부족하며 active3 gate까지 도달하지 않았으므로 active3 거절이나 terminal-third 양성의 증명이 아니다. 모든 다른 구성이 불가능하다는 일반 증명도 아니다. 한도·Q26 제시 예약40·공개 보호 의미를 임의 변경하지 않았다.

UoW는 프레임/읽기/쓰기 오류를 포착하면 connection을 닫고 실패를 latch한다. 호출자가 오류를 잡아도 COMMIT은 거절한다. 로컬 pipe는9MiB 초과 UTF8 왕복을 검사한다. root runner에는 실제 DB staging→paged load→savepoint 복원→COMMIT의 큰 전송 진단, 누락/충돌/순서/UTF8/중복 key/EOF/timeout/추가 출력과 staging0, 금융 COMMIT EOF 후 receipt 관측을 추가했다. 큰 진단 payload를 금융 권한이나 큰 제품 delta로 채택하지 않으며 전체64MiB 논리 저장 성공 증명은 잔여다. 전체 typed state/JSON 물질화 및 기존 ledger capture_output은 RSS 한도라고 주장하지 않는다.

정확한 변경 SHA·source freeze·명령/시간/count/log SHA·미실행은 `/private/tmp/q27-storage-handoff.json`에 반환한다. root가 공통 status/계약/queue/evidence를 통합한다. 이 역할에서는 해당 파일이나 frozen baseline7·0001/0002·Q26/Q27 fixture를 수정하지 않는다.

영향 검사에서 archive 대체 초안이 옛 command/nonces/receipts map까지 영구 보존하여 기존 restart 후 새 후보 제시를 막는 회귀를 확인했다. 최종 수정은 권한이 없는 세대의 live index만 퇴역시키고 원본 evidence 기반 결과 조회를 제공한다. 불변 이력 삭제·Q26 한도 확대·다른 quota로의 이동은 하지 않는다. 해당 red와 수정 후 집중 결과는 인계에서 버전별로 구분한다.


## Q27 DEC-004 구현 인계 (2026-10-27)

이번 변경은 로컬 합성 실행의 완료 예약과 완료 command 조회에 한정한다. UI·운영 연결·금융 산식과 고정 용량은 바꾸지 않았다. 실제 PostgreSQL 실행과 최종 전체 판정은 root 담당이며, 아래 SQL 경로를 작성한 것과 실제 DB 통과를 구분한다.

`reclaim_completed(controller_handle)`는 현재 query 권한을 가진 controller가 호출하는 별도 원자적 유지 작업이다. 정확한 immutable `ActionChallenge/ActionReceipt` 쌍이 있는 명령의 `commands/nonces/receipts` 세 lookup만 회수한다. 원본 records·heads·UNIQUE·history·consumed·claim·금융 hold·pending 명령은 보존한다. 다른 owner의 쓰기를 같은 회수 transaction에 섞지 못하도록 SQL에서 업무 상태와 변경 목록을 대조한다. 회수량으로 다른 owner의 예약 소비를 상쇄하지 않는다. 재전달은 영속 lookup을 다시 만들지 않고 원본에서 정확한 challenge/receipt를 해소한 뒤 현재 actor/session/generation/action/target/nonce/hash/원천 권한을 확인한다. old-generation 실행은 거절하고 권한 있는 과거 결과 조회는 유지한다.

공통 예약은 live session의 종료2행과 controller별 현재/향후 stop 각각에 stop1행+같은 query의 재대사1행을 별도로 계산한다. 미사용 session slot은 실제5+종료2+두 stop/재대사 쌍4=11행이다. 다음 공유 복구의 초기 상계는 `2×11 + query/reconciliation 2 + resume 1 = 25`행이다. 이 수치만으로 충분성을 주장하지 않는다. session role, 현재 mode와 generation의 보호 stop 기록, query 보존 여부, 정확한 reconciliation의 account version/source/fence/session, 남은 withdrawal 및 issuer slot을 함께 계산한다. 보호 stop 후에는 mode를 다시 바꾸지 않는 reconcile로 준비를 복원할 수 있다. stopped를 다시 reconciling으로 여는 추가 rebind는 새로운 선택 작업으로 용량을 확보해야 한다. small evidence/index/records copy의 강제 상한과 재대사 사본 여유를 사용하고, 계좌 메타데이터·현재 reconciliation 사본까지 `execution_common_charge`로 전후 측정한다. 이미 예약한 restart/session/rebind/resume/stop/disconnect 단계는 행·bytes 각각 actual+remaining 증가를 거절한다. 한도는 공통128/8MiB·owner384/24MiB·총1024/64MiB·Q26 별도128/8MiB 그대로다.

공유 복구는 같은 계좌·generation/fence의 전체 issuer journal·원장·모든 intent를 동일 current read-set에서 함께 matched로 만들 수 있을 때 한 번으로 충족한다. intent별 미완료 command·withdrawal·금융 의무는 별도이며 서로 상계하지 않는다. 새로운 session/source는 기존 준비를 무효화하면 재대사 예약을 다시 확보해야 한다. 진행 중인 복구에서 새 source가 기존 approval의 원 후보를 해소할 수 없으면 부작용 없이 거절한다. 새 후보 source는 기존 source로 명시 복구/resume를 마친 뒤 교체할 수 있으며 새 admission은 새 source로 실제 위험 계산을 다시 실행한다.

로컬 focused red는 회수 경로가 없던 세 사례를 관찰했다. 구현 후 같은 generation에서 두 실제 intent를 확정 미전송 종료하고 각 withdrawal2를 완료→lookup24행 회수→유효 controller로 stop/rebind/resume→source 교체→세 번째 present/approve/admit/dispatch 양성을 관찰했다. 별도 active3 검사는 두 acknowledged intent의 금융 hold를 보존하고 실제 위험 계산을 거쳐 admission의 active2 gate에서 거절한다. 기존 restart 후 `85+48=133>128` 음성은 다른 경로의 기록으로 유지한다.

root runner에는 `completion_recovery_orders`(일반/두 controller/rebind 후 approver), `completion_same_generation_third`(terminal/active), `completion_lookup_atomicity` 여섯 DB 시나리오를 추가했다. 전이별 actual+remaining 행·bytes, 타 owner 예약, pending map 손실, 정확한 회수 행·copy bytes, replay 권한/변조/old-generation, receipt/save/COMMIT rollback과 응답 유실 관측을 검증한다. 기존 55개 시나리오는 유지한다. 새 SQL의 실제 실행·용량 도달성·전체 bytes 충분성·최종 전체 제품/품질·독립 검토는 아직 완료 증거가 아니며 Q27은 partial이다. 보수적 추가 예약으로 기존 양성의 용량 여유가 달라질 수 있으므로 root는 새 DB 버전에서 이 여섯 시나리오와 기존 포화 경로를 먼저 확인해야 한다.

### root 실제 DB 보정 — 2026-10-27

위25행 예약은 구현자 인계 시점의 초안이다. 실제 DB 재대사에서 새 query와 reconciliation2행이 생기지만 미래1행만 예약되어72→73행이 되는 반례를 확인했다. 현재 SQL은 repair2행/393216bytes, stop+repair3행/458752bytes, 세션13행/1376256bytes, 다음 공동복구29행/3211264bytes를 확보한다. 정상/두controller/세션추가 후재대사·보호stop·reconcile·resume와 같은 세대 terminal-third admission/dispatch는 이 SQL 버전의 실제 DB에서 통과했다. 고정128/8MiB 등 상한은 유지한다.

active3는 실제 command 발급에서 actual66+future65=131행으로 먼저 거절됐다. 기존 완료 승인의 중복 lookup3행을 유지한 상태이므로 새 admission challenge 전 같은 controller의 기존 `reclaim_completed`를 한 번 더 실행하는 검사 경로를 추가했다. 원본 approval/challenge/receipt·활성 금융 hold는 보존하고 실제 admission gate 거절을 여전히 요구한다. 이 보완은 후속 실제DB에서 active gate 도달2와 capacity_exceeded 거절, 신규 intent/claim 없음·기존 hold 보존을 확인했다. 초기 실패/진단·수정은 root 증거에 별도로 보존하며 미실행 full61·독립/전체 판정과 합산하지 않는다.

거절 admission에서는 내부의 원 승인 권한 검사(`approve`)가 SQL actor/action 문맥에 남는 실제 오류도 확인했다. `execute`는 결과 생성 뒤 원래 handle·challenge action을 현재 권한으로 다시 인증하고 SQL command에 결속한다. SQL의 actor/action/nonce/session 비교는 그대로이며 이를 우회하는 flag는 없다. 수정본 실제DB6시나리오/11검사묶음(380.178초)에서 인증 음성·active3·조회회수원자성/응답유실·포화후종료·기존terminal용량음성·대용량전송을 통과했다. 소유28 SHA 전후 불변·ownDB6정리. 앞선 정상/두controller/무효화복구/terminal-third 양성은 재인증 보완 이전 버전의 집중검사이며 최신 전체61 또는 독립 판정으로 합산하지 않는다.

### SEC1·SEC2 보안 보완 — 2026-10-27, root 실제 DB 재실행 전

공개 `execution-completion-security-red-2026-10-27.json`의 실제 SEC1 반례는 두 intent와 각 withdrawal2 완료→restart→controller/approver→matched rebind→approver disconnect다. 종료가 대사를 무효화하면서 actual+remaining이73→74행, 1,477,951→1,746,007bytes로 증가해 rollback됐다. 비controller의 live 종료 예약에 종료2행/131072bytes와 새 query+대사2행/393216bytes를 함께 둔다. 미사용 슬롯에서 실제 발급5행까지 합쳐9행/851968bytes다. 기존 controller의13행/1376256bytes 및 다음 공동복구29행/3211264bytes 안에 들어가므로 한도를 늘리지 않는다. 종료 후에는 그 세션의 예약이 사라지고 공유 재대사 예약만 남는다. 타 controller·intent의 몫은 빌리지 않는다. 실제 red 측정에 이 예약을 적용한 산술은75→74행, 1,871,167→1,746,007bytes이며 수정본 SQL 실행값은 아니다.

session은 시각 만료나 permission 회수만으로 paused로 바뀌거나 종료 예약을 잃지 않는다. 명시 disconnect는 현재 인증을 거치며, 세대 교체는 기존 generation invalidation 경로를 사용한다. approval의 revoke/expire/deny는 session 종료와 다른 command/approval 예약 경로다. 이 경로의 read-set 무효화 비용까지 SQL 전체 충분성이 증명됐다는 주장은 하지 않으며 별도 검토 사항을 인계한다.

SEC2는 `_handoff_ready`의 실제 최종 DB read/risk 검사와 COMMIT·연결 정리가 끝난 뒤 시각이31초 진행해도 전송되던 결함이다. 내부 불변 `_HandoffWindow`는 같은 lock 아래 확인한 실제 attempt/intent·검사시각·모든 별도 deadline을 묶는다. submit에는 actor와 원 approver의 principal/session 만료·liveness, approval TTL, 승인 정책, 원 요청, 새 위험 결정의 전체 원천/가격/FX/권리/분류 유효시간, 실행 정책·일간 창·주문조건·비용규칙·capability를 포함한다. 취소에는 별도 protective actor/session/liveness·command TTL을 묶는다. 기존 보호 취소에 원 승인/시장자료의 유효성을 추가 요구하지 않는다.

`dispatch`/`dispatch_cancel`은 최종 DB 메서드 반환 후 broker handoff 바로 앞에서 현재 시각을 읽어 모든 deadline의 최솟값과 대조한다. 과거 시각·잘못된 시계는 `clock_invalid`, 만료는 `expired`로 실패한다. 이 사이 DB I/O나 공개 bool/callback은 없다. 공유 gate가 다른 권한/원천/세대 전이를 막고, 단조 시각 검사가 이미 통과한 valid_from도 보존한다. 실패 시 영속 armed attempt와 금융 hold를 유지하며 새 세션으로도 자동 재전송하지 않는다. `_handoff_ready`의 내부 반환만3항으로 바뀌고 공개 repository·broker API는 유지한다.

root runner는 기존61사례를 보존하고5사례를 추가했다. `completion_security_disconnect`는 필수 전이마다 실제 공통 행/index/copy bytes와 remaining을 관측해 비증가·owner 예산/금융 본문 불변·paused·새 rebind/수동 resume를 요구한다. `completion_security_handoff`는 submit/cancel의 실제 최종 DB 반환 뒤 시계31초 및 cancel TTL 경계만 주입하여 수신증가0·정확 expired·armed/hold·noresend를 검사한다. `completion_security_handoff_positive`는 최종 반환 뒤1초 진행한 정상 submit/cancel을 확인한다. 새5사례와 최신전체66 DB는 작성만 했으며 여기서는 Docker/실제 DB를 실행하지 않았다. 집중 unit의 저장 participant는 PostgreSQL 증명이 아니며 SQL 산술 검사는 공개 actual red 측정과의 비교다. 최종 source freeze·명령/시간/개수/로그 SHA·보호파일 대조는 별도 임시 인계 JSON을 따른다. 독립 검토·전체 제품/품질 unittest·고정40 최종 판정은 root/validator 담당이다.


### Q27 종료 예약 수명주기 후속 — 2026-10-27

작업 ID는 Q27-lifecycle-fixes이며 입력은 EXECUTION-DEC-004 마지막 수명주기 보정, 직전 보안수정 소유28 hash, 실제 DB 보안/adjacent 진단이다. 수정 소유는 0003·SQL 집중 시험·root runner·이 문서 네 파일이다. 기존 SEC2 `_HandoffWindow`, execute 재인증, SQL stage 별칭·issuer·raw wire hash 결속과 나머지 source28은 보존한다. 고정 한도·baseline7·fixture·0001/0002·공통 계약은 바꾸지 않는다. 주 담당이 공통 상태를 통합하며 이 worker는 임시 인계 JSON만 작성한다.

비controller의 live terminal 예약은 `plan.resume=0`인 running/일반 stopped에서 2행/131072bytes, 이미 resume 의무가 있는 복구에서 4행/524288bytes다. 선택적 rebind가 resume 의무를 새로 만들면 살아 있는 각 세션과 미소비 승인·발급 명령의 추가 repair 비용까지 같은 SQL 사전 용량 검사에서 확보한다. 보호 disconnect는 mode를 바꾸지 않는다. 정상 running active3의 이전130행 중 불필요한2행만 빠지므로 기존 fixture·명령·실제 active admission assertion은 그대로다. 이는 산술이며 새 실제 DB 통과 주장이 아니다.

필수 restart는 기존 next29행/3211264bytes를 두 session13행/1376256bytes와 repair2행/393216bytes 및 resume1행으로 옮긴다. 세션의 실제 발급5행과 비controller 최대 live4행은 같은13행 슬롯 안에 들어간다. 필수 rebind는 이미 확보한 query+대사2행을 actual로 바꾸고, 수동 resume는 event1행을 쓰며 resume 의무와 세션/명령의 복구 추가분을 해제한다. running에서 stop은 controller의 기존 stop/repair3행을 쓰되 resume 의무를 새로 만들지 않는다. ordinary stopped→rebind는 선택 동작이므로 charge 증가를 허용하되 미래 의무까지 한도 안에 들어야 commit한다. 이미 멈춘 복구의 새 elective rebind와 mandatory repair의 기존 구분을 보존한다.

미소비 승인 보호 명령은 running/일반 stopped에서 발급 시 최소5행, resume 의무가 있으면6행을 확보한다. runtime+새 approval version+receipt+receipt lookup은4행이며 마지막 hold가 없어지면3행이다. 복구에서는 새 query+대사2행이 더 필요하다. 거절 receipt만 생겨도 aggregate version이 바뀌어 matched read-set이 무효화된다. 비보호 발급 명령도 expiry/invalidation을 만들 수 있으므로 복구 중6행, approve는 기존9행을 유지한다. consumed approval의 명령은 기존 owner 예약에서 처리하며 공통 명령 예약 계산은 건너뛴다.

승인 자체의 예약은 보호 명령 발급 후에도 유지한다. 마지막 명령이 TTL 만료로 거절될 때 approved가 살아 있으면 종료 의무도 계속되므로 이전의 `protection_pending→0` 상계는 성립하지 않는다. approved는 평상시7행, 복구 중 미완료 명령이 없으면8행·있으면9행이다. 같은 TX의 새 challenge/index3행+종료3행 또는 hold 유지 시4행+repair2행을 이 승인 예약이 직접 부담한다. 발급 명령의 예약과 서로 다른 약속이며 타 owner 비용으로 상계하지 않는다. pending approval의2행과 immutable current-generation challenge/receipt 기준은 유지한다. 다른 명령이 이미 승인을 종료해도 남은 issued 명령의 거절 완료 예약은 유지된다.

bytes는 행 예약의32768 단위와 기존262144 복사 여유에 더해, 복구 중 각 approved 및 미소비 발급 명령에 repair393216bytes를 사전에 둔다. bounded evidence/state-copy·index 묶음을 challenge65536, runtime65536, approval327680(두147456 이하 복사와 key), receipt/lookup65536으로 보수 계산하면 issued 종료+repair851968bytes와 atomic 종료+repair917504bytes가 각각 command6행 및 approval8행 예약 안에 들어간다. hold 유지에는 approval9행을 남긴다. SQL의 기존 실제 저장행/index/중복 state bytes 계측과 두 completion 부등식을 함께 유지하며, 이 상계는 실제 측정을 대신하지 않는다.

completion guard는 미소비 approval의 revoke/withdraw receipt(적용·거절·같은 TX 발급 포함)와 expired/invalidated terminal 전이에 적용한다. 기존 exact actor/session/action/nonce/hash·같은 TX challenge 검사는 먼저 그대로 수행한다. consumed withdrawal과 성공 approve/admit를 이 추가 guard에 포함하지 않는다. 실제 adjacent 진단90→91행 반례를 같은 입력으로 재계산하면 새 예약상 before101행/6820254bytes→after91행/5427847bytes로 예상한다. 이는 옛 actual 측정에 새 예약을 적용한 예측이며 수정본 DB 관측값이 아니다.

root runner는 기존66개 AST를 순서·내용까지 보존하고 `completion_approval_terminal`7개를 덧붙여 총73개다. kwargs는 기본 issued revoke, `action='withdraw'`, `action='withdraw',atomic=True`, `sibling='withdraw'`, `action='withdraw',atomic=True,sibling='admit'`, `expiry='command'`, `action='admit',expiry='approval'`다. 발급은 선택 동작으로 charge와 caps를 관측하고, issued/atomic 보호 종료·거절·fresh query+대사·manual resume에는 실제 rows/bytes 비증가를 요구한다. 현재 actor/nonce와 권한 철회 후 replay 음성, pending map 제거 시 immutable reserve 불변 및 실제 deferred atomicity 거절, 기존 evidence 보존도 검사한다. heartbeat 포화로 revoke 실패를 주장하지 않는다.

expired target 사례는 별도 경계다. 기존 `application/execution.py:validate_current`가 복구에서도 원래 approval TTL을 요구하므로 expired approval 이후 fresh reconcile은 unresolved이고 manual resume는 차단될 것으로 예상한다. 새 사례는 terminal 완료 비증가와 이 기존 fail-closed 경계를 각각 검사한다. 이 source 계약 수정은 허용 소유 밖이어서 변경하지 않았으며 실제 DB 결과와 root 판단이 필요하다. 다른6개 시나리오의 성공 경로와 합쳐 모든 보호 종료 복구가 통과했다고 주장하지 않는다.

이 worker는 수정된 SQL 집중 검사와 공개 quality/team/diff만 수행한다. 실제 PostgreSQL7개 신규·기존 active3/SEC1/복구 전이, 독립 검토, 최신전체73 DB 및 제품/품질 unittest는 root/최종 validator가 수행한다. 정확한 source freeze·실행 명령/시간/개수/로그 SHA·보호 snapshot·미확인은 `/private/tmp/q27-lifecycle-fixes-{preversion,sourcefreeze,handoff}.json`에 남기며 이전 인계를 덮어쓰지 않는다. Q27 partial 유지.


## DEC005 현재 계좌 복구 구현 인계 (2026-10-27)

주문 `validate_current`는 실제 Q24 재현·candidate/terms·approval/request TTL을 계속 검사한다. 내부 `_validate_account_current`는 승인을 받지 않고 계좌 전체 Q20/Q21/Q23·시장자료·현재 권리·실행/target 정책의 절대 유효구간을 계산한다. 원 요청을 연장하거나 가짜 승인으로 복구하지 않는다. 신선도 종료는 실제 source/price/FX 시점과 정책·권리의 교집합이며 검사 시각에 TTL을 더하지 않는다.

`refresh_current`/`rebind`의 선택적 `execution_policy`는 현재 `policy` 권한, 정확한 account/target 정책 참조와 다음 버전을 요구한다. `rebind(..., market_inputs=..., execution_policy=...)`는 잠긴 실제 원장·issuer query로 현재 자료를 재계산한다. 현재 정책이 만료됐으면 적법한 새 정책 없이는 재개하지 않는다. `replace_source`는 새 Q24 자체를 실제 재현하며 옛 candidate를 새 source에서 찾지 않는다. 이전 pending/approved는 invalidated, consumed/claim/원본 evidence는 보존한다. `source_archive` 원문과 registry의 원본 repository 연결을 보존하고 source8MiB 및 실제 저장행/복사본 예산에 계상한다. 용량 부족은 선택 작업 전에 거절한다.

새 대사는 current identity·검증 버전 `q27-account-current-v1`·절대 유효구간을 포함한다. SQL owner context는 같은 source/version/generation/fence/query/cursor를 결속하고 `common_plan`과 명시 resume도 같은 결속을 검사한다. identity는 변경 탐지값이다. runtime은 정책 참조를 바꿀 수 없다. 같은 gate 안에서 commit 이후에만 자료를 registry에 공유하고 rollback은 staging을 버린다. COMMIT 응답 유실은 새 connection의 DB 결속·정확한 version을 관측해 해소하며 불명확하면 공유 registry 전체를 차단한다. 금융 write를 재시도하지 않는다.

재시작 시 archive가 존재하면 `restart(..., source_history=(...))`에 정확히 보존한 합성 원본 repository 연결을 제공해야 한다. DB archive와 byte 단위로 다르면 거절한다. 옛 형식 matched는 새 검증 없이 resume 근거로 사용할 수 없다. unknown/prepared/armed·비용 미확정·미지원 정정·예약/manifest 불일치는 자료 교체로 해소하지 않는다. SEC2의 DB commit/close 이후 전송 직전 시각 검사는 유지한다.

작성된 실제 DB 행렬은 기존73개를 유지하고 DEC00511개(승인 0개, request/정책 만료 분리, 새 source와 실제 새 후보 실행, runtime 권한, unknown/cost hold, 현재 권리, rollback/COMMIT EOF/SQL read-set)를 추가한다. 기존 expired-target 진단 JSON은 보존하고 해당 시나리오의 새 기대는 matched/명시 resume와 옛 승인 0효과다. 이 문단은 실제 DB 통과 증거가 아니다. 단위 memory participant는 PostgreSQL 원자성을 증명하지 않는다. root 실제 DB → 독립 보안/일반 검토 → 최신 전체 validator가 남으며 Q27 partial이다.

같은 원본의 권리 축소는 별도로 보존한다. 요청·artifact·repository·시장/원장 자료가 정확히 같고 purposes 축소 또는 revocation만 빨라지는 경우에는 현재 권리를 회수할 수 있다. 이 전이는 새 유효 자료·matched·주문 권한을 만들지 않으며 보호 철회를 막지 않는다. 최초 source는 실제 Q24 재현 후 결속한다.
