# Q20 합성 로컬 원장 개발 인계

기록일: 2026-10-24. 작업 ID `LEDGER-local` / Q20 F01·02·03·08의 로컬 합성 하위 범위. 구현자 자기 검증 기록이며 독립 검토나 Q20 운영 완료 판정이 아니다. root가 공통 상태·큐·증거를 통합한다.

## L1/L2 제한 수정 인계 — 2026-10-24

입력은 [초기 독립 검토 L1/L2](../evidence/ledger-review-initial-2026-10-24.json), [계약의 Q20 검토 보완](../contracts/ledger-local-v1.md), [작업 카드](../tasks/LEDGER-local.md)와 현재 소유 파일이다. 아래 기존 구현 기록은 당시 결과이며, 이 보완이 이번 수정 범위와 검증 결과다. 역사적 구현 SHA를 현재 파일로 복원하지 않았다.

이번 변경은 `src/quantharbor/application/ledger.py`, `migrations/0002_synthetic_ledger.sql`, `tests/product/test_ledger.py`, `scripts/check_ledger.py`, 이 문서의 5개 파일뿐이다. 단독 작성·순차 실행했으며 위임하지 않았다. root의 최종 PID1 postgres 준비 확인과 runner 품질 회귀는 변경하지 않았고, SQL의 `dependency_ref` 지역명 구분도 보존했다. domain과 fixture는 변경할 필요가 없었다. 상태·계약·config·baseline·0001·다른 모듈에는 쓰지 않았다.

- L1: 미래 settlement 정정에서 기존 replacement와 `dependency_refs`가 달라지면 `prospective_dependency_change_unsupported`로 격리한다. Python과 SQL 모두 revision 연결·미래 시각 검사 이후, 경제 사건 추가 전에 차단한다. 기존 `already_settled` 검사는 그대로 유지한다. 동일 dependency의 미래 정정 및 기존 소급 settlement 정정은 계속 허용한다.
- L2: 선택된 split과 같은 position identity에 대해, 이후 sequence로 기록되고 효력이 split 시점 이전/같은 replacement도 영향 검사에 포함한다. 따라서 빈 baseline에 새 key를 추가하는 소급 정정, 늦은 original, 다른 key에서 해당 key로 옮겨 오는 replacement를 잡는다. 기존 reversal 영향 규칙도 유지한다. `correction_consequences_unresolved`와 complete=false를 표시하며 누락 split 증분은 계산하지 않는다. 이전 지식 경계·split 이전 projection·다른 identity·split 이후 효력의 새 original을 보존한다.

실제 실행 결과:

| 단계 | 실행 결과 |
|---|---|
| 수정 전 기존 제품 전체 | 217개 통과 |
| 수정 전 runner 품질 | 12개 통과; PID1 회귀 포함 |
| 회귀 추가 최초 실행, 구현 수정 전 | 원장 62개 중 실패7; 이 중1은 두 trade의 clearing 기대값을100으로 잘못 쓴 fixture 단정 |
| clearing 기대값200으로 바로잡은 재현, 구현 수정 전 | 원장 62개 중 실패6·통과56; L1 2개, L2 4개 |
| 구현 수정 후 원장 | 62개 통과 |
| 최종 제품 전체 | 226개 통과 |
| 최종 runner 품질 | 12개 통과; PID1 회귀 포함 |
| 새 DB runner 시나리오의 메모리 합성 사전 실행 | 8계좌·35입력·4검사 묶음 통과; subprocess 실행 차단 |
| runner 독립 단정의 오류 주입 | 잘못된 accepted, 현금800, split complete=true를 각각 status/cash/completeness 고정 오류로 거부; 3개 통과 |

