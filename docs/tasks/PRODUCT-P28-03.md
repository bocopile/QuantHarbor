# P28-03 — 로컬 실행 조립·영속성·15분 분석

- 상태: 진행 — 내부1/2a/2b-1납품·다음2b-2a배정준비
- 단계·선행조건: EXEC-DEC-003, P28-02 product-read-v1 준비·P28-01 정적 산출물. Q27/실제화면 미해결은 통합·완료 관문 유지
- 요청 근거·범위: 사용자 전체 계획 우선 진행·실패 큐. 현재호스트 로컬 합성 제품 조립·영속성·활성세션15분 분석
- 담당: root 공통계약/큐/상태, qh_implementer 지정파일, 독립 일반/보안 검토·root 실제 합성DB. worker1/writer1·재귀0
- 입력: 코드기준8a27220, product-read-v1 revision5 SHA35f6ed51edb43e04711f3dcec290c553bc4a5af201467a3110ae1bc64edd0977, product-ai-persistence-v1 revision1 SHAf95ec6afccd549d15e6ce1df0a02612bbbd5d688b13e31bf7523785dec3aafdb. 기존exact타입/금융migration1~3보존. 과거단계입력은하단이력.
- 소유: 실행 단위별 아래 명시. 기존 사용자수정 보존. 계약·status·큐는root만 통합
- Git: codex/qh-local-delivery-20261030, base80403ab·코드HEAD8a27220, 내부1 93222a0/내부2a6c8786f/Q27보강8a27220 각각origin SHA확인. 별도Q27최종검증worktree8a27220고정·PR/merge없음
- 허용: 제한 qh_development, Sol/high, 로컬 합성 구현/요청검증·새유료/외부연결/실제금융 없음
- 검증: 단계별 의미있는단위·실제합성DB 재시작·원자성·계약대조·독립검토. 실행하지 않은 전체통합/사용자인증/브라우저/금융은NOT RUN
- 시간·비용: 배정별1200초·자동재시도0·기존구독

## 내부 순차 구현 단위

1. 제품 PostgreSQL 수명관리: 같은 정확타입 PostgresLedger에 명시 product_synthetic 진입점, private root/binding/단일잠금/고정image·migration검증, 종료자료보존. 무인자 disposable 검증 경로는 보존.
2. 비금융영속저장: canonical DTO/hash/lineage·append+목록 원자성, capability/session/nonce 복원금지.
3. 6화면read model: 확정필드/통화/시점/원본참조·미확인/부분/범위.
4. 조회snapshot·현재권리: bounded materialization/TTL/cursor/commit gate·회수·순서.
5. 제품조립/재시작: tests/scripts fixture 의존없는 public서비스·제품adapter조립, 새authority_generation/기존사실보존·대사 전 차단.
6. 15분분석slot: 기존달력 regular session 기반UTC slot·중복claim 영속·긴작업/절전/시계변화/재기동skip·기존주문추적 우선.

내부단위는 기존12개 큐를 더 늘리거나 완료율에 합산하지 않는다. 일부반환은 P28-03 artifact_ready가 아니다. 모든단위/필수영향검증/독립검토와 실제조립증거 확보 전 P28-03 completed 아님.

## 현재 인계

초안이며 실제 배정/파일변경/검증 증거는 아래에 실행 후 기록한다. P28-04 실제보호사용자인증/정책명령과 P28-06 HTTP/브라우저는 본 단계 미구현으로 명시한다.

## 내부1 배정 — P28-03-database-build-a01

- 04 Sol/high·qh_development 별도부모,1200초·자동재시도0.
- 소유4파일: src/quantharbor/adapters/postgres_ledger.py, src/quantharbor/adapters/product_database.py, containers/compose.product.synthetic.yaml, tests/product/test_product_database.py. 뒤3개신규예정. 보호입력SHA는배정때고정하며root가반환후대조한다.
- API: PostgresLedger.product_synthetic(runtime_root, *, binding_id)에서같은정확타입인스턴스·명시합성제품수명관리를제공. 무인자disposable경로/기존migration/타입guard보존. 제품정상종료는data/volume삭제없이자기DBstop, private root/binding/소유/이미지/schema/단일잠금검증.
- 구현자검증: 집중신규단위·기존수명관리회귀·공백·공개후보검사. Docker/actualDB는NOT RUN이며root가별도구동/재시작자료보존을판정한다.
- 이부분반환만으로P28-03 artifact_ready/completed가아니다. 나머지비금융영속/read model/권리snapshot/실제조립/15분slot이남는다.

