# Q17A 합성 시장 자료

구현·확인 기준일: 2026-10-24. 추가 입력 계약은 `market-data-v1`이다. Q12 기준 7파일과 기존 네 기본형은 변경하지 않았다. 실제 자료·권리 SG-02와 Parquet 영속 저장 Q17B는 미완료다.

## 진입점과 경계

- `market_data.merge_revision(state, item)`: 같은 사실 개정의 정규형은 duplicate, 다른 정규형은 conflict다. 다른 관측 ID·원문 hash·관측/수집 시각은 재관측으로 보존한다. 원문 hash와 canonical hash는 별개다.
- `market_data.select_raw_view(...)`: Q16 context를 확인하지 않은 원시 PIT이며 `context_validated=False`다. `as_of`, `knowledge_cutoff`, 현재 권리 검사 시각 `at`을 모두 전달한다. 발표·관측·수집 시각이 cutoff 이하이고 효력이 도래한 사실만 선택한다. 발표시각 불명, 선행 누락·fork·cycle·identity 변경·tombstone·미지원 개정은 보류한다. revision 문자열을 정렬하지 않는다.
- `application.market_ingest.select_view(...)`: 사용 조회 진입점이다. 원시 선택 뒤 Q16 calendar/TZif binding·종목/venue/단위와 기업행동의 현지 효력 날짜를 확인한다. context에 맞지 않는 action을 제거한 뒤 adjustment 근거도 다시 확인한다. 반환 `ValidatedMarketView.context_validated=True`는 검사를 수행했다는 뜻이며 개별 보류 사유와 selected를 함께 소비한다. `ingest`의 위험 사용 가능 판정은 이 경로만 소비한다. domain에 `select_view` 우회 alias는 없다.
- `mode="restated"`는 더 늦은 cutoff와 `original_cutoff`를 명시해야 한다. 불변 원래 상태·버전을 덮지 않는다. 재관측 대표는 가장 이른 수집/관측/ID 순으로 정해 페이지 순서에 의존하지 않는다.
- `RevisionState.evidence`는 양쪽 사실·모든 재관측을 보존한다. 사실 충돌은 각 정규화 사실의 가장 이른 이용 가능 관측을 전체 evidence에서 골라 `detected_at=max(양쪽의 가장 이른 ingested_at)`으로 결정한다. 늦게 합류한 더 이른 재관측도 매 merge 때 다시 계산한다. observation-ID 충돌은 서로 다른 두 observation claim의 가용 시각으로 계산하며 양쪽을 보존한다. conflict에는 kind/incoming/counterpart/keys/detected_at이 있다. accepted items 투영과 원시 PIT는 별개이며 원시 PIT는 전체 evidence를 사용해 삽입 순서가 과거 결과를 바꾸지 않는다. 현재 충돌은 관련 identity를 보류한다. 과거 dataset version 자체도 보존해야 한다.
- `validate_market_context(...)`: Q16 catalog의 시장/분류/시점·통화·상장/체결 venue와 명시 timezone에 결속된 달력을 검사한다. 가격 봉 전체가 한 정규 세션 안에 있어야 한다. 기업행동 날짜를 거래 세션으로 추정하거나 계좌에 적용하지 않는다. FX는 종목 세션 자료가 아니므로 기존 FX의 방향·출처·시각을 검사한다.
- `application.market_ingest.ingest(...)`: 현재 정확히 `SyntheticPageAdapter`만 받는다. 실제 공급자 어댑터는 활성화되지 않는다. fetch/store 포트 정의와 `SyntheticMemoryStore`는 영속 저장 완료를 의미하지 않는다.

## 수집·품질·권리

요청은 source/dataset/version, 고정 scope, 명시 시작·deadline·cutoff를 가진다. `QueryScope.expected`는 series/event/effective_at의 명시 기대 집합이다. 미수집, 기대 자료 누락, 확인된 빈 조회, 명시 휴장, coverage 불명을 구분한다. `explicit_closed`는 동일한 Q16 명시 휴장일에 속하는 범위인지 확인한다. 봉 부재나 terminal만으로 휴장을 만들지 않는다.

