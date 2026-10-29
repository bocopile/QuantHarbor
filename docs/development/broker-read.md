# Q19 합성 증권사 조회 로컬 구현

2026-10-24 기준. [broker-read-v1](../contracts/broker-read-v1.md)의 로컬 준비 구현이다. 실행 환경은 `synthetic`, 비전송 wire profile은 `paper`다. 실제 KIS 모의 지원·계좌 권한·API 동작을 확인한 결과가 아니며 Q19 완료나 Q20 진입 근거로 쓰지 않는다.

주 진입점은 `application.broker_read.read_broker(request, capability, transport, evaluated_at=...)`다. transport는 정확히 `FixtureTransport`만 받으며 임의 callback·HTTP client를 받지 않는다. 요청·capability·fixture를 생성자로 재검사하고 요청과 capability의 binding/operation/scope가 다르거나 유효기간·요청 시각이 맞지 않으면 fetch 전에 고정 `ContractError`를 반환한다. 미지원/미확인 기능은 fetch 없이 `unsupported` batch다. 포트는 동일 프로세스 악성 코드에 대한 보안 격리가 아니다.

## 등록형과 정확 필드

세 등록형만 기존 canonical registry에 추가했다. 아래 필드가 모두 저장되며 default도 생략하지 않는다. `schema_version`은 정수 1, `environment`는 `synthetic`만 허용하고 wrapper 환경과 일치해야 한다. 모든 중첩형은 닫힌 decoder 표에서 복원한다. 기존 4개 기본형·시장/저장/문서 등록형의 필드·정규화·해시 prefix·64KiB 상한은 유지한다.

| 등록형 | 정확 필드 |
|---|---|
| `BrokerReadCapability` | `schema_version, environment, binding, operation, scope, support, evidence_ref, valid_from, expires_at, max_calls, max_pages, max_rows, max_bytes, max_seconds` |
| `BrokerReadRequest` | `schema_version, environment, query_id, binding, operation, scope, requested_at, deadline_at` |
| `BrokerReadBatch` | `schema_version, environment, request, request_hash, result, page_receipts, missing_scope, reason_codes` |

중첩형의 정확 필드는 다음과 같다.

| 중첩형 | 정확 필드 |
|---|---|
| `BrokerReadBinding` | `binding_version, environment, broker, account_ref, capability_version, wire_profile, endpoint_registry_version, catalog_version` |
| `BrokerReadScope` | `coverage, market, currency, exchange, start_date, end_date, period_class, symbol, price, order_kind` |
| `BrokerCursor` | `forward, next` |
| `SourceNumber` | `source_field, value, missing_reason, currency, unit, semantic_status` |
| `BrokerObservation` | `query_id, binding, operation, scope, kind, source_section, row_key, source_symbol, venue, currency, observed_at, numbers, order_date, order_branch, order_number, original_order_number, mapping_status, instrument_id, execution_granularity, individual_execution_id, settlement_inclusion, reservation_inclusion, usable_for_internal_available_cash` |
| `BrokerPageReceipt` | `request_hash, page_index, request_cursor, response_cursor, received_at, body_sha256, received_bytes, received_rows, validation, reason, account_evidence, wire_marker, terminal_evidence` |
| `BrokerQueryResult` | frozen data-v1의 `query_id, environment, account_ref, capability_version, queried_scope, items, status, complete, continuation, pages_fetched, started_at, finished_at, source_as_of, temporal_consistency, source_error, raw_reference` |

binding은 `broker-read-binding-v1`, `kis`, `paper`, `kis-read-synthetic-v1`을 고정한다. account_ref는 `synthetic-account:` 접두어의 더미 참조다. 실제 계좌 번호·host·인증값을 받는 필드는 없다. scope는 operation별 exact shape이며 다른 operation의 필터를 덧붙여도 거부한다. 국내 주문은 `cash_orders`, 해외 주문은 `broker_overseas_all` 범위다. 기간 분류 `inner|before`는 국내 주문 호출자가 명시한다.

## 비전송 계획과 source 관측

`adapters.kis_read.WirePlan(request, cursor)`는 GET method/path/TR/params를 계산한다. 6종 고정 경로와 paper TR 외에는 만들지 못한다. CANO/ACNT_PRDT_CD 값은 해석하지 않는 symbolic slot이다. 다음 페이지 요청만 `tr_cont=N`을 만든다. 실제 host·인증 헤더·요청 전송 함수는 없다.

공식 고정 커밋의 function/chk를 함께 읽어 `SECTIONS`에 section shape, identity, 숫자, 미사용 허용 필드를 분리했다. 공개 `chk`는 여러 section의 필드를 하나의 mapping에 합치므로 section별 완전한 실제 wire schema를 증명하지 않는다. 이 표는 합성 fixture의 보수적 허용 계약이며 실제 응답과의 검증은 미완료다. 임의 dict fallback이나 모르는 필드 무시는 없다. 해외 함수가 명시적으로 처리하는 object/list 두 shape는 둘 다 허용한다. 국내 잔고는 list/list, 국내 주문은 list/object, 국내 매수가능은 object다.

