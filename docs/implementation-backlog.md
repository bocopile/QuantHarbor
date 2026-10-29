# 구현 인계 v1 — Q12 통합 검토 통과

입력은 요구 v1과 data/execution/operations/serialization v1이다. 독립 Q12 통과 후 시작한다. 큐의 기존36개 순서·110개 원래 ID를 유지한다. 아래 경로는 제품 소스 구현 예정이며 현재 기능 존재/완료를 뜻하지 않는다. 각 단계 착수 때 [작업 카드](templates/task.md)에 실제 head·입력 hash·소유 파일·검증 명령·선행 관문·승인 범위를 구체화한다.

## 소유권·의존 방향

root는 계약·공통 설정·migration·의존성·status·큐를 통합한다. 기본 writer는 root 한 명이며 구현 worker를 맡길 때는 해당 소유 파일을 넘기고 root의 동시 수정을 중단한다. 조사·검토·보안 역할은 읽기 전용, validator는 명시 합성 검증만 실행한다. 재귀 위임 없음. 검토와 검증은 실제 수행한 범위만 기록한다.

제품은 `src/quantharbor/` 패키지로 만든다. domain은 외부 네트워크/DB에 의존하지 않는다. application은 domain과 port에 의존하고 adapters가 port를 구현한다. CLI/runtime가 wiring을 한다. ledger/approval/execution의 쓰기는 각 소유 application 경로로만 하며 연구/보고는 버전 read view를 소비한다. broker adapter가 ledger table을 직접 고치거나 domain이 CLI를 import하지 않는다. 기존 개발 ENV scripts/tests는 보존하며 제품 코드와 경로/fixture를 분리한다.

## 순차 실행 카드별 경계

| 큐·기존 ID | 소유할 제품 경로·산출물 | 실제 완료 증거·관문 |
|---|---|---|
| Q13 C01/02/03/05 | pyproject·lock/의존성 manifest·src 기본형/설정/CLI·개발 컨테이너 정의·migrations 기반·docs/development | SG03 고정 버전/LICENSE·설치·기동·잘못된 설정 거부·canonical golden·합성 DB migration/복귀·재현 명령. Dockerfile만으로 컨테이너/DB 실행 완료 금지 |
| Q14 D01/02/03/05/06/07 | 환경별 role/network/resource 설정·private 경로 검증·research runner·egress gate | 실제 허용/거부·자원 초과·canary 유출방지·환경 교차·prompt injection·liveness 차단. 키는 합성. 실제 격리 불가 시 완료 보류 |
| Q15 C04/06 | local quality/security/license checks·CI 정의·개발 가이드 | 로컬 결과·보호 파일 diff·문서/계약 검사. 원격 실행/보호 변경은 AP06별도; 정의와 실행을 구분 |
| Q16 E01/02 | domain/catalog·calendar·adapter 매핑 fixture | 충돌ticker·유효기간·일반ETF unknown 제외·DST/휴장/조기폐장. 실제자료는 SG02 |
| Q17 E03/05/06/07 | market_data·quality·price/FX/action storage | 페이지·정정·결측·staleness·조정/시점·권리 검사, 합성 재수집 멱등. 실제수집 SG02 |
| Q18 E04 | documents/news ingestion·lineage | 발표/수집 구분·정정·기업연결·원문권리. 실제원문 SG02; 데이터없음을 성공수집으로 표시하지 않음 |
| Q19 I01-R/I02-R/I08-R | brokers/ports·synthetic adapter·KIS read adapter | 완전/부분/empty·scope·rate limit·binding·오류, 합성 시험과 승인된 모의 조회 증거 구분. PG01·SG01·AP05 실제연결 전 필수 |
| Q20 F01/02/03/08 | ledger/events·journal·projection·replay | 통화별균형·revision·late/correction·미결제·중복/정정·inbox/outbox·DB실패. 합성 입력. 실현원가법은 F07 계산 계약 전 별도 고정 |
| Q21 F04/05/06 | valuation·reconciliation·snapshots | unknown 평가·NAV 소계 혼동·as_known/restated·cash/reservation·실제 계좌 대사. 합성만으로 실제대사 완료 불가 |
| Q22 J01/02/06 조회 | reporting/local read views·CLI | 수량/현금/잠정·확정/차이 표시·정정 추적, 로컬조회만 |
| Q23 F07/G01~04 | research/experiments·metrics·engine adapter·strategy comparison | PG02 평가 명세, 원가/성과/입출금/비용 정의, SG03엔진·SG02데이터, 재현성·PIT·비용/회전율/낙폭. 전략운용 선택은 PG03 |
| Q24 G05/06/07 연구 | portfolio/target·candidate builder | full/partial·미체결충돌·rounding/units·현금/노출/일간예약·미평가·미정 정책 거부. 합성값은 실제정책 아님 |
| Q25 H01~08/J03 | investment_ai requests/results/hypotheses·review·budget | 출처/구조/권한/비용/TTL 평가셋. SG02/04·AP03 실제활성화. stub 성공을 실제AI평가로 합산 금지 |
| Q26 J05 | approval·local control principal·nonce/generation | candidate binding·동시 소비·expiry/revoke/withdrawal·세션단절·복원세대, 보안검토. PG01 운영값 |
| Q27 I-W/I03~08 | execution/intent/risk/reservations·broker submit/cancel·egress | unknown최종성·부분/역순체결·cancel경합·최악노출·DB실패·stale·manualresume. 합성/실제모의 구분, PG01/03·SG01·AP05 |
| Q28 J04/M01/02/04 준비 | report delivery·health/alerts·backup/restore | 결과불명/권리철회·거래재실행금지·복원옛승인무효화·대사. 외부전달 AP10/SG02, 예약 AP08 |
| Q29 K01~07 | 통합 합성/허용모의 시나리오·보안/장애 보고 | REQ9·SC16+계약 실패 사례, 회귀·각 경계 evidence, 미실행을 별도 표기 |
| Q30 L01/02/G07/M 운영 | 지속 모의/그림자 실행 기록 | PG04·AP05/08/10·관찰 기간/범위 확정, 실제 장시간 기록·비용/오류/개입. 시뮬레이션으로 대체 완료 금지 |
| Q31 D04/I08 | 별도 live 자원·binding·지원차이 | PG05·SG01/02·AP03/05, 모의/실전 교차차단·복원·단일egress 실제 증거 |
| Q32 L03 | 실전 진입 검토 카드 | 사용자 AP07 특정 계좌/전략/금액/기간/한도 결정. 문서/모의 통과가 승인 아님 |
| Q33 L04/M 운영 | 승인 범위 소액 실전 결과 | 실제 체결/비용/대사/오류/개입 검토, AP07 제한 |
| Q34 L05/G07/A05 | 자동운영 정책·예외 중단 | 별도 사용자정책·AP08·검증, 초기 후보별 승인을 자동으로 변경하지 않음 |
| Q35 M03~06 | 변경복귀·월간/연간 대조·내보내기 | 실제 운영/복구/보존 증거, 원시개인자료는 private |
| Q36 M07 | 추가 broker/model/optimization 검토 | 기존운영근거·사용자확장결정·권리/비용/시험, 현시점자동확장금지 |

