# P28-02 로컬 조회·인증·실행 연결 계약 v1

상태: root 설계 초안. 제안 경로·프로토콜이며 아직 구현·배치되지 않았다. P28-01 정적 설계 산출물은 독립 일반/보안 검토 지적0으로 준비됐으며 실제 화면 검수는 FUP-P28-002에 남아 있다. 설계 자문7건을 반영하고 조회인증을 쿠키 없는 origin-memory token으로 정리한 root revision5이며 독립 최종 확인 전이다. 실제 운영값/계좌/키/주문 권한을 추가하지 않는다.

## 소유와 호환

새 계약은 product-read-v1이며 data-v1/execution-v1/operations-v1/serialization-v1을 소비한다. 기존 DTO/schema와 migration1~3, frozen baseline7은 변경하지 않는다. 생산자는 application 서비스와 소유 저장소, 소비자는 새 read-model 어댑터·조회 HTTP·브라우저다. 제어는 기존 approval/execution 서비스의 보호 CLI/IPC만 소비한다. UI 표시 DTO를 역직렬화해 ApprovalRecord/PrincipalEvidence/SessionRecord를 생성하지 않는다.

기존 reporting.presentation_data는 ReportPresentationRequest의 현재 권리를 검증한 synthetic 보고용 함수다. 자산/대사 표시의 출발점으로 쓰되 이 함수의 schema_version=1을 새 대시보드 전체 schema로 재해석하지 않는다. orders.reason=orders_not_queried는 주문이 없다는 뜻이 아니다. 별도 주문 저장소의 현재 관측을 얻지 못하면 MISSING/UNKNOWN이다. report_id/hash/cursor와 대시보드 snapshot_id/version을 구분한다.

제안 구현 파일은 domain/product_view.py, application/product_view.py, ports/product_view.py, runtime/product_http.py, runtime/product_cli.py, runtime/product_composition.py, adapters/product_read.py다. 실제 존재한다고 보고하지 않는다. 승인/금융 모듈의 소유 transaction을 새 view가 쓰지 않는다. P28-03에서 조립·영속 어댑터를 만들고 P28-04에서 보호 사용자 제어, P28-06에서 HTTP/화면을 연결한다.

## 두 종류 세션

1. ViewSession: 합성개발 프로필 절대만료300초·자동연장없음·최대8세션. 민감 조회만 허용하는 서버 메모리 세션. 조회 범위(environment/account/screen), 현재 권리 version, authority_generation, issued_at/expires_at, revoked 상태를 결속한다. 제어 principal 또는 approval을 내포하지 않는다.
2. ControlSession: 기존 SessionRecord의 principal_ref/policy_ref/code_version/state_version/clock_epoch/liveness_deadline. 인증된 보호 CLI/IPC만 갱신한다. 브라우저 열기·조회·로그인·오류 재시도·폴링·페이지 복원은 제어 이벤트가 아니다.

ViewSession이 유효해도 control이 paused/stopped/expired일 수 있다. UI가 running을 표시해도 execution은 현재 DB·principal·policy·generation·liveness를 admission/dispatch/egress에서 재검사한다. 프로세스 종료·절전·시계 역행/불확실·IPC 단절은 기존 fail-closed 규칙이며 금융 자동 재전송/자동 resume가 없다. 이미 제출한 주문의 조회/체결·대사는 별도 허용 범위로 유지한다.

## 로컬 HTTP와 조회 인증

초기 지원은 현재 macOS 호스트의 synthetic 환경. 서버는 127.0.0.1의 한 주소/기동 시 고정된 포트만 바인딩한다. 0.0.0.0·LAN·프록시·remote tunnel·IPv6 자동추가 없음. loopback 자체는 인증이 아니다. Host는 기동 때 확정한 정확한 host:port만 허용하고 전달 헤더로 덮어쓰지 않는다. CORS 허용 없음. API는 같은 origin의 전용 헤더 X-QH-View: 1과 아래 origin-memory token과 서버 ViewSession을 함께 요구하며, Origin이 있으면 정확히 비교하고 없으면 Sec-Fetch-Site: same-origin을 요구한다. null/cross-origin·다른 Host·알 수 없는 메서드·절대 URL target을 거부한다. DNS rebinding·브라우저 외 임의 클라이언트는 capability/권리 검사 없이 조회할 수 없다. same-OS-user/관리자 침해에 대한 방어는 주장하지 않는다.

