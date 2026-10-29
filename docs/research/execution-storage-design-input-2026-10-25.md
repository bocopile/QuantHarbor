**Q27 저장 예산·SQL 불변식 최소설계 자문 초안 — 2026-10-25**

읽기 전용 정적 검토다. 파일 수정·시험·DB/Docker 실행·agent·네트워크·Git 변경은 수행하지 않았다. 요청된 `qh_review / Astra/high` 역할·모델의 실제 runtime 로드는 확인하지 않았다.

**현재 한도를 유지하면서 보완할 수 있지만, “임의의 broker 사건 8건을 모두 처리할 수 있다”는 192행 원장 배분은 입증할 수 없다.** 현재 Q20 구조에서 수수료·세금이 있는 최초 체결과 정정 7건은 원장 관련 **255행**을 요구한다. 최소안은 발급 전에 전체 완료 비용을 계산하여 기존 배분에 들어오는 합성 manifest만 수용하고, 이미 발급한 사실에는 확보한 공간을 반드시 사용하는 것이다. 모든 8건 조합의 처리를 요구한다면 192행 배분과 충돌하므로 완료 판정을 보류해야 한다.

**검토 기준과 기존 판정**

최신 상태는 복구 수정 후 실제 DB 11시나리오·11검사 통과, ownDB 11개 정리다. 초기 실행은 11시나리오·22검사 통과 후 case12 실패·12개 정리였고, root는 원본 typed issuer ID 검증으로 red1/green2를 거쳐 수정했다. 초기 앞10개와 수정 후11개는 **서로 다른 버전의 집중21 범위**이며 최신 전체46/fixed40 완료가 아니다.

제어 단위 결과도 final1 집중15·영향39와 final2 신규/영향7을 분리한다. latest-all28은 미실행이다. 근거: [status.md](/Users/okestro/projects/QuantHarbor/docs/status.md:671), [최신 DB 증거](/Users/okestro/projects/QuantHarbor/docs/evidence/execution-database-control-2026-10-25.json:14), [제어 인계 counts](/Users/okestro/projects/QuantHarbor/docs/evidence/execution-control-partial-2026-10-25.json:2195).

용량·SQL 인증 미완료는 이미 인계된 known remaining이다. 아래 내용은 그 잔여를 구체화한 정적 발견이며, 금융·제어 양성 결과가 모두 무효라는 판정은 아니다.

**1. 저장 한도의 의미와 계상 단위**

root에는 **64MiB를 논리 canonical 데이터와 저장된 인덱스 키의 byte 한도로 명문화하는 선택**을 권고한다. PostgreSQL 전체 디스크 64MiB 보장은 현재 계약·구조로 성립하지 않는다. heap/index 페이지, TOAST, MVCC 이전 tuple, WAL, catalog, 임시 작업 공간은 canonical 길이와 다르다. `pg_column_size` 일부 합계로 이들을 보장할 수도 없다.

다음 구분이 필요하다.

| 대상 | logical record 수 | byte 계상 |
|---|---:|---|
| 불변 evidence/history, claim, intent/current head, reservation, command/receipt, budget 소유 행 | 각각 계상 | 저장 canonical 내용과 메타데이터 |
| 별도 저장한 authoritative lookup/map 행 | 각각 계상 | key/value 전체 |
| PostgreSQL PK/UNIQUE/보조 index entry | **추가 logical record로 세지 않는 것을 권고** | 각 index의 실제 참여 key canonical bytes를 별도 합산 |
| 재구성 가능한 임시 조회 map | 영속 record 아님 | 별도 제한된 작업 메모리 |
| state JSON 안의 원본 복제 | 독립 권위 record로 위장하지 않음 | **복제된 실제 bytes는 생략 불가** |

물리 index entry를 모두 logical record로 세는 해석이라면 아래 원장 사례만 693개가 되어 384 배분에도 들어가지 않는다. 반면 Q26의 `commands/nonces/receipts` map은 현재 명시적으로 record 수에 포함되어 있으므로, 이 추천을 적용하여 Q26 기존 계상까지 자동 축소하면 안 된다.

