# AI·목표·승인·주문 계약 v1 — Q10

상태: Q10 명시 범위 독립 검토 통과. [data-v1](data-v1.md), 요구 v1·A-DEC-001~003·PG/SG를 입력으로 한다. 아래는 구현할 계약이며 실행 서비스·운용정책값·주문 권한을 제공하지 않는다.

## 운영 AI 경계

`ResearchRequest`는 request/run ID, environment, 목적, 읽을 snapshot/data/strategy/policy 버전, as_of/knowledge_cutoff, 허용 도구/출처, 권리 판정, 기한·토큰/호출/비용 상한을 갖는다. 자격증명·직접 계좌번호·원시 개인 로그는 입력하지 않는다. 권리·예산·필수 한도가 없는 실제 외부 호출은 비활성이다(SG-02·04).

`ResearchResult`는 request ID·입력 hash, 모델/지침/도구 스키마 버전, 출처별 주장·관측시각·가정·반대 근거·미확인, 가설/실험 제안, 비용/사용량, `complete|partial|invalid|blocked|failed`와 사유를 갖는다. timeout·잘린 출력·스키마 오류·인용 불일치를 complete로 올리지 않는다. 별도 검토는 동일 버전 결과에 연결한다. 모델 합의나 자신감으로 출처/계산 검사를 대체하지 않는다.

- 수집/학습/전략 제안/위험 반례/보고 역할은 조회용 산출물과 정해진 도구만 사용한다. 주문·정책·승인·원장 쓰기 도구 및 실행 키는 없다. 실제 권한 구현·거부 검증은 Q14/Q25다.
- 외부 문서·도구 출력·이전 모델 기억은 비신뢰 자료다. 그 안의 지시로 도구·사용자 권한·정책을 추가하지 않는다. 도구 인자는 구조화 검증하며 임의 URL·명령·파일 경로 실행을 금지한다.
- `Hypothesis`는 ID·출처·입력 버전·생성/만료·검증 상태·대체 관계를 가진다. TTL/사용 가능 기간이 미설정이면 실행 후보 생성 입력으로 재사용하지 않는다. 최신 데이터/정책/전략 변경 시 의존 가설을 재검증한다. 원천 정정·권리 철회도 무효화 조건이며 기억 속 사용자 정책을 별도 정책 정본보다 우선하지 않는다. 기억 삭제·보존과 가설의 유효성은 별도다(Q11).
- 결정론적 코드가 수량·비용·현금·제약을 계산한다. AI는 설명과 검토를 제공하며 숫자 출력은 계산 입력 스키마/제약을 통과해야 한다. AI 미완료 시 자동으로 다른 전략/모델을 채택하지 않는다.
- 초기 제품 API 비용 상한은 신규0이며 disabled 경로가 기본이다. 합성 응답의 성공을 실제 모델 평가로 표시하지 않는다. 활성화 이후에도 호출 전 상한 예약·사용량 확정·미확인 청구 예약 유지, 한도 초과 중단을 구현한다. 재시도/모델 상향 횟수·비용의 명시 정책 없이는 자동 재시도하지 않는다.

## TargetPlan와 OrderCandidate

`TargetPlan` 필수: plan ID/version/hash, environment/account_ref, strategy/policy/data/snapshot refs, 생성/만료, `mode=full|partial`, scope(종목·현금·시장), 기준통화·가격/FX·평가 기준, `target_basis=quantity|weight` 중 하나·목표값과 단위, 근거/위험/검토 결과, 기존 계획 관계, 상태.

- full은 명시 scope 전체의 목표다. 생략 종목을0으로 취급하려면 포함 범위와 `omitted=zero`가 명시되어야 하고 청산 후보도 별도 생성·승인이 필요하다. 모호한 생략은 거부한다. partial은 명시 항목만 바꾸며 생략은 유지한다. 계좌 전체 현금·노출 검사는 둘 다 수행한다.
- 목표 비중은 가용금과 같지 않다. 전체 NAV가 불완전하면 비중 계산·정상 목표 발행을 보류한다. 금액·수량 목표도 필요한 입력·제약이 불완전하면 실행 후보로 승격하지 않는다.
- 새 목표는 기존 승인·주문을 자동 취소/대체하지 않는다. 동일 종목·계좌의 활성 의도/미체결/상태불명과 충돌하면 보류하고 조회·대사 후 새 후보를 계산한다. 반대 방향 주문으로 조용히 상쇄하지 않는다.
- 계획 상태는 draft→reviewed→eligible 또는 blocked/expired/superseded다. eligible은 후보 생성 가능 상태이며 제출 권한이 아니다. superseded에서도 기존 주문·원장 사실은 유지한다.

