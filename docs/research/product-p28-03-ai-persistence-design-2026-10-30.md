권장안은 **서버가 생성하는 typed internal checkpoint codec + 명시적 transition 경계 + 공유 lock adapter**입니다. 기존 Python 예산·검증 규칙을 재사용하고, SQL은 revision CAS·원자 저장·처리 표식·용량을 담당하게 합니다. 단순 `RLock.__exit__` 저장이나 `execute()` 전체 transaction은 채택하지 않습니다.

이번 결과는 읽기 설계 권고입니다. 코드·문서 수정, 시험, 네트워크·원격 작업, agent 실행은 하지 않았습니다. **2a 완료나 새 검증 PASS를 전제하지 않습니다.**

**확인된 코드 사실**

현재 `SyntheticAIRepository` 파일은 준비 메모의 430행과 달리 473행입니다.

- [reserve](../../src/quantharbor/adapters/synthetic_investment_ai.py)는 한 lock에서 payload 동일성, scope 차단, 정책/window, 동시성·예산을 검사합니다. request/policy/attempt와 `(3, 3×65536)` closing hold를 확보한 호출만 `new=True`를 받습니다. 예산은 기존 attempt의 실제 사용량 또는 예약량에서 계산됩니다.
- [query](../../src/quantharbor/adapters/synthetic_investment_ai.py)는 형식·deadline·허용범위·attempt·authorization 검사 뒤 count를 증가시키고 `sources.validate()`를 호출합니다. **그 이후의 source 실패·receipt 용량 실패도 count를 환급하지 않습니다.** `AIDenied`만 `_query_denials`에 추가하며 `Incomplete`·`ContractError`와 구별합니다.
- [execute](../../src/quantharbor/adapters/synthetic_investment_ai.py)는 `_run_research()` 동안 lock을 잡지 않습니다. 이후 lock 안에서 receipt 일치 → `_processed` 설정 → `finish()` → receipt 제거를 수행합니다. 실패하면 임시 marker를 제거합니다.
- [application 실행 경계](../../src/quantharbor/application/investment_ai.py)는 reserve → dispatch → **client.invoke** → settle → 응답·source 검증입니다. 중복 reserve는 client를 다시 호출하지 않습니다. `_settle_dispatched()`의 넓은 예외 처리 때문에 저장 장애가 fallback에 삼켜지는 상황도 설계해야 합니다.
- [review](../../src/quantharbor/adapters/synthetic_investment_ai.py)는 처리된 원본을 확인하고 현재 source로 재검증한 뒤 request/review를 함께 저장합니다. 실패 시 records와 marker를 복구합니다.
- [settle/finish](../../src/quantharbor/adapters/synthetic_investment_ai.py)는 known settlement 보존, unknown/overrun scope 차단, finish 실패 시 hold 복구를 이미 구현합니다. **비용 예약과 closing storage hold는 별개**입니다.
- [Sources](../../src/quantharbor/application/investment_ai.py)는 실제 runtime 객체를 조립하고 repository에 bind합니다. 문서 현재권리·금융 replay·snapshot 재구성·candidate 재생성을 수행하므로 ref 목록만 복원해서 이를 대체할 수 없습니다.

**권장 저장 계약과 API**

공개 진입점은 다음 하나를 추가합니다.

```python
SyntheticAIRepository.product_synthetic(
    database, *, capacity=128, byte_capacity=8388608
)
```

반환값은 같은 정확한 `SyntheticAIRepository` 타입입니다. 기존 생성자는 메모리 동작을 그대로 유지합니다. 입력 DB는 정확한 `PostgresLedger`이며, 현재 active인 정확한 제품 `ProductDatabase`, private root/binding/소유 lock, ready 상태, factory 당시 open-generation을 매 작업에서 확인합니다. disposable·foreign DB·subclass·caller DSN/SQL·복원 JSON은 받지 않습니다.