Q26 128records/8MiB 독립 제한은 계속 적용한다. Q26 자료를 Q27에 실제 복제한 비용도 없어지지 않는다. 동일 자료에 두 quota 검사를 적용하는 것과, 한 quota 안에서 같은 물리 저장을 두 번 더하는 것은 구분한다.

근거: [root 예산 계약](/Users/okestro/projects/QuantHarbor/docs/contracts/execution-local-v1.md:49), [Q26 계상](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_approval.py:145).

**2. 원장 192행의 독립 계산**

현재 실행 경로는 trade·fee·tax 각각 Q20 append를 호출한다. 정상 최초 append 하나는 다음 8행을 만든다.

`event 1 + journal 2 + decision 1 + projection 1 + outbox 1 + delivery 1 + consumer inbox 1 = 8`

정상 정정 append 하나는 reversal와 replacement를 생성하므로 다음 11행이다.

`event 2 + journal 4 + decision 1 + projection 1 + outbox 1 + delivery 1 + consumer inbox 1 = 11`

소비 전이라도 inbox의 **미래 완료 공간을 예약**해야 하므로 이를 빼서 종료 비용을 줄일 수 없다.

| broker 사건 구성 | trade | fee | tax | settlement | 원장 행 합계 |
|---|---:|---:|---:|---:|---:|
| 양수 fee/tax 최초 fill 1건 | 8 | 8 | 8 | 0 | 24 |
| 동일 체결의 정상 정정 1건 | 11 | 11 | 11 | 0 | 33 |
| 독립 settlement 1건 | 0 | 0 | 0 | 8 | 8 |
| 최초 fill 1 + 정정 7 | 85 | 85 | 85 | 0 | **255** |
| 최초 fill 1 + 정정 6 + settlement 1 | 74 | 74 | 74 | 8 | **230** |
| 서로 다른 최초 fill 8건 | 64 | 64 | 64 | 0 | **192** |

첫 번째 8건 최악 사례의 테이블별 분해는 다음과 같다.

| 테이블/구분 | 행 수 |
|---|---:|
| replacement event | 24 |
| reversal event | 21 |
| journal | 90 |
| decision | 24 |
| projection | 24 |
| ledger outbox | 24 |
| delivery | 24 |
| consumer inbox | 24 |
| 합계 | **255** |

계좌 단위 `ledger_workstate`, `execution_cursor` 신규 생성분은 별도로 공통 몫에 계상한다. 기존 stream의 갱신은 새 logical row가 아니지만 새 값의 byte 변화는 반영한다.

따라서 192행 대비 **63행 부족**이다. 소비 inbox를 아직 만들지 않아도 231행으로 39행 부족하다. 다른 root 세부 배분을 그대로 전부 보호하면 `32+64+255+64+32=447`로 intent 384보다 63행 많다. 이는 전체 최악 trace를 실행한 수치가 아니라, **기존 배분을 동시에 보장하는 합산 증명이 실패한다는 산술 근거**다.

근거: [trade 생성](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:744), [fee/tax 생성](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:913), [settlement 생성](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:990), [Q20 append](/Users/okestro/projects/QuantHarbor/migrations/0002_synthetic_ledger.sql:528), [소비 inbox](/Users/okestro/projects/QuantHarbor/migrations/0002_synthetic_ledger.sql:568).

현재 index 정의로 위 255행에 대응하는 index entry는 다음과 같다.

`event 180 + journal 90 + decision 24 + projection 72 + outbox 24 + delivery 24 + inbox 24 = 438`

이를 record로 더하면 693개다. index는 bytes로 계상하더라도 비용을 생략하면 안 된다. 근거: [Q20 테이블·index](/Users/okestro/projects/QuantHarbor/migrations/0002_synthetic_ledger.sql:160).

**byte 계산은 행 수와 별도로 수행한다.** 현재 입력 전체의 실제 길이를 측정하지 않았으므로 정확한 사용 byte를 주장하지 않는다. 구현용 보수적 상계는 다음처럼 만들 수 있다.

