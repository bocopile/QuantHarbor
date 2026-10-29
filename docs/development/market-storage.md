# Q17B 저장 환경과 검증

2026-10-24: 저장 어댑터·회귀 구현과 자체 검증을 마쳤다. root 디스크 환경 통합 및 독립 검토·검증은 진행 중이며 실제 자료 권리 SG-02는 미완료다.

고정 Python3.13.17 Linuxarm64 이미지에 PyArrow26.0.0 wheel을 오프라인 설치한다. [별도 lock](../../config/market-storage-lock.json), [Dockerfile](../../containers/Dockerfile.market-storage), [요구 파일](../../containers/requirements.market-storage.txt)은 공개 품질 검사가 정확히 대조한다. 기본 pyproject/Q13 기반 및 Q14 연구 실행기의 의존성·자원 한도는 변경하지 않는다.

공식 PyPI wheel을 저장소 밖에 준비하고 lock의 bytes/hash가 일치하는 경우에만 다음 검증기를 실행한다. 검증기는 다운로드하거나 host Python에 설치하지 않는다.

```sh
python3.13 -I -S scripts/check_market_storage.py --wheel /absolute/private/path/to/pyarrow-26.0.0-cp313-cp313-manylinux_2_28_aarch64.whl
```

검증기는 지정한 wheel과 Git 공개 후보 중 허용된 소스만 임시 build context로 복사한다. 내용 읽기 전에 Git ignore(전역 제외 포함)·보호 경로·고정 필수 파일 집합을 확인하며 private 하위 디렉터리를 순회하지 않는다. 파일은 nonblocking/no-follow·정규파일 검사 후 읽으므로 FIFO를 거부한다. 기존 Docker 설정은 context 이름·local Unix endpoint 선별 조회에만 쓰고, 실제 build/run에는 빈 HOME/Docker설정과 제한된 환경을 준다. 네트워크 없는 build에서 hash-pinned wheel만 설치하고 포함된 LICENSE/NOTICE를 유지한다. 실행은 network none, host bind mount 없음, 자기 UUID local named volume만 /store에 연결, read-only, uid10001, cap drop, no-new-privileges, memory512MiB/cpu1/pids64/tmp64MiB다. trusted 개발 검증 코드용이며 Q14의 untrusted 연구 실행기를 대체하지 않는다.

정확한 decimal/UTC 시각의 파일 기록 프로세스와 새 읽기 프로세스, 전체 제품 테스트, 저장 전용 테스트를 수행한다. 현재 준비 단계에서 저장 테스트가0개인 결과는 라이브러리 호환만 의미한다. 최종 Q17B 판정은 저장 테스트의 실제 개수와 독립 검토·검증 증거를 요구한다.

정상 종료에서는 자신의 UUID/label과 일치하는 container/volume/image만 제거하고 부재를 재확인한다. 전역 prune이나 사용자 container·image 정리는 하지 않는다. controller 강제 종료 시 자동 정리 보장은 없으며 남은 labelled 자원은 별도 확인해야 한다. 오류 출력에는 원시 Docker 환경/daemon 메시지를 노출하지 않는다.

확인 결과는 [저장 환경 증거](../evidence/data-storage-runtime-2026-10-24.json), 의존성 근거는 [공식 출처](../evidence/data-storage-official-sources-2026-10-24.json)에 있다. 실제 자료·금융 원장·운영 보존정책·실계좌 대사 검증은 아니다.

## Q17B 구현 — 2026-10-24

앞 절은 의존성 준비 당시 기록이다. 현재 구현은 `domain/market_storage.py`, `application/market_ingest.py`의 trace/replay와 `adapters/parquet_market_store.py`다. 실제 공급자·권리 발급·금융 원장·운영 서비스는 제공하지 않는다.

