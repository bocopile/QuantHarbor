# Q18 합성 문서 계보와 저장

구현·자기 검증 기준일: 2026-10-24. 입력은 [document-lineage-v1](../contracts/document-lineage-v1.md)과 DATA-DEC-002다. 원문 단위의 공시·재무보고·뉴스 추적이며 재무 숫자 추출, 실제 수집·자료 권리 확보, AI 해석 또는 금융 실행 서비스는 아니다. 새 의존성은 없다.

## 사용 경로

`application.document_ingest.collect_documents(...)`에 명시 request/limits/receipt, 합성 originals/claims, entity context, 정확한 Q16 catalog, 현재 RightsGrant와 evaluated_at을 전달한다. 네트워크·현재 시각·retry·sleep은 사용하지 않는다. 반환 `DocumentBundle`은 고유 전체 evidence와 수신 순서·중복을 유지하는 receipt를 함께 보존한다. 미수집은 `not_collected`로 명시하며 빈 성공으로 만들지 않는다.

`domain.documents.select_view(...)`는 현재 목적별 권리와 observation의 rights_ref를 확인하고 cutoff 안의 근거로 chain과 conflict를 다시 만든다. mode는 as_known/restated이며 restated는 original_cutoff < knowledge_cutoff를 요구하고 결과에 보존한다. published_at 불명을 관측/수집 시각으로 채우지 않는다. 나중 정정·충돌은 이전 cutoff 결과를 바꾸지 않으며 opaque revision 이름이나 입력 순서로 최신을 정하지 않는다. 원본·양쪽 상충 내용·observation ID 충돌을 모두 보존한다.

기업·종목 연구 용도는 호출자가 지정한 목적 권리에 더해 현재 research 권리도 요구한다. purpose=store/ai/report로 연구 권리를 대신할 수 없다. 파일 reader는 두 권리를 manifest와 본문을 열기 전에 확인하고, 복원 후 전체 observation의 rights_ref 대조를 유지한다.

조회 목적은 다음과 같이 구분한다.

- `use="preserve"`: 확인 가능한 원시 PIT 선택이다. 기업 연결이 없어도 원문을 보존/조회할 수 있으며 연구 사용 가능으로 표시하지 않는다.
- `use="entity_research"`: exact revision_ref에 연결된 명시 entity/version/evidence와 known_at을 요구한다. 본문·ticker에서 기업을 추정하지 않는다.
- `use="instrument_research"`: instrument_id와 listing_venue_id도 명시한다. issuer 링크의 정확한 catalog/instrument version, venue, 유효구간, known_at과 Q16의 eligible 분류를 cutoff에서 검사한다.

issuer는 발행인 관계다. ETF의 발행인을 ETF 기초자산·보유기업 노출로 해석하지 않는다. 연결이 없거나 미공개·상충·unknown이면 기업/종목 연구 선택을 보류한다. 원문 자체는 bundle에 남는다.

`DocumentView`는 mode/original_cutoff/knowledge_cutoff/evaluated_at, 현재 policy_ref, 완전성·누락·보류와 freshness를 구분한다. receipt가 cutoff보다 늦으면 과거 범위 완전성을 소급 확정하지 않는다. complete는 supplied scope에 대한 확인일 뿐 공급자의 전체 문서 수집을 뜻하지 않는다. 신선도는 현재 명시 평가시각과 max_age_seconds로 다시 계산한다. partial/unknown/context 오류를 fresh로 숨기지 않는다. `usable_for_research`는 검증된 자료 지표이며 투자·주문 승인 권한이 아니다.

## 고정형과 상한

기존 Q13/Q17 형식을 유지하고 다음 다섯 개만 additive 등록했다. top-level과 nested의 정확한 key는 추가 계약의 고정 표와 같고 누락한 nullable key도 거부한다.

| schema | 보존 사실 |
|---|---|
| DocumentOriginal | text/plain, utf-8, 정확한 원문 text/UTF8 길이/raw SHA256 |
| DocumentRevision | source/dataset/document/revision, 선행 관계, kind/action, source URL, 발표/불명, 원문 canonical hash |
| DocumentObservation | 정확 revision_ref/hash, observation ID, 관측/수집, rights_ref, dataset version |
| DocumentEntityContext | 명시 entity/version과 문서 연결·issuer 연결 근거 |
| DocumentBatchManifest | request/limits/receipt, 전체 claim pair, 고정 file refs, context/catalog hash |

원문은 비어 있지 않은 UTF8 8KiB 이하이며 Unicode·줄바꿈을 정규화하거나 잘라내지 않는다. raw SHA256과 DocumentOriginal canonical hash는 다르다. publish/replace는 원문 참조, retract는 명시 부재 사유를 요구한다. URL은 최대2048자의 HTTP(S) 출처 metadata이며 접속하지 않는다. 제어문자·userinfo·빈 host·비HTTP(S)를 거부하고, 초기 validator는 ASCII DNS host/제한된 bracket host 구문만 지원한다. Unicode 경로는 그대로 보존한다.