## 내부1 실제 반환

- Sol/high655.158초 정상반환·소유4파일만변경·보호653개root재대조불변. [근거](../evidence/product-p28-03-database-build-2026-10-30.json).
- 집중mock24/24 PASS·공개657파일지적0·공백검사PASS. 초기mock인자/label준비실패a01 FAIL16/a02 FAIL1·ERROR14를보존하고FUP-P28-004로추적한다.
- 실제DB 초기화/동일자원stop·reopen·ledger자료보존/별도프로세스잠금과독립검토를진행한다. 전체제품789은새수명관리소스에서NOT RUN. 내부1과P28-03 전체완료는구분한다.

## 최초 actualDB FAIL — 표현 정합성

- 실제검사0.946초 FAIL, 초기context에서product_container_identity_or_safety_mismatch. 컨테이너기동전이며자기자료보존/소스4SHA불변이다. [근거](../evidence/product-p28-03-actual-db-a01-2026-10-30.json).
- 읽기진단: Docker의HostConfig.Binds가자기namedvolume:/var/lib/postgresql:rw를표시한다. 현재None/[]검사가정상volume표현을거부했다. hostbind허용이아니며, 정확자기volume만허용/다른source·target·mode거부회귀가필요하다. FUP-P28-005등록.
- 06검토입력은고정해반환을받고최소수정/의미있는단위·실제DB재확인으로진행한다. 미기동volume를삭제/권한확장하지않는다.

## Binds 보완·실제 재검사

- root는helper의정확자기volume Binds형식만허용, 독립Mounts검증과다른source/target/mode/추가hostbind거부를유지했다. 회귀red26중ERROR1→green26PASS. [수정](../evidence/product-p28-03-binds-fix-2026-10-30.json).
- actualDB a02 8.205초·9항목PASS/소스4불변: uid999/schema3순서·별도프로세스flock·금융사실commit·stop후같은container/volume·재시작원장보존·중복거래재계상없음·wrongbinding거부·legacy정리. 제품자료/볼륨은보존했다. [실제근거](../evidence/product-p28-03-actual-db-a02-2026-10-30.json).
- 독립일반138.335초지적0·같은최종4SHA. [검토](../evidence/product-p28-03-database-review-a01-2026-10-30.json). 초기mock실패전체의정확한수정전bytes는남지않아독립확정한계를명시했고,비민감trace/파일변경타임라인을FUP-P28-004에추가했다.
- 보안delta최종확인후내부1수용판정. 전체P28-03의나머지5단위/실제제어·HTTP·15분slot·전체신규소스789는미실행/미구현이다.

## 내부1 현재 판정과 다음 단위

- 최종source4개는독립일반138.335초·보안delta101.486초지적0·동일SHA다. 기능검증mock26/실제9PASS로DB수명관리seam을후속격리구현에사용할수있다. [최종보안](../evidence/product-p28-03-database-security-a02-2026-10-30.json).
- FUP-P28-005는해결. FUP-P28-004의과거mock필드별원인전체복원은증거한계로후속큐에남긴다. 이를현재제품의실제검증성공과혼동하지않고P28-03 전체완료/전체수용은선언하지않는다.
- 사용자작업단위commit/push지시대로내부1기능을독립작업브랜치에기록한다. 다음내부2는2a 보고/평가/연구/목표의불변canonical저장·목록,2b AI예산/작업mutable상태복구로분해한다.

## 내부2a 설계 입력 — 2026-10-30

- [불변산출물 계약](../contracts/product-artifacts-v1.md) root초안: 보고/평가/연구/목표만, mutable AI작업/예산은2b별도. 기존exact타입·메모리경로·canonical/lineage/목표묶음원자성보존. 금융schema1~3변경없음.
- 03 제한Astra/high 읽기설계검토 후root확정, 04지정파일순차구현. 새코드/실제DB/전체통합은아직NOT RUN.

## 내부2a 설계 반환·revision2