Q13~18은 승인된 로컬/합성 범위를 진행한다. 실제 공급자 자료/권한이 필요한 완료 조건은 해당 증거 없이는 미완료다. 특히 Q19 실제연결/조회 또는 Q21 실제대사를 합성 성공만으로 완료 처리해 다음 단계로 넘기지 않는다. 순서 변경/범위 조정이 필요하면 준비된 결과·남은 조건을 제시해 사용자에게 실제 결정만 요청한다.

## 요구·시나리오 추적

| 수용 기준 | 계약 정본 | 구현/검증 |
|---|---|---|
| REQ01·SC01/13 | data 기본형/종목·operations 달력/세션 | Q16·19·27·29 |
| REQ02·SC02/08 | execution TargetPlan/후보·operations slot | Q24·26·27·29 |
| REQ03·SC07 | data cash/query·execution 예약 | Q19~21·24·27·29 |
| REQ04·SC05/06/12 | data 품질/완전성·execution RiskDecision | Q17~21·27·29 |
| REQ05·SC03/09 | execution Approval/dispatch·serialization hash | Q13·26·27·29 |
| REQ06·SC10/11 | data revision·execution Order/Cancel/unknown | Q20·21·27·29 |
| REQ07·SC14 | execution stop/resume·operations restore/generation | Q14·26~29·31 |
| REQ08·SC16 | execution Research/Hypothesis·operations 연구격리 | Q14·23~25·29 |
| REQ09·SC04/15 | operations Report/Delivery/alert | Q22·25·28·29 |

## 검토 기록·아직 충족하지 않은 조건

Q07 요구 관문, Q08 선정 조건, Q09 FX/정정/시점/null, Q10 미접수최종성/철회/한도예약, Q11 복원권한/취소egress/liveness 지적과 수정은 각 카드·reviewed_sha256 증거에 보존한다. Q12는 계약 간 결합과 구현 가능한 명세를 검토하며 과거 증거 hash를 현재 파일 hash로 다시 써서 이력을 지우지 않는다.

미정 실제 정책·계좌/capability·자료권리·모델성능·운영보존/복구값은 PG/SG에 남는다. 초기 단일 호스트/수동운영의 가용성 한계·중단 후 원격체결 가능성·동일 host 관리자 신뢰를 사용자 경계로 명시했다. 모의·실전 실제 성능이나 수익은 확인하지 않았다. 상세 소스별 테스트는 구현 시 요청된 범위에서 필요한 실패경로를 작성하며 문서 줄을 그대로 확인하는 형식적 테스트는 만들지 않는다.