`OrderCandidate`는 불변 ID/version/hash, plan ref, authority_generation, environment/account_ref, instrument/venue/capability/calendar refs, side, 정확한 수량·주문유형·유효조건·가격 한계, 통화별 최대 자금 부담/비용 상한, 제출 가능 기간, 정책/입력 refs, 정규장 조건을 갖는다. 거래 단위/비용/최악 부담을 확정할 수 없으면 제출 후보가 아니다. 초기 실행은 확정 상한을 갖는 주문만 설계 대상으로 하며 실제 주문유형 지원은 SG-01에서 확인한다. 분할·가격 변경·잔량 대체는 새 후보이며 기존 승인을 복사하지 않는다. 계획 전체 승인으로 여러 후보 실행 권한을 만들지 않으며 여러 주문의 원자적 체결을 보장하지 않는다.

## Approval와 경합 기준

`Approval` 필수: approval ID, 인증된 user/권한 참조·authority_generation, candidate ID/version/hash, environment/account_ref, 허용 action·수량/금액/가격 경계, 정책 버전, issued_at/expires_at, 인증/결정 증거 참조, state/version, 소비 intent ID. 사용자 대상 화면은 이 정확한 내용과 위험·추정비용·실행 만료를 보여준다. 승인 메시지 텍스트나 AI 출력은 인증 근거가 아니다.

- 상태: pending→approved 또는 denied; approved→revoked/expired/invalidated/consumed. 최종 상태를 approved로 되돌리지 않는다. 단일 후보·단일 제출 의도에만 소비하며 같은 후보에 병렬 승인 생성이 있어도 제출 고유키는 하나다.
- 정책/후보/계좌/환경 변경 또는 필수 입력 재검사 실패는 기존 승인을 재해석하지 않는다. 새 후보 승인이나 사용자 확인이 필요하다. 가격의 허용 변화·만료 기간은 PG-01/05 값이며15분을 기본값으로 대입하지 않는다.
- 후보 변경 없이 입력을 새로 조회할 때도 현재 입력 refs와 RiskDecision을 남기고 승인된 한계 안인지 확인한다. 조건을 완화하거나 비용 상한을 늘리지 않는다.
- 실행 admission transaction이 승인 유효성·현재 시각·계좌 실행 세대·정책 버전·예약·정규장·RiskDecision을 확인하고 approval 소비, intent prepared 상태 생성, 예약, outbox를 원자적으로 기록한다. 승인·중단·철회·정책 변경도 같은 계좌의 직렬화 경계를 사용한다.
- prepared 이후 실제 dispatch 직전에는 별도 transaction에서 철회·기한·현재 정책·위험·예약·세대를 재확인하고 dispatching을 확정한다. 철회와 dispatching 전이는 같은 잠금/버전 경계를 사용한다. 철회가 dispatching보다 먼저 확정되면 제출 불가다. dispatching 이후 철회는 `withdrawal_requested`로 별도 기록하며 이미 시작된 외부 호출 중단을 보장하지 않는다. egress가 아직 보내지 않았다면 최종 검사로 차단하고, 전송 중/후면 조회·대사한다. 취소는 별도 명령·권한이다. UI는 ‘철회 요청’과 ‘외부 제출 방지 확인’을 구분한다.
- consumed 승인도 prepared 시점부터 `WithdrawalRequest`(request ID·user·approval/intent ID·시각·상태)를 받는다. consumed를 되돌리지 않고 같은 계좌/intent 잠금에서 철회를 영속하며, dispatching 이전이고 미전송이 확정되면 intent를 aborted_unsent로 끝내고 egress를 차단한다. dispatching과 경합한 경우 먼저 확정된 상태를 반환하며 dispatching 이후는 withdrawal_requested·결과 조회/별도 취소 경로로 남긴다. 소비됐다는 이유로 prepared 철회 요청을 거절하지 않는다.
- 호출 직전 기한/세션/중단/세대/정책을 다시 검사한다. 세션 검사는 operations-v1의 인증된 principal/session liveness·authority_generation 유효성을 포함하고 연결상실/기한만료는 신규 admission/dispatch/egress 차단이다. admission 후 기한 경과·프로세스 재시작·전송 여부 불명은 자동 제출하지 않는다. 아직 전송하지 않았음을 확정한 폐기 의도라도 소비 승인을 재사용하지 않는다.

