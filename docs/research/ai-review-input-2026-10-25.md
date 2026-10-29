**CHANGES REQUIRED — P2 6건.** fixes3 최종 해시 기준의 독립 정적 검토입니다. 테스트·제품 코드는 실행하지 않았습니다.

1. **P2 — 정상 응답이 결과 포장 후 크기 제한을 넘으면 완료 기록이 유실됩니다.**  
   [application/investment_ai.py:574](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:574)  
   예: 기본 응답의 assumptions에 ASCII 2,048자 문자열 31개와 1,400자 문자열 하나를 넣으면 응답 자체는 64KiB 이내지만, request/attempt 참조 등을 붙인 ResearchResult는 한도를 넘습니다. 생성자 예외가 처리 범위 밖으로 나가 정산된 attempt와 저장 예약만 남고 결과는 저장되지 않습니다. 결과 포장 크기를 제한하고, 초과 응답도 청구를 보존한 작은 실패 결과로 확정해야 합니다.

2. **P2 — dispatch 전 clock 오류가 예약과 동시성 슬롯을 남깁니다.**  
   [application/investment_ai.py:516](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:516)  
   clock이 `[NOW, None, NOW]`를 반환하면 예약 후 시각 검증이 실패합니다. 이어 reserved 상태의 attempt를 가진 결과 저장도 [저장소 검사](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_investment_ai.py:77)에서 거부됩니다. 서로 다른 요청으로 두 번 발생하면 client 호출 없이 동시성 한도가 소진됩니다. 전송 전 실패에서는 소유 예약을 취소·해제해야 합니다.

3. **P2 — 거래가 있는 slippage claim은 정확한 값도 invalid가 됩니다.**  
   [application/investment_ai.py:349](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:349)  
   실제 TradeCostFact의 `slippage`는 Fraction인데, 문자열만 받는 `number()`에 다시 전달합니다. 예: 수량 10, 기준가격 100, 매도가격 99인 거래의 정확한 slippage `10`도 거부됩니다. Fraction을 그대로 합산한 뒤 `finite()`로 변환해야 합니다. 현재 selector 시험은 거래 없는 비용 `0`만 확인합니다.

4. **P2 — 금융 claim의 종목 identity가 무시됩니다.**  
   [application/investment_ai.py:339](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:339)  
   정상 performance ref와 TWR `0.21`을 유지하면서 claim.position을 무관한 종목·거래소로 바꿔도 해당 필드를 검사하지 않아 complete가 가능합니다. snapshot.nav/economic_cash도 같습니다. 계좌 전체 selector에는 position을 거부하고, 종목 selector에는 정확한 identity 일치를 강제해야 합니다.

5. **P2 — AI 응답 실패가 검증 가능한 기간 지표까지 제거합니다.**  
   [application/investment_ai.py:534](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:534)  
   완전한 주간 원천과 정상 권리가 있어도 client가 알려진 usage와 `b'{'`를 반환하면 period 계산에 도달하지 않아 `period_review=None`이 됩니다. client 예외도 같습니다. 계약대로 결정론적 기간 지표를 응답 파싱과 별도로 계산·보존하고 설명 실패 상태를 구분해야 합니다.

6. **P2 — 평가 전 manifest에 사례별 실제 변형 입력이 빠집니다.**  
   [test_investment_ai_evaluation.py:46](/Users/okestro/projects/QuantHarbor/tests/product/test_investment_ai_evaluation.py:46)  
   manifest는 공통 fixture만 기록하지만 E03 정정 문서, E04 누락 문서, E21 변경 grant 등은 사례 실행 중 생성됩니다. 확인한 fixes2 평가 JSON도 24개 사례 모두 같은 input_refs를 기록합니다. spec SHA·실행 identity의 사전 기록은 있으나, 사례별 실제 입력 refs의 사전 고정은 충족하지 못합니다. 변형 입력을 첫 평가 전에 구성하고 사례별로 결속해야 합니다.

검토 전후 **소유 13/13·baseline 7/7·fixedspec 1/1, 총 21개 해시가 동일**하며 fixes3·최종 보안 기록과 일치합니다. 고정 spec SHA는 `726411c4f367720820d7d47cc829e0baedca39254718c90c31a8bb8058004f3f`입니다.

Q18 인용 결속, 금융 원천 재검증, 현재 권리·TTL·철회, exact review hash, Q24 후보 불변, 공유 예산·불명 청구 경로를 검토했습니다. 실제 client는 disabled이며 실행 경로가 추가되지 않았습니다.

남은 게이트는 위 결함 수정·재검토와 **최종 소스의 독립 전체 시험·고정 24개 평가**입니다. fixes2의 24/24와 과거 전체 521 통과는 최신 버전 검증으로 집계하지 않았습니다. 수정·subagent·네트워크·private 접근·Docker·Git 변경은 수행하지 않았습니다.