- event/decision/projection의 canonical 본문 64KiB와 중복 메타데이터 최대 2KiB를 각각 검증한다.
- journal/outbox/delivery/inbox의 전체 canonical row는 각각 1KiB 이내인지 검증한다.
- 현재 Q20 index key는 identifier 128자 등 기존 제약에서 계산하여 entry별 512bytes 이내인지 검증한다.
- 특히 projection 본문 64KiB 제한은 Q27 경계에서 추가 검증해야 한다. 현재 SQL projection trigger는 재생 결과 일치를 검사하지만 해당 byte 제한을 직접 강제하지 않는다.

위 조건이 강제된 후의 보수적 상계는 다음과 같다.

`93×67,584 + 162×1,024 + 438×512 = 6,675,456 bytes`

이는 **추가 검증을 전제로 한 상계**이며 실제 측정값이 아니다. 이 사례는 byte 24MiB보다 **record 배분 192의 부족**이 먼저 문제다. 0001/0002를 바꾸어 원장 행을 생략하는 해결은 권고하지 않는다.

**3. 원장 외 행·history·hold의 현재 한계**

| 대상 | 현재 소스에서 확인한 수량/한계 | 필요한 처리 |
|---|---|---|
| claim | intent당 1행, terminal 이후 보존 | generation과 무관한 고유성 유지 |
| intent/current outbox/budget | 각각 intent당 1행 | body 복제·키 bytes도 포함 |
| reservation | 정상 admission당 정확히 4행 | `(intent, component)` UNIQUE로 SQL에서도 고정 |
| submit/cancel attempt | submit 1, cancel 최대2 | 취소 명령·receipt/history 포함하여 계산 |
| broker fact | issuer가 intent당 최대8 | DB에도 동일한 발급 manifest 결속 |
| broker inbox | 사실 identity별 저장 | 중복은 추가 경제행0 |
| resolution/history | 현재 사건8에서 고정 상한을 도출할 수 없음 | 동일 미해결 재처리의 무변화 반환 필요 |
| query evidence | broker 발급은20 제한 | 동일 query 재사용으로 history 증식 금지 |
| reconciliation | 호출마다 새 UUID evidence | 동일 read-set 결과 재사용 또는 발급 시 비용 예약 |
| session/approval hold | 별도 보호 몫 | 사용 불가능한 session 미래 몫만 회수 |
| source/risk/index/history | 여러 map·evidence에 분산 | 소유자와 실제 비용을 모두 지정 |

특히 `reprocess()`는 predecessor가 계속 없는 동일 사건을 다시 처리하여 intent history를 추가할 수 있다. `reconcile()`도 같은 query에 새 reconciliation을 만든다. 따라서 “broker8이므로 전이/history64 이하”는 현재 소스에서 증명되지 않는다. 전체 저장 한도에 닿을 때까지 보호 공간을 소진할 수 있는 경로다.

최소 보완은 사건별 최초 처리와 명시 재처리 결과를 구분하되, **동일 사건·동일 dependency/read-set·동일 결과이면 기존 결과를 반환**하는 것이다. 원본 사실은 한 번 저장하고, quarantine alias와 원본 객체의 복제를 늘리지 않는다. 재처리 성공에 필요한 predecessor는 새 사실 슬롯에서 계상한다. 예약은 query 변경 때 새 행을 만들지 않고 기존 4개 component의 cutoff/reflected 값을 원자 갱신한다.

근거: [admission·예약](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:385), [재처리](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:768), [reconciliation](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:633), [query 발급](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_execution_broker.py:160).

**4. 한도를 늘리지 않는 예약·발급 전이**

현재 `greatest(전체 실제량, 전체 예약량)`은 소유자별 보호를 증명하지 못한다. 한 intent의 초과 사용이 다른 intent의 미사용 예약을 먹어도 전체 합계만으로 드러나지 않을 수 있다. 다음 계상을 권고한다.

```text
owner_charge = actual_used + remaining_completion_reserve

각 intent:
  owner_charge_records <= 384
  owner_charge_bytes   <= 24MiB

전체:
  실제 보존 자료 + 모든 미사용 보호 예약 <= 1024records / 64MiB
```