조회 최초 연결은 보호 로컬 CLI가 발급한 단회·60초 만료 코드의 수동 입력 POST /view-session으로만 수행한다. 코드는 OS CSPRNG256bit 이상으로 발급하고 서버에는 비교용digest만 보관한다. 코드는 URL/명령줄/프로세스환경/로그/HTML소스/브라우저영속저장에 넣지 않는다. CLI의 사용자 명시 요청으로만 발급하며 요청계좌·현재조회권리·서버기동세대에 결속한다. 입력 폼은 same-origin CSRF nonce·정확한 Origin을 요구한다. 소비/실패횟수(코드당3회·동시미소비코드1개)/최대크기(POST4096bytes)/만료를 서버가 검사하고 실패시 새 코드 자동발급 없음. 코드의 지식만으로 금융 권한을 주지 않는다.

인증 성공 응답은 OS CSPRNG256bit 이상의 독립적인 opaque view_token과 비밀값이 아닌 view_generation, 요청ID를 no-store JSON에서 한 번 전달한다. 서버에는 token 비교용digest와 principal/scope/정확origin/server_generation/view_generation/발급·절대만료만 보관한다. 클라이언트는 토큰을 해당 origin의 모듈/closure 메모리에만 보관하며 cookie/URL/명령줄/환경/HTML원문/로그/브라우저영속저장/window.name/탭간공유에 넣지 않는다. 최초인증코드와 view_token은 서로 다른 값이고 금융principal/권한으로 변환하지 않는다. 민감 GET과 종료POST는 X-QH-View-Token과 X-QH-View-Generation 헤더를 요구하며 현재 서버세션/권리와 모두검증한다. fetch는 credentials: omit이며 서버는 인증cookie를 발급하거나 Cookie/HTTP자동인증을 조회권위로 사용하지 않는다. login/end 포함 모든응답에 Set-Cookie가 없다. UI는 자체 정적 스크립트와 textContent 출력만 사용하고 원문 HTML/inline event/eval/임의리다이렉트·외부자원을 받지 않는다. 토큰의 JavaScript 메모리 노출 위험을 CSP/엄격한 출력/현재권리·절대만료로 줄이되 XSS/같은OS사용자·관리자 침해 방어를 보장하지 않는다.

POST /view-session/end는 조회세션만 회수한다. 같은 Origin/현재token/generation을 요구하고 해당서버세션을무효화한다. 클라이언트는 현재token/generation으로 제한된단회종료요청을먼저구성하고 login_epoch증가·기존조회pending취소·장기보관token/민감DOM삭제를수행한뒤 종료요청을한번발송한다. 종료발송버퍼는응답/timeout시즉시해제하며자동재전송하지않는다.  종료확인실패도 금융logout/stop으로 확대하지 않는다. 해당token을상실했으면 서버절대만료300초 또는 보호CLI의명시조회회수로차단한다. 지연된로그인JSON/오류/종료응답은 발송당시epoch/request_id를검증해이전epoch이면무조건폐기한다. cookie공유/Set-Cookie변경이없으므로 다른세대/탭의인증상태를브라우저가자동변경하지않는다. 새로그인은새token/generation을발급하며기존token을연장/덮어쓰지않는다. 서버활성/고아발급세션합계최대8개·미만료5분범위를유지하고초과429, 누락token은401이다. token미채택/상실에도서버의기존세션이만료될때까지상한에포함한다. 재시작은모든viewtoken을폐기하고새server_generation을확정하며세션권위를디스크에서복원하지않는다. 이계약에는cookie잔존장부가필요하지않다.

브라우저창닫힘은감지보장이없으므로 서버절대만료/명시회수가최종통제다. 모든민감GET은처음과직렬화직전에현재권리·view만료/회수·generation을재확인한다. 회수경합은아래권리coordinator/응답commit gate로순서를정하며이후신규응답을차단한다. 이미전송된자료의회수/스크린샷제거를보장하지않는다. 제어CLI종료는기존control세션차단규칙을따르고view인증/폴링은liveness를갱신하지않는다.

