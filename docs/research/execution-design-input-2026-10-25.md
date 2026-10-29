**Q26 로컬 수락을 전제로 Q27 설계를 진행할 수 있습니다. 다만 구현 배정 전에 root가 승인·실행의 단일 DB 권위, 현재 위험 계산, broker 증거 계약을 먼저 고정해야 합니다.** 메모리 승인 소비와 DB intent 저장을 연결하는 방식은 수락할 수 없습니다.

이번 작업은 공개 파일의 읽기 전용 자문입니다. 편집·시험·네트워크·private 접근·Docker·Git·subagent 실행은 하지 않았습니다.

1. **확인한 실제 사실**

| 근거 | 확인 결과와 Q27 영향 |
|---|---|
| [Q26 최종 수락](/Users/okestro/projects/QuantHarbor/docs/evidence/approval-validation-final-2026-10-25.json:269) | `root_acceptance.result=pass`, 범위는 `Q26_synthetic_local_only`. 기존 증거는 제품630·품질87·baseline7 불변을 기록한다. 이번 자문에서 재실행한 결과는 아니다. |
| [현재 상태](/Users/okestro/projects/QuantHarbor/docs/status.md:650), [EXECUTION-local](/Users/okestro/projects/QuantHarbor/docs/tasks/EXECUTION-local.md:1) | Q26 로컬 완료, Q27 설계 배정. 다만 `status.md:75`의 “Q26 재검토 중” 문장은 오래된 상태이므로 root가 정정해야 한다. |
| [ApprovalApplication](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/approval.py:132) | 생성자가 정확히 `SyntheticApprovalRepository`만 허용한다. 현재 Protocol 선언만으로 DB adapter를 주입할 수 없다. |
| [Q26 simulation](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_approval.py:582) | 승인 소비·claim·intent·예약·outbox를 공유 메모리에서 교체한다. `record_risk(...,'clear')`도 합성 사건 주입이다. 영속 원자성이나 실제 위험 계산의 증거가 아니다. |
| [Q24 원천 검사](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:90) | 실제 원장·평가·전체계좌 대사·성과·권리를 재검사하지만 활성 broker 주문/로컬 intent를 전부 거부한다. 현재 예약을 포함한 Q27 실행 계산으로 그대로 사용할 수 없다. |
| [Q21 broker 검사](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/valuation.py:213) | Q19 batch가 complete여도 금액 의미·결제/예약 포함 관계·전체계좌 범위 등을 미확인으로 유지한다. 이를 실행 가능한 계좌 사실로 승격하면 안 된다. |
| [Q20 PostgreSQL adapter](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_ledger.py:77) | Python `append/consume`는 각각 별도 transaction을 연다. 반면 [SQL `ledger_append`](/Users/okestro/projects/QuantHarbor/migrations/0002_synthetic_ledger.sql:485)는 호출한 transaction에 참여하므로 Q27 공통 transaction에서 재사용할 수 있다. |
| [Q14 경계](/Users/okestro/projects/QuantHarbor/src/quantharbor/runtime/boundary.py:27) | 고정 synthetic binding이며 broker·host·key는 disabled. controller identity/liveness는 합성 통제이고 실제 사용자 인증이나 OS 격리가 아니다. |

2. **먼저 고정할 `execution-local-v1`의 범위**

기존 baseline7과 `approval-fixture-v1.json`은 보존합니다. 새 계약은 `environment='synthetic'`, 현금계좌, 정규장, 현재 Q24가 발행한 정확한 지정가 후보만 지원합니다. `submit/cancel` 합성 경로만 추가하며 replace·환전·청산·실제 broker write adapter·credential loader는 제공하지 않습니다.

기존 `TargetRef`, `OrderTerms`, `ApprovalRecord`, `ActionChallenge`, `ActionReceipt`, `WithdrawalRequest`의 의미와 enum을 재해석하지 않습니다. 취소·실행·대사에는 별도의 닫힌 타입을 추가합니다.

공통 직렬화는 기존 `qh-canonical-json-v1`, UTC instant, 정확 decimal-string을 사용합니다. 다음 타입의 필드를 구현 전 명세와 fixture에 고정하는 것을 권고합니다.