수신 claim은 중복을 포함해16개 이하이고 고유 claim도16개 이하다. context는 entities16/document links32/instrument links32 이하, file refs64 이하, 각 canonical 객체는64KiB, manifest를 포함한 배치 전체는4MiB와 max_bytes 이하다. 초과는 명시 거부한다. 중복 수신 count와 evidence deduplication은 별개다. float/nonfinite, bool-as-count, surrogate, 임의 dict payload, unknown field/schema/version 및 중복 JSON key를 거부한다.

Manifest.claims는 revision_hash/observation_hash pair 순으로 정렬한 고유 집합이다. receipt.claim_refs는 수신 순서·반복을 유지한다. file refs는 원문·개정·관측·context 전체와 정확히 대응하며 누락/미참조 객체나 중복 이름·역할 모순을 거부한다. catalog_hash는 `qh-document-catalog-v1` prefix와 고정 typed source facts의 SHA256이다. 등록 canonical hash나 실제 자료의 진위 증명으로 사용하지 않는다.

## 표준 라이브러리 파일 adapter

`DocumentFileStore(existing_private_root, source_id=..., dataset_id=...)`를 context manager로 연다. `write(bundle, rights=..., at=..., catalog=...)`는 현재 전체 배치 store 권리를 먼저 확인하고 모든 관계·canonical 크기를 다시 검증한다. 부분 권리 허용은 지원하지 않는다. dataset version마다 한 immutable batch를 생성하며 같은 version은 덮어쓰지 않는다. 외부 ID나 URL을 파일명으로 쓰지 않고 내부 original/revision/observation index와 context.json만 사용한다.

`read(version, rights=..., at=..., catalog=..., knowledge_cutoff=...)`는 현재 목적별 권리를 manifest/본문을 열기 전에 확인한다. 모든 listed file의 유형·UID·권한·link count·크기를 본문보다 먼저 검사한다. observation 파일의 rights_ref도 원문 text보다 먼저 확인하고 전체 복원 후 다시 대조한다. 저장된 projection을 신뢰하지 않고 전체 evidence에서 PIT·연결·품질을 다시 계산한다. 원문을 포함한 bundle과 현재 view를 구분해 반환한다. research만 있는 현재 권리로 읽기 위해 store 권리를 임시 생성하지 않는다.

caller는 저장 당시와 정확히 같은 catalog source facts를 제공해야 한다. version 이름이 같아도 값이 바뀌면 거부하며 자동 migration하지 않는다. entity context 자체는 canonical 파일로 저장하고 manifest hash에 결속한다.

기존 private root와 version directory는 현재 UID/0700, 파일과 지속 flock inode는 현재 UID/0600/regular/nlink1을 요구한다. 절대 경로의 각 component를 dirfd/no-follow로 열고 FIFO는 nonblocking open 후 정규 파일 검사에서 거부한다. 잠금 inode를 삭제해 stale lock을 복구하지 않는다. 파일은 exclusive 생성→bounded 재확인→fsync하고 directory를 fsync한 뒤 manifest를 마지막에 no-overwrite hard link로 공개한다.

manifest 전 crash orphan은 비공개이며 같은 version 재시도도 conflict다. link 직후 crash로 manifest/pending 두 이름이 남으면 nlink2라 fail closed한다. 자동 복구/삭제를 수행하지 않는다. reader는 manifest가 나열한 고정 파일만 열며 나열하지 않은 파일의 내용을 탐색하지 않는다. 동일 UID/관리자의 전체 재작성에 대한 서명·진위 또는 전원 장애 내구성을 제공하지 않는다.

## 비신뢰 원문과 확인 범위

text와 source URL은 데이터다. shell/eval/template·URL fetch·도구 호출·승인·주문으로 연결하지 않는다. `DocumentSelection.trust`는 untrusted_text이며 원문을 보존한 것을 향후 AI prompt-injection 방어 전체 완료로 해석하지 않는다. 현재 외부 AI 호출은 없다.

전용 합성 테스트는 Unicode/줄바꿈/hash, unknown 발표, 기업/종목 연결 시점·version, 정정·누락·fork·cycle·철회·입력 순열·충돌 cutoff, partial/empty/not_collected, 현재 권리·신선도·상한·strict decoder, receipt/파일 변조, 경로/symlink/FIFO/lock/overwrite/crash를 검사한다. writer 종료 후 새 reader process에서 정정·두 종류 충돌의 whole bundle/hash와 PIT 결과도 대조한다.

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -v
python3.13 -I -S -m unittest discover -s tests/quality -v
python3.13 -I -S scripts/check_quality.py
python3.13 scripts/check_foundation.py
python3.13 -I -S scripts/check_market_storage.py --wheel /explicit/pinned/pyarrow-26.0.0-cp313-cp313-manylinux_2_28_aarch64.whl
```

foundation app의 /tmp는 tmpfs이므로 해당 실행은 새 프로세스 재읽기 증거다. Q17 own-volume harness는 동일 product suite를 local Docker volume의 TMPDIR에서 실행하므로 그 결과를 디스크 파일 재현 증거로 별도 구분한다. 실제 자료/API/권리 발급·HTML/PDF 추출·재무 숫자 계산·AI 해석·운영 보존정책·power-loss는 검증하지 않는다.