## Endpoint와 불변 read model

GET /api/v1/view?screen=<six-screen-id>&cursor=<opaque>만 민감 조회를 제공한다. screen은 assets/analysis/candidates/orders/investment-ai/operations 고정 목록. 계좌·환경은 인증세션에서만 결정하고 query의 임의 account_ref로 바꾸지 않는다. HTML/static GET은 허용목록 경로만, 임의파일/디렉터리조회 없음. 금융 승인/철회/중단/취소/청산/재개 endpoint는 없다. 메서드별 allowlist 외는 405, 경로 미등록은 404. 요청본문은 인증2종 POST에서만 제한적으로 받고, API GET본문·중복키·잘못된 UTF-8·과대헤더/쿼리·비정상 URL decoding을 거부한다.

### 화면별 data와 조회 포트

다음 포트는 신규 제품소유 읽기 전용 제안이다. 기존 ReportRepository의 get/append를 목록 API라고 부르지 않는다. 각 screen은 items라는 단일 주목록만 페이지화한다. details는 주목록 행의 제한된 요약이며, 전체 상세는 같은 endpoint의 item_id 선택자(세션 scope·snapshot membership검사)로 한 건을 조회한다. 주목록 이외 통화별 summary는 최대2통화·20필드의 별도 고정 구조다. 상세 내 하위목록은 최대20행과 complete/missing_scope를 표시하고 초과 시 부분표시 및 P28-06 별도 drilldown을 요구한다. 임의 중첩 전체 덤프는 금지한다.

| 화면 | 기존 생산자 → 제안 조회 포트 | 필수 data·안정 정렬키 | 미제공/nullable |
|---|---|---|---|
| assets | valuation/reporting와 실행DB의 동일 cursor 관측 → ProductQuery.assets | summary:통화별 L/H/F/B/U/D/A, holdings items:instrument_ref/quantity/unit/valuation/state, reconciliation scope/status/reasons, risk blocks, report/snapshot/cursor refs; instrument_ref 오름차순 | 미평가 금액/FX null+MISSING, 주문 미조회 unknown. 자산합계 null은0 아님 |
| analysis | research/document/market 결과와 manifest → ProductQuery.analysis | analysis_id/version/input_refs/as_of/strategy_ref/evidence/assumptions/counterarguments/validation/expiry; created_at 내림차순+ID 오름차순 | 데이터/분석 미수집 DISCONNECTED/MISSING, 완료된 빈목록만 EMPTY |
| candidates | target와 승인DB 읽기 → ProductQuery.candidates | candidate_ref/version/hash, target_mode(full/partial), target_scope/omission_meaning, instrument/side/quantity/price/currency, policy refs, approval outcome/expiry/consumption, replaces/ref; created_at 내림차순+ID 오름차순 | 목표 partial은 조회부분완전 partial과 별개. scope/생략의미 미확정이면 BLOCKED. 미제공승인은 UNKNOWN |
| orders | 실행DB와 ledger 대사 → ProductQuery.orders | intent/attempt/order/candidate/approval refs, quantity/filled/remaining/cancel status, reservation/cost/currency, ledger/reconcile refs, unknown/finality; created_at 내림차순+ID 오름차순 | broker번호 미확인 null+UNKNOWN; 조회실패는 주문실패 아님 |
| investment-ai | investment_ai 검증 저장결과 → ProductQuery.investment_ai | job_id/role/input_refs/output_validation/evidence/status/reason, provider/model/usage/budget_state; created_at 내림차순+ID 오름차순 | 미연결 provider/model/비용 null+DISCONNECTED/MISSING, 0 비용 추정 금지 |
| operations | runtime/ops 소유 상태·delivery/backup manifest → ProductQuery.operations | job_id/kind/status/reasons, connection readiness, controlstate/liveness 관측, report/delivery refs, backup/restore/version refs; created_at 내림차순+ID 오름차순 | 관측 못한 제어/백업/복원 null+UNKNOWN, 보고 미전달과 거래실패 구분 |

