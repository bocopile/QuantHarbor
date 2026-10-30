# P28-03 — 로컬 실행 조립·영속성·15분 분석

- 상태: 진행 — 내부1 기능검증·독립검토 확인, 내부2 준비
- 단계·선행조건: EXEC-DEC-003, P28-02 product-read-v1 준비·P28-01 정적 산출물. Q27/실제화면 미해결은 통합·완료 관문 유지
- 요청 근거·범위: 사용자 전체 계획 우선 진행·실패 큐. 현재호스트 로컬 합성 제품 조립·영속성·활성세션15분 분석
- 담당: root 공통계약/큐/상태, qh_implementer 지정파일, 독립 일반/보안 검토·root 실제 합성DB. worker1/writer1·재귀0
- 입력: main80403ab 미커밋기준, product-read-v1 revision5 SHA35f6ed51edb43e04711f3dcec290c553bc4a5af201467a3110ae1bc64edd0977, 기존 exact-type repository/UoW/ledger 계약과 migration1~3
- 소유: 실행 단위별 아래 명시. 기존 사용자수정 보존. 계약·status·큐는root만 통합
- Git: codex/qh-local-delivery-20261030, base80403ab, 내부1 commit93222a0/origin SHA확인. Q27고정worktree불변·PR/merge없음
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