`ingest(...).bundle`은 descriptor, ordered receipts, 전체 `state.revisions.evidence`, state/envelope, expected summary를 담는 불변 `StorageBundle`이다. `ParquetMarketStore(existing_private_root, source_id=..., dataset_id=...)`를 context manager로 열고 `write(bundle, rights=현재권리, at=명시시각, catalog=..., calendar=..., timezone=...)`로 저장한다. source/dataset/version에 대한 현재 store 권리를 먼저 검사한다. writer는 descriptor/receipts/full evidence를 다시 재생해 supplied state·envelope·summary와 비교한 다음 파일을 작성한다. `previous_version`을 쓰면 같은 저장소의 완성 manifest가 존재해야 한다.

`read(version, rights=..., at=..., limits=현재신선도정책, catalog=..., calendar=..., timezone=..., purpose=...)`는 현재 목적별 권리를 파일 열기 전에 확인한다. manifest가 명시한 파일만 읽고 hash·행 수·고정 스키마·canonical/typed 값과 receipt 재생·summary를 대조한다. `StorageReadResult.historical`은 당시 결과이고 `current_view/current_quality`는 현재 권리·시각·정책으로 다시 판단한 결과다. 과거 fresh를 현재로 복사하지 않는다. `as_of/knowledge_cutoff/view_mode/original_cutoff`를 명시해 새 PIT/restated view를 얻을 수 있으며 기존 파일은 수정하지 않는다.

context는 현재 별도 저장하지 않는다. caller가 제공하는 catalog/calendar/timezone는 descriptor의 **exact historical source-facts digest**와 일치해야 한다. 동일 version의 값 변경도 거부한다. 새 catalog/calendar version으로 기존 bundle을 바로 읽는 기능은 없다. historical replay와 다른 context로 migration하는 서비스는 후속 범위다. context digest는 고정 typed source facts의 별도 SHA256이며 등록 canonical hash나 실제 자료 진위 증명으로 쓰지 않는다. timezone digest는 명시 TZif content hash와 metadata에 결속된다.

## 저장 스키마와 제한

기존 다섯 시장 스키마를 유지하고 `MarketStorageManifest`, `MarketIngestDescriptor`, `MarketPageReceipt`, `MarketEvidenceIndex` 네 개만 추가 등록했다. top-level key는 `market-storage-v1` 표와 같으며, schema_version은 정수1, environment는 synthetic이다. nullable key도 생략할 수 없다. 고정 버전은 storage=`market-evidence-v1`, reducer=`market-reducer-v1`, canonical=`qh-canonical-json-v1`이다.

| 중첩형 | 정확한 key |
|---|---|
| ClaimRef | revision_hash, observation_hash |
| ContextRef | kind, context_id, version, sha256 |
| FileRef | role, name, size_bytes, sha256, row_count |
| ConflictSummary | kind, left, right, detected_at |
| ReplaySummary | pages, bytes_received, records_received, next_cursor, seen_cursors, errors, terminal, snapshots, snapshot_missing, not_before, last_received_at, accepted_record_set_hash, evidence_index_hash, conflicts, quality |
| FetchRequest | request_id, environment, source_id, dataset_id, dataset_version, scope, started_at, deadline, knowledge_cutoff |
| QueryScope | series_ids, starts_at, ends_at, expected, coverage_kind, coverage_ref |
| ExpectedEvent | series_id, event_id, effective_at |
| IngestLimits | max_pages, max_bytes, max_records, max_age_seconds, policy_ref |
| RightsGrant | rights_ref, environment, source_id, dataset_id, dataset_version, purposes, valid_from, valid_to, revoked_at |

QualityResult는 Q17A의 고정형을 재사용한다. ConflictSummary.left/right는 ClaimRef다. request/limits/권리/context refs도 recursive typed decoder가 복원하며 임의 dict·동적 스키마·pickle은 없다.

전체 evidence index는 `(revision_hash, observation_hash)` 순으로 정렬하고 같은 쌍을 중복 저장하지 않는다. 같은 observation ID의 상충 내용도 별도 claim으로 보존한다. accepted RecordRefSet hash는 full evidence index hash와 구분한다. 페이지 item_refs는 순서·반복을 유지하며 중복 수신 count와 evidence deduplication은 별개다.