## BrokerPort·OrderIntent·OrderEvent

조회 port는 capability, holdings/cash/open-orders/order-detail/fills의 범위 있는 BrokerQueryResult를 반환한다. write port는 submit/cancel만 갖고 환전·출금·자동 청산은 제공하지 않는다. native replace는 초기 비활성이며 취소 완료·대사 후 새 후보/승인으로 대체한다. 모의/실전 endpoint·계좌·TR·키 참조가 바인딩과 다르면 기동/호출 거부다.

`OrderIntent`는 ID·candidate/approval refs·환경/계좌·idempotency key·불변 요청 hash·정확한 주문 내용·상한·예약refs·policy/risk refs·권한 복원 세대(authority_generation)·세대번호(fence)·현재 상태/version을 가진다. 같은 key 동일내용은 기존 의도 반환, 다른 내용은 충돌 차단. 공급자가 client key를 지원하지 않아도 내부 동일 의도를 새 주문으로 재전송하지 않는다.

| 상태/사건 | 전이·허용 행동 |
|---|---|
| prepared | 승인 소비·예약 저장됨. 아직 호출 안 함. 재검사 후 dispatching 또는 aborted_unsent |
| dispatching | 외부 요청이 가능해진 경계. 접수 증거→acknowledged, 확정 미접수 거절→rejected, timeout/연결종료/기록 실패→unknown |
| acknowledged | broker ID 연결. 체결→partially_filled/filled, 명시 취소 요청은 별도 cancel command |
| partially_filled | 확정 체결 누계와 미확정 잔량을 분리. 추가체결→filled, 취소 완료 시 cancelled_remaining |
| unknown | 같은 의도 자동 재전송 금지. 조회 목록에 없다는 사실만으로 미접수를 확정하지 않음. 요청 내용·식별자·시간 범위의 완전 조회/대사로 접수/체결 확인. 미접수 확정은 아래 최종성 근거에 한정하며 부재만으로 해소하지 않음 |
| rejected / aborted_unsent | 외부 미접수 또는 미전송 근거가 확정된 경우만 예약 해제. 자동 재승인/재제출 없음 |
| filled / cancelled_remaining / expired_remaining | 미체결 잔량 종료 상태. 기체결 유지. 늦은 체결/정정은 증거로 반영·대사하며 신규 제출 보류 가능 |

unknown의 미접수 확정과 예약 해제는 해당 요청에 결속된 공급자의 최종 거절처럼 계약상 이후 접수 불가능한 결과, 또는 egress가 확정한 미전송 증거를 요구한다. 공급자의 응답 최종성·지연접수 한계·조회 보존 범위가 미확인인 경우, 완전 조회나 대사를 반복해도 부재만으로 미접수로 전환하지 않는다. unknown·예약·신규 제출 차단을 유지하고 늦은 접수를 추적한다. 시간 경과나 사용자 재시도 요청으로 이 불확실성을 삭제하지 않는다.

`OrderEvent`는 event/source identity·revision·환경/계좌/intent/broker ID·유형·원천/수신시각·누적/증분 수량의 의미·가격/비용·증빙·순서 근거를 포함한다. 같은 체결은 data-v1 멱등/정정 규칙으로 한 번만 계상한다. cumulative와 delta를 섞지 않으며 의미 불명 이벤트는 보류한다. 유효 누계는 정정 경로 외 감소하지 않고 주문 총량 초과·상충 ID는 충돌 대사한다. ACK보다 체결이 먼저 올 수 있으며 미확인 연결은 조사하고 새 주문을 만들지 않는다.