기본 상한은 페이지8·응답누적64KiB·수신 record64다. 설정 가능한 hard 최대는 페이지16·누적1MiB·record128이다. 중복 record도 수신 한도에 센다. bytes는 실제 합성 응답 길이와 typed 정규화 bytes 중 큰 값을 누적한다. scope/cursor 혼선·반복 cursor·미래 관측·deadline·한도·정규화 실패는 중단한다. 유효하게 받은 항목과 sticky 오류는 보존하며 빈 마지막 페이지가 오류를 지우지 않는다. rate limit은 `not_before`를 반환하고 재시도/sleep은0회다.

시간은 합성 입력이다. `received_at`은 supplied deadline 및 평가시각 이하여야 하고, `IngestState.last_received_at`보다 역행할 수 없다. rejected page는 이전 state를 지우지 않는다. 실제 blocking I/O를 중단하는 타이머를 구현한 것이 아니다. 알려진 cutoff가 수집 시작보다 늦어도 평가 시각 이하이면 당일 수집 PIT로 사용할 수 있다. source snapshot의 consistent/mixed/unknown은 완전성과 별도 lineage로 남긴다. complete가 원자 스냅샷 보장은 아니다.

신선도는 명시 `max_age_seconds` 정책으로 **각 요청 series**의 최신 효력시각을 확인한다. 하나라도 stale이면 전체 stale, 누락/미정 정책은 unknown이다. 분석15분을 정책으로 쓰지 않는다. 수집 coverage가 충족돼도 chain/PIT/context 보류가 있으면 신규 위험 사용 가능으로 승격하지 않는다. `QualityResult.eligible_for_new_risk`는 complete/fresh/권리 허용 조건의 자료 지표이며 실제 주문 권한이 아니다.