각 canonical 객체는64KiB, evidence128, page attempts16 한도를 유지한다. evidence 파일은 최대4개·파일당32행·4MiB, descriptor/receipt 파일은 각64KiB, bundle 파일 합계는20MiB 이하다. 큰 객체는 명시 거부하며 parser 한도를 늘리지 않는다. 파일명은 경로 없는 제한 ASCII basename과 고정 json/parquet 확장자이며, version은 최대64자 ASCII 영숫자/underscore/hyphen이다.

Parquet의 정확한 열은 다음과 같다. schema metadata는 `quantharbor.storage=market-evidence-v1`로 고정한다.

- non-null binary: revision_bytes, observation_bytes
- non-null string: revision_hash, observation_hash, payload_kind
- UTC timestamp microseconds: effective_at, observed_at, ingested_at(non-null), published_at(nullable)
- nullable decimal128(38,18): open, high, low, close, volume, fx_rate, split_numerator, split_denominator, cash_per_unit
- nullable string: instrument_id, listing_venue_id, execution_venue_id, currency, quantity_unit, base_currency, quote_currency, adjustment

canonical bytes에는 모든 단위·날짜·조정 metadata가 있고 typed column은 그 값과 이중 대조한다. float·암묵 추론·timestamp truncation·decimal 반올림을 쓰지 않는다. PyArrow26.0.0만 허용한다. read는 최대2 row group/파일, group당16행, batch16행, flat schema depth4·제한 thrift metadata를 사용한다. full Arrow validation과 page checksum을 확인한다. 고정 UNCOMPRESSED만 허용하고 선언된 비압축 크기도 group4MiB/파일8MiB로 제한한다. extension/KMS/외부 filesystem은 사용하지 않으며 모든 Parquet 입력은 검증한 로컬 FD에서 읽은 bounded bytes다.

## receipt 재생과 생략 경계

실제 `PageResult.response_bytes`는 `page_facts`가 길이/SHA256으로 바꾸고 `reduce_page_facts`로 전달한다. receipt도 같은 core를 사용한다. 재생용 가짜 bytes를 만들지 않는다. raw response bytes는 저장하지 않으므로 원문 재파싱·원문 진위를 검증했다고 주장하지 않는다.

- `kind=page`: typed items를 claim refs로 저장하고 길이/hash 사실로 완전히 재생한다. success/failed/rate_limited/normalization_failed를 구분한다.
- `kind=rejection`: core가 본문을 받기 전에 거부한 입력이다. item_refs는 비우고 제한된 metadata/고정 사유만 보존한다. request/scope/cursor/clock 거부는 metadata로 재생한다. byte/record/record-scope/normalization 거부에서 생략한 본문은 재검증할 수 없으며 bounded rejection claim으로 남긴다. 이 실패를 정상 수집으로 승격하지 않는다. scope/future record가 섞인 페이지는 전체 본문을 거부하며 이전 페이지는 보존한다.
- `kind=fetch_failure`: 원시 예외 대신 고정 `fetch_or_normalization_failed`를 남긴다. 네트워크·sleep·자동 재시도는 없다.

ordinal 연속성과 stop 상태를 검사한다. 허용된 수집인데 receipt가 없거나 terminal/실패/한도 없이 trace가 끝나면 잘린 trace로 거부한다. 누락/남는 claim, 순서/요청 혼선, supplied summary/state 불일치도 거부한다. raw 길이/hash는 관측 주장일 뿐이다. 현재 실제 fetch는 여전히 합성 adapter만 허용한다.

## 파일 경계와 crash 의미