| 추가 타입 | 필수 필드 |
|---|---|
| `ExecutionRef` | `kind`, `id`, `version`, `canonicalization_version`, `sha256`. kind는 `policy/source/risk/intent/reservation/attempt/event/query/cancel/reconciliation/runtime/receipt/fixture`의 닫힌 집합 |
| `ExecutionAccountState` | account/environment, state/version, authority generation, issuer instance, fence, executor/egress owner, lease deadline, policy refs, current source ref, ledger cursor, clock epoch, last control/reconciliation refs |
| `ExecutionSourceSet` | 원래 `ApprovalSource`의 request/plan/candidate/result refs, **현재** typed 입력 manifest, 전체계좌 scope, query/statement refs, ledger cursor, execution version, 예약/체결 cutoff, 가격·FX·분류·달력·권리·성과 refs |
| `ExecutionRiskDecision` | candidate/approval refs, exact `OrderTerms` hash, policy refs, source-set ref, 검사시각/종료시각, account version/cursor/generation/fence, 통화별 현금 계산, 종목별 sellable 계산, 노출·일간·회전율·손실 계산, `allow/deny/unknown`, 고정 reason codes |
| `OrderIntent` | candidate/consumed approval refs, immutable terms, request hash, idempotency key, admission risk ref, generation/fence, state/version/previous ref, reservation refs, attempt ref, 확정 체결량·관측 체결량, withdrawal refs |
| `ReservationSlice` | intent, 경제적 obligation ID·component, cash/quantity/risk 차원과 단위, 정책 집계창, held/used/released 금액·수량, ledger/event refs, B 반영 근거, source cutoff |
| `DispatchAttempt` | intent 또는 cancel ref, request hash, generation/fence, egress instance, 순번, 상태 `armed/handed_off/result_stored/unknown/proven_unsent`, 실제 issuer receipt ref |
| `SyntheticBrokerReceipt` | fixture/issuer instance, request/attempt hash, account, intent, broker order ID, 발급 sequence/time, 결과 종류, finality 종류, issuer journal ref |
| `SyntheticOrderEvent` | issuer/event ID/revision/predecessor, request/intent/broker ID, event 종류, 원천/수신시각, `delta/cumulative`, execution ID 또는 cumulative sequence, 수량·금액·비용·완전성, correction ref, 실제 receipt ref |
| `SyntheticExecutionQuery` | request scope와 실제 covered/missing scope, 계좌·시장·통화·기간·order 범위, snapshot/cutoff, pages/termination, success/partial/error/unknown, issued receipts/events, completeness 근거 |
| `CancelCommand` | 별도 command/nonce, actor/session/generation, 대상 intent·broker ID·잔량 상한, expected version, 상태, attempt/result refs |
| `ExecutionReconciliation` | 전체계좌 query/statement refs, 승인 소비·claim·intent·예약·broker 사건·원장 cursor를 비교한 manifest, 차이/미해결 refs, source cutoff, generation/fence, 결과 |
| `ExecutionCommandReceipt` | command/payload hash, actor/session, action/target/version, 결과 ref, 기록시각, account version |

`ExecutionSourceSet`은 임의 JSON 묶음이나 hash 목록만 받지 않습니다. 해소한 실제 객체의 정확 타입과 전체 입력 manifest를 요구합니다. `RiskDecision.allow`, `complete`, `unsent`라는 호출자 값은 권한이나 증거가 아닙니다.

3. **Q26–Q27 단일 권위와 UnitOfWork**

**권고안은 Q27 composition 시작부터 Q26 승인 상태를 DB adapter에 두는 것입니다.** 메모리에서 먼저 approve/consume한 결과를 DB 권위로 복사하는 정상 경로를 만들지 않습니다.

