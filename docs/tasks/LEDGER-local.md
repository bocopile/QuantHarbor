# LEDGER-local — Q20 합성 원장과 재처리

- 상태: 로컬 합성 하위 범위 완료
- 단계·선행조건: Q12 고정 계약·Q13~18 로컬 기반·Q19 합성 조회 독립 검증, EXEC-DEC-001 순서 변경
- 요청 근거·실행 범위: 비밀번호 없이 가능한 잔여 작업의 순차 구현·합성 검증. F01/02/03/08 로컬 하위 범위
- 담당·독립 검토: root 계약 통합 → 별도 제한 qh_review/Astra-high 설계 → qh_development/Sol-high 구현 → qh_review/Sol-high 검토 → Luna-high 검증
- 입력: data-v1·serialization-v1·execution-v1, 기존 정확 소수·시각·canonical 기본형, synthetic PostgreSQL 기반
- 소유: src/quantharbor/domain/ledger.py, application/ledger.py, ports/ledger.py, adapters/synthetic_ledger.py, adapters/postgres_ledger.py, tests/product/*ledger*, scripts/check_ledger.py, docs/development/ledger.md. root는 계약·migration·공통 직렬화·상태 통합; 구현자에 명시 배정 시 동시 쓰기 중단
- Git 기준: codex/arc-contracts HEAD2fa8f1d, 기존 변경 보존. 추가 commit/원격 변경 없음
- 허용 도구·외부 변경: 로컬 공개 코드 읽기/쓰기, 기존 고정 이미지의 새 UUID 합성 PostgreSQL 검증. 실제 키·계좌·native 비밀번호·외부 금융 API 없음
- 검증 범위: 정확 소수·통화별 분개·revision/정정·지식/효력 시점 replay·현금 분리·중복/충돌·transaction/outbox/inbox 실패/재전달
- 시간·비용: worker/writer 각1, 재귀 위임 없음, 신규 유료0·기존 구독 범위

## 산출물과 완료 기준

불변 이벤트 원장과 통화별 균형 검사, 식별/개정 충돌 보류, 정정/역분개 및 지식 경계 재생, 결제/미결제 현금 분리, 영속 원자성·중복 수신 검증을 구현한다. 검토된 입력 버전과 실제 시험 결과를 기록한다. 실제 금융 데이터 적재·계좌 대사·원가/세무 규칙·사용자 운영 정책 완료를 뜻하지 않는다.

## 인계

- 실제 변경: 카드·로컬 실행 순서 작성. 설계 자문 진행 중.
- 확인: codebase MCP Transport closed, 공개 코드 파일로 보완. PostgreSQL18.6 합성 기반과 정확 소수 기본형 존재.
- 미실행: Q20 코드 구현·검토·시험·DB 검증.
- 남은 결정·장애: 사용자 비밀번호는 이 하위 작업의 선행조건이 아니다. 실제 Q19 관문은 대기로 보존.
- 다음: 설계 반환 → root 추가 명세 통합 → 단독 구현.

- 설계 반환: 별도 제한 Astra/high 자문을 root가 ledger-local-v1·LEDGER-DEC-001에 통합했다. 구현자에게 migration0002·serializer additive 등록·전용 runner도 소유 배정하고 root 동시 쓰기를 중단한다. 실제 DB 검증은 구현 반환/검토 후 root가 실행한다.

- 구현 반환: 소유12파일 hash 일치, 구현자 제품217(원장53)·runner 품질11 통과. [증거](../evidence/ledger-implementation-2026-10-24.json). root가 실제 PostgreSQL runner를 시작했으며 결과 전 통과로 표시하지 않는다. 독립 검토는 후속이다.

- 실제 DB: root가 시작 시점 경합과 PL/pgSQL 변수명 충돌을 수정했다. diagnostic capture를 붙인 동일 runner에서44입력 parity·14검증·자기 자원 정리 통과. 원본 runner 최종 실행과 독립 검토/검증은 후속이다. [DB 증거](../evidence/ledger-db-initial-2026-10-24.json). root 수정이 있으므로 이 실행을 독립 테스트로 표시하지 않는다.

- 독립 검토 L1/L2: 미래 정산의 dependency 변경에 따른 이중 지급과 분할 기준 수량 변경 누락을 발견했다. [검토](../evidence/ledger-review-initial-2026-10-24.json). 동일 잘못된 의미가 Python/SQL에 공유돼 기존 parity만으로 드러나지 않았다. 계약에 격리/불완전 처리 기준을 보완하고 재현·수정·DB 회귀를 단독 배정한다.

- L1/L2 수정 반환: 최초62시험7실패 중1건은 fixture 기대값 오류로 정정, 유효한 재현은6실패. 수정 후 원장62·제품226·runner 품질12 통과. [증거](../evidence/ledger-review-fixes-2026-10-24.json). 추가8계좌35입력/독립 기대값 검사를 원본 DB runner에 반영했고 root 실행을 시작했다.

- 원본 DB runner 재검증:79입력·18검증·cleanup 통과. L1/L2 기대값 검사를 포함한다. [최종 DB](../evidence/ledger-db-final-2026-10-24.json). 별도 제한 Sol/high 재검토를 배정한다.

- 독립 재검토 PASS: L1/L2 해소·변경 경로 추가 결함 없음·12hash 일치. [재검토](../evidence/ledger-review-final-2026-10-24.json). Luna/high 별도 제한 검증 담당에게 제품·품질·공개/팀·diff와 실행 전후 불변 검증을 배정한다.

## 최종 인계

- 독립 제품226·품질87·공개315findings0·팀/공백 검사 통과,12파일 실행 전후 불변. [최종 검증](../evidence/ledger-validation-final-2026-10-24.json). 품질 최초2실패는 root의 실행옵션 누락이었고 -I -S 재실행으로 소스 변경 없이 해소했다.
- 실제 합성 PostgreSQL79입력·18검증·자기 프로젝트 정리 통과. L1/L2 재검토 PASS. 독립 실행/검토와 root DB 실행의 담당을 구분한다.
- 미실행: 실제 계좌/자료권리·운영 비공개 저장·실제 대사·가용금/원가 정책. 기존 전체 큐와 실제 관문을 완료로 승격하지 않는다.
- 다음: EXEC-DEC-001에 따라 Q21 합성 평가·대사·스냅샷.