실제 기록이 생기면 해당 소유자의 예약에서 같은 비용을 차감한다. `실제량+최초384`로 이중 가산하지 않는다. source 8MiB/128refs, 공통 제어·복구 128records/8MiB, Q26 독립 제한도 각자 검사한다. budget 행과 그 index 자체도 포함한다.

최소 전이는 다음과 같다.

1. **admission 준비:** 고정 issuer의 최대8개 facts와 submit/cancel/withdraw·역순·정정·quarantine·소비 완료 분기를 포함한 비용 manifest를 산출한다. 단순 입력 tuple 순서만 계산하지 않는다.
2. **예약과 admission:** 기존 배분 및 전체 한도 안에 들어올 때만 승인 consumed·claim·intent·4 reservations·outbox·receipt·완료 예약을 같은 transaction으로 commit한다.
3. **사실 발급:** 예약된 issuer/intent/slot과 정확 payload identity에 결속한다. 9번째는 journal 변경 전에 거부한다. 이미 발급된 동일 슬롯은 같은 사실을 반환한다.
4. **수신·정정·취소 확인:** 신규 공용 공간이 아닌 해당 슬롯의 보호 몫을 사용한다. stop·옛 session 만료·새 generation 때문에 이미 발급된 금융 사실을 버리지 않는다.
5. **종료:** 금융 최종성과 issuer의 남은 발급 가능 범위를 확인한 뒤 **사용 불가능해진 미래 저장 예약만** 회수한다. consumed·claim·history·미반영 D·미확정 비용 hold는 유지한다.

현재 broker는 facts를 생성자에서 최대8개로 받으므로 큰 framework 없이 발급 전 manifest를 만들 수 있다. 다만 255행 사례를 **발급 후 거절하거나 정정 근거를 버리는 방식은 불가**다. 기존 192 배분을 유지하려면 이 manifest는 admission/발급 전에 용량 부족으로 거부해야 한다. 이를 “임의8건 보장”으로 표시하지 않는다.

**active2와 영구 예약도 각각 수정해야 한다.**

Python은 현재 `len(s['intents']) >= 2`로 **누적 두 개**를 제한한다. SQL은 active만 세지만, budget 384/24MiB를 terminal 이후에도 줄이지 않는다. 세 번째 intent는 SQL에서도 예약만 `1152+128=1280records`, `72+16=88MiB`가 되어 막힌다. 근거: [Python admission](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:388), [SQL 예약·합계](/Users/okestro/projects/QuantHarbor/migrations/0003_synthetic_execution.sql:193).

active count와 저장 여유를 분리하고 terminal의 **잔여 필요 비용**을 계산해야 한다. 단, `active≤2`는 무한 이력 보존 상태에서 항상 두 주문을 새로 열 수 있다는 보장이 아니다. 두 active의 48MiB와 공통/source 16MiB를 모두 보호하면 이전 terminal 이력용 여유가 없다. 세 번째 양성 검사는 과거 실제 사용량·잔여 보호량이 들어가는 trace에서 입증하고, 공간 부족 자체는 명시적으로 거부해야 한다.

**5. Q26 `retired_commands` 처리**

현재 실제 함수명은 `_invalidate_generation`이다. 이전 commands/nonces/receipts/cancel_nonces를 generation별 archive에 복사하고 live map을 비운다. `_usage`는 archive를 제외하며, 상위 Q26 계상도 정해진 map만 센다.

- immutable `records`는 계속 Q26 사용량에 남는다.
- 이동한 command/nonce/receipt 인덱스의 record 비용은 Q26에서 사라진다.
- archive 내용은 state JSON에 남아 실제 저장·전송 비용은 계속 발생한다.
- Q27 SQL은 archive 내부 항목을 독립 row로 세지 않는다.
- generation별 archive 수에 별도 상한이 없으므로 반복 복구가 원래 계상을 우회한다.