- Q26 `present/challenge/execute/withdraw/control/query` API는 유지합니다.
- root가 `application/approval.py`, `ports/approval.py`, 필요한 authority 결속 코드를 **명시적인 승인 통합 소유 파일**로 배정합니다.
- `ApprovalApplication`의 정확 타입 검사를 신뢰된 두 adapter의 닫힌 구성으로 확장합니다. 임의 duck-typed repository를 인증된 저장소로 받아들이지 않습니다.
- Q26 메모리 adapter는 기존 simulation으로 유지합니다. DB composition에서 해당 adapter의 `admit/dispatch/record_risk`를 호출하지 않습니다.
- issuer의 opaque handle identity는 살아 있는 registry에서 확인합니다. session·현재 permissions·nonce·approval head·control state는 동일 DB에서 읽습니다. 저장된 `PrincipalEvidence`는 불변 감사 증거이며 살아 있는 handle의 대체물이 아닙니다.
- 코드 hash는 입력 버전 식별용입니다. 현재 권한·현재 세대·실제 issuer identity를 증명하지 않습니다.

공통 `ExecutionUnitOfWork`는 **하나의 실제 PostgreSQL 연결·transaction**을 소유합니다. 잠금 순서는 Q20 `ledger_stream` → 실행 account row → 개별 head 순으로 고정합니다. 승인·철회·중단·권한/정책 변경·admission·dispatch·체결·대사는 같은 계좌 경계를 따릅니다.

admission 성공 commit에는 다음이 모두 있어야 합니다.

```text
현재 권한/세션/시각/정책/원천/위험 확인
+ approved → consumed
+ candidate submission claim
+ prepared intent
+ 현금·매도수량·위험 예약
+ execution outbox
+ nonce/command receipt
+ 불변 history
```

어느 단계에서든 DB 실패가 나면 **전체 rollback**입니다. 승인만 consumed, 예약만 생성, nonce만 사용된 상태를 남기지 않습니다. commit 응답 유실은 같은 command의 DB 결과를 조회하며 새 admission을 만들지 않습니다.

현재 무의존성 환경에는 기존 `psql` 방식의 제한된 연결 소유 adapter가 맞습니다. 고정 SQL만 사용하는 한 연결에서 `BEGIN → 잠금/조회 → Python typed 계산 → 버전·시각 재검사/쓰기 → COMMIT`을 수행하고, framing·시간·출력 상한을 둡니다. 연결을 유지할 수 없는 구현이라면 검증된 전체 read-set을 SQL transaction 안에서 다시 비교해야 하며, 바뀐 입력을 이전 `allow`로 통과시키면 안 됩니다.

`consume_approval()`의 독립 commit API와 `PostgresLedger.append()`를 나중에 호출하는 조합은 금지합니다.

기존 메모리 승인의 import는 최소 구현에서 비활성으로 두는 것이 안전합니다. 추후 필요하면 issuer가 원 저장소를 영구 동결하고 DB handoff receipt를 발급하는 단방향 절차가 필요합니다. 실패·응답 유실 중에는 양쪽 실행을 차단하며, rollback으로 메모리 소비 권한을 되살리지 않습니다. JSON snapshot import만으로는 이 조건을 만족하지 못합니다.

4. **현재 원천과 실제 계산의 연결**

원래 후보 검증과 현재 실행 위험 검증을 분리해야 합니다.

- **원래 후보:** Q26 `validate_source()`로 실제 Q24 request/inputs/artifacts/repository를 재현하고 승인 당시 `OrderTerms` 전체와 표시를 확인합니다.
- **현재 계좌:** DB의 모든 활성 intent·예약·미결제 의무·조회 이후 사건을 읽어 새 `ExecutionSourceSet`을 만듭니다. 원래 Q24 facts의 빈 `local_active_intents`를 재사용하지 않습니다.
- **현재 broker 사실:** 전용 합성 issuer가 독립적으로 발급한 statement/query를 사용합니다. 로컬 원장 결과를 그대로 복사하여 “broker matched”를 만드는 fixture는 제외합니다.
- **Q19:** 기존 `FixtureTransport/BrokerReadBatch`는 조회 계약의 부정·완전성 사례에 사용합니다. Q21이 미확인으로 남기는 포함 관계를 Q27이 임의로 보완하지 않습니다.
- **Q20/Q21/Q23:** 실제 `ledger_replay`, `value_projection`, `reconcile`, `build_bound_performance`, `validate_trade_costs`를 연결합니다. 정정·비용 미확정 등 현재 계산기가 지원하지 않는 의미는 신규 주문을 차단합니다.

