**FUP-Q27-006_STATIC_MAPPING_ACCEPTABLE=false**

정적 연결은 **34개 supported_static, 6개 real_gap**입니다. 아래 gap은 필수 입력·관측의 부족이며, 제품 결함을 재현했다는 뜻은 아닙니다. 새 집중 보강 EX02/05/18/25/31과 EX12는 본문상 연결을 확인했습니다.

표의 D는 `scripts/check_execution.py`, F는 `test_execution_financial.py`입니다. `supported_static`은 동적 PASS나 Q27 완료를 의미하지 않습니다.

| 정본 | 판정 | 본문에서 확인한 assertion·준비조건 |
|---|---|---|
| EX01 | supported_static | [D:85](../../scripts/check_execution.py#L85): 3/100/2/302, applied, intent/claim/outbox/예약 행 수와 consumed 확인. |
| EX02 | supported_static | [D:280](../../scripts/check_execution.py#L280), [D:868](../../scripts/check_execution.py#L868): 경쟁 승인 미소비, 세대 변경·aborted_unsent 후 **새 실제 승인**도 candidate_already_consumed. |
| EX03 | supported_static | [D:225](../../scripts/check_execution.py#L225): 실제 SQL lock 대기·요청 중첩, 승자 하나, 잔액 298/198. |
| EX04 | supported_static | [D:87](../../scripts/check_execution.py#L87): consumed부터 commit까지 각 fault의 commit_failed와 fingerprint 불변. |
| EX05 | supported_static | [D:249](../../scripts/check_execution.py#L249): 실제 COMMIT 후 응답 프레임 유실, 조회 재실행 무변경. 다른 approval payload는 replay_conflict·intent 추가 없음. |
| EX06 | supported_static | [D:121](../../scripts/check_execution.py#L121): A598 전체 현금 구성값, 실제 Q20 수량1·payable−100. |
| EX07 | supported_static | [D:132](../../scripts/check_execution.py#L132): 결제 후 L900/H202/B1000/U202/D100/A598. |
| EX08 | supported_static | [D:149](../../scripts/check_execution.py#L149): 독립 fresh query, cutoff/reflection, A598, 다음 실제 admission 후196. |
| EX09 | supported_static | [D:911](../../scripts/check_execution.py#L911): 실제 구성값12/4/10/2/1과 sellable 호출 인자 확인, 7 허용·8 거부. |
| EX10 | **real_gap** | [F:188](../../tests/product/test_execution_financial.py#L188)은 미수금100. [D:388](../../scripts/check_execution.py#L388)도 기본 1×100이며 정본 입력500이 없음. |
| EX11 | supported_static | [D:931](../../scripts/check_execution.py#L931): 400+100+50, 실제 current_risk 진입·risk_blocked. 반대매도 비상계는 [D:560](../../scripts/check_execution.py#L560)의 별도 관측. |
| EX12 | supported_static | [D:569](../../scripts/check_execution.py#L569), [D:592](../../scripts/check_execution.py#L592): 실제 gross400/NAV1000/가용금≥300, current_risk·prospective_loss 진입, turnover 인자400/650/0/1000 및 daily 선행 거부. |
| EX13 | supported_static | [D:599](../../scripts/check_execution.py#L599): 실제 손실40와 prospective_loss 인자40/15/960. [수학:68](../../tests/product/test_execution_math.py#L68)은55·미확인 분모 거부. |
| EX14 | supported_static | [단위:91](../../tests/product/test_execution.py#L91): 자기 예약 제외. [제어:380](../../tests/product/test_execution_control.py#L380): 실제 deadline 집합·정확 만료 거부. heartbeat 불연장은 공통 [AP07:182](../../tests/product/test_approval.py#L182). |
| EX15 | supported_static | [D:674](../../scripts/check_execution.py#L674): stop/withdraw 양 순서의 실제 스레드 경쟁·송신0/1·handoff 후 release0. |
| EX16 | supported_static | [D:173](../../scripts/check_execution.py#L173): handoff 후 장애, received1·unknown·hold302·재송신 거부. |
| EX17 | supported_static | [D:752](../../scripts/check_execution.py#L752): 새 authority/세대, 옛 handle 거부·예약/claim/원장 보존·미해결 resume 거부. |
| EX18 | supported_static | [D:186](../../scripts/check_execution.py#L186), [D:1979](../../scripts/check_execution.py#L1979): 빈 조회는 unresolved. 하루 경과 후 intent·양수 hold 보존, 새 intent/send 없음. |
| EX19 | supported_static | [D:503](../../scripts/check_execution.py#L503): 위조/foreign/bool 거부·fingerprint 불변, 실제 issuer final_reject만 예약 해제. |
| EX20 | supported_static | [D:123](../../scripts/check_execution.py#L123): 중복 fill 무변경·수량1. [D:314](../../scripts/check_execution.py#L314): fill 선행 후 late ACK가 partially_filled를 퇴행시키지 않음. |
| EX21 | **real_gap** | [F:118](../../tests/product/test_execution_financial.py#L118), [D:370](../../scripts/check_execution.py#L370): 누계3·누락 선행사건·재처리는 확인. **mixed semantics 입력·격리 assertion 없음.** |
| EX22 | supported_static | [F:105](../../tests/product/test_execution_financial.py#L105): revision2 선행 격리→revision1→명시 재처리, 유효수량2·이전 revision 무퇴행. |
| EX23 | supported_static | [D:411](../../scripts/check_execution.py#L411): 충돌·초과체결 증거4개 보존, used100 유지·신규 거부·Q20 incomplete. |
| EX24 | supported_static | [D:112](../../scripts/check_execution.py#L112): inbox/ledger/reservation/intent/history/commit 각각 fingerprint 불변 후 동일 발급 사건 적용. |
| EX25 | supported_static | [D:137](../../scripts/check_execution.py#L137), [D:1996](../../scripts/check_execution.py#L1996): 역순·중복 inbox 분리, 실제 consume COMMIT fault rollback→accepted→duplicate noop·workstate cursor 확인. |
| EX26 | supported_static | [D:347](../../scripts/check_execution.py#L347): 미확인 비용의 보수적 used/hold, 동일 사건 완성 revision·fee/tax·결제·중복 무변경. 미지원 경계는 별도 safe-block 근거로 분리. |
| EX27 | **real_gap** | [D:629](../../scripts/check_execution.py#L629): 별도 cancel·ACK 무해제. [제어:454](../../tests/product/test_execution_control.py#L454)는 승인자 권한 거부, [제어:462](../../tests/product/test_execution_control.py#L462)는 버전 거부. wrong-account/target 관측 연결 부족. |
| EX28 | supported_static | [D:633](../../scripts/check_execution.py#L633): ACK/timeout 후 fill 수용, 확정 잔량만200 해제, 중복·재송신 거부. |
| EX29 | supported_static | [D:718](../../scripts/check_execution.py#L718): 기존 승인·source 권리 상실 후 새 controller 철회 성공·송신0. 금융 조회 제한은 상속 query와 [AP06:172](../../tests/product/test_approval.py#L172)의 보조 연결. |
| EX30 | supported_static | [D:886](../../scripts/check_execution.py#L886): session/current-query 결속. [D:1854](../../scripts/check_execution.py#L1854): 초기 빈 계좌의 실제 matched→명시 resume·주문0. |
| EX31 | supported_static | [D:755](../../scripts/check_execution.py#L755), [D:1982](../../scripts/check_execution.py#L1982): 세대 복구 시 claim/예약 보존·옛 handle 거부, 하루 경과 옛 challenge 거부·추가 금융 효과0. |
| EX32 | supported_static | [D:1168](../../scripts/check_execution.py#L1168): 포화 예약 중 fill/correction/cancel/withdraw/stop/restart. [D:1567](../../scripts/check_execution.py#L1567): 실제 active3 입장 가드·무추가. rows/key bytes/미래예약 범위로 한정. |
| EX33 | **real_gap** | [단위:102](../../tests/product/test_execution.py#L102)와 [F:346](../../tests/product/test_execution_financial.py#L346)은 권리·위조 조회·stale query를 관측. stale cost/classification 등 정본 나머지 조건의 실제 거부 assertion 연결 부족. |
| EX34 | **real_gap** | [D:1025](../../scripts/check_execution.py#L1025): closed-field/삭제/보존식·COMMIT orphan 검사는 있음. cross-account/enum/negative/행 version·FK의 독립 SQL 음성 입력 부족. |
| EX35 | supported_static | [D:207](../../scripts/check_execution.py#L207): 두 facade, 공유 gate, 별도 SQL lock 경쟁과 단일 경제 효과. **one process 범위.** |
| EX36 | supported_static | [경계:27](../../tests/product/test_execution_runner.py#L27), [단위:115](../../tests/product/test_execution.py#L115): 임의 객체·subclass·duck adapter 거부. exact adapter 직접 단위검사가 적절함. |
| EX37 | **real_gap** | [D:1272](../../scripts/check_execution.py#L1272): framing/UTF8/EOF/timeout/rollback 확인. 공통 byte/text 검사도 있으나 **전체 해소 집합128refs 한도를 실제 유발하는 assertion 연결 없음.** |
| EX38 | supported_static | [D:441](../../scripts/check_execution.py#L441): obligations=True에서 실제800→498→96. |
| EX39 | supported_static | [D:329](../../scripts/check_execution.py#L329): 정정 후 principal used290/held10/cost held2, 실제 Q20 수량3·보존식. |
| EX40 | supported_static | [D:70](../../scripts/check_execution.py#L70): migration 재적용·count3. [D:2093](../../scripts/check_execution.py#L2093): own DB context·cleanup 수거. 현재 전체 실행의 실제 최종 정리 판정은 보류. |

필요한 최소 보완은 다음과 같습니다. 모두 **P2 수용 근거 공백**이며 정본·생산 가드·한도 변경을 요구하지 않습니다.

| Gap | 정본 절 | 누락 조건과 최소 보완 |
|---|---|---|
| EX10 | [fixture:178](../../docs/contracts/execution-fixture-v1.json#L178) | 매도 미수금 **500**을 실제 생성하고 금액을 assert. 예: 유효한 5×100 매도와 대응 결제에서 fresh complete query 전 가용금 불증가 확인. 현재 수학 검사의 broker500·ledger1500은 미수금500 관측을 대신하지 못함. |
| EX21 | [fixture:235](../../docs/contracts/execution-fixture-v1.json#L235) | 동일 intent에 delta→cumulative처럼 혼합 의미의 실제 issuer 사건을 입력. [mixed_semantics 가드](../../src/quantharbor/adapters/postgres_execution.py#L1219)에 도달해 격리·증거 보존·기존 경제량 불변을 확인. |
| EX27 | [fixture:265](../../docs/contracts/execution-fixture-v1.json#L265) | 유효한 cancel 준비 후 foreign-account 권한/다른 target을 각각 제출하고 거부·송신 불증가·금융 불변 확인. 기존 승인자·버전 음성 검사는 그대로 재사용해 매핑에 연결. |
| EX33 | [fixture:295](../../docs/contracts/execution-fixture-v1.json#L295) | 만료 cost rule과 classification을 다른 조건이 유효한 현재 입력에서 각각 유발. 해당 시간 가드에 도달한 거부·입장 무효과를 assert. 기존 Q24 공통 검사는 정확한 호출·assert 연결을 추가하면 재사용 가능. |
| EX34 | [fixture:300](../../docs/contracts/execution-fixture-v1.json#L300) | owner SQL로 cross-account/FK, 잘못된 enum, 음수, 잘못된 행 version을 각각 주입. permission/syntax 실패가 가드를 가리지 않도록 원인과 fingerprint rollback 확인. header version 공격만으로 행 version 제약을 대체하지 않음. |
| EX37 | [fixture:109](../../docs/contracts/execution-fixture-v1.json#L109) | 8MiB 이하에서 **서로 다른 전체 해소 refs가128을 초과**하는 source를 구성하고 [실제 count 가드](../../src/quantharbor/application/approval.py#L76)의 capacity_exceeded·무변경을 확인. 반복한 동일 refs나 bytes 초과 거부로 대체하지 않음. |

DEC002 미지원 4종은 [기존 supplemental 기록](../../docs/evidence/execution-resume-supplemental-db-initial-2026-10-30.json#L12)의 **증거 보존·safe-block 관측**으로만 취급했습니다. 해당 문서 전체 status는 storage 검사 실패이며, 미지원 정상 재해석 PASS로 올리지 않았습니다. EX32에도 물리 RAM/disk·모든 순열 증명을 추가하지 않았습니다.

입력 11개는 검토 전후 모두 지정 SHA와 일치했습니다. 매핑의 정본 입력·기대 문자열40개도 일치하며 범위는 driver86/45 symbols/57 unit methods입니다.

```text
map JSON 전=후
6c1e6b754eab08679abc06c053a0d295725a6b330b5b4c19de6e685b78ff477c

map MD 전=후
bf95a9887a35d91f34b97a730e8e0e7cba8d7e62b29033bbc6685d41de667e49
```

**시험·Docker·네트워크: NOT RUN. 파일쓰기·하위 agent·Git mutation·자동 retry: 0.** FUP-Q27-005의 동일708입력 전체836/86 최종 동적 수용은 별도 미확정 관문으로 유지하며, Q27 완료로 판정하지 않습니다.
