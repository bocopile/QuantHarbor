# P28-03 내부2a 비금융 산출물 영속 계약 v1

상태: revision2 구현입력·미구현. root초안의P2두건을192.227초설계자문후보완했다. product-read-v1의 비금융 영속성을 보고/평가/연구/목표와 AI예산·작업상태로 나누며 기존12개 큐/완료율에 더하지 않는다. 내부2a는 앞4종만, AI의 mutable budget/holds/processed/query quota는 내부2b에서 별도 원자복구 계약으로 처리한다.

## 생산자/소비자와 타입

기존 SyntheticReportRepository/SyntheticSnapshotRepository/SyntheticExperimentRepository/SyntheticTargetRepository의 get/append와 canonical DTO/hash/lineage 검사를 보존한다. 각 exact repository에 명시 product_synthetic(database, *, capacity=128) factory를 추가해 같은정확타입을 반환한다. 무인자/기존생성자 메모리동작과 기존회귀는보존한다. arbitraryprotocol/approvedJSON/세션handle을받아권위로전환하지않는다. 제품backend는exact PostgresLedger·명시제품모드·현재ready/active/단일소유lock일때만연결하고매작업에재확인한다. legacydisposable이나foreignDB·미ready는거부한다.

신규 backend 제안: adapters/product_artifacts.py. 새 SQL은 migrations/product/0001_artifacts.sql의별도 qh_product schema/version/checksum으로관리한다. 기존qh.schema_migrations1~3과파일/baseline/DBlifecycle pin은변경하지않는다. 새마이그레이션DDL/데이터/버전기록은한transaction·checksummismatch/futureversion은차단한다. 신규미설치와기존schema존재/버전기록결손을구분해후자는차단한다. reopen후새factory는지원version/checksum/필수구조를재검증한다. 제품DB진입이후명시초기화만, import시파일/DB/network I/O없음.

| namespace | 허용 typed record·키 | account/created 시각과 정정 |
|---|---|---|
| report | Report / report_id | record.account_ref/created_at, supersedes_report_id 기존검사 |
| snapshot | PortfolioSnapshot / snapshot_id | account_ref/created_at, supersedes_snapshot_id 기존검사 |
| experiment | ExperimentResult / result_id | manifest.account_ref/created_at, predecessor/comparison_key·한부모분기거부 보존 |
| target | TargetPlan, OrderCandidate, TargetBuildResult / (kind,id) | body.account_ref, 같은묶음plan.body.request.evaluated_at; plan/candidates/result 한묶음 |

canonical_bytes(CanonicalPayload(...))의정확한 bytes를보존한다. namespace별정확DTO·canonical_bytes(parse_payload(raw))==raw·record_hash·wire_sha256·ID/version/environment/account와파생목록indexmetadata를읽기에도재검증한다. target은복원때plan/result/candidate순서와내용의기존전체묶음검사를재사용한다. 숫자float/pickle/eval/임의schema/discriminator·callerSQL/DSN없음. SQLliteral은기존hex/고정param규칙이며저장record에서SQL/경로를실행하지않는다.

## 원자성·중복·정정

동일키/동일canonical값은멱등, 다른값은충돌·불변기록덮어쓰기없음. target전체묶음과목록색인/카운트는하나의SQLtransaction으로commit하고, 한항목충돌/용량초과/commit실패면모두rollback한다. 기억상태를먼저성공으로반영하지않고commit확정뒤반환한다. rollback확정실패와COMMIT응답유실unknown을구분하고금융권한/자동외부재시도로변환하지않는다. unknown은현재DB의동일키/bytes/목표전체묶음을조회해저장여부를판별하며확인전성공/실패단정하지않는다.

제품DB내여러repository facade는PostgresLedger의제품전용RLock gate를공유한다. 제품open/close와모든제품저장작업은같은gate를잡고,facade는factory당시메모리open-generation에결속한다. close/reopen뒤옛facade는거부하고명시새factory로재연결한다. legacydisposable동작과금융schema는변경하지않는다. predecessor/fork검사·증분용량계산·묶음/index/count확정까지gate안에서수행하며,DB중복/참조/quota검증과실제write는단일SQLtransaction/고정advisorylock에결속한다. 별도_query호출간SQL잠금이이어진다고가정하지않는다. predecessor존재/동일계좌·시각·순환등은각기존저장소검사를보존한다. 한부모두자식거부·comparison_key·조건부UNIQUE는experiment에한정한다. report/snapshot/target에없던공통분기금지를추가하지않는다. 직접복원한dict를권위캐시로사용하지않는다. 데이터/index가부분저장되거나hash/lineage가깨지면완전/확정목록으로노출하지않는다.

합성개발한도: namespace당record128개·canonicalpayload합8MiB·개별canonical64KiB, 전체512개·payload32MiB. 동일재append는quota증분0이다. 각facade의capacity는해당namespace의공유저장전체기존+새고유행에적용하는더낮은개인정책이며DB전체hardcap128과함께검사한다. 기존capacity인자는상한128이내의더작은정책으로만적용하며완료기록eviction/무제한증액없음. metadata/key/index는고정필드와ASCII128자refs로별도bounded. 이값은canonicalpayloadquota이며물리diskquota나Q27금융완료예약이아니다. 실제지원규모/지연은P28-08/PG04에서검증한다.

## 목록과 재시작

신규제품조회 backend는(namespace,environment,account_ref,created_at,key)의검증된목록색인과최대128행boundedscan을제공한다. 전체조회와페이지complete를구분하고, 후속read model이기존product-read-v1정렬/불변snapshot을만든다. 브라우저에DBtoken/원시canonical전체/authority를주지않는다. get은기존scope/ref/hash의거부규칙을약화하지않는다.

stop/reopen동일제품DB에서행·hash·정정관계·묶음/index를재구성한다. canonicalID·timestamp·생성종류·출처를새값으로고치지않는다. 과거target의authority_generation은역사자료이며새runtime의source/승인권한으로자동승격하지않는다. approval/principal/session/nonce/handle은이비금융저장소의허용종류가아니며financialDB/현재권리검사를대신하지않는다.

## 검증과 인계

최소의미검증: 기본memory회귀4종, exactfactory와미ready/foreignbackend거부, typedwire/ID/account/hash변조거부, 동일append/다른값충돌, lineage/fork/scope, target중간충돌시앞행없음, record/byte상한원자거부·eviction없음, 명시migration checksum/재시작완전성. mock/정적SQL문자열은실제DB원자성증거아님. root가실제제품DB에서4종유효DTO·stop/reopen·중복/충돌·targetbatchrollback·lineage를증명한다.

제품코드의tests/scripts fixture import·실제AI호출/새유료API·실계좌/외부보고는없음. 단위2a만으로내부2b/나머지P28-03/readHTTP/분석slot완료를선언하지않는다.