Q24의 `available_cash`, `cost_bounds`, 정확 수치·노출 계산을 재사용합니다. 현재 private 함수에 활성 주문 검사를 끄는 옵션을 넣기보다, root가 공통 순수 계산 추출을 배정하고 Q24의 기존 동작을 보존해야 합니다. Q27은 활성 예약과 post-query 사건을 추가하는 명시적인 실행 계산을 맡습니다.

통화별로 다음을 그대로 적용합니다.

\[
A_c=\min(L_c-H_c-F_c,\;B_c-U_c-D_c)
\]

\[
R_{\text{buy}}=q\,p_{\max}+fee_{\max}+tax_{\max}
\]

`R ≤ A`를 검사하고 음수 A를 0으로 숨기지 않습니다. 매도는 미래 매도대금을 더하지 않고 비용 상한을 별도로 확보합니다.

\[
S=\min(Q_{\text{ledger sellable}}-Q_{\text{all sell holds}},
       Q_{\text{broker sellable}}-Q_{\text{unreflected holds}}-Q_{\text{post-query fills}})
\]

수량 단위·결제/매도가능 포함 관계가 확인되지 않으면 unknown입니다. 매수 체결량을 즉시 매도가능 수량으로 간주하지 않습니다.

H/U/D는 합계 입력을 신뢰하지 않고 obligation의 **원금·비용 component와 이행 부분**으로 계산합니다.

- 미체결 부분은 reservation, 체결 부분은 미결제채무 또는 확정 지출로 이동합니다.
- B에 미반영된 같은 부분은 U 또는 D 한 곳에만 속합니다.
- 체결 직후 원장 L이 아직 줄지 않았다면 체결 지급채무는 H에 남고 broker 측 차감은 D가 됩니다.
- 결제 후에는 L 감소와 H 해제가 함께 반영됩니다. D는 새 B가 해당 차감을 포함했다는 증거가 생길 때까지 유지합니다.
- 조회 갱신은 B·반영 obligation 집합·U/D·수량 대응값을 같은 버전으로 교체합니다.
- source cutoff 이후 입금·매도대금은 새 완전 조회/대사 전 broker 가용금에 더하지 않습니다.

위험은 현재 보유에 **활성 매수만 체결된 상한**과 **활성 매도만 체결된 하한**을 따로 적용합니다. 반대 주문으로 상계하지 않습니다. 종목·업종·시장·통화 한도, 통화별 funding, 주문량/금액, 거래량 참여, 일간 사용량에 모든 prepared/dispatching/unknown 예약을 포함합니다.

Q24 정책에는 회전율 한도 필드가 없으므로 additive `SyntheticExecutionPolicy`에 명시합니다. 합성 기본값은 `max_gross_turnover='1'`로 고정하고, 실제 Q23 시간가중 NAV를 분모로 사용합니다. 사용 거래대금과 활성·신규 최악 거래대금을 합산하며 분모 unknown이면 차단합니다.

손실·낙폭도 현재 관측값에 최악 비용/불리한 체결 영향을 반영합니다. 관측 손실만 한도 이내라는 이유로 잔여 위험을 허용하지 않습니다. 정책·권리·가격/FX·분류·정규장·계좌 cutoff·원 승인자의 현재 approve 권한·liveness·generation/fence를 admission과 dispatch에서 다시 확인합니다.

dispatch 시 이미 잡힌 **자기 예약을 다시 신규 부담으로 더하지 않습니다.** 자기 예약을 검증 대상으로 분리하고, 다른 예약과 함께 기존 예약 범위가 여전히 충분한지 계산합니다.

5. **계좌 경합과 DB 제약**

두 후보가 동시에 같은 현금을 보는 문제는 account 잠금 안에서 해결합니다. 첫 transaction의 예약을 두 번째가 읽고 다시 계산해야 합니다.

후보 고유키는 최소 다음으로 둡니다.

```text
UNIQUE(environment, account_ref, candidate_id, candidate_version)
```