| 선택 | 장점 | 비용·제약 |
|---|---|---|
| 정규화 tables + operation transitions | SQL에서 상태·참조·quota를 직접 검사하기 좋음 | 현재 여러 dict/set과 Python 예산 규칙을 대폭 재구성해야 하며 SQL/Python 규칙 중복이 커짐 |
| **typed checkpoint + 명시 transition** | 기존 reserve/settle/finish 및 예외 복구 재사용, 한 revision으로 전체 상태 원자 저장 | 매 phase의 bounded 재검증·재인코딩 비용, 엄격한 codec·transition 검증 필요 |

2b에서는 후자를 채택합니다. checkpoint는 외부 DTO나 일반 restore API가 아니며, 제품 backend만 생성·읽는 닫힌 내부 형식입니다.

저장 구조는 작게 유지합니다.

- `ai_state`: 단일 공유 book, codec version, revision, checkpoint bytes/hash, 마지막 operation ID·입력 digest·확정 revision.
- `ai_processed`: result/review별 exact ref/hash와 생성 transition 종류·revision. 최대 records 수 이내의 불변 표식.
- 무제한 event journal이나 새로운 job framework는 추가하지 않습니다.

checkpoint 필드는 명시적으로 고정합니다.

| 기존 상태 | 저장·복원 규칙 |
|---|---|
| `_records` | 허용된 6종 canonical bytes, key/type/ID/version/environment/hash 재검증 |
| `_attempts` | 검증된 attempt records에서 재구성; 별도 선언값을 정본으로 두지 않음 |
| `_payloads` | 최초 reserve의 request/policy exact refs와 reserved Usage 보존; 원문 재구성 후 동일성 비교 |
| `_holds` | attempt별 정확한 closing hold 및 retain 여부 보존 |
| `_policies` | scope/window → exact policy ref; 동일성·중첩 window 규칙 검사 |
| `_blocked` | 보존하며 unknown/overrun attempt와 교차 검증; 세대/window 변경으로 제거 금지 |
| `_processed` | **검증된 `ai_processed` 표식에서만** exact record bytes로 재구성 |
| `_query_totals` | exact request ref별 0..16, 성공 receipt 개수에서 역산 금지 |
| receipts/denials | attempt 결속·순서·허용 reason·32KiB 제한 검증 |
| `_current_sources` | 저장하지 않음; 새 exact `Sources(repository=새 facade)`로 bind |

중복 JSON key, 알 수 없는 필드·버전, bool-as-int, 잘못된 시각, 비canonical bytes, dangling 내부 ref, terminal/result 불일치를 거부합니다. 외부 source ref는 역사적 참조로 보존하되 현재 객체가 존재하거나 현재 사용권이 있다는 뜻으로 해석하지 않습니다.

`__dict__` 복사·pickle·동적 class import·일반 `restore(mapping)`은 금지합니다. 검증 후 만든 메모리 자료구조는 해당 phase의 작업용 상태이며 DB보다 우선하는 cache가 아닙니다.

**원자성·lock·실패 계약**

공유 lock 순서는 **제품 gate → AI 작업 상태 lock → 단일 SQL transaction/advisory lock**으로 고정합니다. 중첩 core 호출은 같은 phase에 참여하고 중첩 commit을 만들지 않습니다. 여러 facade는 같은 DB revision·budget book을 사용합니다.

명시 phase는 `append`, `reserve`, `dispatch`, `cancel`, `settle`, `query_charge`, `query_outcome`, `finish_processed`, `review_processed`, `restart_reconcile`로 제한합니다.

- `reserve`: request/policy/attempt, payload binding, 정책 binding, closing hold를 함께 commit한 뒤에만 `new=True`.
- `dispatch`: 동일 owner의 `reserved → dispatched`를 durable 확정한 뒤 반환. owner는 해당 실행의 메모리 상태이며 재시작으로 재발급하지 않습니다.
- `finish_processed`: 실제 `execute()` 반환 경로에서 receipt 대조를 마친 경우에만 result·processed 표식·hold 해제·receipt 제거를 한 transaction으로 확정합니다.
- `review_processed`: 실제 `_review_result()`를 수행한 경로에서 review request·review·marker를 함께 확정합니다.
- 단독 result append, `finish()`에 전달된 임의 result, 기존 result 존재만으로 marker를 생성할 수 없습니다. loader도 누락 marker를 “수리”하지 않습니다.

