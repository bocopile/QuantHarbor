# P28-03 내부2b — AI 예산·작업 상태 영속 계약 v1

2026-10-30 · root 구현입력 revision1 · 실제2b구현/검증 NOT RUN. [독립 설계 자문](../research/product-p28-03-ai-persistence-design-2026-10-30.md)의 확인된코드사실과명시transition안을채택하며아래구현범위·보수한도를확정한다. P28-03 전체완료/실제AI연결허가가아니다.

## 문제와 범위

기존 SyntheticAIRepository의budget/holds/query quota/processed상태가메모리에있다. 재시작이예산초기화·중복client호출·미확인비용환급·처리결과위조로이어지지않도록명시제품mode만영속화한다. 기본생성자/기존memory/get/append/예외규칙은보존한다. 금융authority/session/nonce/client/Sources객체는복원하지않는다. actual_disabled·retry_disabled와기존가격fixture/정책은불변이고유료AI/실제계좌/외부전송은실행하지않는다.

추가API는 SyntheticAIRepository.product_synthetic(database, *, capacity=128, byte_capacity=8388608)다. 같은정확타입을반환한다. 정확한PostgresLedger·active제품ProductDatabase·ready/privatebinding/소유lock·open-generation을매작업확인한다. 여러facade가같은단일book을공유하며book분할로정책cap을우회하지않는다. 외부DSN/SQL/book ID/restore JSON을받지않는다.

## 저장 구조와 신뢰 경계

서버생성typed checkpoint와명시transition을쓴다. 단순__dict__/pickle/일반restore(mapping/bytes)/임의class import는없다. codec raw입력은검증된DB유계읽기에서만오며,기존memory repository나호출자가미리만든JSON을제품권위로수입하는진입점을만들지않는다. 제품backend가현재세대의facade/phase에결속한내부객체만발급한다.

- ai_state: 고정공유book,codec version/revision,canonical checkpoint bytes/hash,마지막operation ID/input digest/확정revision.
- ai_processed: result/review exact content hash·종류·생성transition·revision의불변표식. 최대128개이며닫힌내부ref/hash로기록한다.
- 무제한event journal/job framework는추가하지않는다. request/attempt/terminal/result가작업상태정본이다.

records는허용6종의canonical bytes를보존하고parse/re-encode동일성·정확DTO·ID/version/environment/hash를재검증한다. attempts는attempt records에서재구성한다. payloads는최초request/policy exact refs와Usage로결속하고원문을재구성해중복reserve동일성을보존한다. policies의scope/window binding,blocked scope,holds,request별query total0..16,attempt별receipts/denials를명시codec필드로보존한다. 알려지지않은필드/버전·중복키·bool-as-int·잘못된시각/상태/참조/용량을거부한다.

processed는DB의검증된ai_processed표식에서만원문과대조해재구성한다. result존재나사용자가만든memory_processed값으로표식을추가·수리하지않는다. 실제execute/review의검증된반환경로가발급한비직렬화phase증거만새marker를생성할수있다. 단독result append/임의finish입력은그증거가아니다. 외부source refs와아직처리하지않은request의입력refs는역사자료이며현재권리/실제자료존재로승격하지않는다.

Sources는checkpoint에없다. 새facade에 exact Sources(repository=새facade)를현재호스트가명시bind한다. 다른facade의Sources를공유·복원하거나옛current_sources로대체하지않는다. phase작업용메모리복원은cache권위가아니며다음작업마다현재DB revision과대조한다.

## 원자성·호출·예외

잠금순서는제품gate→AI상태lock→단일SQLtransaction/advisorylock이다. 중첩core호출은같은phase에참여한다. phase는append/reserve/dispatch/cancel/settle/query_charge/query_outcome/finish_processed/review_processed/restart_reconcile로닫는다. 일반lock.__exit__에서무조건저장하거나execute전체를하나의SQLtransaction으로묶지않는다.

reserve는request/policy/attempt/payload binding/closing storage예약을함께확정한호출만new=True를반환한다. dispatch는현재실행의비직렬화owner와정확세대에서reserved→dispatched를durable확정한뒤에만client호출로이어진다. client호출동안제품gate/AIlock/SQLtransaction을잡지않는다. 내부client adapter가owner/세대/저장장애latch와호출1회를확인한다. close뒤늦은결과는저장하지않고다음open에서보수복구한다.

finish_processed는현재실제execute의receipt/결과검증뒤result+marker+hold해제+receipt제거를한transaction으로확정한다. review_processed도실제review경로의request/review/marker를원자확정한다. 기존synthetic review를유료호출권한으로승격하지않는다. 정상종료drain/직접금융UoW-closegate는P03내부5관문이다.

저장실패는업무AIDenied와구분하고같은DB-generation의모든AI facade에실패latch를공유한다. application/client의넓은catch가잡아도후속source/query/성공반환/marker생성을막는다. COMMIT불명은operation ID/input digest/revision/checkpoint hash/marker를정확재조회하기전성공이아니다. 확인불가면차단,자동write replay없음. 특히dispatch가unknown으로분류된실행은나중에commit이보여도client를호출하지않는다.

