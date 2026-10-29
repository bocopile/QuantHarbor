# 권한·배포·운영·보고 계약 v1 — Q11

상태: Q11 명시 범위 보안·일반 독립 검토 통과. data-v1·execution-v1을 결합한다. 아래 자원·권한은 구현 목표이며 현재 배치/검증 완료가 아니다. 신규 유료 비용0, 사용자 시작/종료 로컬 모의 세션, 자동 failover 없음. 실제 API·계좌·제품 AI·외부 보고는 기존 PG/SG/AP를 충족해야 한다.

## 초기 배포·신뢰 경계

| 영역 | 권한/입력 | 강제할 경계·완료 작업 |
|---|---|---|
| 개발 | 공개 코드·합성 fixture·개발 DB | 실제 운영 볼륨/키 없음. C/D에서 실제 파일/네트워크 거부 시험 |
| 자료 수집 | 허용 공급자 요청·수집 저장소 쓰기 | 목적별 권리·크기/시간/유량 제한, ledger/order DB 쓰기 없음 |
| 연구/백테스트 | 고정된 읽기 dataset·합성/권리 허용 snapshot, 결과 전용 쓰기 | 별도 비특권 컨테이너/VM 작업, read-only root·명시 입력만 mount·capability 제거·네트워크 기본 없음. host home/프로젝트 비밀파일/소켓/DB/키 mount 금지 |
| 원장/대사 | 검증된 사건·조회 관측, ledger 소유 쓰기 | ledger writer만 이벤트/투영 transaction. 승인/주문 전송 권한 없음 |
| 제안/AI | 읽기 view·허용 자료·결과 저장 | 금융 쓰기/승인/실행 키 없음. 외부 AI는 별도 최소 egress와 SG04 필요 |
| 로컬 사용자 제어 | 정확한 후보 표시·사용자 결정, policy/approval 쓰기 서비스 | 네트워크 승인 endpoint 기본 없음. 초기 대화형 로컬 CLI·보호된 IPC, 사용자가 직접 확인 |
| 실행 제어 | intent/예약/dispatch DB 권한 | runtime 정책/epoch 검사. broker write key는 직접 읽지 않음 |
| broker egress | 지정 환경·계좌의 key와 최소 write API | 계좌별 유일 dispatch slot·세대 검사. 연구/AI/보고 접근 불가. 목적 host/TLS/요청형식 고정, 임의 URL·redirect·proxy 우회 금지 |
| 보고 | 지정 read-only view·보고 저장소 | 원장/승인/intent 변경 없음. 외부 전달은 별도 connector와 AP10 |

초기 로컬은 위 논리 모듈과 보호된 실행 경계를 조합한다. 신뢰된 제어 모듈의 같은 프로세스 배치는 가능하나 연구 코드와 같은 권한/프로세스로 실행하지 않는다. 환경별 DB·role·queue namespace·볼륨·계좌/키 참조를 분리하며 synthetic/paper/live 값 하나만 바꾸어 전환하지 않는다. live 자원은 Q31까지 생성/활성화하지 않는다. 같은 OS 사용자·worktree·폴더 이름·Python import 경계만으로 보안 격리를 주장하지 않는다.

실제 런타임 제품/고정 버전은 SG03/Q13에서 현재 호스트 가용성을 확인한다. 무료·기존 자원으로 강제할 수 없으면 경계를 약화하지 않고 해당 기동을 보류한다. 호스트 관리자/컨테이너 데몬 소유자는 신뢰 기반이며 같은 호스트 관리자 침해까지 막는다고 보장하지 않는다. 데몬 소켓과 privileged/host network는 연구 작업에 주지 않는다.

## 자격증명·설정·기동

- 공개 예제에는 스키마/더미 값만, 실제 연결 식별자·정책값·키는 비공개 별도 영역. ignore는 추적 중 비밀값을 보호하지 않는다. 실제 파일 읽기·이동·입력은 해당 연결 승인 후다.
- 환경·broker·계좌 ref·host·TR·key ref·capability·DB/queue namespace를 한 binding version으로 검증한다. 일부 누락·cross-environment·실전 host가 포함된 모의 설정은 기동 거부. 자동 fallback host/계좌·자동환전 없음.
- runtime 데이터 루트는 저장소/그 하위/심볼릭 링크 우회 경로를 거부한다. 사용자 소유·접근권한을 확인하고 private 디렉터리0700·파일0600 또는 동등 ACL을 요구한다. 합성 개발 DB/fixture는 별도 명시 synthetic 영역만 예외다.
- 키는 egress 해당 서비스에만 승인된 자격증명 저장소/보호된 파일 descriptor로 주입한다. 명령줄·공개 env dump·오류·모델 입력에 실리지 않게 한다. DB 비밀번호/보고 토큰도 서비스별 분리, 전체 host env 상속 금지.
- 운영 키 교체·폐기·외부 권한 변경은 대상/영향이 있는 사용자 승인으로 수행한다. 침해 의심은 신규 제출 중단·세션 차단·증거 보존, 자동 주문취소/청산이나 임의 키 폐기 없음.
- 실제 운영 데이터의 암호화 저장 위치·키 관리·보존은 PG01/API 전 초기 프로필과 PG04/05 확대 시 확정/검증한다. 일반 파일 권한만으로 디스크 암호화를 입증하지 않는다. 확보되지 않은 실제 데이터 저장/연결은 보류한다. 지금 공개 설계는 실제 비밀값을 읽지 않는다.