client 호출 전후에는 별도 phase를 사용합니다. **client 호출 중에는 SQL transaction·제품 gate·AI lock을 보유하지 않습니다.** 제품 전용 내부 호출 adapter가 호출 진입 시 generation·owner·저장 장애 latch를 다시 확인합니다. 호출 중 close가 발생하면 늦은 결과의 저장을 거부하고 다음 open에서 dispatched를 보수적으로 복구합니다. 정상 종료 drain 전체는 기존 P03 내부5 인계로 남깁니다.

저장 장애는 업무 `AIDenied`와 구별한 storage error로 처리합니다. application의 broad catch나 synthetic client가 이를 잡더라도 backend의 실패 latch가 후속 query/source 진행·성공 반환·marker 생성을 막아야 합니다.

COMMIT 응답 유실은 다음처럼 처리합니다.

1. gate를 유지한 채 마지막 operation ID·입력 digest·revision·checkpoint hash와 marker를 읽어 대조합니다.
2. 정확한 commit 확인 전에는 성공을 반환하지 않습니다.
3. 확인 불능이면 해당 DB-generation의 모든 AI facade에 쓰기 차단을 공유합니다. cache를 이전 상태로 되돌리고 계속 진행하지 않습니다.
4. 일반 write는 확인된 결과만 반환할 수 있지만, **dispatch 응답이 unknown으로 분류된 실행은 이후 commit이 발견돼도 client를 호출하지 않습니다.** readback은 재호출 권한이 아닙니다.
5. CAS 실패에 automatic replay를 붙이지 않습니다.

**query quota에는 별도 durable barrier가 필요합니다**

현재의 검사 순서를 유지하며, count를 실제로 증가시키는 지점에만 `query_charge`를 둡니다.

```text
기존 사전검사
→ request 저장/attempt·authorization 확인
→ count + 1 durable 확정
→ 현재 Sources.validate()
→ receipt 또는 denial 확정
→ 반환 또는 원래 예외
```

- 잘못된 query·deadline 등 **count 증가 이전 거부**까지 무조건 과금하지 않습니다.
- count 확정 실패/unknown이면 source validation을 실행하지 않습니다.
- source validation 이후 `AIDenied`, `Incomplete`, `ContractError`, receipt capacity 실패가 나도 count는 유지합니다.
- `AIDenied`의 기존 denial 기록은 함께 보존합니다. 다른 예외를 임의의 domain denial로 바꾸지 않습니다.
- charge 이후 crash라면 “소비됐으나 receipt 없음”으로 남깁니다. receipt를 합성하거나 quota를 환급하지 않습니다.
- request당 16은 attempt·dispatcher·facade·재시작 전체에 공유됩니다.

따라서 query 메서드 전체에 일반 rollback wrapper를 적용할 수 없습니다.

**재시작 규칙**

첫 AI factory가 새 DB open-generation에서만 recovery barrier를 수행합니다. 같은 generation에 추가 facade를 만드는 것은 재시작이 아니므로 다른 실행의 예약을 취소하지 않습니다. recovery가 실패하면 제품 AI를 노출하지 않습니다.

