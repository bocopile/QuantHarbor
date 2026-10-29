# 합성 평가·대사·스냅샷 계약 v1 — Q21

상태: root 구현 기준. 고정 data-v1/serialization-v1·ledger-local-v1·Q17/Q19 계약을 소비하는 추가 명세다. EXEC-DEC-001에 따른 synthetic 전용 읽기 모델이며 실제 계좌 대사·자료 권리·운영 저장·주문 가능 판정은 아니다.

## 입력·타입·경계

ValuationRequest는 schema_version1/environment synthetic/account_ref/request_id, as_of, knowledge_cutoff, evaluated_at, projection_mode, base_currency, 소비 purpose(research 또는 report), 정책 참조, original_cutoff와 supersedes_snapshot_id를 갖는다. 시각/계좌/환경/cursor는 Q20 projection과 결속한다. as_known/restated를 혼합하지 않고 request 기준과 projection의 경제/지식 경계가 다르면 거부한다. evaluated_at보다 미래 지식 경계를 허용하지 않는다.

ValuationPolicy는 버전·가격 방식(raw close)·명시 source/dataset/version/series 선택·최대 가격/FX 나이·통화별 양수 quantum·half_even·반올림 단계의 불변 합성 정책이다. ReconciliationPolicy는 버전·수량 단위/통화별 tolerance를 필수로 가지며 합성 기본 fixture는0을 명시한다. 실제 운용 정책으로 승격하지 않는다.

애플리케이션:
- value_projection(projection, request, market_inputs, policy): 실제 Q17 select_view를 다시 호출하고 입력 근거를 검증한다.
- reconcile(projection, synthetic_statement, request, policy): scope/시각/의미 검증 후 원단위 비교한다.
- inspect_broker_batch(batch, request): 현재 Q19의 미해결 의미를 보고하며 확정 statement로 변환하지 않는다.
- build_snapshot(...): 모든 하위 결과의 projection/request/policy/hash/계좌/시각 결속을 확인해 불변 결과를 저장한다.

시장 입력은 기존 RevisionState, RightsGrant, dataset/version, catalog/calendar/timezone, 수집 품질·범위·manifest 또는 동등한 검증 가능한 근거를 묶는다. 외부가 만든 RawMarketView/ValidatedMarketView의 bool만 신뢰하지 않는다. 등록된 증빙의 hash·타입·서로의 결속을 확인하며 검증을 우회하는 임의 가격/quality=true 입력은 받지 않는다. aggregate된 상태를 사용할 때도 원시 evidence에서 재검증하고 충돌/누락을 숨기지 않는다.

새 domain 타입은 닫힌 불변 dataclass, nested 관계·순서·중복·유한 정확값·unknown 이유·집계/완전성 불변식을 검사한다. 상충 ID·알 수 없는 schema/필드/float·bool 숫자·위조된 결과를 canonical 복원에서도 거부한다. 입력128개/기존 canonical64KiB 등 한도를 명시하며 초과를 조용히 자르지 않는다.

## 평가·현금·손익

보유 identity는 instrument_id/venue_id/mapping_version/unit, 수량은 원장 그대로 보존한다. 통화/매핑/가격이 없으면 보유를 제거하지 않고 unallocated 또는 unvalued 상태와 사유를 남긴다. 0 보유도 명시 사실과 미확인을 구분한다.

경제적 현금[c] = settled_cash[c] + unsettled_receivable[c] + unsettled_payable[c]. payable은 원장 부호인 음수다. clearing·opening_equity·external_flow·비용/수익 상대 계정을 NAV 현금으로 다시 더하지 않는다. 매매→결제의 계정 이동으로 총자산이 이중 변하지 않아야 한다. 예약금을 NAV에서 다시 차감하지 않는다.

원천 총액·예약금·증권사 매수가능액·가용금은 별도 unknown 값/사유로 남긴다. Q20의 available_cash/reserved_cash/broker_buy_capacity=None을 보존한다. 주문 목록을 조회하지 않은 empty open_order_refs는 주문 없음이 아니므로 open_orders_status=unknown을 기록한다.