unit 실행 명령:

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -p 'test_ledger.py'
PYTHONPATH=src python3.13 -m unittest discover -s tests/product
PYTHONPATH=src python3.13 -m unittest discover -s tests/quality -p 'test_ledger_runner.py' -v
```

9개 추가 unit 회귀는 전체 현금 계정·수량·baseline_known·complete/reason을 고정 기대값으로 확인한다. L1 재현에서 기존 결제 후 현금900·남은 미결제채무-100이어야 하는데 수정 전 현금800·미결제0이 나왔다. L2에서는 수량25를 확정하지 않고 불완전으로 표시해야 한다. baseline에5주가 새로 생긴 2:1 분할의 경제상 결과30주를 자동 추정하거나 원장에 추가하지 않는다. 이전 지식 경계는20주·complete=true로 유지한다.

실제 DB runner의 `check_l1_l2`는 parity 외에 accepted/quarantined와 정확한 reason, 전체 현금·보유·완전성·이전 cutoff를 독립 단정한다. baseline 새 key·늦은 original의 split 이전/같은 효력·key를 추가하는 replacement·기존 허용/무관 사건을 포함한다. 이 8계좌도 기존 dump/restore 재생 비교에 포함했다. 기존44입력에35입력을 추가했으므로 실제 runner의 예정 parity 입력은79개이며, 이는 아직 실제 DB 통과 수가 아니다.

**남은 검증과 한계:** 이번 역할은 Docker·실제 PostgreSQL·hdiutil·네트워크·비공개 데이터·키·실제 API·Git 명령을 실행하지 않았다. SQL은 같은 제한을 구현했지만 실제 migration/함수 실행 결과는 root가 새 합성 DB에서 runner 전체를 실행해 확인해야 한다. 기존 split revision 미지원은 그대로이며, 일반적인 split 재계산/영향 해소 절차나 복잡한 미래 정산 이전을 추가하지 않았다. 이 기록은 자기 검증이며 독립 검토를 대체하지 않는다. root가 최종 파일 SHA와 결과를 받아 공통 상태·증거를 통합한다.

## 입력·소유권

선행조건은 Q12 계약, Q13~18 로컬 기반, Q19 합성 조회와 EXEC-DEC-001의 입력 없는 순차 실행이다. 입력은 [ledger-local-v1](../contracts/ledger-local-v1.md), [data-v1](../contracts/data-v1.md), [serialization-v1](../contracts/serialization-v1.md), [LEDGER-DEC-001](../decisions/LEDGER-DEC-001-local-replay.md)이다. 작업 시작 시 HEAD는 `2fa8f1d`였다. 기존 변경을 보존했고 Git 변경 명령을 실행하지 않았다.

배정된 새 파일은 `domain/ledger.py`, `application/ledger.py`, `ports/ledger.py`, `adapters/synthetic_ledger.py`, `adapters/postgres_ledger.py`, `migrations/0002_synthetic_ledger.sql`, `tests/product/synthetic_ledger.py`, `tests/product/test_ledger.py`, `scripts/check_ledger.py`, `tests/quality/test_ledger_runner.py`, 이 문서다. `domain/serialization.py`는 원장 schema 등록·nested 복원만 추가했다. frozen 계약·0001·그 밖의 source/config/status/queue는 수정하지 않았다. 새 패키지·외부 자료·실제 입력은 사용하지 않았다.

## 경제 입력과 결과

`SyntheticLedgerSubmission`은 닫힌 frozen dataclass다. 환경은 `synthetic`만, 계좌는 `synthetic-account:` 접두사의 내부 참조만 받는다. 원천 identity는 source_kind/key/revision이다. `LedgerCompleteness(complete,costs_known,semantics_known)`, 선택적 전체 계좌 `LedgerBaseline`, dependency_refs, 선택적 `SplitRatio`를 명시한다. 누락 필드·잘못된 nullable·unknown field/enum·중복 JSON key·float·bool-as-int는 ContractError 또는 DB의 고정 `ledger_contract` 오류다. 입력 원문을 오류에 넣지 않는다.

다음 의미를 구현했다.

- baseline: 전체 계좌의 현금/보유 범위를 명시한다. 0 잔고는 빈 legs/holdings인 완전 baseline으로 표현한다. baseline 없이 받은 사건은 누적 변화로만 표시한다. 최초 baseline은 다른 경제 사건보다 먼저 입력한다. baseline full replacement 정정도 정확한 역분개를 거친다.
- trade: 종목/venue/mapping/unit가 결속된 수량 1개와 같은 통화의 미결제채권 또는 미결제채무/trade_clearing 2개 분개다. 매수는 미결제채무 음수, 매도는 미결제채권 양수다.
- settlement: 유효 trade 한 개를 dependency로 참조하고 그 미결제액을 정확히 settled_cash로 이동한다. 수량 재계상·다른 금액·독립적인 중복 결제는 격리한다. 결제 자체의 full replacement와 중복 재전달에도 같은 규칙을 적용한다.
- fee/tax/deposit/withdrawal/dividend: 결제현금과 각각 fee_expense/tax_expense/external_flow/dividend_income을 구분한다. 비용 포함 관계가 확인되지 않은 입력은 격리한다. unknown 비용을 0으로 채우지 않는다.
- fx: KRW/USD 각각 settled_cash/fx_clearing 분개를 명시한다. 통화별 균형과 서로 반대인 현금 방향을 요구한다. 환율을 추정하거나 환전을 실행하지 않는다.
- split: 완전한 기존 보유와 명시한 정수 비율을 대조해 수량 증분을 정확히 확인한다. 반올림이 필요한 비율 차이는 격리한다.

`LedgerProjection`은 통화/계정별 cash_balances와 수량 holdings를 보존한다. 기준 보유 부족·음수 보유/현금 또는 비정상 미결제 방향·미해결 격리·연계 정정 영향은 reason_codes와 complete=false로 나타낸다. available_cash/reserved_cash/broker_buy_capacity는 모두 null이고 availability_reason을 제공한다. settled_cash를 가용금으로 승격하지 않는다. 이 결과는 평가나 실제 대사를 끝낸 PortfolioSnapshot이 아니다.

## 정정·시점·hash

revision은 1부터 연속이며 predecessor와 correction_of가 직전 replacement를 가리켜야 한다. 원천 identity 고유키는 replacement만 소유한다. reversal은 `internal-reversal`/자신의 event ID/1의 별도 identity를 갖는다. 같은 revision/hash는 duplicate로 원래 cursor/event/projection 참조를 반환한다. 상충 hash는 원본을 보존하고 quarantined 판정을 추가한다. 격리 재전달은 duplicate이며, 명시적 `reprocess=True`만 새 판정을 만든다. 선행조건이 해소된 동일 입력의 새 accepted 판정은 이전 격리 사유를 해소한다. source collision은 자동 해소하지 않는다.

retroactive는 이전 효력시각에서, prospective는 처리시각보다 미래 T에서 정확한 reversal/replacement를 한 bundle로 기록한다. 미발효 replacement의 재정정·효력시각 소급 이동·delta revision은 격리한다. **split 자체의 revision은 `split_revision_unsupported`로 격리**한다. 이미 적용된 분할 이후의 수량 사건/다른 기업행동까지 연쇄 조정하는 일반 기업행동 엔진은 구현하지 않았다. 기존 split 또는 settlement에 영향을 주는 선행 정정은 `correction_consequences_unresolved`로 표시한다. settlement는 올바른 후속 revision으로 새로운 trade를 참조하면 그 연계 영향을 해소할 수 있다. dependency는 현재 유효 replacement를 참조해야 한다. 그 밖의 공급자별 gross/net·기업행동·현금 포함 관계는 임의 해석하지 않고 unsupported 또는 incomplete 입력으로 격리한다.

replay는 bundle 끝 cursor만 받아 recorded_at≤knowledge_cutoff 및 effective_at≤as_of인 signed 사건을 합산한다. 최신 revision만 골라서 합산하지 않는다. 미래 사건을 앞당기지 않으며 mode와 reducer_version을 결과에 포함한다. `restated`를 원천 당시 이용 가능했던 정보라고 주장하지 않는다. 기존 투영은 변경하지 않고 append 시 새 투영의 supersedes_projection_id로 연결한다. 동일 경계·버전·supersedes의 재생은 동일 canonical 결과다.

submission_hash는 전달시각과 내부 sequence/ID를 제외한 typed 의미 입력의 canonical hash다. event payload_hash는 sequence/recorded_at/correction/증빙/경제 내용을 포함한 LedgerEventBody의 hash이며 envelope에 분리한다. event envelope/DB event에는 canonicalization_version도 저장한다. body의 submission_hash와 envelope hash를 재검사한다. 기존 canonical prefix·wrapper·golden vector는 유지했다.

## 구현 한도

| 항목 | 고정 한도 |
|---|---|
| identifier | 기존 ASCII 문법, 최대128자 |
| 시간 | UTC 정규화 후 2000~2100년, 최대 microsecond |
| 금액·수량 | 입력80자, 정규화 후 정수20/소수18자리, KRW/USD |
| cash legs / position deltas / evidence / dependency | 각각32개, 중복 identity/참조 거부 |
| 계좌별 경제 events / 판정 | 각각4096개 |
| sequence | 1..2147483647, 공개0은 초기 cursor |
| canonical wrapper / SQL wire | 최대65536 bytes, 초과 시 transaction 실패 |
| SplitRatio | numerator/denominator 각각1..1000000 |
| reducer | `synthetic-ledger-v1` |

합산·반전은 Python 고정소수 정수로 수행한다. DB journal은 무제한 numeric과 정확 범위/scale CHECK를 사용한다. NUMERIC(38,18)의 사전 반올림을 사용하지 않는다. 한도를 넘는 투영/합산은 부분 성공으로 저장하지 않는다.

## PostgreSQL 경로와 root 실행

`PostgresLedger()`에는 DSN·기존 프로젝트/DB·credential·SQL 인자가 없다. 명시적 context 진입에서 기존 고정 Compose 이미지의 **새 UUID 프로젝트**를 만든다. Docker context가 Unix socket인지 검사하고 published port/host mount 없는 합성 DB만 사용한다. 설치나 image pull을 하지 않는다. subprocess 환경은 필요한 Docker/local 경로 변수만 보존하며 키·PGPASSWORD·DOCKER_HOST를 복사하지 않는다. 공개 경제 API는 고정 함수 호출만 구성하고 문자열은 UTF-8 hex 데이터로 전달한다. 내부 `_query`는 배정된 runner와 migration을 위한 구현 상세다.

DB append 함수는 계좌 row lock 후 검증·decision·event·journal·projection·cursor·outbox·delivery를 단일 session transaction에서 처리한다. immutable UPDATE/DELETE, 원천 revision·reversal 고유성, 동일 계좌 FK와 지연 commit 시 분개/정정/bundle/outbox 검사를 둔다. 투영은 저장 전에 DB replay 결과와 대조한다. consumer는 inbox와 업무 cursor를 같은 transaction으로 처리하며 hash collision을 별도 기록한다. ACK 유실 재전달과 역순 전달은 경제/업무 효과를 중복하거나 cursor를 퇴행시키지 않는다. 관리자까지 불변이거나 외부 exactly-once라고 주장하지 않는다.

root 실행 명령:

```sh
PYTHONPATH=src python3.13 scripts/check_ledger.py
```

runner는 인자를 받지 않으며 자신의 UUID 프로젝트만 정리한다. pass/fail·고정 이유 코드·완료 검사 목록·migration checksum·cleanup을 JSON으로 출력하고 raw SQL/daemon 오류를 출력하지 않는다. 실제 append에 단위 시험과 동일한 fixture를 제출하고 Python application 결과와 event/projection hash 전체를 대조한다. 별도의 성공 전용 SQL 원장 경로는 없다.

작성된 DB 검사는 migration 순서/checksum/재적용, 반복 snapshot·연속/소급/장래 revision·중간 cursor, baseline/비용/현금 의미와 격리 재판정, 결제 revision·연계 정정·분할, SQL 직접 입력의 schema/중복 key/숫자/시각, 정확 숫자 한도와 overflow/sequence 소진 rollback, events/projection/outbox 경계 실패, immutable/지연 journal 검사, 실제 두 session row lock 경합, commit 전 backend 연결 종료, inbox/workstate rollback·collision·ACK 유실·역순 전달, 같은 경제 이력의 dump/restore·재생·복원 후 revision 재전달을 포함한다. tmpfs는 전원 장애 내구성 증거가 아니다.

## 실행한 명령과 결과

2026-10-24 구현자 환경에서 실행:

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -p 'test_ledger*.py' -v
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -v
PYTHONPATH=src python3.13 -m unittest discover -s tests/quality -p 'test_ledger_runner.py' -v
```