`RightsGrant`는 synthetic source/dataset/**dataset version**, 목적(store/research/ai/report), 유효구간과 철회시각을 검사한다. write 전 및 현재 read/use 시점마다 다시 검사한다. 메모리 store의 동일 version 재작성은 거부하며 재수집은 새 version으로 저장한다. 실제 권리 승인·발급 체계는 없다. 실제 계좌·키·네트워크·주문·자동 환산·기업행동 적용은 없다.

## 고정 canonical 스키마

wrapper는 기존과 같은 `schema_name, schema_version, environment, payload`다. schema_version은 정수1이며 Q17 payload/wrapper environment는 synthetic으로 일치해야 한다. nullable key도 반드시 존재한다. 문자열 ID는 기존 ASCII128자 한도, decimal/time은 Q13 기본형 규칙, 배열은 최대128개다. JSON parser와 canonical 출력은64KiB를 넘으면 거부한다. 큰 자료는 후속 chunk/manifest로 나누며 상한을 늘리지 않는다.

신규 등록은 아래 **5개만**이다. 중첩형은 독립 schema로 등록하지 않고 고정 recursive decoder가 복원한다. 알 수 없는 field/version/enum, 중복 JSON key, float/nonfinite, 잘못된 bool-as-int, surrogate, 임의 dict payload를 거부한다. 기존 Money/Quantity/Price/FX bytes·hash·escape와 미등록 OrderCandidate 거부는 유지한다.

| schema | payload의 정확한 key |
|---|---|
| MarketRevision | schema_version, environment, source_id, dataset_id, series_id, event_id, revision_id, predecessor_revision_id, revision_kind, effective_at, published_at, publication_unknown_reason, normalization_version, payload |
| MarketObservation | schema_version, environment, observation_id, source_id, dataset_id, series_id, event_id, revision_id, revision_hash, observed_at, ingested_at, source_content_sha256, evidence_ref, rights_ref, catalog_version, calendar_version |
| RecordRefSet | schema_version, environment, records |
| MarketEnvelope | envelope_id, schema_version, source_id, dataset_id, dataset_version, environment, queried_scope, items, as_of, observed_at, ingested_at, quality, rights_ref, content_hash, lineage_refs |
| DatasetManifest | schema_version, environment, dataset_id, dataset_version, previous_version, normalization_version, canonical_version, source_id, coverage_start, coverage_end, files, record_set, record_set_hash, quality_ref, rights_ref, view_mode, as_of, knowledge_cutoff, created_at |

중첩형의 정확한 key:

| type | key |
|---|---|
| PriceBar | instrument_id, listing_venue_id, execution_venue_id, source_code, starts_at, ends_at, open, high, low, close, volume, volume_unknown_reason, adjustment, adjustment_details |
| Adjustment | method, version, basis_at, action_refs, knowledge_at, evidence_ref |
| ActionRef | environment, source_id, dataset_id, series_id, event_id, revision_id, revision_hash |
| FXObservation | fx |
| CorporateAction | instrument_id, listing_venue_id, execution_venue_id, source_code, action_kind, quantity_unit, effective_date, record_date, payment_date, dates_unknown_reason, numerator, denominator, cash_per_unit |
| MarketItem | revision, observation |
| RecordRef | environment, source_id, dataset_id, series_id, event_id, revision_id, revision_hash, observation_id, observation_hash |
| QualityResult | status, missing_scope, reasons, freshness, evaluated_at, policy_ref, rights_allowed |
| ManifestFile | name, size_bytes, sha256, row_count, record_set_hash |

`PriceBar` OHLC는 Price, volume은 Quantity 또는 명시 unknown이다. raw는 adjustment_details=null, adjusted는 Adjustment를 요구한다. 조정된 view는 ActionRef의 정확한 revision identity와 hash를 사용한다. action은 같은 environment/source/dataset/instrument/listing/execution venue/quantity unit에 속해야 한다. action의 published_at/observed_at/ingested_at은 모두 adjustment.knowledge_at 이하, effective_at은 basis_at 이하여야 한다. 후일 조회 cutoff가 이 과거 근거 경계를 대신할 수 없다. 보류·철회된 action은 유효 근거로 사용하지 않는다. 미확인 action·미래 action을 암묵 적용하지 않는다. 실제 가격 변환을 계산하지 않는다. split은 정확한 양수 numerator/denominator, cash_dividend는 Money이며 효력·기준·지급 날짜를 별도로 보존한다.

`RecordRefSet.records`는 environment/source/dataset/series/event/revision/observation identity 순으로 정렬하고 중복 observation ID를 거부한다. `MarketEnvelope.content_hash`는 이 집합의 canonical hash다. envelope 자체의 canonical hash는 객체 밖에서 계산한다. items의 의미 있는 수신 순서는 유지한다. observation은 revision canonical hash를 참조한다.

Manifest는 경로 없이 제한된 `chunk-name.parquet` 파일명, bytes/hash/row_count/논리 record-set hash를 가진다. 전체 row_count는 observation을 포함한 record ref 수와 일치한다. 파일 bytes hash와 논리 record-set hash는 다르다. 이 단계는 manifest **형식과 참조 검증만** 제공한다. 실제 Parquet schema·파일 검증·원자 공개·새 프로세스 재읽기는 Q17B가 수행해야 한다. 양쪽 충돌·전체 observation evidence와 page clock 상태는 현재 반환 IngestState에 있으며 독립 canonical 저장 스키마는 등록하지 않았다. 실패/충돌 상태의 영속 보존도 Q17B에서 별도 확인해야 한다.

## 검증 범위

합성 자료만 사용한다. 신규 `test_market_data.py`, `test_market_ingest.py`, 독립 검토 실패재현 `test_market_review.py`와 기존 전체 제품 회귀를 실행한다.

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -v
python3.13 -I -S scripts/check_quality.py
```

호스트 실행은 고정 컨테이너 재현이나 독립 검토를 대신하지 않는다. 실제 공급자 capability·시장 자료 권리·운영 보존정책·금융 원장·실계좌 대사는 이 단계의 완료 대상이 아니다.