해당 행에 canonical hash를 고정하고 동일 ID/version의 다른 hash를 충돌로 거부합니다. approval ID·generation·fence를 uniqueness 완화 요소로 넣지 않습니다. 같은 후보는 다른 승인으로도 최대 한 intent만 만들며, aborted_unsent 이후에도 claim을 보존합니다.

DB에는 다음을 강제합니다.

- synthetic-only CHECK, exact enum·숫자·UTC·nullable 검사.
- consumed approval↔intent와 candidate claim의 FK/고유성.
- 동일 계좌/환경 참조, history 연속 version·previous hash·허용 전이.
- 예약의 음수 금지와 held→used/released 보존식.
- intent 하나당 submit attempt 최대 하나.
- immutable terms/evidence/history의 UPDATE/DELETE 거부.
- 승인 소비·claim·예약·outbox·receipt의 commit-time 결속.
- broker event identity/revision 및 command/nonce 고유성.
- source cutoff와 ledger cursor가 뒤로 가지 않는 검사.

기존 Q20 migration은 수정하지 않고 `0003_synthetic_execution.sql`로 확장합니다.

6. **dispatch와 실제 합성 egress**

상태 전이는 다음으로 고정합니다.

| 상태/사건 | 결과 |
|---|---|
| prepared + 유효한 재검사 | dispatching |
| prepared + 승인된 철회 및 미전송 증거 | aborted_unsent |
| dispatching + issuer ACK | acknowledged |
| dispatching/acknowledged + 검증된 부분체결 | partially_filled |
| 검증된 전량체결 | filled |
| 외부 handoff 가능 이후 timeout/연결종료/결과 저장 실패 | unknown |
| 요청에 결속된 최종 미접수 거절 | rejected |
| 잔량의 확정 취소/만료 | cancelled_remaining/expired_remaining |

egress 입력은 `action + intent/cancel ID`뿐입니다. 계좌·수량·가격·host를 호출자가 덮어쓸 수 없습니다. egress가 DB에서 승인·불변 요청·세션·현재 권한·정책·예약·generation/fence를 다시 해소합니다.

외부 handoff를 DB transaction 안에 넣지 않습니다. 최종 검사 commit 이후 handoff까지의 경합은 **하나의 합성 egress gate**로 직렬화합니다. stop/withdraw/generation 변경도 같은 gate에 참여하여, 최종 검사 뒤 이미 확정된 중단을 건너뛰지 않게 합니다. 이 gate는 합성 프로그램의 경계이며 실제 OS/network 격리 증명이 아닙니다.

실제 handoff 전 `DispatchAttempt`를 영속합니다. handoff 후 결과 저장이 실패하면 DB에는 dispatching/armed가 남을 수 있으므로 재시작 시 unknown으로 취급합니다. broker가 접수하지 않았다고 추정하지 않습니다.

execution outbox는 상태 확인을 깨우는 전달 수단입니다. 재전달은 기존 상태를 조회할 뿐, 주문을 자동 재생하지 않습니다. 새 lease나 새 worker도 기존 attempt를 다시 보내지 못합니다.

7. **broker fixture·이벤트·Q20 연결**

별도 `SyntheticExecutionBroker`는 고정 manifest의 명령과 사건만 발급합니다. 임의 callback·URL·HTTP client·credential 입력을 받지 않습니다.

issuer는 실제로 받은 request hash와 발급 receipt/event/query를 자신의 journal에 기록합니다. 소비자는 정확 타입 검사에 더해 **그 issuer가 실제 발급한 항목인지** 해소합니다. `provenance='synthetic'`, hash 일치, 호출자의 `final=True`만으로 통과시키지 않습니다.

fixture의 최종 거절은 해당 request에 대해 이후 접수가 불가능하다는 규칙을 명시합니다. 미전송 증거는 egress가 해당 attempt의 handoff 권한을 폐기하고 아직 전달하지 않았음을 확인한 경우에만 발급합니다. issuer journal을 잃었으면 미전송을 증명할 수 없습니다.

이벤트 처리는 다음처럼 제한합니다.