## 사용자 제어 인증과 권한

초기 승인은 사용자가 직접 실행한 로컬 대화형 제어 CLI에서만 받는다. 서비스 IPC는 OS 소유자·접근 ACL과 인증된 세션 principal을 검증한다. 단순 loopback IP·입력 user_id·보유한 candidate hash를 신원으로 신뢰하지 않는다. 웹 승인/Slack 버튼/외부 webhook은 초기 비활성이다. 나중에 도입하면 요청 서명·유효시간·nonce 재사용 방지·사용자/계좌 권한·CSRF/세션 검증을 별도 설계/시험한다.

제어 CLI가 표시한 canonical 후보와 사용자가 확인한 내용에 결정을 결속한다. 승인/철회/중단/재개마다 principal·session ID·action·대상/version/hash·시각·결과를 기록한다. IPC command ID·nonce는 한 번 소비하며 재전달은 기존 결과를 반환하고 상충 payload를 거부한다. 봇·모델·개발 알림 메시지를 사용자 금융 승인으로 변환하지 않는다. 동일 사용자 기기의 악성 관리자/직접 DB 변조 방지는 별도 신뢰 가정이며 DB 해시를 전자서명으로 표현하지 않는다.

중단은 인증된 사용자 또는 내부 장애 정책이 새 admission/dispatch를 차단하는 행동이다. 취소·청산·resume는 별도 권한과 대상 확인을 요구한다. 프로세스가 꺼진 동안 원격 증권사의 주문이 멈춘다고 표현하지 않는다.

## 단일 egress·장애 인수

계좌/environment별 유일 egress와 DB epoch/dispatch slot을 사용하고 서명된 임의 broker 명령을 다른 worker가 직접 보내지 못하도록 키/네트워크를 차단한다. 실행 worker는 고정 enum action과 submit용 intent ID 또는 cancel용 CancelCommand ID를 전달한다. action/ID 자체는 권한이 아니다. submit은 egress가 DB의 불변 의도·소비 승인·세대를 다시 검증한다. cancel은 별도 CancelCommand의 사용자/정책 권한·대상 broker ID·잔량·환경/계좌·세대·상태를 DB에서 다시 읽는다. 원 intent 존재나 원 주문 승인만으로 취소 권한을 부여하지 않는다. payload로 host·계좌·수량·권한을 덮어쓰지 못한다.

이전 egress의 종료와 외부 접근 차단, in-flight 요청의 결과를 확인하기 전에는 새 egress 제출을 열지 않는다. DB 연결/lease 상실 시 신규 전송 중단·진행중 attempt unknown·예약 유지. 자동 인수 없음. 외부 API는 DB transaction과 원자적이지 않으므로 dispatch 이후 철회·네트워크 단절은 execution-v1의 불확실성/최종성 규칙을 따른다. 주문 outbox는 intent 상태 확인 없는 자동 재전달을 금지한다.

## 로컬 세션·스케줄·자원

`Session`은 ID·principal·environment/account binding·정책/코드 버전·시작/종료·상태를 가진다. `stopped → reconciling → ready → running`, 장애는 paused/faulted, 종료는 stopping→stopped다. ready/running 진입은 완전 대사·관문/정책·데이터·권한·자원 확인과 사용자 수동 resume를 요구한다. 처음 켰다고 이전 주문을 다시 보내지 않는다.

