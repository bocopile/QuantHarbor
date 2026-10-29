# 공통 데이터·원장 계약 v1 — Q09

상태: Q09 명시 범위 독립 검토 통과. 요구 v1, B-DEC-001, PG/SG 관문을 입력으로 한다. 이 문서의 모듈 경로·테이블은 구현 예정이며 현재 실행 서비스가 아니다. 승인·주문 상세는 Q10, 배포·권한·보존은 Q11에서 결합한다.

## 책임과 소유권

| 구성요소·제안 경로 | 소유 데이터·생산 계약 | 소비·금지 경계 |
|---|---|---|
| `domain/catalog` | 종목·거래소·통화·세션·상품 분류/근거 버전 | 공급자 코드는 어댑터에서 매핑. 불명확 상품은 허용하지 않음 |
| `market_data` | DataEnvelope·자료 manifest·품질/권리 결과 | SG-02 없는 실제 수집/보존/외부 제공 금지 |
| `brokers` | BrokerQueryResult·외부 관측·capability | 원장은 직접 수정하지 않음. 조회 실패를 빈 성공으로 변환 금지 |
| `ledger` | 수량/현금 이벤트·정정·투영·대사 결과 | 검증된 관측만 반영, 원장 단일 쓰기 경로. 평가·보고를 위해 수량/현금을 역산하지 않음 |
| `research`·`investment_ai` | 실험·근거·가설·제안 | 버전 읽기 모델만 소비, 주문/승인/원장 변경 불가 |
| `portfolio` | Snapshot·평가·미체결 반영 목표 입력 | 미평가 자산을 삭제하지 않음. 목표안은 원장 사실이 아님 |
| `approval`·`execution` | 승인·OrderIntent/OrderEvent·예약금 근거(Q10) | 제출 전 정책·capability·조회/대사 재검사, 계좌별 단일 실행자 |
| `reporting` | 버전 보고·전달 outbox/receipt | 조회 모델 소비, 거래 재실행 금지. 외부 전송 AP-10/SG-02 별도 |
| `runtime` | 세션·작업·재개/중단·관문 상태 | 사용자 시작/종료, 활성 세션에서 분석15분. 실제 예약 실행은 별도 |

초기 배포는 위 책임을 가진 Python 구성요소로 설계한다. 프로세스·서비스 계정의 분리는 Q11에서 정한다. 금융 원장·승인·주문 의도와 해당 outbox는 PostgreSQL transaction 안에서 원자적으로 저장하고, 외부 API 호출은 transaction 밖에서 수행한다. DB 커밋과 외부 접수 사이의 실패를 상태불명/대사로 처리하며 분산 exactly-once를 보장한다고 주장하지 않는다. 연구용 Parquet는 원장 정본이 아니다.

## 공통 기본형

- 모든 계약은 `schema_version`, 내부 불변 ID, `environment=synthetic|paper|live`, 생성 시각, 원천/요청 상관 ID를 갖는다. 계좌 참조와 실제 계좌번호/키는 분리한다. synthetic ID를 live 식별자로 변환하지 않는다.
- Money는 `{amount: decimal-string, currency}`다. Quantity도 decimal-string이며 float·NaN·Infinity 입력을 거부한다. 주문 수량은 양수, 원장 변화량은 부호를 갖는다. 반올림·최소수량·호가단위는 상품/시장 계약으로 명시하며 저장 시 몰래 반올림하지 않는다. JSON의 숫자 부동소수형에 금융값을 맡기지 않는다.
- Quantity는 종목 ID·단위를 포함한다. 소수 수량은 capability 확인 없이 정수로 바꾸지 않는다. Price는 금액·통화·종목·수량 단위를 포함한다. FX는 `base_currency`, `quote_currency`, `rate`(유한한 양수 decimal-string), 기준시각과 원천을 갖고 rate의 단위는 기준통화1단위당 상대통화 금액이다. 환산은 `quote_amount = base_amount * rate`, 역변환은 `base_amount = quote_amount / rate`로 정의하며 방향을 명시한다. 같은 통화쌍의 다른 방향 값을 자동 혼용하지 않는다. 통화별 반올림 규칙·정밀도가 없는 환산은 거부하며 임의 실제 환율값을 채우지 않는다. 종목 매핑은 유효기간을 가지며 상장 venue와 실제 체결 venue를 구분한다.
- 통화는 버전 catalog의 명시 값(KRW/USD 초기), 종목은 `instrument_id + venue_id + symbol_mapping_version`으로 구분한다. 동일 ticker를 세계 공통 ID로 취급하지 않는다. 종목명·문자열 패턴만으로 국가/상품을 판정하지 않는다.
- 순간은 timezone-aware UTC, 시장 시간대와 거래일·세션 ID는 별도다. naive 시각은 거부한다. 거래일은 UTC 날짜에서 추정하지 않고 버전 달력으로 매핑한다.
- 금액·가격·환율·수량의 단위와 스케일·통화, 실제 0과 unknown/null을 구분한다. 필수 비-null 필드의 null은 사용 거부이며 표시용 결측을 0으로 계산하지 않는다.

