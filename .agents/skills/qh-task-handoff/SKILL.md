---
name: qh-task-handoff
description: QuantHarbor 작업을 착수·재개·인계할 때 작업 ID, 선행조건, 소유 파일, 실제 완료 증거를 정리한다. 일반 질의응답에는 적용하지 않는다.
---

# QuantHarbor 작업 인계

저장소 루트의 `AGENTS.md`와 `docs/status.md`를 읽는다. 현재 단계는 `docs/plan.md`, 개발 환경의 실제 상태는 `docs/development-environment.md`를 따른다.

1. 작업 ID와 `docs/tasks/`의 해당 카드를 확인한다. 새 카드가 필요하면 `docs/templates/task.md`를 사용한다.
2. 입력 계약 버전·소유 파일·완료 기준·외부 변경 및 검증 요청 범위를 명시한다. 기존 요청은 다시 묻지 않는다.
3. 합성 입력과 실제 금융 데이터, 구현 완료와 실계좌 확인, 설정 파일 작성과 실제 로드를 구분한다.
4. 종료 시 실제 변경·확인·미실행·막힌 결정·다음 행동을 카드에 남기고 주 담당이 `docs/status.md`를 갱신한다.

검토/조사 역할은 파일을 수정하지 않고 인계 내용을 반환한다. 이 Skill은 agent 생성·테스트·외부 전송 권한을 추가하지 않는다.
