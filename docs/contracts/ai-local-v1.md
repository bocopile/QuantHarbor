# 합성 AI 소비·검토·예산 계약 v1 — Q25

상태: root 구현 기준. EXEC-DEC-001 H01~08/J03 합성 범위, Q24 로컬 완료 후 적용. frozen execution/data/operations/serialization-v1 보존. [설계 자문](../research/ai-design-input-2026-10-24.md) 2~8번의 필수 필드·역할표·원천/예산·가설·보고·한도를 아래 보완과 함께 채택한다. 실제 모델·도구 활성화/정책 채택/비용 승인은 아니다.

## 평가 고정과 실행 경계

ai-evaluation-spec-v1.json의24개 시나리오·예상상태/수치/효과0·상한을 평가 전 고정한다. raw SHA는 AI-DEC-001에 기록한다. 고정 사례의 fixture를 실제 구현한 뒤 첫 평가 전 해당 fixture/source/lock 해시와 실제 입력 refs를 산출물 manifest에 남긴다. fixture 구성이나 기대값을 결과에 맞춰 조용히 바꾸지 않는다. 초기 fixture 오류·제품 red·수정/최종 실행을 구분해 보존한다. 추가 회귀는 기존 spec을 수정하지 않고 추가할 수 있다.

실제 AI client는 항상 disabled·신규제품API비용0. 합성 client는 model_id=null/evaluation_kind=synthetic와 명시 가상 usage를 반환한다. 로컬 deterministic query dispatcher만 만들며 실제 MCP 등록/외부 서버 연결·URL/파일/쉘/주문/승인/정책 쓰기 기능을 제공하지 않는다. 여섯 역할의 명시 허용표와 request.allowed_queries 교집합을 검사하며 ref/scope/account/time/purpose를 도구 인자로 넓히지 않는다. Q14 role authorization을 세부역할 권한/프로세스격리로 과장하지 않는다.

## 닫힌 데이터와 원천 검증

새 최상위형은 ResearchRequest/ResearchResult/ResearchReview/Hypothesis/AIBudgetPolicy/AIBudgetAttempt. Q23 ExperimentResult와 구별한다. 닫힌 typed nested claims/citations/checks/period/query/usage/state/refs를 등록한다. AIRef kind enum과 실제 object resolver만 허용하며 임의 JSONPath/SQL/expression 없음. candidate를 AIRef로 참조할 수 있어도 기존 TargetRef.kind는 확장하지 않는다.

문서 실제 Q18 bundle/catalog/currentgrant를 재검증하고 exact UTF8 byte 범위/quote/manifest/revision/observation/original/context를 결속한다. 인용 일치는 내용의 진실성이나 해석의 타당성을 증명하지 않는다. 인용 밖 주장은 명시 inference/hypothesis로 표시하고 확정 사실로 승격하지 않는다. 자유서술을 구조검사만으로 의미 검증 완료라 하지 않는다. 문서 숫자는 인용일 뿐, 숫자claim의 authoritative source는 기존 typed 금융 API다.

숫자 원천은 Q20 실제 events/replay와 Q21 snapshot 재구성, Q23 bound performance/flows와 benchmark 실제 입력을 해소한다. scalar benchmark만으로 검증됐다고 하지 않는다. snapshot.nav, economic_cash, holding_quantity, performance.twr/amount_pnl/observed_mdd/gross_turnover/fees/taxes/slippage, candidate.quantity/limit_price/cost_bound/maximum_burden 등 고정 selector만 제공하고 미지원은 명시 unknown/거부다. 통화/단위/기간/종목/시장/정확값과 claim을 대조하며 AI의 계산을 실행 입력으로 쓰지 않는다.