취소는 `CancelCommand(requested|dispatching|acknowledged|unknown|rejected|completed)`와 대상 broker ID·잔량 상한·권한/요청자를 별도로 기록한다. 취소 접수는 주문 종료가 아니다. 취소 요청/응답 유실 후에도 체결을 계속 수용한다. confirmed cancelled remaining만 예약 해제하며 취소 실패가 기존 주문 실패를 뜻하지 않는다. 주문/취소 timeout은 HTTP 클라이언트의 자동 write 재시도 대상에서 제외한다.

## 위험 검사·현금·수량 예약

`RiskDecision`은 검사 ID/version·시각·후보hash·입력 snapshot/query/price/FX/분류/calendar refs·policy/capability 버전·계산내역·판정 `allow|deny|unknown`과 사유를 갖는다. unknown은 제출 불가다. 정책·대사·권리·freshness·세션·상품·최대부담·현금·보유·미체결 포함 노출·일간 한도·손실/낙폭을 각각 검사한다. 누락 한도를 무제한으로 해석하지 않는다.

현금은 동일 통화·동일 평가 컷오프로 정렬해 다음처럼 계산한다. L/H는 현재 원장/예약 컷오프이며 B는 마지막 완전 broker 조회 기준값이다. 그 이후 확인된 변동은 D/U로 정렬한다. 단위·포함 관계·관측 이후 변동이 검증되지 않으면 산식 적용 불가다.

- `L`: 원장상 결제 완료 현금. 미결제 매도대금은 L에 추가하지 않는다.
- `H`: 현재 원장 컷오프의 아직 이행되지 않은 모든 현금 의무/비용 상한/주문 예약. 이미 L에 반영된 지출을 재차 포함하지 않도록 원천 의무 ID로 결속한다.
- `F`: 사용자 통화별 현금 하한. `B`: 신용/자동환전 제외가 검증된 broker 매수가능 현금.
- `U`: B에 아직 반영되지 않은 미체결 의무/로컬예약. `D`: B의 기준시각 이후 확인됐지만 B에는 반영되지 않은 체결/비용 등의 현금 차감이며 U와 중복 분류하지 않는다. 같은 의무를 H와 U에 두는 것은 각각의 독립 상한 비교이며 두 결과를 다시 더해서 차감하지 않는다. 공급자 반영관계 불명 시 U를 추측하지 않는다.
- 가용금 `A = min(L - H - F, B - U - D)`. 음수는 자금 부족/대사 이상으로 노출하고 신규 제출을 막으며0으로 숨기지 않는다. 이 값은 신규 후보 예약 전 값이며 신규 최대부담 `R = 수량 × 승인된 최악 단가 + 검증된 수수료/세금 상한`이 A 이하여야 한다. 각 통화 별도로 검사하고 다른 통화 잔액으로 메우지 않는다.
- B가 주문유형·종목·가격별 조회값이면 해당 후보 조건에만 적용한다. 시장가의 추정 가격은 보장된 자금 상한이 아니다. 기준 조회 이후 미반영 증액은 새 완전 조회/대사 전 가용금에 더하지 않는다.
- 원천 조회 중/후 발생한 체결·입출금·수동 주문과 내부 예약을 컷오프에 맞춰 대사하지 못하면 A는 unknown이다. 미체결·비용·취소불명 예약을 성공 응답 추정으로 빼지 않는다.
- 매도는 `min(원장 결제/매도가능 수량 - 전체 미체결 매도예약, broker 매도가능수량 - 미반영 로컬매도예약 - 조회 이후 미반영 매도체결수량)` 상한을 적용한다. 단위/포함관계가 확인돼야 하며 short 금지, 매수 체결을 확인하지 않은 예상 수량은 사용할 수 없다.
- 체결의 예약 감소와 미반영 차감 D/수량 차감 전환은 같은 transaction·사실에 결속한다. 새 조회와 대사 시 B/U/D 및 수량 대응값을 같은 버전으로 갱신한다. 비용 미확정분은 남겨 두며, 부분체결 뒤 잔량 예약을 새 승인으로 복제하지 않는다. 매도 체결·결제 가용 확인 전 미래 매도대금으로 매수하지 않는다.

