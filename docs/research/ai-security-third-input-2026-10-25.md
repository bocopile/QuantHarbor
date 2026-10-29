**CHANGES REQUIRED — P2 1건.** 독립 정적 재검토 결과이며 테스트는 실행하지 않았습니다.

**P2 / AS4b·AS5b: 비소유 중복 호출의 clock 실패가 소유자의 정산을 변경합니다.**  
위치: [application/investment_ai.py:570](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:570), [synthetic_investment_ai.py:390](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_investment_ai.py:390).

- A가 예약·dispatch 후 client 응답을 기다립니다.
- 동일 attempt의 B는 `new=False`로 예약을 재조회하고 `budget` 거부 경로로 갑니다.
- B의 마지막 clock이 예외 또는 `None`을 반환하면, 소유권 검사 없이 `settle_unknown()`을 호출하여 A의 attempt와 scope를 변경합니다.
- 이후 A가 정상 usage를 반환해도 기존 `unknown_charge`와 충돌합니다. fallback도 이를 유지하므로 정상 사용량을 기록하지 못하고 scope 차단이 남습니다.

**수정:** 비소유 중복 호출을 정산 fallback에서 제외하십시오. 기존 dispatch 중복 시험에 “B의 마지막 clock 실패”를 결합하여, B가 attempt를 변경하지 않고 A가 정상 정산·완료 저장하는지 확인해야 합니다.

그 외 요청 범위에서는 추가 지적이 없습니다. AS1b의 본문 은닉·안전한 partial 유지, AS3b의 실제 영수증 권한 교집합, 기존 정상 정산 보존, 정상 중복 처리, AS6의 용량 실패 원자성과 성공·멱등 경로를 정적으로 확인했습니다.

검토 전후 **소유 13/13 + baseline 7/7 + spec 1/1 = 총 21개** 해시 일치, drift 0입니다. fixes2 증거도 불변입니다. 시험 정의는 **89개**, 그중 2차 보안 회귀 **23개**입니다. `tests_executed=false`.

최신 전체 시험은 독립 validator 대기이며, 과거 521 통과를 최신 결과로 인정하지 않았습니다. 수정·subagent·네트워크·private 접근·Docker·Git 변경은 수행하지 않았습니다.