모든 risk/history/flow/daily/document/market 의존 입력에 Q25 소비시각 현재 grant의 source/dataset/version/rights_ref·목적·유효기간·철회를 검사한다. 원본 historical grant로 바꿔 현재 mismatch를 숨기지 않는다. 필요한각 proof의 완전성/usable/누락scope·시점이 충족돼야 숫자claim을 complete로 할 수 있다. 현재권리는 ai+research+store, 보고는 ai+report+store이며 연구성과를 소비하면 research도 필요하다. 과거 권한 허용으로 현재를 대체하지 않는다. 원천 미확인→unknown, 일부출처누락/상충→partial, 권리/권한문제→blocked다.

숫자selector와 ref resolution은 유효한 claim을 실제 값과 비교한다. unknown 숫자를0으로 변환하지 않는다. complete는 구조/필수출처/수치/사용량 조건 충족이며 실제 모델의 의미적 정답 보증이 아니다. schema/인용/숫자/단위/identity mismatch invalid; 유효부분만 있으면 partial; 사용거부blocked; client실패/timeout failed. 응답에서 status를 선언해도 검증기가 판정한다. 응답/예외 원문은 오류기록에 반사하지 않는다.

## 합성 예산·동시성·요청 생명주기

평가spec default_profile의 실제명시 한도를 사용하며 누락을 무제한으로 해석하지 않는다. 가상 과금 정수 synthetic_microcredit, input1/output2/fixed1. 실제청구값이 아니다. cap100의70/40/50 golden은 별도 명시 합성 테스트 policy다.

공유 budget repository 단일 잠금에서 globalwindow·role·request·attempt·동시성·저장여유를 함께 검사하고 비용/입출력token/calls 예약후 client호출. 역할별book을 새로 만들어 공유한도 우회하지 않는다. 예약과 상태·감사·최종정산 저장공간을 미리 확보해 성공후 기록불가를 막는다. 비용·usage 범위 정수0..2^63-1, bool/음수/overflow거부. collections/문자열/bytes/deadline 상한은spec그대로다.

예약→dispatch→settled/unknown_charge, 전송전취소만release. 동일attempt+payload 멱등, 다른payload충돌; resultinvalid/failed여도 knownusage정산. actual>reserved는actual을 기록하고scope차단, 잘라내지 않는다. unknowncharge는예약유지·scope추가호출차단, window rollover로 지우지 않는다. 중복정산멱등/상충거부. 결과/감사/usage/실패는 exactrequest+attempt에 결속한다.

재시도/상향 정책은필수, 기본0/빈목록. timeout/unknown때다른client로자동회피없음. 최소v1은 자동retry/escalation미지원으로 명시차단해도되며 인자미설정을 허용으로 보지 않는다. synthetic clock을 주입해 호출전후deadline·늦은결과/usage를 확인한다. in-process faultclient의 hardkill/OS자원격리를 주장하지 않는다. actualclient미구현/비활성이므로실제네트워크시간제한검증아니다.

## 가설·검토·후보

가설 TTL과 source/data/policy/strategy/rights 의존성을 현재 조회마다 검증한다. expires_at끝제외, 누락TTL재사용금지. 과거 accepted review도 현재만료/정정/철회를 우회하지 않는다. supersede/retract는실제 predecessor를확인하는새불변기록, 과거기록보존. originresult/hypothesis ref 순환을 피하도록 result에는 제안본문을 넣고 저장된 hypothesis는완성result를참조하는식의순서를명시한다. source 진위검증과 genericcanonical정합성구별.

검토는 exactresult hash와 distinct invocation identity에 결속, 현재원천/수치검사 재실행. synthetic 두응답은실제독립모델평가아님. 동일작성invocation 자기검토는독립검토로표시하지않는다. Q24 candidate/plan/inputs를 실제해소하고 exacthash에 부속검토만 만든다. candidate문구/금융조건/계획·전략·승인·예약·주문 동작을 변경하지 않는다.

## 주간·월간 로컬 검토