따라서 **현재 이동은 승인된 용량 회수로 인정할 수 없다.** 근거: [Q26 제외 목록](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:178), [archive 이동](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:1150), [root 미승인 기록](/Users/okestro/projects/QuantHarbor/docs/evidence/execution-control-partial-2026-10-25.json:2796).

최소안은 archive 복제 map을 없애고 기존 불변 `ActionChallenge`·`ActionReceipt`·cancel evidence에서 과거 조회를 재구성하는 것이다. 필요한 UNIQUE index는 유지하고 비용을 계상한다. 과거 nonce는 generation 불일치로 실행 불가이며, 과거 결과 조회는 권한 확인 후 기존 evidence를 반환한다.

원본 canonical 기록의 Q26 소유권을 Q27로 옮기지 않는다. 실제로 제거한 **중복 lookup 저장분만** 회수할 수 있다. 살아 있는 명령의 완료 예약은 유지하고, 종료된 session의 불가능한 미래 제어 몫만 회수한다. consumed 승인 보호 철회 몫도 남은 횟수·기존 미완료 명령과 대조해야 한다. 현재 `remaining×8` 대입만으로 원래 hold 보존을 입증하지 않는다.

반복 restart도 새 history를 소비한다. 무한 재시작 보장은 할 수 없으며, 새 세대·session 발급 전에 다음 필요한 복구/종료 공간을 확보해야 한다.

**6. 8MiB 프레임과 전체 state 전송**

현재 `_persist()`는 persistent state 전체와 evidence 전체를 함께 보낸다. state에는 이미 evidence·intent·reservation 등이 포함되어 있다. SQL literal은 UTF-8를 hex로 변환하므로 전송 크기가 다시 두 배가 된다.

따라서 저장 JSON 길이를 `R`, 나머지 SQL·marker 길이를 `H`라 하면 현재 입력 조건은 대략 다음이다.

`2R + H ≤ 8,388,608`

즉 JSON은 **4MiB보다 작은 지점**에서 막힌다. SQL `raw≤8MiB` 검사보다 UoW 프레임 제한이 먼저 작동한다. load·ledger events·fingerprint의 전체 `jsonb_agg` 응답도 단일 프레임 제한과 충돌한다.

근거: [전체 저장](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:214), [hex literal](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_ledger.py:28), [프레임 제한](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/execution_uow.py:36), [전체 fingerprint](/Users/okestro/projects/QuantHarbor/migrations/0003_synthetic_execution.sql:241).

최소 대안은 같은 UoW를 유지하면서 다음만 추가하는 것이다.

- 잠금 후 keyset 기반 `load_page`로 필요한 canonical record를 읽는다. 페이지 사이 transaction을 바꾸지 않는다.
- 저장은 신규 evidence·변경 head·명령 전이만 보낸다. 전체 snapshot 재저장을 제거한다.
- 큰 묶음이 필요하면 **동일 transaction의 session staging**으로 분할한다. product가 임의 temp table을 만들어 신뢰 대상으로 지정하는 API는 두지 않는다.
- chunk 원문 최대65,536bytes, 전달 header 최대4,096bytes, hex 포함 프레임 최대135,168bytes로 제한한다. 최종 serialized frame에도 기존8MiB 검사를 적용한다.
- chunk sequence·개수·누적 원문 bytes·전체 hash·owner/action을 검사한다. Q27 자료는 누적64MiB 이하, 별도 Q26 전송은8MiB 이하이며, 각 quota의 record/index 비용 때문에 허용 payload는 이보다 작아질 수 있다.
- staging은 승인된 전이 delta만 허용한다. 분할 저장을 generic full-snapshot 권한으로 만들지 않는다.
- 누락·중복 충돌·잘못된 순서·timeout·EOF이면 transaction 전체 rollback. commit 후 staging 잔존0, rollback/연결 종료 후 잔존0을 검사한다.

현재 partial pipe write/read 동시 처리, 20초 deadline, statement15초/lock10초, stderr 폐기는 유지할 수 있다. 추가로 전체 transaction deadline과 누적 전송량 제한이 필요하다. 프레임마다 제한 시간을 새로 얻어 무한 진행하게 두면 안 된다.