`decode_page`는 JSON 중복 key·숫자형/float/bool·비정상 깊이·문자열·행 수·64KiB 초과·unknown field·잘못된 section shape를 거부한다. 반환 관측에는 선택한 숫자 source field와 명시적으로 허용한 source identity만 남긴다. 미사용 필드 값과 `msg1`은 복사하지 않는다. 오류는 원문 없는 고정 코드다. 파싱에 실패한 페이지의 `received_rows=0`은 검증된 row 개수를 알 수 없다는 뜻이며 빈 성공이 아니다. 명시적인 행 상한 실패 때 확인한 배열 길이는 receipt에 남긴다.

원천 수치의 `null`, 빈 문자열, 미제공과 정확한 `0`을 구분한다. decimal_string을 재사용하고 trim·반올림·합산하지 않는다. 초기 구현은 내부 Money/Quantity로 승격하지 않으며 숫자의 통화·단위도 미확정이면 null이다. 현금의 결제/예약 포함 관계는 unknown, 내부 가용금 사용은 항상 false다. `max_buy_amt`도 source 관측일 뿐이다.

국내 주문 요약 `tot_ccld_amt`와 해외 현재잔고의 `frcr_evlu_amt2`에는 모호한 label이 있어 의미를 추정하지 않는다. 후자는 output1의 허용 미사용 필드이며 output2에 존재하면 `semantic_status=unknown` 숫자로 보존한다. output2에 이 optional field가 없다는 이유만으로 필수 사실 누락을 만들지 않는다. 실제 field/section 대응과 의미는 후속 확인 대상이다.

공급자 symbol은 내부 ID가 아니다. Q16 catalog의 정확 매핑을 수행하지 않으므로 `mapping_unknown`, `instrument_id=null`을 유지한다. 주문은 날짜·지점·번호와 원주문 번호를 분리하고 `execution_granularity=order_cumulative`, `individual_execution_id=null`이다. 누적 3과 5를 그대로 별도 관측으로 보존하며 차이 2를 체결로 만들지 않는다. 주문 날짜가 요청 범위를 벗어나거나 잔고의 통화/거래소가 요청과 다르면 실패한다.

계좌 echo는 decoder 안에서만 고정 영(零) fixture identity와 비교한다. expected identity가 없으면 echo를 검증 성공으로 표시하지 않는다. echo 부재는 `request_bound_only`다. 숫자 echo는 반환형·repr·canonical·예외에 남기지 않는다. fixture의 raw_body와 tr_cont도 repr에서 제외한다.

## 페이지·완전성·실패

호출/페이지 4회, 수신 원천행 32개, 페이지당 64KiB, 요청 전체 256KiB, 관측 구간 30초가 기술 상한이다. capability는 줄일 수 있고 늘릴 수 없다. `evaluated_at`은 호출자가 명시한 합성 평가 시각이며 fixture 수신 시각의 상한이다. 요청 이후의 순차 시각·deadline·capability 만료를 검사한다. 시간 진행·sleep·재시도·인증 갱신은 없다.

상한에 도달하면 종료 fixture가 있어도 complete로 올리지 않는다. 다음 페이지가 행/byte 상한을 넘으면 그 페이지를 거부하고 앞선 관측을 보존한다. 동일 행도 수신량과 receipt에 포함한다. 중복 판단은 배열 위치에 의존하지 않으며 source identity와 수치를 비교한다. 같은 주문 키의 수량 변경은 `conflicting_observation`, 동일 사실 반복은 `duplicate_observation`이다. 모두 complete=false이며 요약/현금을 더하지 않는다.

M/F는 검증한 cursor 쌍으로 다음 페이지를 요청한다. 누락/반복 cursor, 다음 응답 부재·오류는 incomplete다. 현재잔고처럼 검증한 후속 token이 없는 endpoint의 계속 표시는 `continuation_unverified`다. 순수 decoder는 실제 terminal을 증명하지 않는다. **고정 fixture의 `synthetic_terminal_v1`와 빈 tr_cont가 함께 있어야** application이 합성 종료로 인정한다.

앞선 accepted receipt 후 실패는 `partial`, 첫 페이지 거부는 `error`, 응답 부재는 `unknown`이다. 종료 증거가 없는 accepted 첫 페이지도 성공이 아니라 incomplete다. `source_as_of`는 항상 null, 일관성은 최대 `bounded_observation`이다. 완료는 scope에 한정하며 같은 시점 계좌 snapshot·대사·주문 가능을 뜻하지 않는다.

최종 batch도 기존 canonical 64KiB를 검사한다. 표현 크기를 넘으면 `error/output_oversize`, complete=false와 빈 items의 명시 실패를 반환한다. 관측을 잘라 success로 반환하지 않는다. receipt는 유지하고 실패 사실을 기록한다. 원시 bytes의 SHA256과 request의 canonical hash는 서로 다른 필드다.

## 연결 준비와 현재 검증

