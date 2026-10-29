# 시장 자료 영속 저장 계약 v1 — Q17B

2026-10-24 root 채택, 구현·독립 검토 전. Q17A의 다섯 등록 스키마 및 Q12 baseline은 유지한다. 기존 DatasetManifest는 accepted projection 형식이며 Q17B의 저장 진입점은 새 MarketStorageManifest다. 실제 공급자·자료 권리 SG-02는 미완료다.

## 고정 스키마와 근거

| 등록 스키마 | 필드와 의미 |
|---|---|
| MarketStorageManifest | schema_version, environment, source_id, dataset_id, dataset_version, previous_version, created_at, storage_schema_version, reducer_version, canonical_version, descriptor_file, receipt_files, evidence_files, evidence_count, evidence_index_hash, accepted_record_set_hash, replay_summary |
| MarketIngestDescriptor | schema_version, environment, request, limits, evaluated_at, view_mode, original_cutoff, catalog_ref, calendar_ref, timezone_ref, rights_ref, historical_rights_snapshot |
| MarketPageReceipt | schema_version, environment, ordinal, kind, request_id, scope, cursor_in, cursor_out, terminal, status, source_snapshot, received_at, error_reason, not_before, response_size_bytes, response_sha256, item_refs |
| MarketEvidenceIndex | schema_version, environment, claims |

claims와 item_refs의 고정 ClaimRef는 revision_hash/observation_hash의 쌍이다. index는 두 hash 순으로 정렬하고 같은 쌍을 중복 저장하지 않는다. 페이지 item_refs는 순서·반복을 유지한다. 같은 observation ID라도 상충한 hash는 별개 evidence다. 기존 RecordRefSet을 full evidence index로 전용하지 않는다. index는 별도 등록한 canonical hash를 사용한다.

request/limits는 Q17A FetchRequest/IngestLimits와 expected scope를 그대로 중첩 복원한다. context_ref는 ID/version과 supplied context digest를 결속한다. datetime/decimal/tuple을 고정 typed 규칙으로 인코딩하고 임의 dict·pickle·동적 schema 등록은 없다. context 자체는 reader에게 명시 제공하며 이번 단계에 별도 catalog 저장 서비스를 만들지 않는다. 과거 RightsGrant는 당시 판단 재현용이며 현재 권한을 부여하지 않는다.

FileRef는 role/name/size_bytes/sha256/row_count(nullable)를 갖고 이름은 단일 제한 basename이다. ReplaySummary는 state.revisions 외의 IngestState 필드, accepted refs hash, full evidence index hash, derived conflicts의 typed 요약, 최종 QualityResult를 결속한다. 정확한 nested key와 nullable 의미를 구현 개발 문서에 고정한다. schema/reducer/storage 버전은 정적 상수이며 알 수 없는 값은 거부한다.

각 canonical 객체는 기존64KiB 이하다. evidence128·page attempts16 등 Q17A 한도를 유지하고 저장 bundle 전체에도 명시 hard bound를 둔다. 실제 인코딩 크기가 넘으면 명시 거부하며 parser 상한을 늘리지 않는다.

## 수집 기록과 재생

ingest 결과에 bounded trace 또는 StorageBundle을 추가한다. descriptor, ordered receipts, complete accepted/rejected-conflict evidence, expected summary를 함께 전달한다. fetch 실패는 고정 reason만 기록하며 원시 예외를 저장하지 않는다.

정상/부분/failed/rate-limited/normalization-failed 및 수신시각·scope·cursor/한도 거부 근거를 보존한다. raw response는 길이와 SHA256만 남길 수 있다. 원문 재파싱/정규화 검증을 완료했다고 주장하지 않는다. raw bytes에서 facts를 만드는 실제 경로와 저장 receipt 경로는 같은 순수 reducer core를 사용하며 가짜 길이의 bytes를 만들어 재생하지 않는다.

거부되기 전 본문을 받아들이지 않은 입력은 제한된 rejection receipt로 보존한다. 거부 본문 전체를 저장해 한도를 우회하지 않는다. 생략된 본문에 대한 재파싱은 불가능하다는 한계를 명시하고 해당 실패 상태를 성공으로 승격하지 않는다. 수신 record 수는 중복을 포함하며 evidence 중복제거와 별개다.

writer는 receipt 재생·전체 evidence 기반 conflict 재구성으로 supplied state/summary/accepted projection을 확인한 뒤 저장한다. 다른 요청·결과를 조립한 bundle, 누락/남는 참조·순서 혼선은 거부한다. reference-only 자료의 bytes 길이/hash는 관측 주장이고 원본 진위를 증명하지 않는다.

## Parquet와 공개 원자성

evidence Parquet는 전체 claim pair를 저장한다. 고정 스키마에 MarketRevision/MarketObservation canonical bytes와 대응 금융 typed column을 함께 두고, 금융값은 decimal128(38,18), 시각은 UTC microseconds, 명시 nullable/단위를 보존한다. 읽을 때 typed column과 canonical 객체의 값/형식/hash가 모두 같아야 한다.

파일 bytes/row group/행 수/schema/개별 canonical 크기·metadata 깊이·문자열 개수를 제한하고 bounded batch로 읽는다. full Arrow validation, no custom extension/KMS/원격 filesystem, no float 추론·truncation을 적용한다. 메모리/실행시간 제한은 별도 고정 컨테이너 경계도 사용한다.

단일 writer, private root, directory FD/no-follow, 제한 basename, immutable version을 사용한다. 데이터·descriptor·receipts를 임시 작성/재검증/fsync한 뒤 manifest를 마지막에 원자 공개한다. 기존 version은 덮어쓰지 않는다. reader는 완성 manifest가 지정한 파일만 열며 glob·symlink·경로 탈출·비정규 파일을 거부한다. manifest 없는 orphan은 완료 자료가 아니다. 같은 호스트 관리자/동일 사용자 공격에 대한 격리나 manifest 자체의 전자서명을 제공하는 것은 아니다.

## 현재 사용과 완료 기준

read는 현재 목적별 RightsGrant·평가시각·신선도 정책·Q16 context를 받는다. 먼저 현재 권리를 확인하고 bytes/hash/typed decoder·receipt 재생·full evidence 파생 상태/summary를 대조한다. 당시 결과와 현재 application 검증 view/품질을 구분해 반환하며, 과거 fresh/권리 허용 상태를 현재로 복사하지 않는다. cutoff/view mode 변경은 새 조회 결과이며 저장 버전을 수정하지 않는다.

실제 adapter를 통해 writer process 종료→새 reader process에서 정확 값/형식/hash/PIT/충돌 상태가 같아야 한다. 기업행동/FX/조정 가격, observation-ID/revision 충돌·늦은 재관측, failed/rejected receipt, partial 재수집, 권리 철회·fresh→stale, 변조·누락·참조/row/schema 불일치, overwrite/symlink·중간 crash 비공개를 검증한다. 별도 runtime preflight 성공만으로 Q17B 완료 처리하지 않는다.