baseline 누락, quarantine·정정 영향 미해소·경제적 잔액 오류는 완전성에 전파한다. 각 보유·원통화 합계·기준통화 known_subtotal을 제공하지만 일부라도 미확인이면 NAV=null이다. 부분 소계를 NAV·비중 분모로 사용하지 않는다. 평가 완전성과 대사 상태는 별도 축이다.

cost_basis/unrealized_pnl/price_pnl/fx_pnl은 None과 costing_spec_pending_q23으로 남긴다. Q20 costs_known을 원가법 확정으로 해석하지 않는다.

## 가격·FX·정밀도

Q17 select_view를 매번 실행해 source/record hash·권리/목적·dataset/version·publication/observation/ingestion·catalog/calendar/timezone·adjustment 검증을 재사용한다. 소비 목적 권리는 evaluated_at에, 가격/FX 나이는 as_of에서 검사한다. 저장 시 store 권리도 확인하고 다른 목적 재사용은 다시 검증한다. 현재 RightsGrant enum에 valuation을 추가하지 않는다.

portfolio 가격은 raw PriceBar.close이며 ends_at≤as_of, 양수 가격, 원장 종목/venue/mapping/unit/통화 결속을 요구한다. source/series를 임의 대체하지 않는다. 지정 series에서 사용할 수 있는 최신 완료 bar를 선택하되 같은 기준시각 후보가 모호하면 보류한다. adjusted price·미래/미발표/unknown publication·stale·권리철회·필수 범위 partial은 unknown 사유를 남긴다. 비가격 보유 정보가 사라지면 안 된다.

FX는 기존 FXObservation의 양수 rate를 사용한다. native=FX base/portfolio base=FX quote는 곱셈, 반대는 명시 나눗셈, 동일 통화는 identity로 기록한다. 삼각환산·공급자 자동 대체는 없다.

정확한 정수/유리수로 계산하고 half_even을 양·음수에 적용한다. quantum은 단순 소수 자릿수가 아니라 실제 배수 단위(예:0.05)다. 전역 Decimal context·중간18자리 절삭에 의존하지 않는다.
1. 수량×가격을 정확히 계산한 뒤 보유별 native quantum 반올림.
2. 반올림한 보유값과 정확한 원장 현금값을 통화별 합산.
3. 통화별 소계를 FX 변환한 뒤 기준통화 quantum 반올림.
4. 변환한 소계를 합산.
저장 범위 초과는 거부하며 clamp하지 않는다. 이 단계 규칙은 버전 합성 정책이며 실제 통화/세무 규칙 채택이 아니다.

## 합성 statement·대사

SyntheticAccountStatement는 별도 닫힌 synthetic 계약이다. account/source/statement/source_revision, mapping/semantics 버전, requested/covered scope, status/complete, source_as_of, 관측/수집 시각, temporal_consistency/source_snapshot 근거, holdings와 세 경제적 cash component, omitted_means_zero 의미, 증빙을 포함한다. fixture의 기대값은 projection에서 복사하지 않고 독립 정의한다.

확정 비교에는 동일 환경/계좌·단위/포함 관계·요청 scope, 성공/완전한 페이지/필수 component, source_as_of==projection.as_of, cutoff 내 이용 가능, 검증된 source_snapshot, 완전한 원장 및 명시 비교 정책이 필요하다. bounded_observation과 unknown은 Q21에서 incomplete다. 현재 KIS batch의 숫자 일치나 complete flag로 이 조건을 대체하지 않는다.

원래 수량/현금에서 broker-ledger 차이를 계산하고 단위·threshold·판정을 보존한다. FX·평가 반올림으로 차이를 숨기지 않는다. 양쪽 키 합집합을 비교해 누락/추가 보유·통화를 확인한다. 생략=0은 complete scope와 명시된 omitted_means_zero일 때만 가능하다. 명시 0과 unknown 누락은 다르다. mapping 미확인은 서로 다른 자산의 확정 차이로 단정하지 않는다.