모든 item은 source_refs, source_created_at, as_of, knowledge_cutoff, completeness, missing_scope, state, reason_codes를 갖는다. optional 업무값도 필드 자체는 유지하고 null+reason으로 빠짐을 명시한다. 원문 증빙은 공개 allowlist의 제한된 텍스트 요약만, URL은 허용 스킴/출처 표시와 권리검사 후 별도 링크이며 HTML로 주입하지 않는다. 기존 업무상태와 표시상태의 매핑은 값별 allowlist이며 알 수 없는 enum은 UNKNOWN으로 차단·진단한다.

응답 envelope 필수: contract_version=product-read-v1, environment=synthetic, synthetic=true, display_account_ref, view_generation, request_id, response_sequence, snapshot_id, created_at(조회 snapshot 생성시각), as_of, knowledge_cutoff, source_revisions, scope, screen, state, reason_codes, data, pagination. 실제 principal/nonce/view_token/실계좌/키/내부DB경로/명령payload는 포함하지 않는다. 금액·수량·가격은 canonical decimal 문자열과 통화/단위·표시자릿수를 동반하며 JSON float 금지. UTC Z 시각·시장 timezone·거래일·근거를 따로 둔다. KRW 누락은 null+MISSING이며 0·빈배열로 변환하지 않는다. 검증된 FX·동일cutoff 없이는 NAV 합산을 제시하지 않는다.

state는 READY/PROVISIONAL/UNKNOWN/EMPTY/ZERO/MISSING/FAILED/STALE/EXPIRED/BLOCKED/DISCONNECTED의 표시용 정규화다. 원본 업무 상태를 별도 필드로 보존한다. READY는 현재 입력·권리·완전성을 확인한 조회라는 의미이며 주문 가능/보고 확정이 아니다. EMPTY는 완전 조회에서 결과 없음, ZERO는 확인된 실제0이다. 부분자료는 partial과 missing_scope를 표시하며 실패/unknown을 성공·미접수로 추정하지 않는다. errors는 고정 code/request_id/공개가능한 reason만 주고 예외/SQL/비밀값을 넣지 않는다. 인증실패401·범위/회수403·snapshot/cursor불일치409·만료410·과대413·준비불가503을 구분하며 오류 응답에도 민감 data/cache/로그 원문 없음.

financial read는 같은 저장소의 read-only repeatable snapshot transaction과 ledger cursor/approval/intent version으로 묶는다. 외부 시세/문서/보고는 revision vector와 cutoff를 함께 고정한다. 여러 저장소를 원자적으로 읽지 못하면 시점·inconsistent/partial·영향화면을 표시하며 하나의 확정 합계로 합성하지 않는다. 화면 수치와 현금 L/H/F/B/U/D/A는 기존 검증된 서비스가 산출하고 브라우저가 다시 계산하지 않는다. 임의 SQL/JS 표현식을 받아 실행하지 않는다.

구성요소마다 source_created_at/as_of/knowledge_cutoff/state/completeness와 freshness_policy_ref/display_valid_until을 둔다. 같은 금융 읽기 cursor와 공통 cutoff가 증명되는 구성요소만 envelope as_of/knowledge_cutoff를 채우고, 아니면 null에 coherence=INCONSISTENT 또는 PARTIAL·missing_scope를 표시한다. created_at은 조회 snapshot 생성시각이며 입력시각을 대신하지 않는다. envelope state는 인증/회수오류(오류응답) 다음 FAILED→DISCONNECTED→UNKNOWN→MISSING→BLOCKED→EXPIRED→STALE→PROVISIONAL 우선순위로 필수구성요소의 최악상태를 택한다. 선택구성요소는 summary.partial/reasons에 반영한다. 전부 빈 완전주목록은 EMPTY, 단일금액 조회의 확인된0은 ZERO, 그외는 READY다. 구성요소의 ZERO가 다른 MISSING을 덮지 않는다. 신선도정책/유효기한 없으면 UNKNOWN이며 운영값을15분에서 추정하지 않는다. FX/비율/표시반올림도 serialization-v1의 decimal 문자열·명시단위·서버 산식을 따른다.