- Astra/high192.227초·P2두건: 없는created_at과공통branch금지. root는target목록시각evaluated_at/experiment만fork금지로보완했다. [자문](../research/product-p28-03-artifacts-design-2026-10-30.md).
- 추가확정: 제품open/close공유gate·세대결속/옛facade거부, canonical재인코딩/목표묶음재검증, 단일SQLtransaction·증분quota·버전결손차단·COMMIT응답unknown판별. 기존금융schema/pin/권한가드불변.
- 구현소유예정9파일: adapters/synthetic_reporting.py, synthetic_valuation.py, synthetic_research.py, synthetic_target.py, postgres_ledger.py, product_artifacts.py, migrations/product/0001_artifacts.sql, tests/product/test_product_artifacts.py, test_product_database.py.

## 내부2a 구현 배정 — P28-03-artifacts-build-a01

- Sol/high·qh_development 별도부모,1200초·자동재시도0·worker1/writer1. 위확정9파일만소유, root는반환전공개파일쓰기를멈추고보호SHA를보존한다.
- 계약revision2 SHAf29ef5fb9f458522deadf3f234c8770c9d0f25024af88eef1a55edbdc809bfc8, HEAD439f15e 기반. 기본메모리4종·exactfactory·gate/세대·canonical/lineage·목표묶음·별도migration/quota검사. actualDB/새전체통합은NOT RUN으로인계한다.
- 내부1은현재mock26/actual9/독립일반·보안/초기fixture원인후속해결로기능수용. [후속독립판정](../evidence/planning-evidence-precommit-2026-10-30.json). 정확과거testbytes없음의역사한계는그대로남긴다. 내부1수용은전체P28-03완료가아니다.

## 내부2a 실제 반환·현재 수용관문

- Sol/high844.414초·지정9파일구현,기존메모리43+새artifact19+DBmock27=89PASS·공개683지적0. 작성자가rootbefore.json을덮어쓴기록사고로원래680all-public초기증명은없음. root가writer초기tracked673SHA는재대조불변확인했고원래전체불변으로확대하지않는다. 이후rootbaseline은worker권한밖.runtime/team에별도보존한다. [구현](../evidence/product-p28-03-artifacts-build-2026-10-30.json).
- 일반231.865초P2 COMMIT후ERROR오분류→root보완RED1/새4·전체artifact20PASS. 실제a02확인ERROR해소와보안214.612초독립해결확인.
- actuala01 44.461초FAIL/1검사, a02 104.218초FAIL/5검사(시험준비), 동일source연속a03 32.744초6PASS. root가임의targetID를만들지않고실제SQL의반드시거부할metadata중간충돌로원자성을검사했다. 4종canonical/정정분기/COMMIT응답유실·afterERROR/별도schema/oversize/체크섬거부/stopreopen동일자료·oldfacade거부를버전별로구분한다. 자기자료보존. [후속](../evidence/product-p28-03-artifacts-actual-a03-2026-10-30.json).
- 추가보안P2는설치함수본문손상검출누락(FUP-P28-008)으로현재보완. 내부2a전체수용/commit은이검증과최종검토뒤, P03전체artifact_ready는아직아니다.
- 내부5에직접execution_uow.Popen의제품close공유gate직렬화/정상종료drain을명시인계. 2a성공을금융조립종료전체수용으로확대하지않는다.

## 내부2b 독립 설계 착수

- 내부2a저장기능최종가드/검토확인·최종commit준비동안[AI예산·작업복구계약준비](../contracts/product-ai-persistence-v1.md)를03Astra/high읽기설계에배정한다. 내부2a미완료를완료로올리지않고독립설계만진행한다.
- 입력: SyntheticAIRepository의실제reserve/dispatch/settle/query/execute/processed규칙,기존ai-local-v1과product-read-v1,현재제품DBgate/세대/별도schema1. mutable상태의단순dict/JSON권위복원금지. 신규실제AI비용/자동외부retry없음.
- 설계자문540초·자동재시도0·쓰기/시험/하위agent없음. 실제구현소유·완료기준·migration2변경목록은root가반환후확정한다.

## 内部2a 납품·2b-1 다음 배정 준비