`Session`은 인증된 제어 연결의 liveness를 권한 조건으로 갖는다. 정상 종료·로그아웃·감지된 IPC 단절은 즉시 paused/stopped로 전이하고 새 admission/dispatch/egress를 차단한다. 감지되지 않는 단절에는 명시한 liveness deadline을 적용하며 갱신 주체는 인증된 제어 세션뿐이다. worker/egress가 대신 갱신할 수 없다. 기한 값·검증 시계가 없거나 만료/시간 불확실이면 faulted로 차단한다. admission·dispatch transaction과 외부 호출 직전 egress는 DB의 running 문자열뿐 아니라 현재 principal/session/authority_generation·liveness deadline을 확인한다. 이미 보낸 요청은 취소됐다고 가정하지 않고 추적하며 조회·대사·수신 체결 처리는 허용된 범위에서 계속한다. 연결이 돌아와도 자동 재개하지 않는다. 합성 timeout은 Q13에서 고정하고 실제 세션 값은 첫 연결 전 초기 프로필에 둔다.

사용자 세션이 켜진 동안 해당 시장의 정규장 달력 기준15분 분석 slot을 생성한다. slot key는 environment/account/market/session/trading-date/UTC slot/전략버전이고 중복 실행을 막는다. DST·조기폐장·휴장은 버전 달력으로 계산한다. 놓친 slot을 재시작 후 몰아서 실행하지 않고 skip 사유를 남긴다. 아직 실행 중이면 중복 시작하지 않으며 오래된 결과는 만료 정책으로 폐기한다. quote 수집/실제 주문/보고 주기는15분으로 추정하지 않는다. OS cron·상시 daemon·앱 종료 뒤 감시는 생성하지 않는다.

작업 상태는 queued/running/succeeded/partial/failed/cancelled/expired. 업무 결과와 프로세스 exit를 분리한다. 작업마다 최대 입력/출력 크기·CPU·메모리·시간·디스크·큐 깊이·동시성·retry 상한을 적용한다. 누락은 무제한이 아니라 기동 거부다. 개발 합성 한도는 root가 버전 고정해 검사하며 운영 한도는 해당 관문에 연결한다. broker rate limit은 계좌/endpoint별 현재 capability를 따르고 미확인 값으로 호출하지 않는다. 접수 불명 write는 유량 재시도 대상으로 처리하지 않는다.

오류/혼잡 시 신규 분석·제출보다 기존 주문 조회·체결 수집·대사·중단을 우선하되 보호용 조회 몫/timeout도 제한한다. 자동 무제한 큐·재시도·모델 상향 없음. 프로세스 종료 시 미완료 작업/dispatch 상태를 영속하고 가능하면 조회/대사를 마친다. 강제 종료 후 재기동은 항상 reconciling이며 종료 처리의 성공을 가정하지 않는다.

## 감사·관찰·경보

감사는 정책/후보/승인/의도/체결/원장/대사/보고/전달 참조, action·결과·사유 코드·시간·버전·correlation을 구조화하여 저장한다. 실제 금융 상세는 비공개 감사 영역만. 토큰·원시 HTTP·프롬프트/뉴스 원문·SQL 연결 문자열·개인 식별값을 일반 로그에 넣지 않는다. 마스킹은 허용 필드 목록을 기본으로 하고 오류/예외/대용량 입력도 같은 경계를 적용한다. 감사 저장 실패는 금융 변경/신규 제출 차단 사유다.

관찰 항목: 세션/단일 실행자 heartbeat, quote/조회 지연·누락, unknown 주문·예약 나이, 대사 차이·미평가 자산, 한도/예산 예약·사용량, DB/outbox backlog, 오류·차단 사유, 백업/복원 상태. 공개 개발 기록은 수치 없는 비민감 결과 요약이다. 해시 연결·append-only 정책이 host admin 변조를 기술적으로 불가능하게 하지는 않는다.

초기 필수 경보 수단은 활성 로컬 제어 세션의 오류 표시·상태 저장이다. 표시/감사 경로가 실패하면 신규 제출을 멈추고 수동 확인·복구 후 resume한다. 외부 경보는 AP10 없이는 보내지 않는다. 사용자가 외부 경보를 필수로 채택한 이후에는 그 전달 불능도 동일 중단 조건에 추가한다. 앱/호스트 종료 중 알림 보장은 없다.

## Report·Delivery 계약

`Report`는 ID/version·environment/account scope·trading-date/as_of/knowledge_cutoff·ledger cursor/snapshot·policy/계산 버전·`provisional|reconciled`·미평가/미확정/대사 차이·자료권리·정정 이전ID·생성시각을 갖는다. 이전 보고를 덮어쓰지 않고 새 버전/정정 관계를 만든다. 부분자료를 확정 손익·NAV로 표현하지 않는다. AI 설명 실패가 결정론적 수치나 원장을 바꾸지 않는다.