PeriodReview 중첩형은 cadence/start/end/timezone/version/accountscope/basecurrency/source/performance/benchmarkrefs/metrics/researchchanges/strategychanges/interventionunknowns/supersession을 갖는다. v1 시간대는 명시 Asia/Seoul과 Q16 timezone ref, 주간 월요일00:00부터 다음월요일00:00, 월간 해당월1일00:00부터다음월1일00:00. 요청UTC경계는timezone로검증한다. 이후다른timezone는명시버전변경, UTC추정금지.

기간 [start,end)의 표시는 직전경계NAV와 Q23 (start,end] 사건 규칙의 대응을 명시한다: 성과평가 경계start/end를 그대로 사용하며 종료경계 사건은 Q23규칙대로 포함한다고 보고에알린다. 실제후속거래집계를 [start,end)로 주장하지 않는다. 다른3일fold를한달성과로재명명하지 않는다. 완전기간원천이없으면지표unknown/partial; 개입기록없음은개입0아님. deterministic수치는원천에서보존하고 AI설명실패와구별한다. 생성/표시현재report권리검사, 외부전송/예약없음.

## 저장·직렬화·시험

기존 canonical64KiB, 해소8MiB, 참조128/claims32/citations64/hypotheses8/checks/reasons64/문자열UTF8 2KiB. memory전체128records/8MiB 자동eviction없음, canonical bytes저장후재파싱. directconstructor/parser/app/repository에서동일상한·identity·상태/합계/참조불변식검사. source를포함하지않은 standalonecanonical이원천참임을증명하지않는다. localRLock은프로세스내동시성만, 운영재시작/영속청구·권한격리는별도다.

24고정사례와경계회귀를실제원천으로실행하고평가JSON에caseid/status/예상과실제/근거해시/버전/usage/효과0를기록한다. 다국어/주입/명명/단위/잘림/권한/예산/TTL에대한합성프로토콜평가이며실제LLM품질평가가아니다. 숫자golden을제품함수로역산하지않는다. concurrent70+40/settle50, unknownreservation/newwindow, wrongclaim/missingproof/candidateunchanged등실제경로를검증한다.

단독 구현자 소유: src/quantharbor/{domain,ports,application}/investment_ai.py, adapters/synthetic_investment_ai.py, additive domain/serialization.py, tests/product/synthetic_investment_ai.py·test_investment_ai*.py, docs/development/investment-ai.md. 필요시동일모듈범위에서파일분할가능하나최종목록반환. root는contract/spec/decision/task/status/evidence/queue통합. 기존금융모듈/TargetRef/frozen/migration/config는보존, 새dependency/범용agentframework없음.

## AS1~AS5 보안 검토 보완

- AS1: 멱등 재호출/캐시 반환도 현재 소비 권리·참조·철회·기한 검사를 수행한다. 거부 시 과거 complete 본문/인용/수치를 반환하지 않는다. 과거 기록은 변경하지 않고 현재 사용거부 결과와 구분한다.
- AS2: 가설 dependencies는 origin result의 supporting/opposing claim과 필수 원천·권리·정책/전략/자료 버전에서 결정론적으로 도출한 필수 집합을 포함해야 한다. caller가 timezone ref 등으로 교체/누락할 수 없다. 저장과 현재조회 모두 해소하고 철회·정정·TTL을 검사한다.
- AS3: result 상태/reasons/checks/query receipts/attempt는 실제 처리된 정규화 응답·query 허용 판정·사용량·검증 결과에 결속한다. 새 result ID나 hash만으로 blocked를 complete로 저장하거나 accepted review를 만들 수 없다. 저장소는 실제 request/attempt/처리 증거와 대조하며 검토도 query의 역할/요청 허용범위를 다시 확인한다. caller 선언 checks/status를 단독 권위로 쓰지 않는다. 실제 source 진위와 local 처리 영수증의 한계를 구분한다.
- AS4: dispatched 후 usage가 malformed/요금불일치/정산불능이면 예약을 유지하는 unknown_charge와 scope 차단을 원자적으로 확정한다. 이미 유효하게 정산된 usage를 되돌리지 않으며, 불명 잔존을 다음 window나 요청으로 우회하지 않는다. known invalid response usage는 정상 정산한다.
- AS5: 도구query 한도는 요청 전체 모든 attempt에 걸쳐 공유 repository에서 원자적으로 예약/누적한다. 새 dispatcher/재호출/동시 attempt로 초기화하지 않는다. 고정 한도16에서 허용된 실제 query 실행은 총16회 이하이며 거부된 query는 실행되지 않는다. 사용량·receipt·request binding과 멱등 재조회 처리를 구분한다.

