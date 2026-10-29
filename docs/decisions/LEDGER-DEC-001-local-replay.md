# LEDGER-DEC-001 — 합성 원장·정정·재생 구현 기준

- 날짜: 2026-10-24
- 관련 작업 ID: Q20 F01/02/03/08
- 상태: 채택 — 로컬 합성 범위
- 결정 담당·요청 근거: root, 사용자 입력 없는 순차 작업 요청과 별도 제한 Astra/high 설계 자문

## 요구와 확인 사실

data-v1은 불변 이벤트·통화별 균형·revision 정정·시점 재생·PostgreSQL transaction을 요구한다. 기존 0001은 금융 원장이 아니다. BrokerObservation에는 개별 체결/결제 의미가 미확정이므로 실제 조회를 자동 원장 입력으로 전환하지 않는다.

## 선택과 이유

[ledger-local-v1](../contracts/ledger-local-v1.md)에 닫힌 합성 입력, 의미 hash와 event body hash 분리, full replacement의 정확 reversal/replacement, 소급/장래 효력, transaction 끝 cursor, 지식/효력 경계 재생을 명시했다. 고정소수 정수 연산·DB numeric scale 검사로 조용한 반올림을 거부한다. 기존 PostgreSQL/psql 경로로 실제 합성 원자성을 검증하고 새 DB 드라이버·SQLite 대체를 도입하지 않는다.

root가 공통 계약을 작성하고 구현자 한 명에게 migration0002·serializer additive 등록·전용 runner까지 명시 배정한다. root는 구현 중 동시 작성하지 않고 반환 후 통합한다. 기존 frozen baseline/0001은 보존한다.

## 미확인과 재검토 조건

비공개 저장·키·실제 입력/대사·가용금·원가/세무 정책은 미완료다. 복잡한 효력일 이동/미발효 정정은 격리하며 지원 확대 시 의미와 영향 사건을 재검토한다. 합성 테스트/검토 통과 전 로컬 완료로 표시하지 않는다.

검토 L1/L2 보완: 미래 settlement의 dependency 변경은 격리하고, 분할 기준에 뒤늦게 들어오는 신규/대체 수량도 불완전으로 표시한다. 기존 사건을 자동 재계산하지 않는 초기 범위와 사용자 통제 원칙을 유지한다.