ReconciliationResult는 status(unreconciled|matched|mismatch|incomplete), requested/covered/missing scope, compared_domains, source refs/times, 차이 목록, scope_matched, full_account_balances_matched를 갖는다. subset 일치는 scope_matched만 참이며 snapshot 전체 matched로 승격하지 않는다. 전 계좌 보유·세 cash component 범위를 검증해야 full_account_balances_matched가 가능하고 주문·체결을 포함한 전체 운영 대사 완료를 뜻하지 않는다. 불완전 입력에서 확인 가능한 차이도 상세에 보존한다. 원장 쓰기 경로는 제공하지 않는다.

## Q19 bridge·snapshot·저장

inspect_broker_batch는 query/batch hash·scope·오류/완전성을 보존하고 해당하는 mapping_unknown/source_number_semantics_unverified/settlement_inclusion_unknown/reservation_inclusion_unknown/source_as_of_unknown/temporal_consistency_insufficient/scope_not_entire_account를 반환한다. 정상·빈 Q19 batch도 확정 대사로 승격하지 않는다.

PortfolioSnapshot은 data-v1 필수 필드 전체를 유지하고 schema_version1·created_at·base_currency·projection_hash·정책hash·평가/대사 상세·open_orders_status를 추가 명세로 구체화한다. 모든 하위 결과의 동일 입력·정책·scope·시각 결속과 합계/unknown 불변식을 검사한다. data_refs는 ledger/cursor/reducer/hash, 기존 가격/FX RecordRef, dataset 품질/범위 근거, context refs, 권리·정책, statement/batch hash를 연결한다.

ID는 고정된 입력 manifest hash에서 결정하고 완성 snapshot의 canonical hash는 별도 보관해 자기 해시 재귀를 피한다. 동일 입력/평가시각/버전은 같은 ID와 내용이다. supersedes는 repository의 실제 predecessor를 조회해 같은 환경/계좌/경제시각/scope/기준통화와 비순환을 확인한다. 최초 null, restated는 이전 snapshot과 더 늦은 cutoff를 요구한다. 과거 결과를 덮어쓰지 않는다.

SnapshotRepository는 append/get만 제공한다. 메모리 구현은 동일 ID/hash 멱등, 다른 hash 충돌, 환경/계좌 읽기 결속, 최대128 snapshot 초과 거부로 범위를 제한한다. 새 DB driver/migration/network 없이 읽기 모델을 검증한다. 메모리 저장은 재시작 내구성/운영 persistence 완료가 아니다.

## 검증·소유·후속

정확한 가격/현금/정·역 FX,0.05 quantum·양음수 half-even·Decimal context 독립성·overflow; baseline/가격/통화/FX unknown과 NAV 금지; 권리/시각/매핑/adjustment/위조 view; 계좌/범위/시점/누락·추가/0·tolerance·부분/오류/빈조회; KIS bridge 미완전; as_known/restated/미래결제·supersedes/canonical/ID충돌을 검증한다. Q20 불완전 projection이 완전 NAV/대사로 승격되지 않는 통합 회귀를 포함한다.

root가 계약/카드/상태를 소유하고 구현자에게 domain/application/ports/adapter와 additive serializer·관련 시험·개발 안내만 단독 배정한다. Q20 원장·Q17 시세 계약/코드·0001/0002/frozen baseline은 변경하지 않는다. Q22는 검증된 읽기 모델을 소비하며 Q23에서 원가·성과를 별도 정의한다.

## 독립 검토 V1~V3 보완

- store 권리가 없는 원시 selected payload는 snapshot/repository에 저장할 수 없다. unknown 평가로 바꾸는 것만으로 저장 허용이 되지 않는다. builder와 직접 canonical/append 경로 모두 같은 강제 조건을 적용한다. 권리가 차단된 입력의 거부/비저장 시험을 둔다.
- canonical 복원에서도 명시 series의 최신 완료 후보 유일성 및 observation–rights_ref 결속을 생성 경로와 동일하게 검사한다. 금액·manifest를 함께 다시 계산해도 이전 가격으로 바꾼 스냅샷이나 권리 불일치 proof를 수용하지 않는다.
- 독립 ReconciliationResult의 matched는 확인 가능한 statement·covered/requested scope·비교 영역 및 판정 조건을 필수로 한다. 단순 bool/status 조합만으로 전체 일치를 선언할 수 없다. snapshot의 재대사만으로 독립 등록 스키마 검증을 대체하지 않는다.
