# Q21 합성 평가·대사·스냅샷

- 작업 ID: VALUATION-local / Q21, EXEC-DEC-001, VAL-DEC-001.
- 상태: V1~V3 회귀 재현·수정 및 로컬 합성 검증, root 독립 재검토 대기.
- 입력: valuation-local-v1, 고정 data-v1/serialization-v1, Q20 LedgerProjection, Q17 저장 증빙·조회, Q19 BrokerReadBatch.
- 담당: 단독 구현자. 공통 계약·상태·작업 카드·기존 원장/시세/증권사 코드는 root 소유다.
- 범위: 공개 소스와 독립 합성 fixture. 외부 API·키·실제 계좌·DB·설치·Git 변경 명령은 실행하지 않는다.

## 소비 API

`application.valuation.value_projection(projection, request, market_inputs, policy)`는 모든 보유 수량과 identity를 보존한다. request의 environment/account/cursor/as_of/knowledge_cutoff/mode를 projection에 결속한다. 시장 입력은 `ports.valuation.MarketDatasetInput(bundle, catalog, calendar, timezone, current_rights)`의 tuple이다. bool·임의 가격·외부에서 만든 view는 입력 계약이 아니다.

Q17의 실제 `replay_storage`로 descriptor·receipt·원시 evidence에서 상태/품질/envelope/summary를 재구축해 공급된 aggregate와 비교한다. 현재 권리로 실제 `select_view`를 다시 호출하며 catalog/calendar/고정 TZif context, 자료/정책 series, 권리·소비 목적·store, observation/revision hash 및 scope를 검증한다. `MarketProof`는 기존 RecordRef와 context refs, descriptor/receipt/evidence-index/envelope/summary hash, 실제 선택된 MarketItem 및 품질/권리를 연결한다. 미래·미발표·partial·stale·조정 가격·잘못된 identity는 unknown 사유가 된다. 악성 hash/context/aggregate나 잘못된 계약 입력은 거부한다. 원시 evidence에서 상태를 재구축하는 시장 알고리즘은 Q17 구현을 그대로 호출한다.

`value_projection`의 unknown 결과는 저장 허가가 아니다. selected 원시 payload가 있으면 builder와 `PortfolioSnapshot` 생성·canonical 복원·직접 repository append 모두 request의 `evaluated_at`에서 store 권리를 요구한다. 권리 차단으로 selected payload가 비어 있는 불완전 결과는 저장할 수 있다. proof의 모든 selected observation은 실제 `rights_ref`와 결속하며 가격·FX 참조는 해당 series의 최신 유일 후보여야 한다.

`ValuationPolicy`는 raw close와 명시 source/dataset/version/series, 나이, 통화별 양수 quantum, half_even 및 고정 단계 순서를 가진다. 입력 가격을 자동 대체하거나 삼각 FX를 계산하지 않는다. FX의 native/base 방향에 따라 곱셈 또는 나눗셈을 기록한다. 정수/유리수로 중간 계산하고 실제 quantum 배수로 반올림한다. 보유별 native 반올림 → 정확 원장 현금과 통화별 합산 → 통화별 FX 후 base 반올림 → base 합산 순서다. 0.05는 소수 자릿수 설정이 아니다. 저장 범위 초과는 거부한다.

현금은 settled_cash + unsettled_receivable + 음수 unsettled_payable만 합산한다. counterpart를 더하거나 예약금을 다시 차감하지 않는다. source_total/reserved_cash/available_cash/broker_buy_capacity는 None이며 이유를 보존한다. 원장 불완전성과 미평가 보유가 하나라도 있으면 NAV는 None이다. native known_subtotal 및 base known_subtotal은 확인된 부분 소계이고 비중 분모가 아니다. cost_basis/unrealized_pnl/price_pnl/fx_pnl은 `costing_spec_pending_q23`로 남긴다.

`reconcile(projection, synthetic_statement, request, reconciliation_policy)`는 평가액이 아닌 원수량과 세 현금 component를 비교한다. `StatementSourceSnapshot`은 독립 source/statement/revision/source_snapshot/계좌/scope/시각/identity/현금/증빙을 가진 canonical 자료다. `SyntheticAccountStatement`는 이 snapshot hash, 요청 범위, 페이지/상태 완전성, source_snapshot 시간 의미, 매핑·포함 관계 및 생략=0 의미를 명시한다. fixture 기대값은 projection에서 생성하지 않는다. Q19 batch를 이 계약으로 자동 변환하지 않는다.