고정24평가 명세와 실제 운영 정책은 변경하지 않는다. 추가 보안 회귀와 실패 이력은 별도로 기록한다.

## 보안 2차 검토의 구체 경계

- AS1b: 현재 원천이 누락되거나 참조가 변경되어 소비 권리를 확인하지 못하면 current_result도 과거 본문·인용을 숨긴다. 원래부터 partial인 결과의 안전한 사용 가능 부분과 현재 확인 실패를 구분한다.
- AS3b: 독립 검토는 응답이 선언한 queries뿐 아니라 실제 query_receipts의 모든 실행을 원래 요청·검토 요청의 권한 교집합으로 확인한다.
- AS4b: dispatch 이후 시각 역행 등 정산 전제 실패도 불명 청구와 scope 차단으로 확정한다. 유효한 기존 정산은 보존하고, 기록 시각은 마지막 확정 시각보다 뒤로 돌리지 않는다.
- AS5b: 동일 attempt의 실행 소유권과 예약을 결속한다. 비소유자는 예약·dispatch를 새로 수행하거나 소유자의 결과를 실패로 덮어쓰지 않는다.
- AS6: 검토 request와 review를 함께 용량 검사·저장한다. 실패 시 둘 다 저장되지 않아야 하며 성공 경로와 과거 기록은 유지한다.

## 일반 검토 AR1~AR6의 구체 경계

- AR1: 응답과 최종 ResearchResult 모두 canonical 크기 한도를 적용한다. 포장 후 초과해도 실제 사용량·감사 예약을 보존한 작은 invalid 결과를 확정하고, 정산만 남긴 채 결과 저장을 유실하지 않는다.
- AR2: dispatch 전 clock 오류는 해당 실행 소유자의 예약을 해제하고 호출0·사용량0의 실패 기록으로 남긴다. 비소유자의 예약 해제나 이미 dispatch한 호출의 무청구 해제는 금지한다.
- AR3: TradeCostFact의 Fraction slippage를 정확하게 합산하고 출력 계약에서만 유한 십진 표현으로 변환한다. 10주·기준100·매도99의 slippage는10이며 실제 원천에 결속한다.
- AR4: 계좌 전체 NAV/현금/성과 selector에는 종목 position을 허용하지 않는다. 종목별 selector는 실제 종목·거래소 identity와 정확히 일치해야 한다.
- AR5: 정상 기간 원천으로 계산할 수 있는 결정론적 PeriodReview는 AI 응답 파싱/설명 실패와 분리해 보존한다. 설명 invalid/failed를 complete로 바꾸지 않고, 원천 권리·누락·기간 경계 실패는 그대로 적용한다.
- AR6: 고정24 사례의 실제 변형 입력을 첫 평가 전에 구성하고 사례별 input refs/입력 내용 hash를 manifest에 고정한다. 공통 fixture refs를 모든 사례의 실제 입력으로 복사하지 않는다. 기존 spec·예상값은 불변이며 변형 ref·누락 의도·응답/정책/시각 입력도 사례와 결속한다.

AR1의 결과 저장 여유를 위해 실제 query receipt JSON 누적 상한은 32KiB로 둔다. 한도를 넘는 조회는 capacity로 거부하며 실제 실행/거부 이력을 숨기지 않는다. AR6의 실행 산출물(result/hypothesis) 의존 참조는 사전에 명시한 output binding 규칙을 실행 중 exact ref에 결속한다. 이를 사전 확정된 외부 원천 입력으로 표시하지 않는다.