- ACK 전 체결은 유효한 request/receipt 결속으로 연결합니다. 나중 ACK가 partially_filled/filled를 acknowledged로 되돌리지 않습니다.
- delta는 execution ID별 독립 체결입니다. cumulative는 동일 stream의 명시된 누계입니다. 두 표현을 같은 체결로 중복 계상하지 않습니다.
- cumulative의 연속성이 확인된 경우만 차이를 계산합니다. 누락 predecessor·감소 누계·의미 혼합은 보류합니다.
- 동일 identity/revision/hash는 duplicate입니다. 동일 identity/revision의 다른 payload는 conflict입니다.
- revision은 원본의 개정입니다. Q20의 predecessor/correction 연결과 역분개·대체를 사용하며 별도 체결로 더하지 않습니다.
- 상위 revision 선도착은 격리하고 명시적 재처리로 연결합니다. 과거 revision은 유효 누계를 되돌리지 않습니다.
- overfill·broker ID 충돌·최종 종료 뒤 늦은 체결은 증거를 보존하고 계좌 신규 주문을 중단합니다. 수량을 clamp하거나 이벤트를 버리지 않습니다.

검증된 체결 반영 transaction은 다음을 함께 저장합니다.

```text
broker inbox/event
+ intent 체결 상태
+ reservation → used/D/잔여예약 전환
+ qh.ledger_append(...)의 원장·projection·ledger outbox
+ execution↔ledger mapping
+ history
```

Q20 Python `append()`의 별도 commit을 호출하지 않습니다. 같은 SQL transaction에서 기존 함수를 호출합니다.

Q20 `ledger_inbox`는 **ledger outbox projection 메시지**를 참조합니다. broker event ID를 여기에 넣지 않습니다. broker inbox는 별도로 두고, ledger outbox 소비 시 `ledger_consume`와 실행 측 cursor 갱신을 같은 transaction에 묶습니다. 이미 반영한 체결을 outbox 소비에서 다시 원장에 쓰지 않습니다.

매수 principal은 Q20의 unsettled payable/trade clearing, 매도는 unsettled receivable/trade clearing을 사용합니다. settlement는 기존 trade dependency의 이동이며 수량을 다시 계상하지 않습니다. fee/tax도 명시적 별도 사건으로 연결합니다.

비용이 미확정이면 잔여 비용 상한을 유지합니다. Q20의 `costs_known`을 거짓으로 true로 만들지 않습니다. Q20이 수락하지 못하는 불완전 체결은 관측·보수적 D/수량/위험 사용분을 같은 DB transaction에 보존하고, 원장/대사는 incomplete·신규 주문 차단으로 남깁니다. 완전한 비용 근거가 도착한 뒤 기존 멱등키로 확정합니다.

8. **철회·취소·unknown·재개**

Q26 보호 `withdraw()`는 DB에서도 내부 발급·nonce·결정·history를 한 transaction으로 처리합니다.

- approved 철회가 먼저 commit되면 revoked, admission은 실패합니다.
- admission이 먼저면 approval은 consumed를 유지하고 별도 WithdrawalRequest를 받습니다.
- prepared 철회가 dispatch보다 먼저면 stored attempt 상태와 실제 미전송 증거에 따라 aborted_unsent·예약 해제를 함께 확정합니다.
- dispatch가 먼저면 withdrawal requested를 기록합니다. egress가 아직 보내지 않았음을 실제로 증명할 수 있는 경우에만 후속 종료합니다.
- 전송중/unknown이면 예약을 유지합니다. caller가 `prepared/unsent`를 넘기는 API는 없습니다.

취소는 원 주문 승인과 별도의 인증된 command입니다. Q26 기존 action enum에 몰래 추가하지 않고, 동일 issuer/session 기반의 실행 제어 권한으로 결속합니다. 취소 접수는 주문 종료가 아니며 취소 unknown 중에도 fill을 계속 받습니다. 확정된 cancelled remaining만 해제합니다.

unknown 주문이 완전 조회에 없더라도 예약을 해제하지 않습니다. 시간 경과·사용자 retry·complete query만으로 rejected로 바꿀 수 없습니다. 요청에 결속된 최종 거절 또는 실제 issuer의 미전송 증거만 미접수 종료 근거가 됩니다.

