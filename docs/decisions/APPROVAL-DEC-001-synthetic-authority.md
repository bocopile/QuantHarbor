# APPROVAL-DEC-001 — 합성 승인 권한과 원자성 연결

- 날짜: 2026-10-25
- 작업: Q26-local/J05, EXEC-DEC-001
- 상태: 채택 — 로컬 합성 범위
- 결정 담당: root, 사용자의 입력 없는 순차 진행 및 팀 위임 지시

## 요구와 확인 사실

Q25 로컬 독립 판정이 완료됐다. Q24 후보의 금융/표시 조건은 exact hash로 결속되지만 실제 사용자 인증을 제공하지 않는다. frozen 계약은 승인 소비·intent·예약·outbox 동일 transaction을 요구한다. 설계 자문과 실제 코드 근거는 approval-design-input에 보존했다.

## 선택과 이유

발급자 registry에 결속한 합성 opaque handle·challenge·불변 이력과 공유 aggregate simulation을 채택한다. 실제 인증을 암호 모사로 대신하거나 별도 승인 소비 commit을 만들지 않는다. pending 종료 전이를 additive로 채택한다. 표시 후 만료가 늘어나지 않도록 rendered_at+TTL 상한을 고정한다. 합성 TTL20/10/120/30초는 운영 정책이 아니다.

고정 fixture raw SHA256: `84190ff349d81877bbfdace4ffd23d9e0c1de5d474c3a3c6568c870504c71300`. 21개 사례는 구현/시험 전에 고정됐으며 실제 원천 refs와 추가 회귀/실패는 별도 증거로 남긴다.

## 미확인과 재검토 조건

실제 인증·비밀번호·PG01 정책·계좌 권한·Q27 영속 admission/egress·복원 후 실제 대사는 미완료다. 이 결과는 실제 금융 승인이 아니다. 구현 시 현재 권리나 Q24 계약과 충돌하면 root에게 근거를 반환해 additive 계약에서 해결한다.

## 2026-10-25 AS1·AS2 보완

원 승인자의 현재 권한을 dispatch 직전 확인하고 미처리 명령의 완료 비용을 보호 공간과 별도로 보장한다. 분리 발급된 철회 challenge도 반복 만료될 수 있어 유한 기록 한도만 늘리는 대안은 종료 보장이 되지 않는다. 기존 계약의 보호 철회 요구를 만족하도록 원자적 합성 withdraw API를 채택한다. 실패 시 발급까지 롤백하고 기존 2단계 command는 인수하지 않는다. 실제 DB 원자성은 Q27에서 구현·검증한다. 고정 fixture·실제 사용자 승인·외부 권한에는 변경이 없다. [수정 증거](../evidence/approval-security-fixes-2026-10-25.json).
