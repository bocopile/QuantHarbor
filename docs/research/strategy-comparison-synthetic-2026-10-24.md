# 합성 기준 전략 비교 — 2026-10-24

24개 고정 합성 실행을 실제 로컬 구현으로 계산했다. 실제 시장 수익률·전략 추천 근거가 아니며 사용자 운용 전략은 아직 채택하지 않았다. 두 fold는 초기 자금으로 각각 시작하므로 수익률을 연결하지 않는다. 금액·비용·90% 배분은 시험 가정이고 실제 정책값이 아니다.

## 선택할 때 비교할 기능

| 기준 전략 | 동작 | 확인할 장점 | 검토할 비용·제약 |
|---|---|---|---|
| 현금 유지 | 매수 없이 현금 보유, 합성 이자0 | 무거래 기준선·주문 경로 비활성 검증 | 실제 이자·인플레이션·기회비용 미반영 |
| 최초 배분 후 보유 | 주식/일반 ETF에 최초 동일 비중 매수 후 유지 | 매매·승인 빈도가 낮은 기준선 | 가격 변동 후 비중 이탈·집중도 검토 필요 |
| 동일 비중 재조정 | 각 합성 평가점의 목표와 보유 차이를 다음 봉에 처리 | 목표 비중 유지·후보 차이 생성 검증 | 추가 비용·미체결·반복 승인 부담 |

이 비교에서는 어느 전략을 자동 채택하지 않는다. 실제 선택 전 대표 기간과 종목군, 실제 이용권·비용·결제·주문 가능 조건, 위험 정책을 확정해 별도로 평가해야 한다. 초기 자동 주문 권한도 생성하지 않는다.

## 24개 실행 결과

TWR·MDD는 백분율, PnL·수수료·세금·슬리피지는 KR=KRW, US=USD다. MDD는 지정 관측점 기준이다. 슬리피지는 체결대금에 이미 반영되어 NAV에서 재차 차감하지 않았다. 비용0은 별도 통제 시나리오다.

| 시장 | 비용 조건 | 구간 | 전략 | TWR % | PnL | MDD % | 수수료 | 세금 | 슬리피지 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| KR | explicit_costs | fold01 | cash | 0 | 0 | 0 | 0 | 0 | 0 |
| KR | explicit_costs | fold01 | buy_hold | -0.4735800 | -47358 | 0.4735800 | 8987 | 0 | 5171 |
| KR | explicit_costs | fold01 | equal_weight_rebalance | -0.4820300 | -48203 | 0.4820300 | 9325 | 312 | 5366 |
| KR | explicit_costs | fold02 | cash | 0 | 0 | 0 | 0 | 0 | 0 |
| KR | explicit_costs | fold02 | buy_hold | 0.7299200 | 72992 | 0.1420800 | 9111 | 0 | 5097 |
| KR | explicit_costs | fold02 | equal_weight_rebalance | 0.7192100 | 71921 | 0.1420800 | 9487 | 488 | 5304 |
| KR | zero_cost_control | fold01 | cash | 0 | 0 | 0 | 0 | 0 | 0 |
| KR | zero_cost_control | fold01 | buy_hold | -0.33200 | -33200 | 0.33200 | 0 | 0 | 0 |
| KR | zero_cost_control | fold01 | equal_weight_rebalance | -0.33200 | -33200 | 0.33200 | 0 | 0 | 0 |
| KR | zero_cost_control | fold02 | cash | 0 | 0 | 0 | 0 | 0 | 0 |
| KR | zero_cost_control | fold02 | buy_hold | 0.87200 | 87200 | 0 | 0 | 0 | 0 |
| KR | zero_cost_control | fold02 | equal_weight_rebalance | 0.87200 | 87200 | 0 | 0 | 0 | 0 |
| US | explicit_costs | fold01 | cash | 0 | 0 | 0 | 0 | 0 | 0 |
| US | explicit_costs | fold01 | buy_hold | -0.451900 | -45.19 | 0.451900 | 8.88 | 0 | 5.11 |
| US | explicit_costs | fold01 | equal_weight_rebalance | -0.458300 | -45.83 | 0.458300 | 9.15 | 0.21 | 5.27 |
| US | explicit_costs | fold02 | cash | 0 | 0 | 0 | 0 | 0 | 0 |
| US | explicit_costs | fold02 | buy_hold | 0.714900 | 71.49 | 0.141100 | 9.05 | 0 | 5.06 |
| US | explicit_costs | fold02 | equal_weight_rebalance | 0.704300 | 70.43 | 0.141100 | 9.45 | 0.44 | 5.28 |
| US | zero_cost_control | fold01 | cash | 0 | 0 | 0 | 0 | 0 | 0 |
| US | zero_cost_control | fold01 | buy_hold | -0.31200 | -31.2 | 0.31200 | 0 | 0 | 0 |
| US | zero_cost_control | fold01 | equal_weight_rebalance | -0.31200 | -31.2 | 0.31200 | 0 | 0 | 0 |
| US | zero_cost_control | fold02 | cash | 0 | 0 | 0 | 0 | 0 | 0 |
| US | zero_cost_control | fold02 | buy_hold | 0.85600 | 85.6 | 0 | 0 | 0 | 0 |
| US | zero_cost_control | fold02 | equal_weight_rebalance | 0.85600 | 85.6 | 0 | 0 | 0 | 0 |

## 재현과 한계

[고정 비교 명세](../contracts/comparison-spec-v1.json) · [산식·시점 계약](../contracts/research-local-v1.md) · [24개 결과와 manifest/result 해시](strategy-comparison-synthetic-2026-10-24.json) · [최종 독립 검증](../evidence/research-validation-final-2026-10-24.json).

신호는 당시 사용 가능한 입력으로 만들고 다음 적격 봉에서 체결했다. 두 시장·두 비용·두 fold·세 전략을 빠짐없이 포함했다. 합성 T+0 결제와 좁은 원가 지원 범위이며 실제 증권사·시장자료·LEAN·세무 기준의 검증은 수행하지 않았다.