## DataEnvelope v1

필수 필드: `envelope_id`, `schema_version`, `source_id`, `dataset_id`, `dataset_version`, `environment`, `queried_scope`, `items`, `as_of`, `observed_at`, `ingested_at`, `quality`, `rights_ref`, `content_hash`, `lineage_refs`.

- 각 항목은 종목/통화/필드 단위·효력 시각을 포함한다. `published_at`은 원천에 존재하면 기록하고 없으면 명시 unknown이다. `as_of`는 자료의 기준 시점, `observed_at`은 획득 관측 시점, `ingested_at`은 내부 저장 시점이다. 발표 시각 부재를 수집 시각으로 채우지 않는다.
- `quality`: `complete|partial|unavailable|invalid`와 사유, 누락 범위·허용 지연 정책 참조를 포함한다. 신선도는 소비 시점에 다시 평가하며 complete가 fresh 또는 정확함을 뜻하지 않는다.
- `rights_ref`: 원천/사용자 권리 판정 버전·허용 목적·보존/만료의 비공개 참조. 원시 자료 대신 내부 참조를 외부 모델에 보내더라도 목적별 권리 검사가 필요하다. 허용을 확인하지 못하면 해당 사용을 차단한다.
- 가격조정 방식·환율 기준통화·원천 정정 버전은 명시한다. 서로 다른 조정/단위의 자료를 조용히 대체하지 않는다.
- 과거 평가에는 해당 의사결정 시점에 이용 가능했던 발표/관측 근거를 요구한다. 현재 취득한 정정 데이터로 당시 공개 가능성을 추정하지 않는다. 원천 이용 가능 시각이 불명확하면 해당 point-in-time 평가를 미검증으로 둔다.

## BrokerQueryResult v1

필수 필드: `query_id`, `environment`, `account_ref`, `capability_version`, `queried_scope`, `items`, `status`, `complete`, `continuation`, `pages_fetched`, `started_at`, `finished_at`, `source_as_of`, `temporal_consistency`, `source_error`, `raw_reference`.

- `status=success|partial|error|unsupported|unknown`. `complete=true`는 모든 요청 범위/페이지를 성공적으로 확인하고 필수 필드·중복/반복 cursor 이상 없음·정상 종료를 확인했을 때만 가능하다. 특정 시장·통화·기간 필터의 complete를 계좌 전체로 확대하지 않는다. `success`이고 complete여야 성공한 빈 결과를 판단할 수 있다. 빈 items만으로 주문 없음/잔고0을 판단하지 않는다.
- timeout·페이지 상한·인증/유량 오류는 partial 또는 error/unknown이며 complete=false다. 부분 items는 조사에만 사용하고 전체 잔고·대사 확정에 사용하지 않는다. 이전 정상 결과로 오류를 숨기지 않는다.
- 페이지를 모두 받았다는 사실은 동일 시점 스냅샷 보장이 아니다. `temporal_consistency=source_snapshot|bounded_observation|unknown`과 원천 snapshot ID 또는 관측 시간 구간을 구분한다. source_as_of가 없으면 unknown이다. 변화 중 조회의 일관성이 부족하면 대사 확정/위험 증가 주문을 보류한다.
- raw_reference는 접근 통제된 비공개 증빙 참조이며 원시 응답·계좌·토큰을 공개 로그에 넣지 않는다. 공급자 오류를 내부 처리 가능한 분류로 정규화하되 원인 유실/성공 승격 금지.

## LedgerEvent v1

필수 필드: `event_id`, `schema_version`, `environment`, `account_ref`, `source_kind`, `source_event_key`, `source_revision`, `mapping_version`, `payload_hash`, `event_type`, `effective_at`, `recorded_at`, `sequence`, `cash_legs`, `position_deltas`, `evidence_refs`, `correction_of`, `completeness`.