조회 snapshot은 read transaction에서 생성한 제한된 불변 materialized 결과를 서버 메모리에 보관한다. HTTP 요청 사이 DB transaction을 열어두지 않는다. 합성 개발상한은 snapshot TTL60초·세션당1개·서버8개·전체16MiB(각2MiB·2000주목록행 이하)다. 자료가 넘으면 complete=false/missing_scope와 명시된 제한을 반환하며 숨은 잘림/미평가 확정 합계 금지. 페이지당100행은 한 screen의 items에만 적용한다. 만료/퇴거/회수/재시작/세대변경은 이전cursor에410, snapshot을 조용히 새버전으로 바꾸지 않는다. 현재권리 포트는 페이지마다 다시검사하며 보관 snapshot의 과거권리를 권위로 사용하지 않는다. 서버는 각 객체의 필수source refs와 고정 sort tuple을 함께 보관하여 같은 값/순서만 재사용한다.

페이지는 같은 snapshot_id/revision vector에 결속하고 안정 정렬키+고유ID를 사용한다. 커서는 서버서명/검증 opaque 값으로 scope·screen·generation·snapshot·position·만료에 결속하며 임의 offset/다른계좌 재사용 금지. page_complete와 dataset_complete/next_cursor를 구분한다. 페이지한도100행·응답UTF-8 1MiB·view조회 동시1·미처리요청2·요청10초·폴링최소15초는 합성 개발 프로필 값이며 금융/운영 기본값이 아니다. 한도를 넘으면 명시 truncated/partial 또는 오류, 조용한 누락/무한증가 없음. 부족하면 구조/페이지를 조정하고 baseline/Q27 완료예약 한도를 임의 증액하지 않는다.

### 현재 권리 정본과 응답 경합

신규 UserViewScopePort.current(principal,environment,account)와 DataRightsPort.current(source_refs,purpose,at)가 각각 최신조회범위/자료권리를 반환한다. 공급자는 제품소유 권한 서비스·자료권리 catalog이며 CLI의 명시된 승인/회수 연산만 변경한다. 현재의 ReportPresentationRequest.current_rights는 이 포트에서 새로 얻은 grant로만 구성하고 HTTP 입력/과거 report grant를 재사용하지 않는다. catalog가 없거나 조회 실패/시계불확실이면503/403으로 data를 내보내지 않는다.

관련 user-scope와 모든 data-rights revision은 동일 프로세스 권리 coordinator의 read/commit gate를 공유한다. 변경은 write gate 아래 revision증가·관련 ViewSession/snapshot 회수·읽기응답 취소를 수행한다. 응답은 read gate 아래 현재 revision과 session을 재검증하고 bounded 직렬화/송신을 마친다. 송신시간 제한 초과면 끊고 lock을 해제한다. 회수 완료는 gate 획득 후 이미 시작된 응답의 경계가 종료됐을 때만 확정하며, 그전에 전송된 바이트 회수는 보장하지 않는다. 외부catalog revision을 원자적으로 읽을 수 없으면 신규응답을 차단하고 제품프로세스 내 coordinator와 동기화하기 전 재개하지 않는다. 다중 프로세스/분산 권리 coordinator는 현재 지원하지 않으며 같은 OS사용자/관리자 침해 방어로 주장하지 않는다.

## 권리·캐시·순서·종료

Cache-Control: no-store, private; Pragma: no-cache; Referrer-Policy: no-referrer; X-Content-Type-Options: nosniff; CSP default-src self, connect-src self, frame-ancestors none, base-uri none, form-action self, 외부 자원 없음. 구체 CSP는 inline 금지 self 정적파일 구조와 함께 P28-06에서 검사한다. ETag/304는 민감 API에 쓰지 않고 매번 현재권리를 검사한다. localStorage/sessionStorage/IndexedDB/CacheAPI/serviceworker/다운로드·인쇄 자동실행 없음. 허용 읽기용 메모리만, view 종료·401/403/410·환경/계좌/generation 변경에 즉시 지운다. 권리철회 이후 과거 정상결과를 현재 데이터처럼 남기지 않는다.