| 저장 상태 | 재시작 처리 |
|---|---|
| `reserved` | owner가 사라진 전송 전 예약을 `cancelled_before_dispatch`로 확정하고 비용·closing hold 해제. result/marker 생성 없음 |
| `dispatched` | 기존 `settle_unknown()` 의미대로 `unknown_charge`; 예약 비용·scope 차단 유지. client 재호출 없음 |
| `settled` | actual usage·시각·overrun 사실 그대로 보존 |
| `unknown_charge` | 예약 비용·scope 차단 그대로 보존 |
| `cancelled_before_dispatch` | 기존 취소 사실 보존; 이전 `retain_result=True`로 남은 hold를 임의 삭제하지 않음 |
| terminal + 검증된 result/marker | 그대로 복원; 현재 source 검증 없이 본문을 현재 사용 가능 결과로 승격하지 않음 |
| terminal + result 없음 | result는 `None`/MISSING. 남은 closing hold·receipt 유지; 성공·processed 표식 합성 없음 |

reserved 취소의 `settled_at`은 마지막 확정 `reserved_at`, dispatched unknown의 `settled_at`은 기존 core처럼 `dispatch_at`을 사용합니다. 내부 recovery reason은 각각 고정값으로 기록하고 실제 복구 관측시각과 구분합니다. 기존 domain reason enum을 임의 확장하지 않습니다.

terminal의 결과 유실로 남는 closing hold는 보수적 용량 손실입니다. 이를 숨기거나 자동 eviction하지 않습니다. unknown의 결과가 정상적으로 저장되어 **storage hold가 해제되더라도 비용 예약·scope 차단은 유지**됩니다.

새 runtime authority generation은 금융 권한 무효화에 관한 값입니다. AI budget, 정책 binding, query count, blocked scope의 초기화 키로 사용하지 않습니다.

**용량 계약**

기존 다음 식을 그대로 유지합니다.

```text
record 수 + closing hold 수 ≤ capacity ≤ 128
canonical record bytes + closing hold bytes ≤ byte_capacity ≤ 8MiB
각 closing hold = 3 records / 196608 bytes
```

추가로 제품 전용 개발 상한을 둡니다.

- auxiliary 직렬화 계상 8MiB, checkpoint 전체 encoded bytes 32MiB.
- request/attempt/policy/hold/count 항목 각각 최대 128, marker는 대응 result/review 수 이하.
- receipts는 attempt당 기존 32KiB, request 전체 실행 수 16 이하. denials는 기존 reason 집합의 중복 없는 값만.
- payload/processed/attempt/policy의 중복 표현도 auxiliary 계상에 포함합니다. 저장 형식에서는 가능한 항목을 exact ref로 결속합니다.
- reserve 때 **최종 marker·attempt 변경·receipt/denial·codec 팽창의 최대 증가분**까지 별도 선예약합니다. codec 상한 산식이 증명되지 않으면 reserve를 거부합니다. 기존 3 closing holds에서 이를 빼 쓰지 않습니다.
- reads는 길이·개수 metadata를 먼저 검사하고 bounded chunk로 가져옵니다. 예를 들어 SQL 응답당 256KiB, 전체 checkpoint 32MiB를 넘으면 중단합니다. 전체 `json_agg`·무제한 stdout capture 뒤 검사하는 방식은 제외합니다.
- 동일 append·멱등 transition은 추가 quota를 소비하지 않습니다. 자동 eviction·무제한 journal은 없습니다.

이는 합성 논리 저장·전송 상한입니다. Python 객체 메모리, PostgreSQL WAL/MVCC·index를 포함한 실제 RAM/disk 보장은 아닙니다.

**migration과 파일 소유**

[현재 loader](../../src/quantharbor/adapters/product_artifacts.py)는 migration 행이 정확히 하나라고 검사합니다. [0001](../../migrations/product/0001_artifacts.sql)은 `CHECK(version = 1)`을 갖습니다.

`new product_schema.py`의 **같은 명시 registry**를 artifacts와 AI factory가 사용하도록 합니다.