- 최종artifact20PASS128.542초,설치함수손상실제RED2.340→GREEN2.417초,보안delta79.360초0지적/11SHA불변. 독립납품사전검토164.963초·소스/증거26검토중실제변경24만6c8786f로commit·origin push/원격SHA확인. [납품](../evidence/product-execution-delivery-precommit-2026-10-30.json). P28-03 전체/AI복구/HTTP/15분slot완료는아니다.
- 2b 자문374.138초의typedcheckpoint+명시phase·공유gate/owner/latch/query durable barrier안을root [revision1](../contracts/product-ai-persistence-v1.md)에통합했다. globalauxiliary1MiB예약/closingattempt별128KiB slot·총aux8MiB/encoded32MiB·32KiBchunk의보수제품상한과증명기준을명시했다.
- 2b-1 배정준비 소유6파일: src/quantharbor/adapters/product_schema.py, product_ai.py, migrations/product/0002_ai.sql, tests/product/test_product_ai.py 신규; product_artifacts.py loader위임, tests/product/test_product_artifacts.py 필요회귀. 기존0001 checksum/금융1~3/DBlifecycle/기본AI memory는불변. 2b-1은저장기반이며실제corefactory/client호출연결은2b-2다.
- 다음Sol/high1200초·자동재시도0 배정전root baseline을worker권한밖.runtime/team에보존한다. 현재본문은배정준비이며실제기동/검증은반환후따로기록한다.

## 내부2b-1 부분 반환·root 보완

- Sol/high1199.766초 시간 상한 종료·지정6파일/부분 인계 보존, root 보호713개 SHA 불변. worker AI54/기존artifact23 PASS·최종 registry3 PASS를 버전별 구분한다. 실제 PostgreSQL/독립검토는 NOT RUN이다. [근거](../evidence/product-p28-03-ai-store-build-2026-10-30.json).
- root 신규 회귀에서 processed revision True가 marker1과 같게 판독되는 결함 RED. tuple/hash/transition과 정수 revision의 정확 타입검증 후 현재 AI55 PASS0.681초. FUP-P28-009/010에 후속 판정 연결.
- 저장기반 범위는 공통 schema1→2·typed codec·bounded pipe·request/policy append/CAS·정확 COMMIT readback이다. core factory/reserve/dispatch/settle/query/restart/실제 execute proof와 미래 closing monotonic proof는 내부2b-2 미구현이며 이번 수용으로 확장하지 않는다.

## 내부2b-1 root 실제 DB 확인

- actual 합성 PostgreSQL a01:17.097초·10항목 PASS·6소스SHA 불변·자기제품DB stop/자료보존. [근거](../evidence/product-p28-03-ai-store-actual-a01-2026-10-30.json).
- 기존v1산출물11개 보존→schema2 실제upgrade/known2 artifact factory, 강제DDL오류의 schema/version/table 롤백, request/policy canonical append·동일멱등/충돌·stale CAS, 두facade 경합1commit/1stale, 실제2chunk 복원, COMMIT ACK 유실/COMMIT후SQL ERROR의 정확readback·재write0, stage실패 원자성/임시stage잔여0/공유latch, 동일container/volume stop·reopen 및옛facade 거부, ai_metadata본문손상 거부/복원을 확인했다.
- core 연결·실제 execute marker/closing 미래전이증명/최대32MiB성능/새AI소스전체suite/HTTP·IPC·브라우저/15분slot은 NOT RUN. 실제2chunk 성공을 최대부하 증명으로 확대하지 않는다. 독립일반검토/현재artifact23검사는 진행중이다.

## 내부2b-1 일반P2 보완과 동일버전 실제DB

- 일반검토356.398초 P2세건을FUP-P28-011~013에보존. CHECK내용손상은실제RED2.650초/자료복원, deadline·완료receipt 신규4시험6FAIL로재현했다. root정확CHECK정의대조/진입절대deadline·timedlock·같은deadline schema pipe·최종판정/완료receipt관계를보완했다. [수정근거](../evidence/product-p28-03-ai-store-fixes-2026-10-30.json).
- 현재AI59 PASS0.868초. actuala02 동일6SHA11 PASS17.621초·원본v2보존·별도자기v1에합성11산출물준비후upgrade/DDL원자성부터반복, CHECK완화숨김book거부GREEN추가. 첫seed는macOS /var symlink로기존NOFOLLOW거부(새DB기동전); 준비경로만canonical로보정, 제품guard보존. [현재실제](../evidence/product-p28-03-ai-store-actual-a02-2026-10-30.json).
- 보안및일반최종검토·현재82회귀/commit은진행중. core factory/phase연결·closing미래전이증명/최대32MiB성능·전체제품/HTTP/브라우저/15분slot은미실행이다.

## 내부2b-1 보안 상속 guard 보완