COMMIT 후 EOF는 성공/실패를 단정하지 않고 동일 command receipt로 관측한다. 자동 금융 write retry는0이다. 예상 JSON 한 개와 정확 종료 marker만 허용하고, extra output·불완전 UTF-8·조기 EOF를 고정 오류로 처리한다.

메모리는 현재 `json.dumps`, `asdict`, `_pack`, hex 생성이 **크기 검사 전에 전체 복제**를 만들며, owner runner의 `capture_output=True`도 출력 상한이 없다. 페이지별 파싱·증분 hash·제한된 출력 수집으로 바꿔야 한다. canonical byte 상한을 Python RSS 상한이라고 주장해서는 안 된다. 정확한 RSS 상계는 이번 정적 검토에서 미확인이다.

**7. SQL AUTH 경계**

**직접 DML 금지만으로 인증·승인 위조를 막지 못한다.**

현재 product role에는 `execution_save`, `execution_event`, `execution_ledger(...,'append',...)` 실행 권한이 있다. 이 함수들은 live opaque handle을 검증하지 않는다. caller가 일관된 hash와 state를 만들어도 그 hash는 권한 증명이 아니다. `execution_event`나 `execution_consume`를 단독 호출하면 `execution_save`의 용량 검사도 반드시 거치는 구조가 아니다.

근거: [함수 구현](/Users/okestro/projects/QuantHarbor/migrations/0003_synthetic_execution.sql:116), [product EXECUTE grant](/Users/okestro/projects/QuantHarbor/migrations/0003_synthetic_execution.sql:260), [단독 consume 경로](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:730).

권고 경계는 **기존 trusted Python composition과 제한된 SQL 권한 전달부**다.

1. trusted Python이 실제 `_SessionHandle` identity와 살아 있는 issuer registry를 현재 gate 안에서 검증한다.
2. 같은 DB transaction에서 ledger→account→head를 잠그고 현재 session/permissions/nonce/head/source/version을 읽는다.
3. 제품 role이 생성할 수 없는 transaction context에 검증된 actor·action·대상·generation/fence·read-set·시각/유효기한·issuer 사실 identity를 결속한다.
4. 고정 전이 함수가 context를 확인하고 DB 현재값을 다시 검사한 뒤 허용된 전이만 계산한다.
5. context는 backend/transaction/operation에 묶고 종료 시 제거한다. 다른 연결·transaction·action에서 재사용할 수 없다.

여기서 hash는 **이미 신뢰 경계가 확인한 내용의 결속값**일 뿐이다. `authorize(hash)`처럼 product가 자기 parameter hash를 제출하여 context를 생성하는 함수, caller 설정 GUC, 일반 bool은 금지한다.

DB는 Python 객체 identity를 스스로 검증할 수 없다. 따라서 product도 위 context 생성 권한을 가진다면 해결되지 않는다. owner/bridge 권한은 trusted host에만 두고 product에는 부여하지 않는다. 현재 연결은 owner 사용자로 접속한 후 `SET LOCAL ROLE`을 사용하므로, 이를 hostile SQL session의 완전 격리라고 주장해서도 안 된다. owner의 `RESET ROLE` 가능성과 제품 role 자체 ACL은 별도 검증 대상이다.

이 설계는 trusted host/DB owner 공격 방지를 주장하지 않는다. 실제 인증·비밀번호·외부 credential을 추가할 필요도 없다.

**8. 최소 SQL schema와 고정 write API**

기존 테이블을 활용하되 `execution_account.state` 전체 JSON을 권위 입력으로 받는 경로를 제거한다. SQL이 조회할 최소 정규 필드는 다음과 같다.