`connection_readiness(binding, checked_at=...)`는 serializer 밖의 고정 `ConnectionReadiness`다. 필드는 `account_ref, checked_at, target_environment, missing_requirements, evidence_refs, real_transport_available, connectable`이다. target은 paper, 실제 transport와 connectable은 항상 false다. 누락 코드는 PG01/SG01/SG02/AP05/private 주입/암호화·키관리/보존·복원이다. boolean flag를 켜 연결하는 경로는 없다. [실제 연결 준비안](paper-connection-preparation.md)을 따른다.

이번 연속 소단계에서는 직접 만든 국내 잔고 1페이지·2관측을 읽고 capability/request/batch 세 등록형의 canonical 왕복을 확인했다. 전용 broker 회귀 25개를 포함한 제품 152개와 품질 22개가 통과했고 공개 후보 267파일 품질 검사 및 팀 설정 6명/큐 36개/작업 ID 110개 정합성도 통과했다. 실행 명령은 아래와 같다. 전용 회귀는 6종 정상/범위별 빈 결과, binding·scope·시각·상한, 중복·누적 충돌, echo 미노출, canonical 위조 거부와 출력 크기 실패를 확인한다. 독립 보안/일반/실행 검토는 후속이다. 실제 API·개인 파일·환경변수·키·DB·Docker·저장 회귀는 이번 구현 확인에 사용하지 않는다.

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -v
python3.13 -I -S -m unittest discover -s tests/quality -v
python3.13 -I -S scripts/check_quality.py
python3.13 -I -S scripts/check_ai_team.py
```

제품 테스트 import는 신뢰된 개발 경로에서 실행한다. 공개 후보 품질 검사 자체는 `-I -S`로 실행해야 한다. 위 확인은 실제 권리·유량·terminal·source snapshot·전체 source schema·ETF 지원 확인을 대체하지 않는다.

첫 전용 실행은 25개 중 2개 실패했다. 64KiB 페이지 equality를 통과시키던 경계를 고치고 30초 equality도 incomplete로 닫았다. Batch 직접 생성의 complete 주장에 결측 숫자·중복 사실·receipt cursor chain 검사가 부족한 점도 수정했다. 재실행 25개와 전체 제품 152개가 통과했다. 단건 매수가능의 빈 object는 현금 0이나 빈 성공으로 바꾸지 않고 missing_fact를 유지한다.


## S1/S2 보안 검토 수정

2026-10-24 독립 지적의 직접 생성·canonical 복원 우회를 4개 회귀로 먼저 재현했다. 당시 전용 29개 중 4개가 실패했다. 도메인 `SOURCE_FIELDS`에 section별 kind·필수/선택 숫자 필드·complete에 필요한 identity를 한 번 정의하고 adapter의 numeric whitelist도 이 표를 공유하게 했다. 스키마 필드는 추가하지 않았다.

관측에 존재하는 venue/currency가 요청 범위와 충돌하면 관측 생성과 복원에서 거부한다. 국내는 KRX/KRW, 해외 잔고는 요청 거래소/USD, 해외 현재잔고는 미국 거래소/USD에 결속한다. 해외 주문의 `broker_overseas_all` 범위를 미국 거래소만으로 축소하지 않는다. 종목별 매수가능의 source symbol도 요청 symbol과 일치해야 한다.

미제공 identity·숫자는 incomplete 관측으로 보존할 수 있지만 필수 identity·숫자 필드 하나라도 없으면 complete batch를 만들거나 복원하지 못한다. 선언되지 않은 숫자 필드로의 교체도 거부한다. `frcr_evlu_amt2`는 명시 optional이며 부재는 정상이다. 이 수정은 원천 숫자의 의미·현금 가용성을 확정하지 않는다.

수정 후 전용 31개·전체 제품 158개·품질 22개, 공개 후보 270파일 검사와 팀 6명/큐 36개/작업 ID 110개 정합성이 통과했다. 전용 회귀는 모든 section의 필수 identity/숫자 누락과 optional 부재·incomplete 보존도 확인했다. 독립 재검토와 실제 연결 관문은 남아 있다.

## R1/R2 일반 검토 수정

2026-10-24 직접 생성·canonical 복원 회귀에서 전용 35개 중 4개가 실패했다. complete에는 지원 operation을 요구하고, 검증한 후속 token이 없는 매수가능/해외 현재잔고는 accepted 한 페이지만 허용하도록 고쳤다. 국내 매수가능 output과 국내 주문 output2는 accepted 페이지마다 하나가 필요한 object section이다. items와 receipt 행 수를 함께 지워도 이 section 수 검사를 통과하지 못한다.

complete batch의 accepted receipt를 received_at으로 묶고 수신 행 수 합계와 같은 observed_at의 item 수를 대조한다. 필수 object section 수도 해당 시각의 accepted 페이지 수와 같아야 한다. 같은 timestamp의 여러 페이지는 합산해 정상 허용한다. 현재 스키마에는 item별 page ID가 없으므로 동일 시각 안의 개별 페이지 귀속까지 증명하지는 않는다. incomplete 보존과 출력 초과의 명시 실패는 유지한다.

수정 후 전용 37개·전체 제품 164개·품질 22개, 공개 후보 273파일 검사와 팀 6명/큐 36개/작업 ID 110개 정합성이 통과했다. 독립 재검토와 실제 연결 관문은 남아 있다.