- `correction_of` 필드는 항상 존재한다. 비정정 원본은 명시 null, 정정은 동일 환경·계좌의 유효한 원본 참조를 요구한다.
- 원장 event/증빙은 추가 기록한다. 동일 `(environment, account_ref, source_kind, source_event_key, source_revision)`의 동일 payload는 기존 event를 반환하고 다시 계상하지 않는다. 같은 key에 다른 payload가 오면 충돌 보류·조사하고 기존 값을 덮어쓰지 않는다. 공급자 execution ID 부재 시 가격/수량만으로 동일체결을 단정하지 않는다. 식별 규칙이 검증되지 않으면 확정 원장 반영을 보류한다.
- 수량 변화와 통화별 현금 분개를 분리한다. 각 `cash_leg`는 계정·통화·부호 있는 정확한 금액·거래/결제 기준을 갖고 하나의 journal에서 통화별 합계0을 확인한다. 잔고 account 외 상대 계정도 명시한다. 서로 다른 통화를 환산해 차변/대변 불일치를 숨기지 않는다.
- 매매·수수료·세금·배당·분할·입출금·환전·결제·정정은 event_type과 증빙으로 구분한다. 매도 접수나 체결만으로 결제 현금 증가를 단정하지 않는다. 환전은 사용자/원천의 확인된 KRW/USD 변화를 각 통화의 상대 계정과 연결하고 시스템 환전 실행은 하지 않는다.
- 체결에서 미결제 금액을 인식했다면 결제는 계정 간 이동이며 현금을 다시 증감시키지 않는다. 수수료/세금·배당 gross/net 포함 관계가 미확인일 때 이중 차감/추정 금지. 외부 입출금은 손익과 분리하고 계좌 간 이동은 양쪽 사실을 각각 확인한다. 분개 의미·금액이 부족한 관측은 관측 저장소에 보류하며, 잠정 수량 사실을 표시하더라도 완전 원장/대사로 승격하지 않는다.
- 분할 등 비현금 수량 사건은 position_deltas와 변환 비율·효력시각 근거로 기록한다. 수수료/세금/결제 정보가 아직 없으면 불완전 상태를 보존하고 확정 손익/가용금으로 표시하지 않는다. 종목별 원가·수익 인식/세무 규칙은 ARC/F 계약에서 별도로 고정한다.
- 잘못된 이벤트의 수정은 원본을 참조하는 역분개/대체 이벤트로 남긴다. 이미 역분개한 event를 중복 반전하지 않도록 연결 고유성을 검사한다. 원천 정정·버전 변경을 단순 중복으로 무시하지 않는다.
- 멱등키의 revision은 동일 경제 사건의 개정 이력이다. 같은 source identity의 새 revision을 독립 사건으로 추가 계상하지 않는다. 공급자의 revision 순서·완전 교체/delta 의미·선행 관계를 검증하고 기존 유효 버전에 연결된 역분개/대체 또는 검증된 차이만 반영한다. 예: 체결수량10이12로 정정되면 유효 수량은12이며22가 아니다. 높은 revision 선도착·선행 버전 누락·순서 의미 불명은 관측으로 보류하고 대사한다. 이미 유효한 상위 revision 이후 도착한 과거 revision은 증빙 이력으로만 보존하고 유효 상태를 되돌리거나 다시 계상하지 않는다. 이미 처리한 revision 동일 내용은 중복, 상충 내용은 충돌 보류다.
- sequence는 내부 기록 순서이고 effective_at의 시간 순서를 보장하지 않는다. 늦은 사건/정정은 영향을 받는 projection을 재생하고 이전 snapshot을 덮어쓰지 않은 새 버전을 발행한다. 동일 입력·정책·계약 버전의 재생 결과가 같아야 한다.

## PortfolioSnapshot v1

필수 필드: `snapshot_id`, `environment`, `account_ref`, `ledger_cursor`, `ledger_schema_version`, `valuation_policy_version`, `data_refs`, `as_of`, `knowledge_cutoff`, `projection_mode`, `supersedes_snapshot_id`, `holdings`, `cash_by_currency`, `open_order_refs`, `reconciliation`, `valuation_status`.

