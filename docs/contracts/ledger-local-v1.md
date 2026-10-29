# 合成 로컬 원장 계약 v1 — Q20

상태: root 구현 기준. data-v1·serialization-v1을 보존하는 추가 명세다. 실제 계좌 입력·주문·가용금·원가/세무·실제 대사는 이 범위 밖이다. EXEC-DEC-001에 따라 Q19 운영 관문을 대기 상태로 유지하고 진행한다.

## 입력·경계

`SyntheticLedgerSubmission`은 environment=synthetic, account_ref, source_kind, source_event_key, source_revision(1부터 연속 정수), predecessor_revision(null 또는 직전), mapping_version, event_type, effective_at, revision_mode, cash_legs, position_deltas, evidence_refs, completeness, baseline 정보를 갖는 닫힌 불변 계약이다. 내부 입력 버전은1. 원천 키/종목/단위는 기존 identifier 검사를 사용하며 실제 BrokerObservation에서 자동 전환하지 않는다. 개별 execution ID·결제/예약 포함 관계가 미확인인 조회값을 체결 증분으로 해석하지 않는다.

`append`는 accepted/duplicate/quarantined 중 하나를 반환한다. 동일 의미 입력의 재전달 시 원래 결과를 반환하고 새 경제 사건을 계상하지 않는다. 계좌/환경/원천키/revision은 식별키다. 같은 키의 상충 payload는 기존 원장을 보존하며 충돌 근거를 추가한다. revision 선행 누락·불완전 입력·미지원 의미는 관측/판정으로 격리한다. 기계적 schema 오류는 원문 없는 ContractError로 거부한다.

초기 범위는 사용자 선택과 무관한 합성 fixture다. 원장에 actual paper/live 환경을 받아들이거나 권한을 자동 승격하지 않는다. 이벤트 수·legs·증빙·JSON 크기·시간/숫자 한도를 코드에 명시하고 초과 시 부분 성공으로 숨기지 않는다.

## 금액·수량·현금

현금 각 leg는 명시 계정·KRW/USD·정확 decimal·trade/settlement 기준이다. 각 journal에서 통화별 합계0. 다른 통화 상계 금지. 수량은 instrument_id/venue_id/mapping_version/unit의 결속과 부호 있는 변화량을 기록한다. `settled_cash`, `unsettled_receivable`, `unsettled_payable`과 명시 상대 계정을 구별한다. 수수료·세금·외부 입출금·배당·환전·결제는 구분된 사건으로 증빙을 요구한다.

매도대금을 미결제채권으로 기록했으면 결제 사건은 결제현금/미결제채권 계정 간 이동이고 수량을 다시 변경하지 않는다. 가용금·예약금·증권사 매수가능액의 포함 관계는 미확인 상태로 남겨 null/reason으로 표시한다. settled cash를 가용금으로 이름만 바꾸지 않는다. 미확정 비용을0으로 채우지 않는다. 완전한 기초 보유/현금 범위의 별도 합성 baseline 없이는 누적 변화만 알려진 것으로 표시한다.

소수는 기존 정수20/소수18 범위를 사용한다. 합산/반전은 정수 기반 고정소수로 수행해 전역 Decimal context의 영향을 없앤다. 저장 범위 초과 거부. DB는 무제한 numeric+정확 범위/scale CHECK를 사용해 numeric(38,18)의 사전 반올림을 방지한다. DB에 직접 넣은 과대 정밀도·NaN·Infinity도 거부한다.

## 정정·효력·지식 경계

full replacement revision만 지원한다. 원본은 revision1/predecessor null. 다음은 직전 유효 revision+1/predecessor 일치와 기존 사건을 참조하는 correction_of를 요구한다. 과거 동일 revision/hash는 duplicate, 상충은 quarantine; 선행 누락은 quarantine. 격리된 기록을 임의 자동 승격하지 않으며 재처리의 새 판정을 기록한다.

후속 replacement는 기존 유효 replacement의 정확한 reversal과 새 replacement를 같은 transaction으로 추가한다. 하나의 대상을 두 번 반전할 수 없다. reversal은 별도 내부 source identity, 원천 revision 고유키는 replacement만 소유한다. 둘 모두 같은 correction bundle/recorded_at에 속한다.

- 소급 정정 `retroactive`: 이전 replacement의 effective_at과 동일한 시점에 reversal/replacement.
- 장래 변경 `prospective`: 명시 T가 이전 effective_at 이후이며 처리 시각보다 미래일 때 T에 둘을 같이 배치한다. T 이전은 이전 상태, 이후는 새 상태.
- 아직 발효하지 않은 replacement를 다시 정정하거나 효력일 자체를 소급 이동하는 복잡한 변경은 quarantine. 연결된 결제/기업행동 영향이 해소되지 않았다면 projection 불완전으로 표시하고 확정 가용금/대사로 승격하지 않는다.

