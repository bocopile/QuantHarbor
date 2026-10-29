# 시장 자료 구현 계약 v1 — Q17

상태: root 채택, Q17 구현·독립 검토 전. Q12의 data-v1/serialization-v1을 구체화하는 추가 명세다. baseline 7파일과 기존 네 기본형의 bytes/hash 규칙은 변경하지 않는다. 실제 자료·공급자 권리는 SG-02 미완료이며 이 구현의 환경은 synthetic만 허용한다.

## 자료와 재관측

| 타입 | 필수 의미와 고정 필드 |
|---|---|
| MarketRevision | schema_version, environment, source_id, dataset_id, series_id, event_id, revision_id, predecessor_revision_id(nullable), revision_kind, effective_at, published_at(nullable), publication_unknown_reason(nullable), normalization_version, payload |
| MarketObservation | schema_version, environment, observation_id, revision의 고정 identity와 canonical hash, observed_at, ingested_at, source_content_sha256, evidence_ref, rights_ref, catalog_version, calendar_version |
| MarketEnvelope | data-v1의 envelope_id, schema_version, source_id, dataset_id, dataset_version, environment, queried_scope, items, as_of, observed_at, ingested_at, quality, rights_ref, content_hash, lineage_refs |
| DatasetManifest | schema_version, environment, dataset_id, dataset_version, previous_version(nullable), normalization/canonical 버전, source/coverage, 파일 목록과 bytes/hash/행 수·논리 record-set hash, 품질/권리 refs, created_at |

구현의 정확한 JSON key·고정 typed decoder는 해당 dataclass와 함께 명시한다. nullable 필드는 누락으로 대체하지 않는다. record의 문자열·정수·목록 크기를 제한하고 알 수 없는 필드·enum·버전·중복 JSON key·bool-as-int를 거부한다. 임의 dict payload나 호출자 지정 hash 제외 필드는 없다.

원천 사실 identity는 environment/source/dataset/series/event이며 revision_id를 더해 사실 개정을 식별한다. 동일 revision의 **정규화 사실**이 같으면 duplicate, 다르면 conflict다. 관측·수집 시각과 원문 bytes가 바뀐 재수집은 별도 MarketObservation으로 남기며 같은 사실을 충돌이나 새 경제 사건으로 만들지 않는다. 원문 hash 변화만으로 정정을 확정하지 않는다.

revision_kind는 original/replacement/retraction/unsupported다. original은 선행 참조가 없고 나머지는 명시한 선행 관계를 검사한다. replacement는 전체 교체 의미만 지원하며 delta 의미를 추정하지 않는다. opaque revision 문자열을 정렬해 최신을 판단하지 않는다. 선행 누락·fork·순환·identity 불일치·정정 의미 불명은 보류/충돌이다. retraction은 tombstone으로 보존하고 삭제하지 않는다. 미지원 자료는 정상 가격·FX·기업행동으로 적용하지 않는다.

## payload

- PriceBar: 종목·상장/체결 venue·통화/수량 단위, bar 시작/끝, OHLC의 정확한 Price, volume의 Quantity 또는 명시 unknown/사유. 가격 양수·동일 단위·high/low 범위·volume 비음수·시각 구간을 검사한다. float를 거치지 않는다.
- adjustment는 raw/adjusted다. raw에는 조정 메타데이터를 섞지 않는다. adjusted에는 방식·버전·기준시점·관련 action refs와 지식 근거가 필요하다. 다른 조정 series를 대체하거나 미래 action으로 과거 평가를 몰래 바꾸지 않는다.
- FXObservation은 기존 FX의 base/quote/rate/as_of/source를 재사용한다. 동일 통화쌍의 양 방향은 별개다. 자동 역수·대체·반올림·실제 환전은 없다. 동일 통화의 환율은 이 경로에서 거부한다.
- CorporateAction은 split/cash_dividend부터 지원한다. split은 정확한 양수 분자/분모와 수량 단위, cash_dividend는 주당 Money·수량 단위다. 효력·권리/기준·지급 날짜는 서로 다른 필드이며 없는 값은 명시 unknown이다. 관측을 계좌 현금·수량 변화로 자동 적용하지 않는다.
- 실제 market/venue·분류·시점 검사는 Q16 catalog와 검증된 달력 경로에 연결한다. 조회할 수 없는 종목/세션·부적합 분류를 임의로 생성하지 않는다. 합성 매핑/달력 시험은 실제 source capability 검증이 아니다.

