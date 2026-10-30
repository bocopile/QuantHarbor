# P28-01 제품 화면·사용 흐름 명세 v1

2026-10-30 · root 작성 · 설계 미리보기. 실제 제품 연결·금융 제어·통합 완료가 아니다.

설계 자문은600초 제한으로 최종 반환 없이 종료했다. 원래 기록은 FUP-P28-001에 보존하고 본 명세는 root가 요구9개/시나리오16개에서 작성했다. [수용 매핑](acceptance-matrix-v1.json)·[실패 후속 큐](../tasks/failure-followup-queue.json).

## 정보 구조

환경/표시용 계좌 → 아래6개 조회 영역 → 대상 상세 → 원천·버전·기준시점·상태 확인 순서다. 후보 승인/철회/중단/취소/청산/재개는 화면에서 실행하지 않고 기존 보호 CLI/IPC 계약으로 연결한다. 제품 사용자 명령이 아직 없는 행동은 구현 대기로 표시하며 가짜 명령을 제시하지 않는다.

| 화면 | 사용자 질문과 표시 영역 | 기존 생산자 / 제품 seam |
|---|---|---|
| 자산·현금·위험 | 통화별 보유와 실제 가용 범위·대사 상태를 확인한다. 통화별 현금, 보유/예약, 계좌 대사, 위험 차단 사유 | `src/quantharbor/application/valuation.py`, `src/quantharbor/application/reporting.py`, `src/quantharbor/adapters/postgres_execution.py`; 제품 read model/API는 P28-02 설계 대상 |
| 분석·근거·반론 | 분석의 기준 시점·출처·반대 근거와 검증 여부를 본다. 분석 목록, 근거/가정, 반론/상충, 자료 시점/권리 | `src/quantharbor/application/research.py`, `src/quantharbor/application/document_ingest.py`, `src/quantharbor/application/market_ingest.py`; 제품 read model/API는 P28-02 설계 대상 |
| 후보·승인 이력 | 주문 조건과 승인 대상·버전·유효 범위를 함께 확인한다. 후보별 정확 조건, 소비/만료/철회 이력, 새 후보 대체 관계, 보호 제어 안내 | `src/quantharbor/application/target.py`, `src/quantharbor/application/approval.py`, `src/quantharbor/domain/approval.py`; 제품 read model/API는 P28-02 설계 대상 |
| 주문·체결·대사 | 접수/체결/취소/상태불명과 금융 반영을 구분한다. 의도/시도/주문 추적, 체결/예약 구성, 취소와 철회, 대사/명시 재개 | `src/quantharbor/application/execution.py`, `src/quantharbor/adapters/postgres_execution.py`, `src/quantharbor/application/ledger.py`; 제품 read model/API는 P28-02 설계 대상 |
| 투자 AI 작업 | 제품 안의 분석 작업·근거·실패·예산 상태를 확인한다. 작업 목록, 역할별 근거/반론, 출력 검증, 공급자/예산 | `src/quantharbor/application/investment_ai.py`, `src/quantharbor/domain/investment_ai.py`; 제품 read model/API는 P28-02 설계 대상 |
| 운영·연결·복원 | 시스템 준비 상태와 장애·보고 전달·백업 근거를 본다. 연결/데이터 준비, 세션/분석 slot, 보고 전달, 백업/업데이트/복원 | `src/quantharbor/runtime/settings.py`, `src/quantharbor/runtime/report_cli.py`, `src/quantharbor/runtime/isolation.py`; 제품 read model/API는 P28-02 설계 대상 |

## 공통 표시·권한

모의/실전/합성을 명확히 표시한다. 계좌는 표시용 참조만 전달한다. 통화별 금액·서버 정밀도·자료 시점·버전·출처를 유지하며 검증된 FX 없이 합산하지 않는다. 브라우저는 원장/위험을 재계산하거나 조회 갱신으로 제어 세션·승인을 연장하지 않는다. 요청별 조회 권한·종료/회수·캐시/오래된 응답 처리는 P28-02에서 구체화한다.

