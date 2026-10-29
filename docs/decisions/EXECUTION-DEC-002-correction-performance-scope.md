# EXECUTION-DEC-002 — 정정 이력의 성과 연결과 미지원 경계

- 날짜: 2026-10-25
- 관련 작업 ID: Q27-local EX08/EX21~26/EX33/EX39, Q23 성과 소비
- 상태: 채택 — 합성 실행용 추가 연결의 구현 기준
- 결정 담당·요청 근거: orchestrator, 승인된 잔여 작업 순차 구현·검증. 금융 부분 인계의 미완료를 고정 계약과 대조한 기술 결정이며 사용자 운영 정책 변경이 아니다.

## 요구와 확인 사실

[고정40사례](../contracts/execution-fixture-v1.json)는 EX26에서 Q20 미지원 정정의 관측 근거·보수적 예약 보존과 incomplete/신규 주문 차단을 요구한다. EX21은 누계1→3의 유효량3, EX22는 revision1→2의 대체와 역순 재처리, EX39는 예약 보존식을 요구한다. 기대값·fixture SHA를 변경하지 않는다.

[금융 부분 인계](../evidence/execution-financial-partial-2026-10-25.json)는 다중 가격·delta/latest cumulative 정정·비용 확정을 보완했으나 Q23 현재 원천 갱신의 정정 이력 재생을 미완료로 남겼다. Q23 `application/research.py::_replay_events`는 event마다 submission을 한 번씩 append하고 마지막 event와 비교한다. Q20 `application/ledger.py::append`는 정정 submission 한 건에서 reversal+replacement를 함께 생성한다. Q23 `validate_trade_costs`도 original trade만 허용한다. 이를 그대로 연결하면 Q20이 정상 반영한 정정 이후에도 실행 성과/위험 갱신이 막힌다.

Q20 fee/tax는 정산현금의 비용 방향을 엄격히 검사한다. 기존0001/0002나 그 금융 의미를 바꿔 미지원 정정을 임의 정상화하지 않는다. 이 결정은 자기 설계 검토이며 독립 검토 통과를 의미하지 않는다.

## 선택과 이유

1. 실제 Q20 전체 이력의 reversal+replacement 묶음을 원 reducer로 재현해 원천·계좌·cursor·recorded/effective 시각·이전 사건·hash·생성된 사건 전체를 검증한다. quarantine에 의한 cursor 간격까지 해소하려면 bounded typed decision 이력을 사용한다. 이력 일부를 버려 가짜 정상 원장을 만드는 방법은 허용하지 않는다.
2. 기존 Q23 public v1과 고정24 비교의 의미를 보존하는 합성 실행용 추가 성과 경로를 만든다. Q21 원천/권리 재검증과 Q23 성과 산식을 재사용하고, 완전한 이력 검증 후 현재 cutoff에서 유효한 trade/fee/tax만 비용·거래량 집계에 포함한다. 과거 원본은 inputs와 증거에 보존한다. 원래 Q24 후보의 재현 경로는 바꾸지 않는다.
3. 정상 정정 후 독립 broker 조회·Q20 현재 projection·Q21 평가/대사·Q23 성과/원가·현재 권리와 일간/FX 위험 계산까지 연결한다. 일반 함수 인자에 caller allow·임의 검증 callback·complete bool을 넣어 검증을 우회하지 않는다.
4. Q20의 알려진 비용 양수→0 정정, 결제 후 trade 정정의 미해결 dependency, 이미 후속 사건이 있는 앞선 누계 sequence 정정의 재해석은 현재 미지원 경계로 유지한다. 해당 증거·관측값·보수적 예약을 보존하고 incomplete/신규 주문 차단을 검증한다. 단순히 다음 유효 revision이 왔다고 미해결 충돌을 지우지 않는다. 이 경로의 자동 해소를 구현 완료로 주장하지 않는다.

생산자는 기존 Q20 실제 DB/reducer와 독립 합성 broker, 소비자는 Q27 현재 위험·복구 및 후속 Q28/Q29다. 구현 소유 범위에 기존 Q27 파일 외 `application/research.py`의 호환성 보존 helper 추출, 새 `application/execution_research.py`와 관련 시험을 명시 추가한다. 새 파일은 이 결정 시점에는 제안된 구현 위치다. 공통 계약·고정명세·기존 migration은 root가 보존한다.

대안은 정상 정정 이후도 계속 차단하거나 Q23의 모든 소비자 의미를 한꺼번에 변경하는 것이다. 전자는 정상 로컬 순환을 완성하지 못하고, 후자는 검증 범위를 불필요하게 넓히므로 채택하지 않는다. 신규 패키지·API 비용·계좌/외부 권한은 추가하지 않는다.

## 미확인과 재검토 조건

추가 경로는 아직 미구현·미검증이다. 실제 DB의 정정 후 현재 원천 갱신과 다음 위험 판단, 원래 Q23/24/26 호환성, 잘못된 bundle/cursor/권리/의존성의 거부를 확인해야 한다. 별도 보안·일반 검토가 미지원 경계에서 근거 유실·예약 해제·재가동 우회를 발견하면 보완 후 재검토한다. 정확 저장 예산·SQL 제약·제어/복구와 전체 독립 시험도 Q27 완료 전 필수다.
