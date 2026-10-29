# Q25 독립 보안 지적

정적 검토이며 실제 재현은 수정 단계에서 수행한다.

**CHANGES REQUIRED — 정적 검토에서 5건 확인.** 아래 입력은 실행하지 않았습니다.

1. **P1 — 재호출로 현재 권리 검사 우회.** 보고 결과 생성 후 현재 grant의 `report` 권리를 제거하고, 같은 repository·request·attempt로 `run_research`를 재호출하면 과거 `complete` 본문을 그대로 반환합니다. [조기 반환](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:476)에도 현재 권리 검사를 적용하고 거부 시 본문을 숨겨야 합니다.

2. **P1 — 가설 의존성 대체로 철회 우회.** 문서 기반 가설의 `dependencies`를 유효한 `timezone_ref` 하나로 바꾸면 저장되며, 원문 권리가 철회되어도 `hypothesis_view`가 가설을 반환합니다. [저장 검사](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_investment_ai.py:79)는 claim ID만 연결하고, [조회 검사](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:258)는 제출된 dependencies만 검사합니다. 원래 claim·출처의 필수 의존성을 결속해야 합니다.

3. **P1 — 차단 결과를 `complete`·`accepted`로 승격 가능.** `collector`의 `snapshot_view` 요청으로 차단된 결과를 `replace(result, result_id='forged', status='complete', reasons=())`로 변경하면, 정상 정산 attempt와 통과한 원천 checks를 재사용해 저장할 수 있습니다. 이후 `review_result`는 응답의 query 권한을 재검사하지 않아 `accepted`를 만듭니다. [저장](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_investment_ai.py:62)과 [검토](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:548)에 실제 검증 결과·query 실행 증거의 결속이 필요합니다.

4. **P2 — 비정상 usage가 불명 청구 차단을 빠져나감.** `ClientReply(valid_payload, Usage(0,0,1,0))`는 [정산](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_investment_ai.py:208)에서 거부되지만 attempt가 `dispatched`로 남습니다. [호출 처리](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:499)는 `invalid`만 반환하며 scope를 차단하지 않아 다음 window의 호출이 가능합니다. 전송 후 정산 불능은 예약을 유지하는 `unknown_charge`로 확정해야 합니다.

5. **P2 — 요청별 query 16회 한도가 attempt마다 초기화됨.** 호출 cap이 4인 동일 request에서 attempt 4개에 허용 query를 각각 16개 제출하면 총 64회 실행됩니다. [dispatcher 지역 카운터](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:356)를 공유 repository의 요청별 원자적 누적 한도로 바꿔야 합니다.

소유 **11/11**, baseline **7/7**, fixedspec SHA256 모두 기록과 일치하며 검토 전후 불변입니다. 외부 client 비활성 및 실제 격리·모델 품질 미구현 표시는 구분되어 있습니다.

`tests_executed=false`; 수정·외부 호출·제품 API 지출 **0**. root 통합용 반환입니다.