## 수집과 완전성

순수 reduce_page/merge_revision와 application의 fetch/store port를 분리한다. 현재 fetch 구현은 합성 page adapter만 제공한다. domain에서 파일·네트워크·sleep·현재시각을 읽지 않는다. 평가시각·정책·catalog/calendar·기존 상태는 입력으로 전달한다.

PageResult는 request/scope·입출력 cursor·terminal·status·items·source snapshot 또는 관측구간·오류분류를 명시한다. 요청 범위의 record만 받아들이며 페이지/요청 수·응답 bytes·record 수·deadline에 명시 상한을 둔다. 반복 cursor·범위 혼선·중복 식별자 충돌·정규화 실패는 실패 상태로 남는다. rate limit은 not_before와 중단 상태를 반환하며 자동 재시도·sleep은 0회다.

정상 terminal만으로 complete를 만들지 않는다. 모든 페이지 성공·scope 충족·필수 정보·cursor 종료와 expected coverage를 확인한다. 과거 실패를 빈 마지막 page로 지우지 않는다. 이미 받은 유효 record는 보존할 수 있으나 결과는 partial이다. 성공한 빈 조회, 미수집, 누락 자료, 명시 휴장을 구분한다. 다음 요청의 재수집은 revision 멱등 병합 후 **새 dataset version**을 만든다.

수집 완전성과 자료의 시간 일관성은 별개다. source snapshot이 없는데 일관된 원자 스냅샷으로 표시하지 않는다. 기대 봉/구간은 명시 입력과 Q16 달력 근거로 확인하며 봉 부재를 휴장으로 추정하지 않는다.

## 시점·품질·권리

as_known은 effective_at <= as_of와 관측·수집·확인 가능한 발표 시각이 knowledge_cutoff 이하인 사실만 선택한다. 발표시각이 없으면 과거 공개 가능성을 수집 시각으로 채우지 않는다. 확인되지 않은 PIT 입력은 미검증으로 보존하고 검증된 과거 평가에 제공하지 않는다. 잘못된 observed/ingested 순서·미래시각도 실패한다.

restated는 명시한 더 늦은 knowledge_cutoff로 재선택한 별도 view/manifest다. 원래 자료나 결과를 덮지 않는다. 알려진 미래 효력 사건을 효력 전에 가격·수량 변환에 적용하지 않는다. 정정은 같은 사건의 교체이며 이중 적용하지 않는다. 선행 누락·fork·tombstone·충돌이 있는 chain을 정상 최신값으로 승격하지 않는다.

QualityResult는 complete/partial/unavailable/invalid, missing scope·이유, freshness=fresh/stale/unknown과 평가시점/정책 참조를 분리한다. 허용 지연값이 미정이면 unknown이며 분석15분을 신선도 정책으로 쓰지 않는다. stale·unknown·partial·invalid·권리 차단 자료는 신규 위험 증가 판단에 사용할 수 없다. 실제 주문 제어와의 연결은 후속 단계다.

RightsGrant는 환경/source/dataset·버전·목적(store/research/ai/report)·유효 구간·철회를 명시한다. 현재 fixture도 synthetic 권리를 갖는다. write 전과 현재 read/use 시점에 현행 권리를 재검사하며, 옛 manifest의 허용 이력만으로 만료·철회를 무시하지 않는다. 실제 권리의 발급/승인이나 외부 공급자 권한을 구현한 것으로 주장하지 않는다. paper/live 입력과 실제 fetch는 차단한다.

