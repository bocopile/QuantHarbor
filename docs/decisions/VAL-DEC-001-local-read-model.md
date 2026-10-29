# VAL-DEC-001 — 합성 평가와 대사 읽기 모델

- 날짜: 2026-10-24
- 관련 작업 ID: Q21 F04/05/06, Q22·Q23 소비
- 상태: 채택 — synthetic 로컬 범위
- 결정 담당·요청 근거: root, 입력 없는 순차 진행 지시·Q20 완료·별도 제한 Astra/high 설계 자문

## 요구와 확인 사실

Q20은 정확 원장·현금 분류·시점 재생을 제공한다. Q17은 권리/시점/종목/달력 조회 검증 경로가 있고, Q19 관측은 종목 매핑·현금 의미·source_as_of가 미확인이다. 가격/FX가 없다고 보유를 삭제하거나 부분 합계를 NAV로 승격할 수 없다.

## 선택과 이유

[valuation-local-v1](../contracts/valuation-local-v1.md)을 추가한다. 기존 시장 application 검증을 재사용하고 raw close·명시 source/series·권리/품질·나이 검사를 한다. native 보유별 양자화→정확 현금 합산→원통화 소계 FX 환산 후 기준통화 양자화의 half_even을 합성 정책으로 명시한다. 실제 수수료/세무/반올림 정책을 대신하지 않는다.

별도 독립 합성 statement로 수량·현금을 원단위 대사한다. 일부 scope 일치와 전체 보유/현금 범위 일치를 구별하고 현재 KIS batch는 미해결 이유만 반환한다. snapshot은 불변·계보·명시 unknown·결속 검사를 제공하며 bounded 메모리 저장으로 검증한다. 새 네트워크/DB 의존성은 없다.

## 미확인과 재검토 조건

실제 계좌 대사·지원/권리·운영 persistence·가용금·주문목록은 미완료다. 원가·가격/환율 손익은 Q23 정책 전 unknown으로 둔다. 조건 없는 source 대체·임의 tolerance·adjusted price 혼용·실제 API 우회는 허용하지 않는다. 구현과 독립 검토/검증 완료 전 로컬 완료로 집계하지 않는다.
