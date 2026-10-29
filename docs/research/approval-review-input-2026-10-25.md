**Q26 독립 정적 검토: P2 2건으로 수정 필요합니다. P1은 발견하지 못했습니다.**

1. **P2 — 반복 `stop`이 `disconnect` 예약을 소진합니다.**  
   [synthetic_approval.py:666](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_approval.py:666)  
   기본 Harness에서 controller hold는 resume·risk 기록 후 6개입니다. 같은 시각에 `stop`을 5번 호출하면 매번 사건을 저장해 hold가 1개가 되고, 정상 `disconnect`가 `capacity_exceeded`로 거부됩니다. `stop`에는 종료 공간 보존 검사가 없습니다. 중복 stop 처리와 예약 계산을 보완해 stop·disconnect 모두 완료 가능하도록 해야 합니다. 기존 종료 공간 테스트는 runtime 반복만 검사합니다.

2. **P2 — 단절된 세션의 사용 불가능한 hold가 영구 유지됩니다.**  
   [synthetic_approval.py:678](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_approval.py:678), [복원 경로:778](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_approval.py:778)  
   새 approver 세션을 바로 disconnect하면 8개 예약 중 2개만 사용하고 **6 records·약 384KiB**가 남습니다. paused 세션은 이후 인증을 통과할 수 없고, restore도 running 세션만 정리하므로 이 예약은 회수되지 않습니다. 반복하면 실제 기록 외의 불필요한 예약 때문에 신규 세션 발급이 조기 차단됩니다. 이력은 보존하면서 종료된 세션의 잔여 hold를 원자적으로 정리해야 합니다.

그 외 요청한 타입·참조·승인 이력, 현재 원천 권리, 만료 경계, 재전달, 원자적 admission·철회·경합·복원 경로에서 추가 P1/P2는 발견하지 못했습니다. 실제 Q24 모듈을 사용하는 **고정21·회귀19·보안17개** assertion과 독립 상수 `3×100+2=302`, 표시 종료 `t0+20초`를 정적으로 대조했습니다.

검토 전후 **소유10/10 + baseline7/7 + fixture1/1 = 총18개 SHA256 일치, drift 0**입니다. 최초 구현9개→수정 전, 수정 후10개→최신 보안 근거 연결도 일치합니다.

Fixture SHA256: `84190ff349d81877bbfdace4ffd23d9e0c1de5d474c3a3c6568c870504c71300`

**테스트 실행 0건.** 전용57 통과는 구현자 기록이며 원천 재현도 재실행하지 않았습니다. 수정·subagent·MCP·네트워크·비공개 읽기·Docker·Git 변경은 없습니다.

남은 Q26 관문은 위 수정·회귀 검증·독립 재검토와 전체 제품/품질87 실행입니다. Q27의 실제 DB 원자성·egress·대사는 별도 미완료 범위입니다.