인증 성공 응답은 no-store JSON의 view_generation/view_token/request_id를 반환한다. 클라이언트는 로그인요청 발송 당시epoch가현재값과같을때만 이를채택하고, 지연된응답/현재token누락을이전세대로fallback하지않는다. login_epoch는 로그인시작시코드입력POST를보내기전에먼저증가시켜기존요청/표시를지운다. 성공응답채택때같은epoch를유지하고view_generation/token만저장한다. 각 GET은 X-QH-Request-ID(클라이언트 제한 길이 난수)와 X-QH-View-Generation, screen/item_id/cursor를 명시한다. request_id는 서버가 길이/형식 검증 후 echo하며 권한 증거가 아니다. 최초 generation 없이 민감 GET을 허용하지 않는다. 서버 sequence는 인증·현재권리 검사 후 불변 snapshot 응답 확정 직전에 해당 view_generation/scope에서 원자적으로 할당하며 오류도 correlation과 요청 세대를 갖는다. 클라이언트는 요청마다 식별자와 현재 view_generation/screen을 붙여 응답을 검증한다. 서버 response_sequence는 세대·scope별 단조 증가한다. 성공/오류를 처리하기 전에 먼저 발송 당시 login_epoch와 현재epoch, request_id·scope·generation을 비교한다. 일치하지 않는 응답은 늦은401/403/410도 무조건 폐기한다. 현재epoch의 인증오류만 DOM/메모리를 지우고 epoch를 다시증가시킨다. 명시 종료/재로그인 시작도 요청취소 전에 epoch증가·민감표시 삭제를 먼저한다. 다른세대/계좌/화면·역순sequence·이전request는 폐기하며 금융권한갱신을 하지 않는다. 활성 탭/명시 조회에서만 폴링하고 hidden/pagehide/freeze는 요청중단·타이머중단·민감DOM/메모리 정리를 수행한다. bfcache pageshow.persisted도 즉시 지우고 재인증/현재조회 전 표시하지 않는다. 마지막응답시각/자료시점이 오래되면 STALE; 시계 불확실이면 UNKNOWN/차단이다. 클라이언트 정리는 편의이며 브라우저 프로세스/OS 복구/화면촬영에 대한 비밀파괴 보장이 아니다. 서버 만료/회수/권리검사가 권한 정본이다.

## 보호 CLI/IPC와 정책 변경

제품 제어 명령은 P28-04 구현 전에는 문자열 예시를 발명하지 않는다. 기존 domain.approval의 PrincipalEvidence/SessionRecord/ActionChallenge/ActionReceipt와 application.approval/execution을 연결한다. 제어 IPC는 private0700 directory/0600 Unix socket, 현재 OS소유자/peer credentials와 서버인증principal·계좌·environment·generation·role/action을 검사한다. macOS peer 검증은 실제 지원 API/설치 버전에서 P28-04 증명 전 활성화하지 않는다. 브라우저 view_token·조회초기코드는 IPC/금융 인증에 사용하지 않는다.

명령은 ID/단회nonce·action·canonical대상version/hash·expected_state_version·발급/만료·현재principal/session/policy/generation에 결속한다. 단순 JSON approved/principal 입력을 권위로 읽지 않는다. 사용자에게 후보·한도·가격·수량·통화·정책/만료·환경·계좌를 보여주고 정확한 대상으로 확인한 후 transaction 내 challenge소비/감사/행동/원장·예약을 기록한다. 동일 ID·동일payload는 기존결과, 상충payload/재사용nonce는 거부. 실패·timeout·unknown에 금융 자동 재전송 없음. protected receipt를 읽어 결과불명과 성공/실패를 확인한다.

정책 종류별 경계는 다음과 같다. target policy는 ApprovalSource/ExecutionInputs의 target_policy_ref가 정본이며 후보를 새로 재생산하고 이전 approval과 source 교체의 별도 판정을 요구한다. approval policy는 SyntheticApprovalPolicy와 approval_policy_ref가 정본이며 기존 replace_policy의 CAS/hold/감사를 재사용한다. execution policy는 SyntheticExecutionPolicy와 current_policy_ref가 정본이며 실행 DB가 target_policy_ref와 함께 현재 버전을검사한다. 새 binding/config policy는 기동·runtime소유 version으로 별도검증하며 위3정책의 동일ID를 공유하지 않는다.