- 기존 `0001_artifacts.sql` bytes/checksum은 불변.
- 기존 version 1의 checksum·구조·함수 정의를 먼저 검증한 뒤 `0002_ai.sql`을 적용합니다.
- migration 2 안에서 기존 version check의 정확한 구조를 확인하고 `version IN (1,2)`로 교체한 뒤 AI 구조와 version 2 기록을 같은 transaction으로 확정합니다.
- 빈 schema에서 시작하면 1 → 2 순서로 적용합니다. 기존 schema의 migration 기록 결손은 신규 설치로 간주하지 않습니다.
- known version 2는 artifact factory에서도 정상입니다. 미지원 버전·누락·checksum 불일치는 차단합니다.
- 기존 `append_artifacts` 본문·signature·owner·언어·security/volatility/config guard를 유지하고 새 함수에도 동등한 guard를 적용합니다.
- 금융 schema 1~3, lifecycle pin, image 설정은 변경하지 않습니다.

최대 두 순차 구현 단위로 나눕니다. 최종 소유 확정은 root가 합니다.

| 순서 | 소유 후보 | 수용·실패 범위 |
|---|---|---|
| **2b-1 저장 기반** | 신규 `product_schema.py`, `product_ai.py`, `0002_ai.sql`; `product_artifacts.py` loader 위임; 신규 `test_product_ai.py`와 필요한 artifact tests | registry 1→2/known2 호환, codec·marker 검증, CAS·bounded I/O. 실패 시 migration 원자 rollback, 2a 자료 보존. AI 실행 연결은 아직 수용하지 않음 |
| **2b-2 core 연결** | `synthetic_investment_ai.py`, `product_ai.py`, `test_product_ai.py`, 필요한 기존 AI tests | exact factory·phase·query barrier·owner·restart·commitunknown 연결. 기본 memory 회귀와 실제 제품DB 증거 확보 후 수용 |

application/domain은 우선 변경하지 않습니다. core의 명시 phase·내부 client adapter로 처리합니다. 부족한 seam이 발견되면 root에게 정확한 추가 파일·이유를 반환하며, 금융·scheduler 범위로 넓히지 않습니다.

**구현 후 필요한 시험 행렬 — 현재 전부 NOT RUN**

| 관점 | mock/core 검증 | actual private synthetic DB 검증 |
|---|---|---|
| 기본 호환 | 기존 AI 보안·review·bounds, actual/retry 비활성, exact factory | disposable/foreign/옛 generation 거부 |
| dispatch | reserve/dispatch 저장 실패·unknown에 client 0 | dispatch commit 직후 종료·재open, 재호출 0 |
| 정산·복구 | malformed usage/clock, overrun, settled 보존 | reserved/dispatched/settled/unknown 각각 재시작·잔액·hold 확인 |
| quota | source 실패·receipt 초과에도 16 불환급, 사전거부 구분 | charge commit 후 crash·receipt 없음·재시작 count 유지 |
| 처리 정본 | result만 주입·marker 누락/변조·위조 review 거부 | result/marker/hold 해제 중간 장애에 전부 또는 전무 |
| 동시 facade | 같은 attempt owner 1, 정책·공유 cap 충돌 | 두 facade 경합·CAS·close/reopen·옛 facade 실패 |
| 응답 유실 | commit 전/후 오류, 확인 실패 latch | COMMIT 성공 후 응답 유실·확인 SELECT 오류, dispatch call 0 |
| source 재bind | 새 source 누락·철회·hash 변경 시 본문 숨김 | 복원 뒤 명시 새 Sources로 재검증 |
| 용량 | 128/8MiB/3holds와 auxiliary·encoded·응답 경계 | near-cap 완료 저장, 초과 원자거부·자료 보존 |
| migration | registry prefix·future·missing·function guard | 기존 v1 upgrade, v2 artifact 재open, DDL 실패 rollback |

2a의 최종 수용·고정 입력 SHA는 root가 연결해야 합니다. Q27 실제 집중, source 현재권리 서비스·HTTP·종합 scheduler 및 P28-05는 독립 후속입니다. 이번 권고는 그 완료를 주장하지 않으며, 공통 상태 기록도 수정하지 않았습니다.