`stop_new_orders`는 신규 admission/dispatch/egress를 막습니다. cancel/liquidate를 만들지 않습니다. 체결 수신·조회·대사·별도 승인 취소는 가능한 범위에서 계속합니다.

수동 resume는 별도 인증 command이며, 현재 DB에 저장된 완전한 합성 대사 결과를 참조해야 합니다. caller의 `reconciled=True`나 DB running 문자열만으로 열리지 않습니다. 승인 소비·claim·intent·예약·broker 사건·원장·현금/보유·미체결 범위와 현재 source cutoff가 모두 맞아야 합니다.

재시작/복원은 stopped/reconciling입니다. snapshot 밖 authority가 새 generation을 발급하고 이전 egress를 폐기합니다. 옛 handle/session/nonce/pending/approved는 실행 불가이며 consumed·claim·unknown·예약·체결은 보존합니다. 새 fence/lease만으로 failover하지 않습니다.

오래된 백업에서 빠진 사건은 issuer journal과 대사해 복구해야 합니다. 복구할 근거가 없으면 차단을 유지합니다. 거래일 rollover도 unknown이나 활성 예약을 삭제하지 않습니다.

9. **구현 전 고정할 독립 golden**

기대값은 production 계산기를 호출해 생성하지 않고 root가 JSON 상수와 수기로 확인한 식으로 고정해야 합니다. 원천 구성은 실제 Q20/Q21/Q24/Q26 경로를 사용합니다.

| 사례 | 고정 기대값 |
|---|---|
| 기존 Q24 기본값 | `L=1000,H=100,F=100,B=950,U=50,D=0 → A=800`. 후보302+402 후 잔여96 |
| 두 후보 경쟁 | 서로 다른 승인된 후보 R302/R402, 현재 A600. 두 연결 중 한 개만 성공. 승자에 따라 잔여298 또는198 |
| 같은 후보·다른 승인 | intent/claim/outbox 각1개. 다른 승인은 소비되지 않음 |
| admission 단계별 fault | 소비·claim·intent·cash/quantity/risk 예약·outbox·receipt 각 단계에서 전체 financial fingerprint 불변 |
| 부분체결 전환 | 별도 fixture: L=B1000, F100, q3×100+비용상한2. 예약302. 1주100 체결 후 미체결원금200+비용hold2, 지급채무100, `H=302,U=202,D=100,A=598` |
| 위 체결의 결제 | `L=900,H=202,U=202,D=100,A=598`. 원금 이중 차감 없음 |
| 새 완전 B 조회 | B900이 해당 체결을 포함, 로컬 잔량예약 미반영이면 `U=202,D=0,A=598` |
| sellable | ledger12−예약4=8, broker10−미반영예약2−post-query fill1=7 → 상한7. 신규8 거부 |
| 미래 매도대금 | 미결제 매도채권500 발생만으로 A 증가 없음 |
| 한쪽 체결 노출 | 현재400+활성매수100+신규매수50=550, 한도500 → 거부. 반대 매도로 상계 금지 |
| 일간 한도 | 사용400+활성350+신규300=1050, 한도1000 → 거부 |
| 회전율·손실 | 시간가중NAV1000, 거래대금400+350+300 →1.05>1 거부. 관측손실40+최악추가15>한도50도 거부 |
| ACK/중복/역순 | fill1→ACK→같은 fill1 duplicate: 수량1. 누계1→3은 총3, 총4가 아님 |
| 정정·overfill | 같은 체결 1→2 정정의 유효량2, 합계3 아님. 주문3에 누계4는 conflict/halt |
| handoff 후 crash | broker 수신1회, DB 결과 저장 실패 → unknown·예약 유지·재전송0 |
| complete-empty query | unknown·예약 그대로. 최종 request-bound 거절/미전송 증거 사례에서만 해제 |
| 철회 양방향 경합 | 철회 우선이면 외부 handoff0. handoff 우선이면 withdrawal requested와 예약 유지 |
| cancel/fill 경쟁 | cancel ACK만으로 해제0. 이후 fill 반영 후 확정 잔량만 해제 |
| restore/rollover | 기존 claim·unknown·예약 유지, old authority 거부, 자동 dispatch0 |
| forged evidence | bool/hash/다른 issuer receipt/축소 scope/미래 cutoff/철회된 권리 모두 신규 주문 거부 |

