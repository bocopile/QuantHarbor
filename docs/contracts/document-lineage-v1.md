# 문서·뉴스 출처 계약 v1 — Q18 추가 계약

2026-10-24. DATA-document-lineage, DATA-DEC-002. Q12 frozen 계약과 Q17 시장 스키마를 유지하고 다섯 고정형만 추가한다. 합성 text/plain 원문·공시/재무보고/뉴스 추적이며 실제 수집·장문파싱·재무숫자추출·AI 실행 권한은 아니다.

## 고정형과 상한

모든 top-level 은 schema_version=정수 1, environment=synthetic. nullable key 도 존재한다. 기존 canonical 64KiB·UTF8·hash prefix 를 유지한다. 아래 key 와 중첩형은 명시 decoder 에만 등록한다. 추가 필드가 필요하면 root 에게 이유를 전달해 계약에 먼저 반영한다.

| 고정형 | 공통 외 필드 |
|---|---|
| DocumentOriginal | media_type, encoding, text, utf8_byte_length, raw_sha256 |
| DocumentRevision | source_id, dataset_id, document_id, revision_id, predecessor_revision_id, kind, action, source_url, published_at, publication_unknown_reason, original_hash, original_absent_reason, evidence_ref |
| DocumentObservation | observation_id, revision_ref, observed_at, ingested_at, rights_ref, dataset_version, evidence_ref |
| DocumentEntityContext | context_id, context_version, entities, document_links, instrument_links |
| DocumentBatchManifest | batch_id, source_id, dataset_id, dataset_version, created_at, request, limits, receipt, claims, file_refs, context_hash, catalog_hash, canonical_version |

DocumentOriginal media_type=text/plain, encoding=utf-8, 정확한 text bytes/hash 를 확인한다. Unicode·줄바꿈을 정규화하거나 잘라내지 않는다. 원문당 UTF8 8192bytes·빈원문금지; escaping 후 64KiB 초과도거부. original_hash 는 DocumentOriginal 의 canonical hash 이고 raw_sha256 과 별개다. publish/replace 는 original_hash 필수·absent_reason null, retract 는 original_hash null·absent_reason 필수. kind=disclosure|financial_report|news, action=publish|replace|retract. source_url 은 HTTP(S) 출처문자열일 뿐 fetch 하지 않는다. 길이 2048 이하·userinfo·제어문자·빈 host·비 HTTP(S) 거부. published_at null 이면 명시 unknown reason 을 요구하고 관측 시각으로 채우지 않는다.

revision_ref 는 정확한 source_id,dataset_id,document_id,revision_id,revision_hash 를 갖는다. identity 는 환경·source·dataset·document·revision 이고 다른 dataset 을 합치지 않는다. observation 은 observed_at≤ingested_at, 명시 datasetversion·rightsref 를 갖는다. 원문/개정/관측을 별도 불변사실로 보존한다.

배치 하나는 source/dataset/version 하나, 수신 claim16 개 이하(중복포함), 고유 claim16 개 이하, 전체 파일 4MiB 이하. 각파일 64KiB 이하, file_refs64 개 이하. 초과는 명시거부하며 자동분할/잘라내기하지 않는다. manifest/schema·수집/조회·연결·출력형의 상한을 함께 검사한다.

## 중첩형

- RevisionRef: source_id,dataset_id,document_id,revision_id,revision_hash.
- ClaimRef: revision_hash,observation_hash. pair 순 정렬한 고유 manifest.claims 이며 receipt.claim_refs 는 수신 순서와반복을 유지한다.
- Entity: entity_id,entity_version,kind(company|fund_issuer|unknown),evidence_ref,known_at.
- DocumentEntityLink: revision_ref,entity_id,entity_version,relation(subject|reporting_entity),evidence_ref,known_at.
- EntityInstrumentLink: entity_id,entity_version,catalog_version,instrument_id,instrument_version,listing_venue_id,relation(issuer),valid_from,valid_to,known_at,evidence_ref.
- DocumentRequest: request_id,source_id,dataset_id,dataset_version,scope_ref,document_ids,expected_document_ids,started_at,deadline. scope_ref 는명시한조회 범위의근거이고 document_ids 빈 tuple 은 해당 scope 의제한되지않은문서집합이다. expected 는명시했을때만누락검사하며 complete 가공급자전체를뜻하지않는다.
- DocumentLimits: max_claims(1~16),max_bytes(1~4MiB),max_age_seconds(양의정수),policy_ref. 실제 byte 예산은 canonical 원문/개정/관측크기를포함한다.
- DocumentReceipt: request_id,scope_ref,status(success|partial|failed|not_collected),complete,received_at,claim_refs,missing_document_ids,error_reason,terminal_ref. 명시 complete 성공은 terminal_ref 필수·오류/누락없음; 실패/미수집은 complete=false. 미수집은 claim 없음. failed 에부분 claim 이있으면부분근거로보존하며성공승격금지. receipt 의 request/scope/clock 및 claims 범위를검사한다.
- DocumentFileRef: schema_name,basename,byte_length,canonical_hash. basename 은내부생성 제한형(json)이고 URL/ID 를경로로쓰지않는다. file_refs 의중복 name/hash 역할모순·미참조/누락 파일 참조를거부한다.