| 상태 | 표시 원칙 |
|---|---|
| 확인됨 (`READY`) | 현재 권리·완전성·시점이 확인된 서버 값 |
| 잠정 (`PROVISIONAL`) | 확정 값과 분리하고 원장/정정 버전을 표시 |
| 미확인 (`UNKNOWN`) | 숫자0·성공·미접수로 대체하지 않음 |
| 결과 없음 (`EMPTY`) | 완전 조회의 빈 결과, 잔고0과 구별 |
| 정상0 (`ZERO`) | 확인된 실제0; 누락과 구별 |
| 자료 누락 (`MISSING`) | 값을 표시하지 않고 영향·차단 사유 표시 |
| 조회 실패 (`FAILED`) | 거래 실패/미접수와 구별 |
| 오래된 자료 (`STALE`) | 자료별 시각·허용범위 판정 결과 표시 |
| 만료 (`EXPIRED`) | 승인/권리/자료 만료의 대상을 명시 |
| 차단 (`BLOCKED`) | 원인·영향·확인할 다음 행동 표시 |
| 미연결 (`DISCONNECTED`) | 과거 정상값을 현재 결과처럼 표시하지 않음 |

합성 예시는 EX08의 두 번째 admission 전 값이다: L900/H202/F100/B900/U202/D0/A598 USD. KRW 자료는 미확인이며0원으로 만들지 않는다. 화면의 SYN-A와 계좌 A는 가공 이름이다. 예시 값은 운영 정책 기본값이나 실시간 결과가 아니다.

## 요구·시나리오 수용 매핑

각 행의 기존 시험은 컴포넌트 근거다. 새 조회 API/사용자 화면 통합 검증은 아직 실행하지 않았다.