계좌별 stream row를 잠근 뒤 sequence와 recorded_at을 부여한다. sequence 범위1..2147483647, 소진은 실패. 기록시각 역행 거부; 수정 묶음은 같은 기록시각. 공개 cursor는 완결 transaction/bundle 끝만 허용하고 reversal만 포함한 중간 cursor를 거부한다. 격리/충돌도 해당 기록시각/cursor와 결속한다.

`replay(account, as_of, knowledge_cutoff, cursor, mode, reducer_version)`는 cursor 및 recorded_at≤knowledge_cutoff인 완결 묶음을 선택해 effective_at≤as_of인 signed events를 적용한다. 최신 revision만 먼저 고르는 구현은 금지한다. 미래효력 사건을 앞당기지 않는다. `as_known`은 해당 지식 경계, `restated`는 명시 이후 경계이며 원천 당시 이용 가능성 검증을 주장하지 않는다. 동일 입력·버전은 동일 canonical 결과. 과거 projection은 불변이고 이후 projection은 supersedes 관계로 연결한다. Q20 `LedgerProjection`은 평가/실제 대사까지 포함한 PortfolioSnapshot이 아니다.

## Canonical·원자성

`submission_hash`는 전달 시각/DB 할당 ID/sequence를 제외한 닫힌 의미 입력 schema hash다. `LedgerEventBody`는 sequence·recorded_at·전체 경제내용·correction/evidence를 포함한다. 논리 event의 `payload_hash`는 body의 canonical hash를 envelope에 별도 저장하므로 자기 해시 재귀가 없다. 기존 prefix/정규화/unknown field 거부를 유지하고 등록 schema만 추가한다. 사용자 지정 제외필드 API는 없다.

PostgreSQL migration0002를 추가하고 0001/frozen 계약은 변경하지 않는다. account별 잠금→검증→event/journal/correction→projection/cursor→outbox가 단일 transaction이다. 어느 경계 실패든 rollback. DB append 함수 또는 하나의 유지된 session으로 처리하며 여러 독립 psql 호출로 원자성을 흉내 내지 않는다. immutable 자료 UPDATE/DELETE 거부, 환경/계좌 FK·source revision·reversal 고유성·commit 시 통화별 균형/정정 결속 검사. DB 관리자까지 불변이라고 주장하지 않는다.

합성 consumer는 inbox(consumer,message)와 업무 결과/cursor를 한 transaction으로 처리한다. 같은 key/hash는 duplicate, 다른 hash는 collision 기록과 기존 상태 보존. commit전 실패시 inbox도 rollback; commit후 ACK 유실은 재전달로 중복 효과 없음. outbox immutable message와 delivery 상태 분리. 외부 exactly-once 보장 없음.

## 저장 경로·검증

새 의존성 없이 고정 이미지의 합성 PostgreSQL/psql Unix socket을 사용한다. adapter는 합성 전용 경로이며 임의 SQL·기존 DB/credential 지정 인자를 받지 않는다. 전용 runner는 새 UUID Compose 프로젝트만 생성·정리하고 raw SQL/daemon 오류 대신 고정 이유 코드를 출력한다. migration 순서/checksum, 두session 경합, 실패/연결종료 rollback, inbox/outbox, 재생 및 dump/restore를 실제 실행한다. tmpfs 검증은 전원 장애 내구성 증거가 아니다.

생산자: Q20 합성 입력/application. 소비자: Q21 평가·대사, Q22보고, Q23연구, Q24후보, Q27실행. 현재 실제 broker 연결은 없음. 추가 schema만 등록해 기존 canonical golden 유지. 시험은 decimal/통화·10→12 정정·연속/역순/미래 정정·중간cursor·unknown/null·DB원자성/충돌·재전달/복원을 포함한다.

## Q20 검토 보완 — L1/L2

- 미래 settlement 정정에서 dependency_refs 변경은 현재 지원하지 않고 `prospective_dependency_change_unsupported`로 격리한다. 기존 유효 정산을 조기에 해제하지 않는다. 같은 효력 구간에서의 복잡한 정산 이전은 후속 명세로 남긴다.
- split 기준 수량에 영향을 주는 늦은 사건은 reversal뿐 아니라 replacement/새 원본까지 추적한다. split보다 나중에 기록됐고 split 시점 이전/같은 효력으로 같은 position identity를 추가·변경하면 영향을 해소하기 전 `correction_consequences_unresolved`와 complete=false로 표시한다. 당시 지식 경계의 과거 결과는 보존한다. 자동 소급 비율 계산이나 누락분 추정은 하지 않는다.