query는기존사전형식/deadline/범위/attempt/authorization검사→count+1 durable확정→현재Sources.validate→receipt/denial확정순서다. count증가전거부를무조건과금하지않는다. charge실패/unknown이면source조회0. source실패/Incomplete/ContractError/receipt초과/crash뒤에도count를환급하지않고원래예외분류를보존한다. request당16은facade/attempt/재시작전체에공유한다.

## 재시작

새open-generation첫AI factory만recovery barrier를실행한다. 같은세대의추가facade는다른실행의예약을취소하지않는다.

| 상태 | 복구 |
|---|---|
| reserved | 사라진owner의전송전예약을cancelled_before_dispatch로확정·비용/closing hold해제,marker/result생성없음 |
| dispatched | settle_unknown의미로unknown_charge·비용예약/scope차단유지·client재호출0 |
| settled | actual usage/시각/overrun보존 |
| unknown_charge | 비용예약·차단유지 |
| cancelled_before_dispatch | 기존취소사실과retain_result로남은hold보존 |
| terminal+검증된result/marker | 역사자료로복원·현재source검증없이현재사용가능으로승격금지 |
| terminal+result없음 | MISSING/None·남은hold/receipt보존·성공/marker합성금지 |

reserved취소시각은reserved_at,dispatched unknown시각은dispatch_at을사용해실제복구관측시각과구분한다. 기존reason enum을임의확장하지않는다. 새금융authority_generation은AIbook 초기화키가아니다.

## 용량·전송의 확정 개발 상한

기존record수+closing hold수≤capacity≤128,canonical record bytes+closing bytes≤byte_capacity≤8MiB,closing hold3records/196608bytes는그대로다. marker/auxiliary를그3개예약에서빼쓰지않는다.

제품auxiliary한도는8MiB,checkpoint encoded한도32MiB다. global metadata는최대1MiB를처음부터논리예약한다. request/policy/querycount/blocked/marker는정확record hash/ref와고정개수/길이로정규화하고긴원문을중복복사하지않는다. pending closing attempt마다별도의128KiB auxiliary slot을확보하며receipts≤32KiB·고정reason/marker/전이metadata가그안에서커지도록한다. 해당slot안의actual+remaining예약은일정해필수종료에용량증가가없어야한다. terminal정리후에도payload binding/정산/차단/querycount를지우지않고필요한compact정보를계속계상한다.

codec가필드별상한과global/attempt귀속을증명해야한다. 미래변경을귀속할수없거나slot상한을증명할수없으면reserve를거부하고client를호출하지않는다. 같은shared정보를여러attempt의사용량으로중복공제하지않는다. 원문records와auxiliary는필요시base64로보존해escaping팽창을유계화하고outer고정metadata≤1MiB를포함한최악encoded크기를계산한다. 보수예약은새지출/한도증액허가가아니다.

읽기는길이/revision/hash/count metadata를먼저확인하고최대32KiB payload chunk/응답256KiB/총32MiB로제한한다. 유계파이프입출력·전체deadline·동일revision/hash를검사하며큰json_agg/unboundedstdout뒤사후검사로대체하지않는다. 쓰기chunk/staging도전체32MiB·개수상한·원자publish/rollback/unknown을검증한다. 자동eviction/journal증식없음. 이는논리payload/전송한도이며실제RAM/WAL/disk보장이아니다.

## migration과 두 순차 구현 단위

0001_artifacts.sql bytes/checksum e82d7893e8a374ff8ff8409b5e2f003c80a11bc69620982a5abaf1e0bca96ee3는불변이다. 새product_schema.py의동일명시registry를artifacts/AI factory가공유한다. 기존v1 checksum/구조/설치함수본문·속성을먼저검증하고0002_ai.sql에서version=1 check를정확확인뒤known1/2로교체·AI구조/version2를한transaction으로적용한다. 신규는1→2,기록결손/future/checksum/함수손상은거부한다. 알려진v2를artifact factory가future로오거부하지않는다. 금융schema1~3/lifecycle/image/pin은불변이다.

v2 DB에v1코드로자동downgrade하지않는다. 실패시transactionrollback/자기자료보존·검증된v2코드또는별도검증된합성복구사본을사용한다. 삭제/권한확장/실계좌는없다.

- 2b-1 저장기반: product_schema.py/product_ai.py/0002_ai.sql/test_product_ai.py신규,product_artifacts.py loader위임,필요한test_product_artifacts.py한정. codec/marker/CAS/유계I/O/원자publish/1→2호환을수용한다. AIcore연결·client호출은아직수용하지않는다.
- 2b-2 core연결: synthetic_investment_ai.py/product_ai.py/test_product_ai.py와필요한기존AI회귀만. exactfactory/phase/query barrier/owner/restart/latch를연결한다. application/domain추가변경필요는root에게파일/이유를인계하며범위를자동확대하지않는다.

각단위는의미있는mock와root의실제private syntheticDB·독립일반/보안·commitpush로인계한다. 검사행렬은자문보고의dispatch0/실패quota16/knownsettlement보존/marker위조거부/closing포화/CAS/upgrade rollback/COMMIT응답유실을따른다. 내부2b/후속readmodel/현재권리/scheduler/P28-05/전체P03은현재NOT RUN·미완료다.