- 보안302.239초는일반3보완확인·상속P2추가. root부모+자식중복행시도는AI factory가ai_chunk STRICT에서이미실패했으므로factory성공/경제오염을재현했다고주장하지않는다. schema guard가관계를명시거부하도록고정4테이블 pg_inherits 부모/자식검사를추가했다. FUP-P28-014와[수정근거](../evidence/product-p28-03-ai-store-fixes-2026-10-30.json)에한계보존.
- 최종6SHA의AI59+registry3=62 PASS36.930초, 실제별도자기v1부터12 PASS18.337초·자료보존. 상속중복행이metadata읽기전schema에서거부됨을확인했다. [현재실제](../evidence/product-p28-03-ai-store-actual-a03-2026-10-30.json). 보안delta·최종일반/납품관문대기. 기존82PASS129.442초는상속guard추가전버전으로분리한다.

## 다음 내부2b-2의 순차 배정 경계

저장기반 납품 이후 다음 세 단계로 나눈다. 아래는 배정 설계이며 실제 실행/검증 완료가 아니다. 새 부모 작업/완료율 항목은 추가하지 않는다.

1. 2b-2a: exact factory·DB 검증본만의 내부 hydration/phase·공유 세대 첫 recovery barrier, 조회/balance/attempt·reserve/cancel을 연결한다. 다른 facade의 같은 세대 작업을 재시작으로 취소하지 않는다. 아직 연결하지 않은 query/dispatch/client/processed 경로는 제품 모드에서 명시 차단한다.
2. 2b-2b: query charge를 Sources 접근 전에 durable 확정하고 실패/재시작에도 요청16회 quota를 환급하지 않는다. 현재 Sources는 새 facade에 명시 bind하며 과거 source객체를 복원하지 않는다.
3. 2b-2c: 실제 execute/review·owner/세대/호출1회·dispatch unknown시 client0·정산/결과/marker/hold/receipt 원자성과 최종 복구를 연결한다. client 대기 중 gate/SQL lock을 유지하지 않는다.

- 2b-2a 소유 예정4파일: src/quantharbor/adapters/synthetic_investment_ai.py, product_ai.py, tests/product/test_product_ai.py, test_product_ai_core.py(신규). application/domain/SQL/registry/lifecycle/공통문서는 root 소유이며 변경 필요는 근거를 반환한다.
- 예약 전 필수 종료 용량증명을 먼저 갖춘다. 제품 모드의 pending attempt 원문은 최대64KiB까지 커질 여유를 byte_capacity 안에 보수 계상하고, 기존 closing3records/196608bytes·128records/8MiB와 auxiliary slot은 유지한다. 이 여유는 실제 원문+기존 closing 한도를 높이는 것이 아니며, pending이 있는 동안 모든 추가 저장에도 같은 보수 가드를 적용한다. global metadata1MiB/attempt slot128KiB의 귀속과 미래 전이 상한을 증명할 수 없으면 reserve/client를 차단한다. 기본 memory 경로는 변경하지 않는다.
- 2b-2a 수용은 실제 예산/취소/세대 복구 저장 경계까지다. query·유료/실제client·processed core 전체 수용으로 올리지 않는다. 구현1200초/자동재시도0, 지정 단위·기존AI회귀·root 실제 합성DB·독립검토·작업단위commit/push로 인계한다.

## 내부2b-1 저장기반 기능수용

- 보안최종delta115.062초 지적0·최종6SHA불변. 이전일반3건의보완은직전보안에서확인,상속guard는최종delta에서해결확인. 현재62집중/actual12PASS와함께저장기반만기능수용한다. [최종보안](../evidence/product-p28-03-ai-store-security-a02-2026-10-30.json).
- FUP-P28-009~014해결. 최초timeout/원래실패/상속재현한계/버전별검증은삭제하지않는다. 현재Git납품사전확인중·아직16번째commit/push를기록하지않았다. 다음2b-2a factory/budget/recovery배정설계는실행전이며미구현 core/query/client/processed/closing/P03전체완료와구분한다.

## 내부2b-1 Git 납품

- ba5b52d816a57b85beccfd4cce78dd24875119b8,19파일을독립10항목191.025초/차단0뒤commit·origin push/원격SHA대조했다. 최종stage공백검사에서보고서Markdown두공백9줄이검출돼commit전공백만정리후PASS,코드6SHA는불변이다. [납품](../evidence/product-p28-03-ai-store-delivery-2026-10-30.json).
- 총16단위납품. 내부2b-2a/b/c는여전히배정설계이며미실행, P28-03 status in_progress/artifact_ready false를유지한다.