EntityContext 는각 16entities,32document_links,32instrument_links 이하. 중복/상충관계와존재하지않는 entityversion 참조를거부한다. Q16 catalog 의정확한 version/종목 version/venue·유효기간·known_at·eligible 분류를조회할 때검사한다. catalog_hash 는고정 source-facts 형식(qh-document-catalog-v1)의 SHA256 이며 canonical 등록형 hash 나자료 진위 증명이아니다. historical context/catalog 와다른입력은거부하고자동 migration 하지않는다.

## 수집·정정·시점·품질

합성입력만받는좁은 application 진입점에서원문/claim/receipt/context/currentrights 를검증해불변 bundle 을만든다. 네트워크·retry·sleep·현재시각은없고 evaluated_at 을명시한다. 원천 fetch 미실행은 not_collected 이며빈성공으로표시하지않는다. raw 예외·원시도구출력은저장하지않는다.

동일 revisionidentity/hash 와동일 observationID/hash 는멱등이다. 동일 identity 의다른내용은양측 claim 을보존하고해당문서사용을보류한다. observationID 충돌도양측문서에영향을준다. predecessor 는같은 source/dataset/document 의정확 revision 을가리킨다. publish 는선행없음, replace/retract 는선행필수. opaque 문자열순서·입력순서로 최신을 정하지 않는다. 누락/분기/cycle·retract 이후후속·kind 변경·정정 발표 역행은보류한다.

as_known(cutoff)은발표·관측·수집·기업 연결 known_at 이 cutoff 이내인근거만으로 chain/conflict 를재구성한다. 나중충돌이과거결과에소급하지않고입력순서에도의존하지않는다. publication_unknown·발표/관측시간모순은사용보류한다. restated 는 original_cutoff<cutoff 와명시 mode 를보존하고기존 산출물을 수정하지 않는다. cutoff≤평가 시각이며과거자료를현재 fetch 로소급확정하지않는다.

일반보존과기업/종목 연구 사용을구분한다. 명시 연결미확인문서는보존할수있지만기업/종목근거사용은보류한다. issuer 연결은 ETF 기초자산/보유기업노출이아니다. 현재자료의신선도는조회평가 시각·max_age_seconds 로재계산하고완전성과분리한다. conflict/unknown/missing/context 불일치를성공또는 fresh 로숨기지않는다.

## 권리·비신뢰 경계

기존 RightsGrant 의 source/dataset/version·store/research/ai/report 목적과 validity/revoked_at 을재사용한다. 모든 claim observation.rights_ref 와현재 grant 가일치해야한다. writer 는전체 배치의현재 store 권리확인후본문을파일로저장한다. reader 는현재목적권리를본문을 열기 전에검사하고복원후모든관측과다시대조한다. historical 권리는현재허가를대체하지않는다. 부분 권리 허용 배치는지원하지 않고 전체를 거부한다.

원문은비신뢰 자료다. shell/eval/template 실행·자동 URL 접속·도구권한·승인·주문으로연결하지않는다. 데이터로원문을보존하는것과향후 AI prompt-injection 방어의완성은다르다. 현재외부 AI 호출없음.

## 저장·완료 증거

표준 lib 파일 adapter 가 wholeevidence(original/revision/observation/context)와 manifest 를저장한다. 요청/수신/누락/실패근거·정확한 filehash/ref 를결속한다. writer 는모든관계와 canonical 크기를검사하고현재 권리후생성한다. reader 는저장된 projection 을신뢰하지않고전체 근거로 PIT/품질을재계산한다.

private0700directory·0600regularfile·현재 UID·dirfd/no-follow/nonblocking·nlink1, 단일 flockwriter·nooverwrite·데이터 fsync→manifest-last 원자게시. manifest 없는 version 은비공개,중간실패 orphan 은자동 복구 성공으로표시하지않는다. hardlink 게시의 nlink2window 가있으면 failclosed·한계를문서화한다. 파일 개수/크기/참조를본문을 읽기 전에검사하고항상 boundedread. 동일 UID/관리자의전체 파일재작성에대한서명/진위·전원 장애 내구성은주장하지않는다.

필수검증: Unicode/줄바꿈/raw 와 canonicalhash,unknown 발표,기업 연결 version/시점/ETF 의미,역순정정·누락·철회·충돌 cutoff 전후·입력순열,partial/empty/not_collected,request/receipt 변조,권리만료/철회/목적차단,신선도,상한,strictdecoder,경로/symlink/FIFO/overwrite/manifest 미게시/누락 파일,writer 종료후새 reader 복원. 기존기본형/Q17 전체회귀를유지한다.

## Q18 보안 검토 S3 반영 — 조회 용도와 권한 결속

`use=entity_research|instrument_research`는 호출자가 지정한 목적의 현재 권리 외에도 현재 `research` 권리를 반드시 요구한다. `purpose=store|ai|report`를 지정해 연구 권리 검사를 대신할 수 없다. 파일 reader 는 두 권리를 manifest/본문 열기 전에 검사하며, 복원 후 전체 관측의 권리 참조도 검증한다. `use=preserve` 결과는 연구 사용 가능으로 표시하지 않는다. 이 규칙은 별도 주문 권한을 부여하지 않는다.
