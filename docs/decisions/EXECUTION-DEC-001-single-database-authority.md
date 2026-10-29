# EXECUTION-DEC-001 — 합성 실행의 단일 DB 권위

- 날짜: 2026-10-25
- 관련 작업 ID: Q27-local, I01-W/I02-W/I08-W·I03~07, Q26 J05
- 상태: 채택 — 비밀번호 없는 로컬 합성 범위
- 결정 담당·요청 근거: orchestrator, 입력 없이 가능한 잔여 작업의 순차 구현·검증 지시

## 요구와 확인 사실

Q26은 메모리 합성 승인/철회 범위를 제품630·품질87과 독립 검토로 완료했다. Q20 SQL ledger_append는 호출자 transaction에 참여하지만 Python append는 자체 commit한다. Q24는 active orders가 없는 후보 원천을 검사하며 현재 실행 예약을 대체하지 않는다. [설계 자문](../research/execution-design-input-2026-10-25.md)의 사실/제안을 구분한다.

## 선택과 이유

최초 표시/승인부터 DB repository로 구성하고 approval 소비·claim·intent·예약·outbox를 한 transaction에 묶는다. 메모리 승인 import/분리 commit 대안은 불일치·재사용 위험 때문에 비활성이다. 기존 Q20 SQL을 같은 연결에서 사용하며 Q24/Q21/Q23 실제 금융 계산과 독립 broker 사실을 연결한다. broker 발급 journal과 request-bound finality를 요구하고 unknown은 부재만으로 해제하지 않는다.

fixed40사례를 먼저 고정한다. 종료/체결/정정이 유발하는 원장 행까지 보호하기 위해 자문의256records/16MiB 대신1024records/64MiB·intent당384records 예산을 채택한다. 초기active2/event8 등 작은 합성 상한과 출처별 계산표를 execution-local-v1에 둔다. 실제 정책/지출/계좌 권한은 바뀌지 않는다. 0001/0002와 baseline7은 보존하고 새0003만 추가한다. actual DB는 root가 기존 고정 이미지의 자기 임시 프로젝트에서 실행한다.

## 미확인과 재검토 조건

현재 설계만 확정했으며 Q27 구현/단위/DB 시험은 미실행이다. 한도 내 최대 행 수가 예약표를 초과하거나 한 transaction/실제 issuer 경계를 입증할 수 없으면 완료로 집계하지 않는다. PostgreSQL 원자성·동시성·복구 및 독립 일반/보안/전체 검증이 필요하다. 과거 백업 전체 복원은 Q28, 실제 인증·권리·연결·주문 승인과 PG01/03은 별도다.