확정 일치는 동일 경제·지식 경계, 성공한 전체 요청 범위, 확인된 매핑/경제적 현금 의미, 완전한 원장과 명시 단위별 tolerance를 요구한다. 키 합집합으로 missing/extra/명시0을 비교한다. 생략=0은 완전한 scope와 명시 의미가 함께 있어야 한다. 불완전 상태에도 확인 가능한 차이는 보존한다. `BalanceScope`는 entire_account 또는 명시 종목 identity/통화/component의 subset이다. subset 일치는 scope_matched만 참이며 전체 snapshot matched로 승격하지 않는다. 비교 API에는 원장 쓰기 경로가 없다.

독립 `ReconciliationResult`의 matched 생성·canonical 복원에서도 실제 statement, 요청/covered/source scope 일치, 성공·완전성·source_snapshot·검증된 의미, compared_domains와 비교 행의 일치, 원천 보유 및 요청 현금 component의 비교 누락, statement 원수량 결속과 생략=0 조건을 검사한다. projection/request/policy의 원문을 함께 가진 snapshot에서는 기존 전체 재대사도 유지한다. 독립 결과에 있는 hash만으로 원문이 없는 원장·요청의 내용을 재구성할 수 있다는 의미는 아니다.

`inspect_broker_batch(batch, request)`는 실제 Q19 계약을 canonical 재검사하고 query/batch hash, 상세 BrokerReadScope, 원천 상태·완전성·실패·missing scope를 보존한다. 정상·빈 batch에도 mapping/숫자 의미/결제 포함/예약 포함/source_as_of/시간 일관성/전체 계좌 범위의 미확인을 반환한다. 실제 계좌 대사 완료를 뜻하지 않는다.

`build_snapshot(projection, request, market_inputs, policy, reconciliation_policy, repository, *, statement=None, valuation=None, reconciliation=None, broker_batch=None, broker_inspection=None)`은 하위 결과를 다시 계산해 supplied 결과의 타입/hash/내용을 비교한다. 모든 결과는 request/projection/policy와 결속한다. `PortfolioSnapshot`은 data-v1 필수 필드 전부와 typed 평가/대사/증빙 상세, created_at/base_currency/policy hash/open_orders_status를 제공한다. 조회하지 않은 open_order_refs=()는 open_orders_status=unknown이다.

## 불변 저장·복원·한도

ID는 `snapshot:` + 고정 `SnapshotInputManifest` canonical hash이고 완성 snapshot의 canonical hash는 별도 저장한다. manifest는 projection/request/정책/검증된 평가·대사/bridge hash를 포함하며 자기 snapshot hash를 포함하지 않는다. 같은 고정 입력과 evaluated_at은 같은 ID/내용이다. 입력·자료·정책·평가 시각이 달라지면 새 manifest다.

Canonical 등록은 additive이고 frozen baseline은 수정하지 않는다. 재구성 시 닫힌 필드/schema/enum/숫자, 중복·정렬, 수량 보존, 현금·native/base 합계·NAV·완전성, 선택된 원시 가격/FX와 RecordRef, request/projection/policy hash, 대사 재계산, manifest/ID/data_refs를 확인한다. statement와 비교 정책도 snapshot에 포함된다. hash는 synthetic 사실의 결속이며 실제 공급자 서명·권리 증명을 대체하지 않는다.

`SyntheticSnapshotRepository`는 append/get만 제공하며 canonical bytes를 저장·재복원한다. 호출자가 반환 객체를 Python 내부 기능으로 변조해도 저장된 bytes를 바꾸지 않는다. 읽기는 환경·계좌·ID/hash 결속을 확인한다. 동일 ID/hash/bytes는 멱등이고 상충 내용은 거부한다. supersedes는 실제 저장된 predecessor를 조회해 환경·계좌·as_of·scope·base_currency 및 시간 순서를 검증한다. restated는 predecessor의 정확한 이전 cutoff와 더 늦은 cutoff를 요구한다. 기존 snapshot을 덮어쓰지 않으며 순환 계보를 거부한다.

읽기 모델의 holdings/cash·시장 원시 evidence 총수·개별 typed collection은 최대128, receipt는 dataset별 최대16, repository는 최대128 snapshot이다. Q17/Q20의 더 작은 입력별 제한도 그대로 적용한다. canonical 한도는 기존64KiB이며 전체 nested snapshot이 이를 넘으면 거부한다. 입력을 조용히 자르지 않는다. 이 메모리 저장은 재시작 내구성·운영 persistence 완료가 아니다.