`Delivery`는 report ID/version·destination의 비공개 ref·권한/자료권리 version·payload hash·request ID·시도와 `pending|sent|confirmed|failed|unknown|cancelled`를 가진다. 전송 직전 수신자·목적·기간·자료 권리를 재검사하며 revocation이면 보내지 않는다. 원장 transaction과 전송 완료를 묶거나 전송 실패로 거래를 재실행하지 않는다. 결과불명은 공급자의 전달 확인/멱등 보장이 없으면 자동 재전송하지 않는다. sent와 실제 동일내용 수신 확인을 구분한다. 정정은 새 delivery로 추적한다.

초기는 로컬 요청형 조회/보고만, 일일·주간·월간 보고 기능은 명시 job으로 구현한다. 시장 종료 후 보고는 달력과 대사 상태를 따른다. 자동 외부 보고 일정은 AP08/10과 PG04에서 별도 확정한다. 개발 Slack AP01은 투자정보 전송·주문 승인 권한을 포함하지 않는다.

## 내구성·백업·복원·보존

PostgreSQL의 금융 event·승인·intent·예약·outbox를 업무 transaction으로 기록하고 성공 확정은 영속 commit 후 반환한다. 원장 외 private 원천 증빙·정책 버전·데이터 manifest의 참조 무결성도 복구 범위다. Parquet와 DB의 독립 복사는 같은 시점 백업이라고 가정하지 않는다.

초기 개발은 합성 데이터로 백업 manifest(코드/schema·cursor·파일hash·완료상태)를 생성하고 독립 복원 영역에서 재생/참조/대사를 확인한다. 실제 모의 연결 전에는 PG01의 초기 운영 프로필에서 암호화·저장위치·보존·복원 가능한 백업을 확인한다. 지속 운영의 정량 RTO/RPO·보존·주기·담당은 PG04이며 지금 임의값을 채우지 않는다. 값 없는 자동 삭제/무인 운영은 비활성이다.

복원 순서: 신규 제출 차단→기존 egress 종료/차단 확인→격리된 새 private 자원에 복원→schema/코드/무결성/정책/참조 확인→기존 승인 소비·intent/unknown/예약 보존→현재 broker 전체 조회·체결·현금·보유 대사→필수 관문 확인→사용자 수동 resume. 오래된 백업에서 누락된 주문/승인을 자동 재생하지 않으며 불완전 기록이면 fail closed다. 복원 데이터를 live 자원으로 자동 전환하지 않는다.

백업 뒤 철회된 미전송 승인·소비된 nonce·세션은 broker 대사로 복원할 수 없다. 따라서 백업 복원 때 이전 모든 승인·사용자 세션·IPC nonce의 실행 권한을 일괄 무효화하고, 재인증과 새 후보 승인만 허용한다. 기존 주문/체결/unknown/예약/소비 이력은 증거로 보존하며 삭제하거나 재실행하지 않는다.

복원 세대 `authority_generation`은 금융 DB 백업에서 되살리지 않는 egress 제어 영역에서 새 불변 값으로 재수립한다. 이전 egress 종료/접근 차단 확인 후에만 새 세대를 활성화한다. 승인·세션·intent·dispatch에는 해당 세대를 결속하고 egress는 현재 세대만 허용한다. DB 안의 오래된 epoch/approved 표시로 현재 제어 세대를 갱신할 수 없다. 현재 세대를 확정할 수 없거나 이전 전송 경로가 살아 있을 수 있으면 재개를 거부한다. 이 구조는 호스트 관리자나 전체 제어 영역까지 rollback한 공격을 막는다고 주장하지 않는다.

기술적인 이전 코드 배포와 금융 사실 취소는 별개다. schema 변경은 expand/검증/전환 순서와 호환 계획을 갖고 파괴적인 down migration은 기본 금지. 복구는 새 snapshot과 정정 사건으로 추적하며 실제 거래를 되돌릴 수 있다고 주장하지 않는다.

보존은 운영 감사·개인정보·원시 공급자 자료·파생자료·가설별로 목적/기간/권리/삭제 책임을 분리한다. 공급자 권리 만료/철회 시 사용 즉시 차단하고 해당 보존 계약과 별도 승인된 삭제 절차를 적용한다. 초기 기간 미확정은 실제자료 무기한 보존 허가가 아니며 해당 수집/저장을 보류한다. 백업도 같은 권리/보존 범위에 넣는다.

## 인계·미실행

D01~07에서 접근/기동 거부·자원 한도·secret canary·주입 공격을 합성 검증한다. J/M/K는 보고 결과불명·중복/정정·감사 실패·세션 중단·DB복원·stale egress·키 없는 연구 접근을 검증한다. 현재 문서만 작성했으며 실제 ACL/컨테이너/키/DB/네트워크/백업·테스트는 미실행이다. 운영 값·실제 공급자/모델/계좌/전송 권한은 PG/SG/AP를 유지한다.