현재 Q26의 20/10/120/30초 TTL과 표시 만료 상한은 그대로 사용합니다. 합성 시험용 추가 한도·사례값은 root가 고정하면 되며 새 사용자 운용정책 선택을 요청할 필요가 없습니다.

10. **상한·권한·소유권과 남은 게이트**

공개 경계는 canonical64KiB, 해소 원천8MiB/128refs, 문자열2KiB, 조회1~20개를 유지합니다. Q27은 별도 execution 저장 상한256 logical records/16MiB, 활성 intent 최대2개, intent당 합성 broker 사건 최대8개로 작게 시작할 것을 권고합니다. Q26의128records/8MiB와 보호 hold 규칙은 줄이지 않습니다.

root는 위 상한 안에서 admission 전에 **종료·늦은 체결·취소·철회·history·inbox·원장 정정까지 필요한 최대 저장량**을 계산한 예산표를 고정해야 합니다. 자동 eviction이나 예약 삭제로 공간을 확보하지 않습니다. 과부하에서도 stop/withdraw와 이미 발급된 broker 증거 보존을 위한 보호 몫을 남깁니다.

보고 역할은 현재 권리를 확인한 읽기 view만, 연구 역할은 금융 상세 없는 summary만 받습니다. handle·nonce·원시 SQL/예외·DSN을 반환하지 않습니다. 오류는 `authority_denied`, `source_unresolved`, `risk_unknown`, `version_conflict`, `capacity_exceeded`, `storage_failed`, `reconciliation_required` 같은 고정 code로 제한합니다. SQL 역할은 직접 table mutation을 허용하지 않는 고정 함수·view 권한으로 구성하고, 관리자 runner 권한과 제품 역할을 구분합니다.

소유권은 다음처럼 고정하는 편이 작고 검토 가능합니다.

| 담당 | 파일 범위 |
|---|---|
| root | `execution-local-v1`, fixture/goldens, 결정·task/status/evidence, migration 승인, 정확한 소유목록 |
| 단독 구현자 | 새 domain/application/ports execution, PostgreSQL UoW·execution adapter, synthetic execution broker, execution 시험·개발 안내 |
| 명시 배정한 통합 seam | Q26 application/ports/authority 결속, additive serialization 등록, Q24 순수 계산 추출, Q20 동일 transaction 호출 지원 |
| 보존 | baseline7, 기존 migration0001/0002, 기존 금융 의미, 실제 연결 설정·credential 경로 |

새 framework나 외부 의존성은 필요하지 않습니다. DB runner는 [check_ledger.py](/Users/okestro/projects/QuantHarbor/scripts/check_ledger.py:37)의 fingerprint·경쟁 연결·backend 종료·dump/restore 패턴을 따릅니다. UUID의 자기 소유 임시 Docker project, 고정 기존 PostgreSQL 이미지, `network_mode:none`, host mount/port 없음, pull/install 없음, 자기 project만 정리하는 구조로 root가 실행하도록 준비합니다. 사용자 비밀번호 입력이나 실제 credential은 필요하지 않습니다.

**Q27 완료에 필요한 미실행 게이트**는 실제 PostgreSQL에서의 전 단계 rollback, 두 연결 경쟁, handoff 전후 crash, Q20 inbox/outbox 원자성, restore·stale executor 차단, 보호 공간 고갈, 원천 결속 양성 경로, 독립 보안/일반 검토입니다. 메모리 시험이나 정적 자문으로 대체할 수 없습니다.

AP-05는 실제 조회에 아직 사용되지 않은 조건부 승인입니다. 실제 주문·취소에는 별도 승인이 필요하며 지금 요청하지 않습니다. PG-01·PG-03과 실제 인증·지원/권리·저장/주입·egress 격리 관문은 계속 차단 상태로 남습니다.