현금 외 위험 한도도 예약한다. 사용자 정책이 정한 거래일/집계창·통화/수량/금액 단위별로 이미 사용한 양 + 모든 활성/dispatching/unknown 의도의 최악 추가 사용량 + 새 의도 부담을 한도와 비교하고 같은 admission transaction에서 한도 사용 예약을 저장한다. 일간 체결금액만 보고 미체결 의도를 빼지 않는다. 체결 시 위험 예약→사용분을 한 번만 전환하고 확정 종료의 잔량만 해제한다. unknown은 예약을 유지하며 거래일 경계에서 자동 삭제하지 않고 적용 집계창·활성 위험을 재검사한다. 종목/업종/시장/통화 집중도와 거래량 참여도 역시 정책의 집계 의미와 활성 주문 최악 영향을 결합한다. 필요한 노출/거래량이 불명확하면 허용하지 않는다.

계좌별 동시 admission은 DB 잠금/기대 버전으로 직렬화한다. 두 후보가 같은 가용금을 각각 소비하지 않도록 검사와 예약 저장을 한 transaction에서 수행한다. ‘위험 감소’라는 AI 판단으로 미확인/중단을 우회하지 않으며 초기 장애 시 모든 신규 제출을 멈춘다. 미체결 매수·매도가 모두 체결된다고 단순 상계하지 않고 한쪽만 체결될 때의 최악 노출도 검사한다. 승인된 별도 취소와 조회/대사는 가능한 범위에서 계속한다.

## 단일 실행자·중단·복구

백업 복원 시 이전 승인·세션의 실행 권한은 operations-v1의 새 authority_generation으로 일괄 무효화한다. 기존 주문/예약/unknown/소비 증거는 보존하되 복원된 approved를 다시 admission에 사용하지 않는다. 새 세대의 재인증·새 후보 승인이 필요하다.

계좌별 lease/단조 증가 fence는 내부 stale writer를 거부한다. DB lease만으로 broker가 과거 요청을 거부한다고 주장하지 않는다. 실제 write 키와 broker egress는 환경별 단일 실행 경로만 가진다. 외부 호출을 시작할 권한은 현재 fence·세션·정책·중단 상태를 검사한 egress가 갖는다. 프로세스/키/네트워크 통제는 Q11/Q14에서 강제한다.

초기 자동 failover는 없다. 이전 실행자의 종료·egress 차단 및 진행 중 요청의 결과 확인이 불가능하면 새 실행자 제출을 열지 않는다. lease 만료만으로 재제출/인수하지 않는다. 네트워크에 이미 전달된 요청은 차단 후에도 접수될 수 있어 대사한다.

`stop_new_orders`, `cancel_order`, `liquidate`, `resume`는 별도 명령이다. 초기 stop은 새 admission/egress를 막지만 이미 접수된 주문을 취소하거나 보유를 청산하지 않는다. liquidate는 초기 자동 경로 없음. 재기동은 stopped/reconciling으로 시작해 의도·소비 승인·예약·체결·미체결·원장·broker 완전 대사를 복원하고 수동 resume 승인을 받아야 한다. 미전송/전송불명 의도를 자동 큐 재생하지 않는다.

## 검증 연결·변경 영향

검증할 사례는 Q24~29에 연결한다: full/partial 생략, 기존 미체결 충돌, 승인 재사용/만료/철회 경합, 가격/정책 변경, 가용금 동시 소비, 취소 중 체결, ACK 전 체결, 누적/증분 혼동, DB 저장 후 호출 전 중단, 접수 후 DB 실패, stale egress, 조회 B 갱신 중 예약→미반영 차감 전환·음수 가용금·외부 수동 주문, 재시작·대사 실패, AI 출처/스키마/예산/기억 만료. 지금은 문서 수준 검토이며 실행하지 않았다.

공통 v1 신규 계약으로 배포 이행은 없다. 의미/enum/필수값/위험 산식 변경은 producer(연구·목표·승인·실행)와 consumer(원장·보고·복구) 함께 version을 올리고 기존 승인 무효화·활성 주문 보존·재생 계획을 검토한다. Q11은 인증·egress·보존·세션/보고를, Q12는 canonical hash·구체 구현 순서를 통합한다. 실제 정책값은 PG, broker/data/model 권리·기능은 SG에 남는다.