| 영역 | 필요한 필드·제약 |
|---|---|
| account | synthetic environment, generation/fence, mode, version, 현재 source/policy refs |
| session/permissions | issuer/principal/account/generation, session 상태·만료·liveness, 현재 action 권한 |
| command/receipt | command ID, nonce UNIQUE, action, session, target/version, expiry, immutable 결과 |
| evidence/head | 닫힌 schema, canonical hash, account/environment, version·previous_ref 연속성 |
| claim/intent/outbox | candidate 고유성, 정확한 consumed approval ref와 intent ID 상호 결속 |
| reservation | intent별 4 component UNIQUE, exact numeric, 보존식, scope·cutoff·근거 refs |
| broker fact/resolution | 실제 issuer·slot·request·revision·payload, bounded disposition 전이 |
| budget | owner별 actual/remaining, category, 발급 슬롯과 완료비용 |

권고 API는 caller가 금융 결과를 지정하지 않는 형태다.

| 고정 함수군 | 허용 입력·동작 |
|---|---|
| session/control | 검증된 actor context와 명시 action; stop/권한변경/세대변경 |
| presentation/challenge/decision | 원천 refs·목표 version; DB가 nonce·전이·receipt 생성 |
| admit | 저장된 승인·명령 참조; consumed/claim/intent/예약/outbox 원자 생성 |
| arm submit/cancel | 대상 ID/version; terms·최대잔량은 DB에서 해소 |
| record broker receipt/fact | live issuer에서 확인한 정확한 사실; SQL이 기존 상태와 결속 |
| refresh/reconcile/resume | 검증된 query/source refs; 동일 read-set과 현재 대사 확인 |
| consume ledger | 저장된 outbox identity; 소비 inbox와 execution cursor 원자 갱신 |
| restart/rebind | trusted composition의 새 issuer 결속; 옛 권한 폐기·기존 경제 보존 |

내부에서만 기존 `ledger_append`를 호출한다. product의 generic append/event/save 실행 권한은 제거한다. 원장 submission·원금·fee/tax·dependency는 검증된 사실과 stored intent에서 도출한다. 호출자가 journal이나 `risk_allow`를 자유롭게 공급하는 API로 대체하지 않는다.

**NULL 지적은 일부 확인된다.** `execution_evidence`의 environment/hash CHECK는 누락 필드에서 SQL NULL이 되어 통과할 수 있다. intent도 environment/account/previous hash 등의 비교가 NULL-safe하지 않다. 다만 `ledger_decimal`은 누락·잘못된 타입을 거부하므로 “빈 intent `{}`가 모든 검사를 통과한다”고 단정하면 부정확하다.

근거: [evidence/intent CHECK](/Users/okestro/projects/QuantHarbor/migrations/0003_synthetic_execution.sql:13), [decimal 검증](/Users/okestro/projects/QuantHarbor/migrations/0002_synthetic_ledger.sql:6).

0003의 validator는 다음을 명시적으로 강제해야 한다.

- 필수 key 집합 정확 일치, 중복 JSON key 거부, 필수값 nonnull, nullable 필드 별도 지정.
- `IS DISTINCT FROM` 또는 `(조건) IS NOT TRUE`로 NULL 통과 제거.
- decimal 문자열·정밀도·범위·정규형 검사 후 계산. bool/float/NaN/Infinity·암묵 반올림 거부.
- UTC 정규형, synthetic environment, account/ref 일치와 복합 FK.
- version `old+1`, 정확 previous hash, 허용 state 전이, immutable terms/승인 대상.
- `bound=held+used+released`, 비음수, `settled/reflected≤used`; release에는 실제 최종성 근거.
- consumed approval의 **정확 version/hash/intent ID**와 claim/intent/outbox의 양방향 commit 결속.
- command/nonce/session/action/target/version/expiry와 receipt 일치.
- 같은 transaction의 현재 permissions·session·source·ledger cursor·시간 재검사.
- 모든 변경 경로의 소유자별 용량 검사. save를 호출하지 않는 consume/control도 예외 없음.

**9. 구현 순서·소유 파일·실제 DB 검사 제안**

단독 구현자가 다음 순서로 진행하는 것이 작고 검토 가능하다.