- `supersedes_snapshot_id` 필드는 항상 존재한다. 최초 snapshot은 명시 null, 이전 snapshot을 대체하거나 restated로 발행할 때는 동일 환경·계좌의 유효한 이전 snapshot ID를 요구한다.
- holdings는 수량·원가 근거와 가격/평가 상태를 분리한다. 가격이 없으면 수량은 보존하고 평가액만 unknown. 전체 평가 합계를 완전한 숫자로 표시하지 않는다. 알려진 자산 소계를 NAV나 비중 분모로 사용하지 않는다.
- cash는 원천 총액·결제/미결제·증권사 매수가능금액·내부 예약금·산출 가용금·조회 완전성/시점을 구분한다. 증권사 가용금이 기존 주문을 반영하는지 모르면 예약금을 다시 차감/중복 사용하지 않는다. 필드의 포함 관계와 가용금 산식은 Q10에서 고정하며 확인 전 제출 불가다.
- 미체결 주문의 예약금 근거는 intent/order/version을 참조하고 체결·취소 완료·정정으로만 조정한다. 취소 요청만으로 해제하지 않는다. 이미 반영한 체결을 중복 계상하지 않는다.
- `reconciliation=unreconciled|matched|mismatch|incomplete`와 비교한 원천 조회 ID·시점·범위·차이·검사 버전을 기록한다. 재기동·불완전 조회·불명확 event는 matched로 통과하지 않는다. 차이를 숨기기 위한 현금 역산/원장 수정은 금지한다. 허용 오차가 필요한 비교는 단위·정책이 명시돼야 하며 미설정 epsilon으로 통과시키지 않는다.
- snapshot은 경제적 기준 `as_of`와 당시 지식 경계 `knowledge_cutoff`(recorded_at 및 ledger_cursor)를 함께 고정한다. 포함 사건은 effective_at ≤ as_of이고 지식 경계 안에 기록된 사건만이다. 미래 효력 분할/결제는 cursor 안에 있어도 효력 전 projection에 반영하지 않는다. `projection_mode=as_known`은 당시 이용 가능했던 개정만 적용하고, `restated`는 명시한 이후 지식 경계까지 반영해 과거 경제 상태를 재작성한다. 늦은 정정은 새 snapshot ID·supersedes_snapshot_id·입력 lineage를 남기며 원본을 바꾸지 않는다. 과거 전략 평가에는 당시 지식 경계와 자료 이용 가능성까지 충족한 as_known만 사용하고 restated를 당시 정보인 것처럼 섞지 않는다.
- snapshot은 특정 cursor·자료/정책 버전의 읽기 모델이다. 연구가 읽는 snapshot을 변경하지 않고 새 버전을 발행한다. 평가 성공은 주문 가능 판정과 다르며 제출 직전 Q10 검사를 다시 한다.

## 저장·전달·호환성

- outbox에는 event ID·계약 버전·destination·payload hash·상태·시도 기록을 저장한다. consumer는 inbox 고유키/동일 hash로 중복 처리하고 충돌을 보류한다. inbox 수신 기록과 consumer 업무 상태 변경도 같은 transaction으로 결속한다. 전달 성공과 업무 결과를 분리한다. ACK 유실은 중복 전달될 수 있으므로 consumer 부작용을 멱등화한다.
- ledger write·projection cursor·outbox 생성 중 같은 업무 원자성이 필요한 묶음은 transaction으로 결속한다. 영속 실패·손상/충돌은 신규 위험 증가 주문을 보류한다. 외부 API를 DB transaction 안에 묶지 않는다.
- v1은 최초 계약이다. 배포된 이전 금융 계약/DB가 없어 현재 migration 실행은 없다. enum/필수 필드/금액·시점 의미 변경은 새 계약 버전으로 올리고 producer/consumer 대응과 replay 계획을 함께 검토한다. 모르는 계약 버전/enum은 거부한다.
- 내부 canonical 직렬화와 hash 알고리즘·소수 정규화·필드 순서는 Q12 구현 계약에서 고정한다. canonicalization 버전을 hash와 함께 기록한다. 해시가 같다는 이유로 권한/출처/정확성을 보장하지 않는다.
- 최소 검증 사례: finite decimal·통화 불일치, naive time/서머타임, partial 빈조회, 완전하지만 시점불일치 조회, 같은 key 다른 payload, 역순 정정/중복 역분개, 가격 없는 보유, 예약금 중복 차감, transaction 중단·outbox 재전달, unknown schema. 현재 실행한 테스트가 아니라 C~K에 연결할 완료 기준이다.

## 영향과 미완료

생산/소비 경계는 C(저장·의존성), E(데이터), I-R(조회), F(원장), G/H(연구), I-W/J(승인·실행·보고)에 적용한다. Q10에서 목표안·승인·주문·예약금 산식과 상태기계를 결합하고 Q11에서 권한·보존·복구를 결합한다. SG/PG가 미완료인 실제 공급자 데이터·계좌를 계약 시험에 사용하지 않는다. 구현·DB·실제 주문·성능/원장 검증은 아직 수행하지 않았다.