root는 caller가 제공한 기존 private directory이며 소유 UID·0700을 검사한다. 경로의 각 디렉터리를 directory FD와 no-follow로 열고 version directory도0700, 파일/지속 writer lock은0600·현재 UID·정규 파일·link count1을 요구한다. reader/writer는 root 권한도 다시 확인한다. symlink·hardlink·경로 탈출·동일 version overwrite를 거부한다. flock은 nonblocking 단일 writer이며 lock inode를 지워 stale 잠금 경합을 만들지 않는다.

파일을 exclusive 생성→재검증→fsync하고 directory도 fsync한 뒤 manifest를 마지막에 no-overwrite hard link로 공개한다. pending link를 지운 후 directory를 fsync한다. link 직후 crash로 pending/manifest 두 이름이 남으면 link count2여서 reader가 **fail closed**한다. 자동 복구 성공으로 표시하지 않는다. manifest 전 crash orphan도 비공개이며 같은 version 재시도는 conflict다. 현재 자동 orphan 복구/삭제 기능은 없다.

동일 사용자/관리자가 저장 파일과 manifest를 모두 바꾸는 공격에 대한 인증이나 전자서명을 제공하지 않는다. fsync 호출을 확인하는 것과 전원 장애 내구성 실험은 다르며 power-loss 검증은 수행하지 않는다.

## 구현 검증 범위

`tests/product/test_market_storage.py`는 Arrow 없이 고정 스키마·reducer facts·완전/실패/거부 trace·전체 conflict evidence·context digest를 확인한다. `tests/storage/test_parquet_market_store.py`는 별도 저장 런타임에서만 PyArrow를 import한다. tempfile/TMPDIR를 따르며 host bind mount나 실제 개인 자료를 읽지 않는다.

실제 adapter의 writer process 종료 후 새 reader process에서 rich 가격/FX/기업행동/조정 자료와 revision/observation-ID conflict의 전체 state·summary·manifest hash·과거 cutoff 결과를 비교한다. 현재 권리 철회/만료/목적 차단과 fresh→stale, 파일/receipt/typed/schema/행 수 변조, 부분 재수집 version, crash orphan/link window, flock, symlink/hardlink/권한도 확인한다. 초기 harness의 TMPDIR는 tmpfs이므로 해당 실행은 프로세스 간 파일 재읽기 증거이며 물리 디스크/power-loss 보장이 아니다. named volume 기반 최종 디스크 재현은 root 통합·독립 검증에서 별도로 기록한다.

## 최종 디스크 검증 환경

root 통합 검증기는 자기 UUID·label의 새 local Docker volume을 /store에 연결한다. 컨테이너의 uid10001·0700과 TMPDIR=/store를 검사하며 /tmp tmpfs와 다른 장치임을 확인한다. 제품104개 이상·저장1개 이상을 요구하고 실제 개수를 출력한다. 종료 후 자기 container→volume→image를 정리하고 UUID별 부재를 확인한다. Docker 호스트 파일시스템에서 새 프로세스 재읽기를 검증하며 전원 장애 내구성·물리 장치 속성을 보장하지 않는다. 지정 wheel은 정확한 basename부터 확인하고 size/hash를 검증한다.

## 일반 검토 R5/R6 보완 — 2026-10-24

생략된 본문의 rejection에도 공통 reducer로 보존된 request/scope/cursor/receipt 시각을 검사한다. metadata의 실제 실패 사유가 receipt와 일치해야 하며, metadata 오류를 body 한도 사유로 바꿔 숨길 수 없다. 정상 metadata를 통과한 뒤에만 생략한 body 기반 거부를 제한된 실패 주장으로 남긴다. 원문 재파싱 불가 한계는 그대로다.

저장 harness는 정확한 wheel basename·nonblocking 정규 파일·길이/hash 경계를 먼저 검사한 후 Docker 실행 파일을 찾는다. Docker 없는 PATH의 FIFO/잘못된 이름·hash 회귀는 실제 Docker 호출 없이 입력 오류를 판정한다. 기존 Git 공개후보·dirfd·고정 label·자기 volume 경계는 유지한다.