1. **계상과 manifest:** 새 작은 `execution_budget.py` 또는 기존 execution 모듈에 순수 비용 계산을 두고 owner/category별 산식을 고정한다. root가 한도 해석과 192행 부족 처리 원칙을 통합한다.
2. **0003:** 닫힌 validator·auth context·고정 전이 함수·budget 강제를 구현한다. 0001/0002는 보존한다.
3. **repository/broker:** generic snapshot 저장 제거, active count 수정, archive 중복 제거, 발급 전 예약, 동일 사건·조회 재처리의 무변화 반환을 적용한다.
4. **UoW:** 같은 연결의 paged load/chunked delta·staging·bounded I/O를 구현한다.
5. **root runner:** actual DB assertions와 cleanup 검사를 추가한다.

주 소유 파일은 [postgres_execution.py](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py), [execution_uow.py](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/execution_uow.py), [synthetic_execution_broker.py](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_execution_broker.py), [0003](/Users/okestro/projects/QuantHarbor/migrations/0003_synthetic_execution.sql), [check_execution.py](/Users/okestro/projects/QuantHarbor/scripts/check_execution.py)와 해당 execution 시험·개발 안내다. Q26 변경이 필요하면 별도 seam으로 명시하고 기존 계약·fixture 의미를 보존한다.

root 실제 DB 검사는 최소 다음을 포함해야 한다.

| 범위 | 필요한 실제 assertion |
|---|---|
| EX32 | 신규 요청 포화 뒤 이미 발급된 fill/정정/취소확인/withdraw/stop/복구 완료 가능; 타 owner 예약 불변 |
| row/byte | 실제 테이블별 행·index key bytes와 독립 산식 일치; reversal·delivery·consumer inbox 포함 |
| 부족 사례 | 255행 manifest는 발급 전 거부·부작용0; 이미 발급한 근거를 용량 오류로 버리지 않음 |
| active/terminal | 여유 있는 trace의 세 번째 intent 양성; active3 거부; terminal 이력·claim·금융 hold 보존 |
| archive | 여러 generation의 실제 사용량 증가가 계상됨; 중복 archive 없음; 옛 권한 거부·새 rebind 양성 |
| SQL AUTH | context 없는 save/append/event·자기서명 hash·다른 연결/context 재사용 거부 |
| SQL CLOSED | 누락/NULL/extra key/enum/bool/decimal/UTC/foreign account/FK/version/previous hash/불법 전이 거부 |
| 원자성 | standalone consumed·intent·outbox, 잘못된 nonce/receipt, 예약 불보존의 COMMIT 실패와 전체 fingerprint 불변 |
| EX37 | 프레임 경계±1, 부분 I/O, malformed/extra output, EOF, timeout, 누락/충돌 chunk, rollback 후 staging0 |
| EX40 | noargs/fixedscope, 기존 고정 이미지·격리, migration 순서/hash/idempotence, 자기 자원 cleanup 실제 확인 |

AUTH가 먼저 거부한 사례를 CLOSED 제약 검증으로 중복 집계하지 않는다. 구조 제약은 root의 관리용 negative transaction과 명시된 정상 권한 context에서 별도로 검사해야 한다.

runner 관찰성은 선택 보완으로 유지한다. stderr에는 고정 scenario 번호·start/end/fail code만 출력하고 rawSQL·원장·환경·비밀값을 출력하지 않는다. 최종 stdout JSON, 실제 assertion, cleanup 판정은 그대로 유지한다.

**미확인·인계 판정**

이번 자문은 192행 배분의 부족량과 현재 계상·권한 전달의 구체적 결함을 정적으로 확인했다. 전체 384행의 모든 경로별 최악 비용, 실제 canonical/index 사용 bytes, staging/RSS 상한, 변경 후 SQL direct negatives와 정상 restart/rebind는 아직 실행 증거가 없다.

root에는 **논리 canonical+index-key byte 해석, 중복 archive 제거, 소유자별 완료 예약, 발급 전 manifest 검사, 고정 SQL 전이와 동일 transaction 권한 전달**을 추천한다. 한도·baseline7·0001/0002·고정 fixture는 확대하거나 변경하지 않는다. 이 자문으로 EX32/34/37/40 완료 또는 전체 보안 PASS를 주장하지 않는다.