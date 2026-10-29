**P1 1건·P2 1건으로 PASS 불가입니다.** 아래는 실행 재현 없이 확인한 정적 경로입니다.

1. **P1 — 승인자 권한 회수 후에도 dispatch가 허용됩니다.**  
   근거: [synthetic_approval.py:589](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_approval.py:589).  
   입력 순서: 정상 approve→admit 후 controller가 `change_permissions(..., 'fixture-approver', ())`로 승인자의 권한을 모두 회수하고 dispatch를 실행합니다. 호출한 controller의 권한은 검사하지만, 원 승인자는 session 상태·만료·liveness만 검사합니다. 따라서 승인자의 현재 권한이 없어도 intent/outbox가 `dispatching`으로 전이됩니다. 같은 잠금 안에서 원 승인자의 현재 권한도 재검증해야 합니다.

2. **P2 — 미처리 challenge의 후속 기록이 보호 철회 예약을 소진합니다.**  
   근거: [challenge 공간 검사:417](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_approval.py:417), [receipt 저장:524](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_approval.py:524).  
   입력 순서: 정상 consumed 상태에서 서로 다른 command ID로 dispatch challenge 3개를 먼저 발급하고 순서대로 실행합니다. 예약 records는 `20→11`; 첫 dispatch 성공으로 `8`, 나머지 두 요청의 거부 receipt/index로 `6→4`가 됩니다. 이후 적법한 withdraw는 최소 8개 검사에서 `capacity_exceeded`로 차단됩니다. 발급 당시 미처리 명령의 완료 비용을 별도로 예약하지 않아 발생하며, 새 controller 세션도 해당 approval의 공간 부족을 해결하지 못합니다.

정상 금융조건 `3×100+2=302`, 단일 claim, 양방향 경합, 8단계 실패 원자성 assertion을 포함한 **시험 메서드 40개(AP 21·회귀 19)**를 정적으로 검토했습니다. 위 두 입력 순서는 기존 시험에서 다루지 않습니다.

검토 전후 **소유 9/9·baseline 7/7·fixture 1/1, 총 17개 SHA256 일치, drift 0**입니다. 최신 구현 증거의 실행 전후 소유 hash도 일치합니다. fixture SHA256: `84190ff349d81877bbfdace4ffd23d9e0c1de5d474c3a3c6568c870504c71300`.

**테스트 미실행.** 기존 40·27 통과 및 개발 중 수정 이력은 기록으로만 확인했습니다. 수정·하위 에이전트·네트워크·비공개 읽기·Docker·Git 변경은 없었습니다. 판정은 명시된 로컬 메모리 시뮬레이션 범위에 한정합니다.