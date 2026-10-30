# P28-02 — 조회·인증·실행 연결 계약

- 상태: 진행 — 정적 계약 artifact_ready·통합/완료 관문 대기
- 단계·선행조건: P28-01 정적 source/spec/mapping artifact_ready. 실제 표시 FUP-P28-002·Q27 최종 관문은 통합/완료 조건으로 보존. EXEC-DEC-003 적용
- 요청 근거·범위: 사용자 전체 계획 우선 실행·실패 후속 큐. 새 로컬 조회 계약 설계, 기존 금융 계약 변경 없음
- 담당: root 계약 통합, qh_architect 읽기 계약 검토 → qh_security_reviewer → qh_reviewer. 동시에 worker1/writer1·재귀0
- 입력 버전: main80403ab 기반·P28-01 화면명세4f90b5fe/매핑9e9a693f·reporting.presentation_data/ReportRepository·기존 approval SessionRecord/PrincipalEvidence/ActionChallenge·data/execution/operations/serialization-v1
- 소유 파일: docs/contracts/product-read-v1.md, 본 카드·큐/status/evidence는 root. 자문/검토자는 수정 없음
- Git: 원래 checkout 미커밋 변경 보존·Q27 고정 worktree 불변·commit/push/PR 없음
- 허용: 제한 qh_review 부모·명시역할모델/high·공개파일읽기/결과반환. 실제 계좌·키·금융·외부전송·새의존성·비용 없음
- 검증: 생산자/소비자/소유·버전호환·금액/시간/완전성·세션/캐시/회수·local-only·영속성 차이·보호IPC/정책교체의 실패 규약 검토. 구현/HTTP/IPC/제품 통합 시험은 NOT RUN
- 시간·비용: 각 읽기 검토600초·자동재시도0·기존구독

## 산출물과 완료 기준

[product-read-v1](../contracts/product-read-v1.md): 6화면 endpoint/envelope·현재권리·같은시점/페이지·권한회수/순서·조회와 control session 분리·브라우저 저장/종료·정확 Host/Origin·조회 단회인증·CLI/IPC·정책교체·기존 영속 adapter gap·검증 인계.

계약 독립 검토와 root 정합성으로 artifact_ready를 판정한다. 실제 P28-03/04/06 구현·검증과 Q27/P28-01 완료는 별도이며 그 전 completed가 아니다.

## 인계

- 실제 변경: root 계약 초안 작성. 기존 공통 금융 DTO/schema·SQL migration1~3·baseline7과 제품 소스는 변경 없음.
- 실제 확인: 그래프로 보고 생산자와 합성repository·승인세션 구조 확인. PostgresLedger가 UUID 임시DB를 만들고 context 종료에 정리하므로 제품 영속성으로 재사용할 수 없음을 명시.
- 미실행: 실제 HTTP/IPC/브라우저·사용자 인증·영속 재시작·금융/운영 검증.
- 다음: bounded 독립 설계/보안/일반 검토, 준비된 계약으로 P28-03 소유/실행 분해.

## 설계 검토·revision2

- Astra/high 설계 자문256.207초 정상반환, 보완7건. [근거](../evidence/product-p28-02-architecture-2026-10-30.json). 범위입력7SHA 불변, 시험/수정 없음.
- root가6화면 data/조회포트, 구성요소시점/완전성과집계상태, 제한된불변snapshot 보존/TTL/정렬, 현재사용자·자료권리정본/응답commit gate, 요청세대/오류역순, 정확repository/DB타입의제품수명관리seam, 정책종류별CAS/중간실패차단을통합했다. 합성조회상한은개발프로필이며운영값아님.
- 다음06독립보안→05일반검토. 실제API/IPC/재시작/제품검증은NOT RUN.

## 보안 보완·revision3

- 독립 보안245.118초·P2 2건: cookie 포트간공유와 지연 Set-Cookie의 다른세대변경. [검토](../evidence/product-p28-02-security-a01-2026-10-30.json). 원본SHA/실제미실행을보존했다.
- root는 cookie+origin 메모리256bit proof 결속, 세대별cookie이름/정확선택·해당세대만종료·지연로그인/종료응답과다중탭규약을revision3로보완했다. FUP-P28-003은 독립재확인대기이며 해결로올리지않았다.
- 05 독립 일반 검토 중, 이어06 원래2건 재확인. 구현/실제HTTP공격시험은후속P28-06/P29로 남는다.

## 일반 검토·revision4

- 독립 일반152.166초: 설계7건/보안2건은계약수준해소, P2잔존cookie수명1건추가. [근거](../evidence/product-p28-02-review-a01-2026-10-30.json).
- root는 절대Expires와 발급Max-Age미사용, 종료/고아proof와독립한 미만료발급8세대장부·재시작보존/권한복원금지·손상/시계불확실차단을보완했다. 현재06 집중재확인중이며 실제브라우저시험은미실행이다.

## 현재 revision5 — origin 메모리 토큰

- 보안 재확인212.249초에서 원래보안2건은해결됐으나 Date/Expires보정으로 cookie잔존수명지적이남았다. [근거](../evidence/product-p28-02-security-a02-2026-10-30.json).
- root는 초기조회인증을 cookie/Set-Cookie없는 origin-memory view_token+명시헤더·credentials omit로정리했다. 서버digest·5분절대만료·고아포함8세션·권리/세대결속은유지한다. cookie만료/장부초안은폐기했고과거증거는보존했다.
- 06최종재확인→05변경부분확인 후 계약artifact_ready만판정한다. 실제HTTP/브라우저/금융제어는NOT RUN.

## 최종 계약 산출물 준비

- revision5 SHA `35f6ed51edb43e04711f3dcec290c553bc4a5af201467a3110ae1bc64edd0977`. 독립 보안129.305초·일반73.609초, 원래지적해결·추가지적0·각최종입력불변. [보안](../evidence/product-p28-02-security-a03-2026-10-30.json)·[일반](../evidence/product-p28-02-review-a02-2026-10-30.json).
- artifact_ready=true는새계약의구현착수준비다. 실제API/IPC/브라우저/권리회수·제품시험은NOT RUN, status in_progress·원래Q27/P28-01 통합/완료관문유지. FUP-P28-003은계약지적해소로해결하며실제시험을PASS로올리지않는다.
- 다음 P28-03 내부1단위 제품DB수명관리구현. 기존6화면/정확금융계약·migration1~3/frozen baseline을보존한다.