| ID | 화면 | 수용 관측 |
|---|---|---|
| REQ-01 | assets, candidates, operations | 종목마다 시장·거래소·상품 유형·통화·환경별 지원 여부를 구분한다. ETF 유형·지원 여부가 불명확하면 주문 허용 대상으로 추정하지 않는다 |
| REQ-02 | analysis, candidates, investment-ai | 분석마다 데이터 기준 시점·전략/정책 버전·후보 ID를 남긴다. 수집·분석·주문·리밸런싱 주기를 분리하며 분석이 제출 권한을 만들지 않는다 |
| REQ-03 | assets, orders | 환전은 사용자가 수행한다. 현금 조회는 통화별 잔고·매수가능금액·시점·완전성을 구분하며 사용자 완료 알림만으로 가용금을 증가시키지 않는다 |
| REQ-04 | assets, analysis, orders, operations | 데이터 누락·지연·시각 불일치·조회 불완전을 정상 값과 구분한다. 해당 입력에 의존하는 위험 증가 주문은 실행 가능으로 판정하지 않는다 |
| REQ-05 | candidates, orders | 승인에는 환경·계좌·후보/정책 버전·행동·유효 범위를 연결한다. 제출 직전 정책·승인·잔고·미체결·위험을 다시 확인한다 |
| REQ-06 | candidates, orders, operations | 판단·승인·제출·체결·대사·보고 전달 상태를 구분한다. 불확실한 상태를 성공·미접수·잔고0으로 추정하지 않는다 |
| REQ-07 | orders, operations | 신규 주문 중단·미체결 취소·청산·재가동을 별도 행동으로 취급한다. 재시작 후 기록과 대사를 확인하고 재가동 조건 충족 전 위험 증가 주문을 보류한다 |
| REQ-08 | analysis, investment-ai | 제안에 출처·시점·가정·반대 근거와 미확인을 표시한다. 금액·위험·원장 계산은 결정론적 코드 검사를 통과해야 하며 AI 동의로 대체하지 않는다 |
| REQ-09 | analysis, orders, operations | 보고의 잠정/확정·기준 원장 버전·정정 관계·전달 결과를 표시한다. 거래 결과와 전달 실패를 분리한다 |
| SC-01 | assets, operations | 각 입력의 시점·버전·완전성 표시. 미설정 필수 정책이나 불완전 입력은 준비 완료로 표시하지 않음 |
| SC-02 | analysis, candidates, investment-ai | 후보 ID·입력 버전·근거·반대 근거·유효 범위 기록. 동일 의도 중복과 변경 후보 관계 식별. 주문 제출은 별도 승인/정책 검사 |
| SC-03 | candidates, orders | 후보→승인→주문→체결→원장→대사 추적 가능. 이 시나리오를 작성했다고 모의 API나 실전 실행이 승인되지 않음 |
| SC-04 | assets, orders, operations | 시장 거래일·기준시점·비용·미체결·차이·잠정/확정 구분. 대사 미완료를 확정 보고로 표현하지 않음. 외부 전달은 AP-10 범위 확정 후 |
| SC-05 | assets, analysis | 영향 범위·사유를 표시하고 관련 후보의 실행 가능 판정 보류. 0이나 과거 정상값으로 조용히 대체하지 않음 |
| SC-06 | analysis, operations | 자료별 시점·지연 표시, 실행 입력에서 제외. 오래된 자료를 사용하는 연구는 구분 표시. 분석 간격을 데이터 신선도 기준으로 자동 사용하지 않음 |
| SC-07 | assets, operations | 불완전/부족/정상0을 구분. 관련 신규 위험 증가 주문 보류·재조회 상태 표시. 시스템 환전이나 임의 현금 증액 없음 |
| SC-08 | candidates, orders | 전체 목표와 부분 변경을 명시적으로 구분하고 누락 종목을 임의 청산하지 않음. 전체 목표에서 누락의 의미도 계약·승인 범위로 명시하며 모호하면 보류. 동일 의도 중복 제출 방지. 새 후보가 기존 승인·미체결을 자동 대체하지 않으며 대체 관계·추가 검토/승인 필요 여부 표시 |
| SC-09 | candidates, orders | 제출 전에는 거부. 이미 제출된 주문은 철회 사실과 주문 상태를 별도 기록하며 취소는 별도 권한·행동. 경합 판정 시점은 ARC-06에서 고정 |
| SC-10 | orders, assets | 체결분·잔량·취소 대기·예약 현금 구분. 재분석 시 기존 체결/미체결 반영, 동일 체결 중복 계상과 잔량 중복 주문 방지 |
| SC-11 | orders, operations | 미접수로 단정하지 않고 조회·대사 전 동일 의도 재제출 금지. 해소되지 않은 위험을 반영해 관련 신규 주문 보류 |
| SC-12 | operations, orders | 조회 실패와 주문 상태불명을 구분. 조회 재시도는 공급자 조건과 제한 내에서만, 주문 제출 재시도는 SC-11 적용. 무한 재시도 금지 |
| SC-13 | operations, analysis, candidates | 달력과 세션을 기준으로 처리. UTC·시장 현지시간·거래일을 구분하고 허용 세션 밖 제출 거부. 정규장만 허용하며 시장별 세션 상세는 후속 계약 |
| SC-14 | orders, operations | 중단/취소/청산/재가동 분리. 기존 의도·승인·미체결·체결 복원과 대사 후 재가동 조건 판정. 저장 또는 대사 실패를 완료로 승격하지 않음 |
| SC-15 | operations, orders | 거래를 재실행하지 않음. 보고 ID·중복 전달·정정 관계 추적, 결과 불명은 확인 전 자동 재전송하지 않음. 초기 로컬 모의에서는 경보 전달 불능 시 신규 제출 중단·확인 후 수동 재개. 지속/확대 운영의 세부 경보정책은 PG-04에서 확정 |
| SC-16 | investment-ai, analysis | 부적합 결과·미확인·미완료를 표시, 검증된 후보로 승격하지 않음. 재시도/상향은 확정 정책 범위, 신규 지출 승인으로 확대하지 않음 |

## 구현·검수 인계

- P28-02: source DTO/API·조회 인증/캐시·종료와 보호 CLI의 계약을 정한다.
- P28-03/04/05: 실제 조립/영속성/사용자 제어/운영을 연결한다. 테스트 전용 composition을 제품 런타임 의존성으로 만들지 않는다.
- P28-06: 정적 와이어프레임을 실제 read model에 연결하고 stale/권한회수/역순응답을 검수한다.
- P28-07/08: 설치·업데이트·보존·한계·접근성과 사용자 안내를 확인한다.
- P29: REQ9/SC16의 사용자 과업과 장애/복원/보안 통합을 실제 결과로 판정한다.

artifact_ready는 산출물 준비이며 completed가 아니다. Q27 필수 후속/최신 actualDB 관문은 유지한다. 현재 본 명세의 제품 동작 검증은 NOT RUN이고 정적 와이어프레임과 독립 검토가 다음 작업이다.
