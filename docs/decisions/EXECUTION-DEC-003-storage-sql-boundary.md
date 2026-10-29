# EXECUTION-DEC-003 — 합성 실행 저장 예산과 SQL 권한 경계

- 날짜: 2026-10-25
- 관련 작업 ID: Q27 / EXECUTION-local, 후속 Q28·Q29
- 상태: 채택 — 구현·독립 검증 전
- 결정 담당·요청 근거: orchestrator, 사용자 입력 없는 잔여 작업 순차 진행·검증 요청

## 요구와 확인 사실

[읽기 전용 자문](../research/execution-storage-design-input-2026-10-25.md)과 [소스 대조](../evidence/execution-storage-design-2026-10-25.json)를 입력으로 사용한다. 실제 DB 제어 검사는 두 버전의 집중21 범위이며 최신 전체 통과가 아니다. 자문은 시험을 실행하지 않았다.

현재 Q20 최초 append는 소비 완료까지8행, 정정 append는11행이다. trade/fee/tax 모두 있는 최초 fill과 정정7개는24+7×33=255행으로 고정192행 배분을 넘는다. 기존 계약은 더 필요한 행을 숨기지 않고 반환하도록 한다. broker 최대8은 모든 사건 조합의 수용 보장이 아니다. 현재 archive 복제의 Q26 계상 누락, aggregate snapshot 전송, generic SQL 함수 권한은 보완 대상이다.

## 선택과 이유

1. 한도·fixture·baseline7·migration0001/0002는 유지한다. 1024 logical records/64MiB는 영속 논리행과 실제 canonical 내용·메타데이터·저장된 index key bytes의 한도다. PostgreSQL 물리 페이지·WAL·MVCC·RSS 한도라고 주장하지 않는다. PK/UNIQUE index entry는 추가 logical row가 아니지만 bytes는 빠짐없이 센다. 별도 영속 lookup은 행과 bytes 모두 센다. Q26의 기존 map별 record 계상은 축소하지 않는다.
2. 소유자별 actual_used+remaining_completion_reserve를 검사한다. 실제 기록 생성 시 해당 예약에서 소비하여 이중 가산하지 않는다. Q20 원장·reversal·delivery·미래 consumer inbox·history·reservation·budget 자신과 index를 포함한다. intent384/24MiB와 세부192행·공통128/8MiB·source8MiB·Q26 128/8MiB를 그대로 둔다.
3. 합성 issuer의 고정 facts manifest에 대해 발급 전 모든 허용 처리 분기의 완료 비용을 계산한다. 역순·정정·quarantine·취소·철회·소비 비용을 포함한다. 255행 사례는 admission/발급 전에 부작용 없이 거부한다. 이미 발급한 사실을 사후 용량 오류로 버리거나 금융 의미를 생략해서 맞추지 않는다. 이를 위해 보수적 상계를 쓰면 강제 조건과 거부 범위를 명시한다.
4. 같은 사건·dependency/read-set·결과의 재처리 및 같은 query의 대사는 기존 결과를 반환한다. 임의 UUID 이력을 쌓지 않는다. active2는 미종료 의도 수이며 누적2로 해석하지 않는다. 종료 사실·consumed·claim·금융 hold는 남기고, issuer의 남은 발급 권한 및 미완료 명령에 비추어 불가능해진 미래 저장 예약만 회수한다. 이전 이력이 있으면 새 admission은 잔여 용량 안에서만 허용된다.
5. retired_commands 중복 archive를 제거한다. 과거 command/receipt 조회는 불변 challenge/receipt/cancel evidence로 재구성한다. 영속 UNIQUE/lookup은 실제 비용을 센다. 불변 Q26 기록을 Q27로 옮겨 Q26 한도를 우회하지 않는다. 오래된 generation의 권한은 복구하지 않는다.
6. trusted Python이 현재 opaque issuer handle과 actor를 검증한 동일 transaction에서 고정 action·account·generation/fence·target/version·nonce·source/read-set·시각·issuer fact에 묶인 권한 context를 전달한다. product role은 context를 만들 수 없다. 자기 hash·GUC·bool은 권한이 아니다. context는 backend/transaction/action 일회성으로 결속한다. 현재 owner 접속 후 SET LOCAL ROLE의 신뢰 한계를 명시하며 hostile owner 격리라고 주장하지 않는다.
7. product의 generic save/event/ledger append 권한을 제거하고 고정 전이 함수로 제한한다. closed keys·NULL-safe 검사·numeric/UTC·FK·version/previous hash·nonce/receipt·reservation 보존식·consumed↔claim↔intent↔outbox commit 결속 및 현재 권한/원천 검사를 강제한다. AUTH 거절과 구조 제약 실패를 따로 검증한다. 실제 Q20 호출은 동일 transaction 내부의 검증된 사실과 stored intent로 도출한다.
8. 같은 연결·transaction에서 paged reads와 제한된 delta/chunk staging으로 8MiB frame과64MiB 논리 저장 한도를 양립시킨다. 전체 snapshot 재전송을 권한 API로 남기지 않는다. chunk 원문≤65536bytes/header≤4096bytes/hex 포함 frame≤135168bytes, 최종 frame8MiB 제한과 전체 transaction deadline·누적 전송 제한을 검사한다. 누락·충돌·EOF·timeout은 전체 rollback; staging 잔존0. commit 응답 유실은 관측으로 해소하며 금융 자동 write retry0을 유지한다.

대안인 한도 확대, 원장 행 생략, archive 예산 이전, 전체 snapshot hash를 인증으로 쓰기는 채택하지 않는다. 신규 제품 API 지출·자격증명·사용자 자금 정책은 변경하지 않는다. 정확한 SQL 내부 함수 분할과 순수 비용 helper는 구현자에게 위임한다.

## 소유권·검증·재검토 조건

기존 Q27 소유23파일에 `src/quantharbor/domain/execution_budget.py`, `tests/product/test_execution_storage.py`, `tests/product/test_execution_sql.py`를 추가 허용한다. 같은 transaction의 제한된 bridge/read 지원이 필요하면 `src/quantharbor/adapters/postgres_ledger.py`, Q26 중복 조회 회수를 위해 `src/quantharbor/adapters/synthetic_approval.py`를 additive seam으로 허용한다. 기존 공개 API·Q26 의미는 보존한다. root가 공통 계약/증거를 작성하고 단독 구현자가 코드·0003·runner·시험·안내를 담당한다.

실제 DB에서 독립 행/index byte 계산, 발급 전255행 거절, 포화 이후 발급된 사실/보호 제어 완료, active3 거절과 여유 있는 terminal 후3번째 의도, 반복 세대 계상, context/closed schema/원자성 음성, chunk 경계/부분 I/O/cleanup을 확인한다. EX09 min(12−4,10−2−1)=7 및 EX11 기존400+활성매수100+신규50=550>500의 실제 전체 경로도 마무리한다. 기존 단순 broker7·500+50 검사를 같은 증명으로 합산하지 않는다.

미확인: 모든 경로의 최악 비용·실측 bytes·완료 예약 보호·새 SQL 양성/음성·최신 전체 DB/제품·독립 검토. 충돌이 발견되면 기존 실패와 미실행을 기록하여 root에게 반환한다. 본 결정만으로 EX32/34/37/40 또는 Q27 완료를 판정하지 않는다.