최종 제품 suite **217개 통과**(기존164 + 새 원장53), 새 runner 품질 시험 **11개 통과**, 실행한 시험의 실패0이다. 원장 시험은 Decimal context 변경·정확 한도 overflow rollback, 10→12와 연속/역순 정정, 이중 reversal 참조 거부, baseline 정정, 연계 settlement 해소, split 정정 격리, 역사적 경계, hash 손상, inbox 재전달을 포함한다. 품질 시험은 subprocess를 mock하며 Docker를 실행하지 않는다. constructor의 무부작용·remote context 거부·기존 DB 인자 거부·단일 transaction SQL·hex 전달·오류 비노출·자기 프로젝트 정리를 확인했다.

구현 중 자기 점검에서 JSONB 변환 후 중복 key가 소실되는 경로를 원문 JSON 검사로 바꿨고, Decimal context 의존 합산·원천 identity를 공유하는 reversal·분할 이후 정정 영향 누락을 방지했다. DB deferred stream 검사는 중간 NEW row 대신 transaction 최종 row를 검사하도록 작성했다. 이 DB 코드의 실행 성공을 이 문서로 주장하지 않는다.

**미실행:** Docker daemon·실제 PostgreSQL migration/함수/SQL 검증·DB 경합/rollback/연결종료/복원 전체, native UI/hdiutil, 네트워크, 비공개 데이터/키·실제 계좌/대사. `scripts/check_ledger.py` 자체는 이번 역할에서 실행하지 않았다. PostgreSQL 문법·transaction·Python/SQL parity의 실제 통과 증거는 root의 후속 실행이 필요하다. 독립 검토·보안 검토도 수행하지 않았다.

다음 담당은 root다. 이 소유 파일의 SHA256과 시험 결과를 검토자에게 전달하고, 승인된 sandbox 경계에서 실제 DB runner를 실행한 뒤 발견 사항을 수정/재검증한다. 실제 Q19 관문과 Q20 전체 운영 완료는 계속 별도로 추적한다.