여러정책/source를 교체할 때는 먼저 admission/dispatch/egress를 명시 차단하고 policy_change_pending을 영속한다. 기대 ref/version/hash·소유transaction별 CAS와 감사를 수행하고, 모두새로운 revision vector가 검증돼야 pending을 닫는다. 중간실패/재시작에는 차단을 유지하고 자동정책복구/자동resume/기존승인승격을 금지한다. 기존 사실/예약을 보존하고 사용자가 현재정책을 확인해 수동재개한다. 실제 구현에서 단일transaction으로 묶을 수 있으면 그경계를 증명하고, 여러저장소의 원자성을 주장하지 않는다.

정책 교체는 현재 정책ref/version/hash CAS와 명시사용자확인·감사로만 수행한다. 기존승인 대상policy/후보/hash와 현재값이 다르면 기존승인 자동확장·갱신 없이 신규admission/dispatch 차단, 진행중의도/unknown/예약은 사실로 보존한다. 이미 보낸 주문은 정책변경으로 취소되지 않는다. 정책 입력 누락/모호/불법값은 fail closed. 중단·취소·철회·청산·재개는 별도 권한/대상이며 같은 버튼/명령으로 합치지 않는다.

## 기존 영속성과 조립 차이

| 영역 | 실제 기존 코드 | 현재 한계·필요 인계 |
|---|---|---|
| 원장/실행 | adapters/postgres_execution.py, execution_uow.py와 PostgreSQL ledger 경로 | 실행 transaction 정본. 기존 PostgresLedger는 매번 UUID project를 만들고 context 종료에 자기 컨테이너를 정리하는 합성 시험용이다. 이를 제품의 재시작 보존 DB라고 부르거나 shutdown 때 기존 자료를 제거하는 경로로 조립하지 않는다. P28-03 소유DB/마이그레이션/안전종료 연결 |
| 보고 | adapters/synthetic_reporting.py SyntheticReportRepository | 합성 in-memory 보고 저장, 재시작 보존 어댑터 별도 필요 |
| 평가 | adapters/synthetic_valuation.py SyntheticSnapshotRepository | 합성 메모리 snapshot, 출처/원장cursor를 보존하는 어댑터 필요 |
| 연구 | adapters/synthetic_research.py SyntheticExperimentRepository | 합성 repository, 결과/lineage 영속 adapter 필요 |
| 투자AI | adapters/synthetic_investment_ai.py SyntheticAIRepository | 합성, 실제 공급자/지출 비활성. 운영 모델 활성화 별도 SG04 |
| 목표/승인 | adapters/synthetic_target.py, synthetic_approval.py | synthetic authority를 실제 사용자 인증으로 재해석하지 않음. 실행DB의 승인 transaction과 조립 |
| 문서/시세 | adapters/document_files.py, parquet_market_store.py | 파일/Parquet 저장 구현 존재. schema/권리/시점 manifest·DB와 일치·복원은 통합 증거 필요 |

### 제품 DB 연결·지원 타입·복원 seam

기존 ApprovalApplication/ExecutionApplication은 PostgresExecutionRepository 정확타입을 요구하고, 해당 repository와 ExecutionUnitOfWork는 PostgresLedger 정확타입·_ready를 요구한다. 이를 임의ducktype/plugin/subclass 허용으로 풀지 않는다. P28-03은 PostgresLedger의 명시적 product_synthetic 수명관리 진입점을 추가해 같은 정확타입 인스턴스가 제품소유 PostgreSQL 자원에 안전하게 연결되도록 확장한다. 기존 무인자 constructor/context의 disposable synthetic 검증 동작은 보존하며 migration1~3 checksum을확인한다. 제품 종료는 연결/소유프로세스만 정상종료하고 data/volume삭제는 호출하지 않는다. 기존 close의 down --volumes 경로와 제품 stop의 분기는 별도 시험한다. 새진입점은 synthetic만, private root/소유자/0700·0600/심볼릭링크·환경binding/단일process잠금·고정image·localunix Docker 검증을 요구한다. 실제운영 저장/암호화관문을 통과했다고 하지 않는다.