## canonical 확장

MarketRevision/MarketObservation/MarketEnvelope/DatasetManifest와 필요한 고정 record-ref 집합 스키마만 additive 등록한다. 스키마별 recursive typed decoder로 nested payload·환경 일치·필드 집합·유일 ID를 검사한다. 기존 Money/Quantity/Price/FX의 golden bytes/hash와 거부 규칙은 불변이다.

envelope의 content_hash는 고정 record-ref 집합(사실/관측 identity와 canonical hash)의 canonical hash로 정의한다. 집합은 명시 stable identity 순으로 정렬하고 중복을 거부한다. envelope 자체 hash는 객체 밖에 둔다. 원문 파일 bytes hash, Parquet bytes hash, 각 typed record의 canonical hash는 서로 다른 근거다.

parser 64KiB 상한을 늘리지 않는다. bounded record/chunk와 manifest로 표현하며 상한을 넘으면 분할 또는 명시 거부한다. 페이지 순서 등 의미 있는 배열은 순서를 보존한다. 새 스키마의 등록과 기존 기본형 회귀를 함께 검토한다.

## Parquet 영속 저장 — Q17B

Q17A의 순수 계약/수집/품질 검토 이후 저장 adapter를 구현한다. PyArrow는 SG-03 고정 배포·고지/플랫폼/호환 확인 후 저장 환경에만 도입하고 domain에서 import하지 않는다. 금융 업무 PostgreSQL 드라이버는 Q17에 도입하지 않는다.

고정 Arrow schema를 사용하고 금융값은 검증된 decimal128(38,18), UTC는 microsecond로 저장한다. 명시 nullable·단위/조정/버전을 보존한다. 재읽기 후 canonical 정규형과 hash를 대조해 반올림·형변환을 탐지한다. 압축/파일 bytes의 변화와 논리 자료 동일성은 별도 검사다.

단일 writer, immutable version 경로, no overwrite, no symlink/탈출을 적용한다. 데이터 파일을 임시 작성→검증→fsync하고 manifest를 마지막에 원자적으로 공개한다. reader는 directory glob 대신 완성 manifest가 열거한 고정 파일만 읽는다. 파일 hash·행 수·스키마·record hash·권리를 확인한다. crash orphan은 미공개이며 자동 성공으로 처리하지 않는다. 동일 version 동시 생성은 conflict다.

완료 증거는 디스크 기록 후 프로세스 종료·새 프로세스 재읽기에서 형/값/hash/PIT 일치, 실패/부분 commit 비노출, 기존 제품 회귀다. 실제 데이터 수집·시장 성능·운영 보존정책·실계좌 대사·금융 원장 완료를 의미하지 않는다.

## Q17A 독립 검토 보완 — 2026-10-24

- 기업행동 effective_at은 명시 Q16 timezone의 effective_date에 속해야 한다. 이를 확인하지 않은 원시 PIT 선택은 검증된 사용 가능 view가 아니다. 원시 선택과 context 검증 진입점을 분리하고, 품질의 위험 사용 가능 판정은 검증 경로만 소비한다.
- 조정 근거는 정확한 action identity와 종목·상장/체결 venue·수량 단위를 결속한다. 해당 action의 발표/관측/수집 시점은 adjustment.knowledge_at 이하, 효력은 basis_at 이하이어야 한다. 후일 조회시각을 과거 조정 근거 시각으로 대체하지 않는다.
- page.received_at은 평가시각 이하이고 페이지 간 역행하지 않아야 한다. 실제 I/O timeout과 별개의 순수 입력 검사다.
- 충돌 인지시각은 양쪽 사실이 알려진 가장 이른 시점으로 결정한다. 기존 재관측 및 충돌 incoming 전체 근거에 대해 입력 순서가 달라도 동일 cutoff 결과를 낸다. 더 이른 재관측이 나중에 추가된 경우도 다시 계산한다.