## 검증과 인계

Q21 전용 시험은 `test_valuation.py`, `test_valuation_reconciliation.py`, `test_valuation_snapshot.py`와 `synthetic_valuation.py`를 사용한다. 독립 숫자 기대값, 실제 Q17/Q19/Q20 소스 API, buy/sell/settlement 불변성, 권리/가격/FX/identity/품질/scope 위조와 미확인, 0.05와 양음수 tie·낮은 Decimal context·overflow, subset/누락/추가/0/tolerance, KIS 보류, canonical 변조·ID 충돌·실제 predecessor·as_known/restated/미래결제를 검증한다.

요청된 검증 명령:

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -v
python3.13 -I -S -B -m unittest discover -s tests/quality -v
python3.13 -I -S scripts/check_quality.py
git diff --check
```

2026-10-24 V1~V3 수정 후 로컬 실행 결과:

- 제품 suite: 301개 통과, 실패/오류0. Q21 75개(기존62 + 회귀13)를 포함한다.
- 품질 suite: 지정한 `-I -S -B` 조건에서87개 통과, 실패/오류0.
- 정적 품질 검사: 현재 작업공간의 공개 후보334파일 pass, findings0(최초 구현 인계의330파일과 구분).
- `git diff --check`: exit0.
- 최초 구현 당시 시험 수정(이번 V1~V3 재현과 별도): 잘못된 source 입력은 계약 거부가 맞으므로 unknown만 기대하던 시험을 수정했다. 유효한 Q17 조정가격 시험은 action의 실제 관측·수집 이후에 조정 지식/발표 시각을 두도록 fixture를 수정했고, Q21의 raw close 거부를 별도로 확인했다.

V1~V3 보완의 실제 재현과 회귀:

- 검토 증거는 `static_code_trace`, `tests_executed=false`였다. 아래 수치는 이번 구현자가 실제 로컬 실행한 결과이며 독립 검증으로 기록하지 않는다.
- 제품 수정 전에 회귀 시험을 작성했다. 초기 탐색 실행은 Q21 74개/실패43/오류0이었다. V1의 권리철회·만료로 selected payload가 사라지는 경우는 거부 대상과 구분해 정상 incomplete 대조군으로 정리했다. 회귀 fixture 실행 오류는 없었으며, 이 기대 범위 정리를 제품 결함으로 집계하지 않는다.
- 확정 red: Q21 75개, 실패49건(11개 테스트 메서드), 오류0. V1 7건/3메서드, V2 12건/4메서드, V3 30건/4메서드다. 실패 건수는 경계별 subTest assertion을 포함한다.
- V1: research만 허용한 실제 시장 입력으로 builder가 raw selected payload를 저장했다. NAV=None인 결과를 직접 snapshot 생성·canonical 복원·append해도 수용됐다. evaluated_at에서 철회된 store 권리도 unknown 결과에서 우회됐다. 수정 후 모두 거부하고 repository는 비어 있다. selected 없는 권리차단 결과는 incomplete로 보존한다.
- V2: 독립 구가격10/신가격11·보유2·현금1000 fixture의 정답은1022다. 구가격 참조·금액1020·manifest·ID·data_refs까지 재계산한 변조가 생성·복원·직접 append에서 수용됐다. 최신 동시 후보의 모호성, proof rights_ref 불일치, FX 구환율 변조도 재현했다. 수정 후 모두 거부하며 정상 raw/FX canonical 왕복과 기존 restated 시험은 통과한다.
- V3: statement=None 결과를 matched/empty reasons/empty missing/true flags로 바꾸면 독립 생성·복원에서 수용됐다. covered/requested scope 변경, 비교 영역·행 누락(영역도 함께 변경), 부적격 statement 및 원천 수량 불일치도 재현했다. 수정 후 모두 거부하며 정상 전체·subset·빈 계좌의 독립 왕복은 통과한다.
- 수정 후 targeted green: 같은 Q21 75개 모두 통과, 실패/오류0. 전체 제품·품질 명령의 결과는 위와 같다.

정확 파일 hash는 최종 인계에 기록한다. 독립 검토·최종 통합 판정과 status/task 갱신은 root 담당이다. 실제 statement·자료 권리·계좌/주문/예약금·Q23 원가/성과·DB 내구성은 후속 작업이다. Q22 이후는 위 callable API를 소비할 수 있다.