기존 PostgresExecutionRepository의 restart/restore/rotate 지원경로로 새issuer/generation을 결속하고, 생성자가 기존DB를 거부하는 검사를 삭제하지 않는다. 실제 재시작연결 가능성과 새authority를 DB백업에서 되살리지 않는 별도수립은 P28-03 검증 전 미확인이다. 이 seam이 부족하면 새명시적 제품수명관리 연산을 정적범위로 추가·검토하고, 금융권한 typeguard를 완화하거나 기존approved JSON을 import하지 않는다.

보고/평가/연구/AI/목표의 새영속저장은 기존 canonical DTO bytes/hash/ID/version/lineage와 원본source refs를 보존하고 append+목록색인을 같은transaction으로 갱신한다. 부분저장·참조결손을 완성/확정조회로 노출하지 않는다. 승인/세션/handle/nonce/capability는 이 비금융 DTO 저장소의 restore 대상이 아니다. 금융사실은 원래DB·관련ledger/inbox/outbox/예약에 보존하고 새generation으로 실행권한만 무효화한다. 새로운 product metadata/migration이필요하면 additive 별도version으로 검토하며 기존3개 migration·frozen baseline 수정은 하지 않는다.

제품은 tests/product 또는 scripts/check_execution.py의 underscore fixture함수에 의존하지 않는다. composition이 기존 public ports/application과 제품소유 adapter를 명시 조립한다. 영속 JSON에 Python객체나 금융권한을 dump/load하지 않는다. 재기동은 reconciling·새authority_generation·이전세션/승인 무효화, 기존소비/의도/체결/예약 사실은 보존한다. 금융DB백업만으로 새authority를 되살리지 않는다. Q27 actualDB24/fixed40·P28 설계/구현·실제PG/SG 경계는 유지한다.

## 검증 인계와 수용

P28-03: 테스트헬퍼 없는 조립/영속 재시작/원자성/slot중복·긴작업·절전·시계변화·우선순위.
P28-04: 실제 local peer·principal인증, nonce/CAS/회수/정책교체·이전승인/대상상충·CLI단절·합성도입.
P28-06: 실제 HTTP/브라우저에서 외부origin/Host/null·CSRF·view코드중복/만료/초과·IDOR·권리회수경합·인증cookie/Set-Cookie미사용·다른origin/port로token미전송·login/end/401역순다중탭세대경합·token헤더/credentialsomit·저장없음·bfcache/hidden·역순응답·snapshot페이지·과대입력·마스킹·상태표시.
P29: 모든 REQ9/SC16 사용자 과업과 장애/보안/복원 통합. 합성 개발상한과 실제 성능/PG04 값을 구분한다.

현재 실제 구현·HTTP/IPC/브라우저·사용자인증·운영성능/실계좌 검증은 NOT RUN. root 문서/경로/소비자 정합성 확인과 독립 일반/보안 검토 후 설계artifact_ready만 판정한다. 필수 후속결함/Q27·이전제품단계 completion_dependencies가 해결되기 전 completed가 아니다.

## revision5 선택과 근거

2026-10-30 확인: [RFC6265 §8.5](https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5)는 cookie의포트별격리부재를명시한다. 앞선revision3/4의cookie+proof/세대별쿠키/만료장부는폐기한초안으로과거검토증거에보존한다. revision5의현재규약은쿠키미사용·origin메모리token·명시요청헤더·credentialsomit·서버절대만료다. 따라서 cookie포트유출·지연Set-Cookie의다른세대변경·브라우저cookie누적경로가현재설계에없다. 메모리token은페이지내스크립트에노출될수있으므로자체정적스크립트/CSP/안전출력/현재권리·5분절대만료를검증해야한다. 이는로컬조회계약선택이며금융웹권한추가가아니다. 실제브라우저/HTTP/공격재현은NOT RUN이고P28-06/P29수용관문으로남긴다.
