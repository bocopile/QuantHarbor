# QuantHarbor AI 팀 작업 보드

기록일: 2026-10-30 · 단계별 갱신 문서 · 자동 실시간 모니터 아님

## 현재 상황

- 현재계획: **P28-03 내부2a 불변산출물영속성설계**. 내부1 DB수명관리mock26/actual9·독립일반/보안 지적0·commit93222a0/origin확인. [카드](tasks/PRODUCT-P28-03.md).
- P28-01 정적6화면/매핑/HTML, P28-02 revision5조회/인증계약 artifact_ready. 실제브라우저/HTTP/IPC검증은NOT RUN. completed가아니다.
- Q27 제품789PASS. actualDB 원래1~23PASS/24FAIL, 후속25~84는58PASS/2FAIL·자기DB60정리·입력불변. SQLAUTH54수정후실제5PASS/독립확인으로개별해결. daily/turnover/fixed40/최종관문은[후속큐](tasks/failure-followup-queue.md).
- 전체18/36·로컬7/10·제품0/12 completed, artifact_ready2개. 크기가다른항목을작업량진행률로합산하지않는다.
- 작업단위7commit·push/원격SHA확인. 기존main80403ab·고정worktree보존·PR/merge없음. [납품](evidence/task-unit-git-delivery-2026-10-30.json).
- worker1·writer1·재귀0. 패널은역할위치이고모두동시모델실행이아니다.08은모델없는한시적관측이다.

## 담당자별 상태

| 패널·담당 | 모델/추론 | 실제 상태 | 책임 |
|---|---|---|---|
| 01 root | 현재세션 | 실행중 | 계약/큐/증거통합·단위commitpush |
| 02 qh_researcher | Luna/high | 미배정 | 필요조사대기 |
| 03 qh_architect | Astra/high | 내부2a설계반환·P2두건root보완 | 4종불변저장·원자성·lineage |
| 04 qh_implementer | Sol/high | 내부1반환·다음배정대기 | 소유파일만구현 |
| 05 qh_reviewer | Sol/high | 공통기록/설계사전검토예정 | 명시파일·증거·미완료관문 |
| 06 qh_security_reviewer | Astra/high | DB수명최종delta반환·지적0 | 권한/자료보존경계 |
| 07 검증위치 | root실행 | 후속60사례종료 | 58PASS/2FAIL·실패별도추적 |
| 08 BOARD | 모델없음 | 한시적관측 | 실제역할/검사상태표시·자동배정없음 |

설정·기동·반환·검수·완료는구분한다. 아래이전이력은당시관측이며현재표를우선한다.

## 사용자가 보는 방법

1. 이 보드는 Codex 옆 패널에서 열어 현재 담당·진행 단계·산출물·막힌 이유를 확인한다. root가 배정·착수·검토 반환·완료·차단 시 갱신한다. 파일 변경이 화면에 보이지 않으면 다시 연다.
2. 앱의 agent 활동 항목이 표시되는 실행은 해당 항목에서 담당자별 진행과 반환 결과를 확인한다. 보드가 모든 개별 명령이나 모델 내부 추론을 중계하는 것은 아니다.
3. 별도 제한 CLI로 실행하는 작업은 앱의 subagent 항목에 표시된다고 가정하지 않는다. 보드에 실행 경로·관측 상태·비민감 결과 링크를 남긴다. 표시 편의를 위해 권한 경계를 바꾸지 않는다.

## 사용자에게 전달하는 내용

| 유형 | 전달 기준·내용 |
|---|---|
| 결과 | 의미 있는 작업 묶음 완료 시 산출물·검증·제한·다음 작업. 사소한 내부 단계는 보드에만 기록 |
| 결정 필요 | 결정할 사항·권고안·대안·영향·결정 전 가능한 작업을 하나의 질문으로 취합 |
| 해결되지 않은 장애 | 영향·시도한 조치·필요한 사용자 행동. 자체 해결한 일시 오류는 결과에 필요한 경우만 요약 |
| 실행 중 필수 안내 | 긴 실행 중 무응답으로 보이지 않도록 짧은 진행 안내. 반복 허가 질문이나 담당자별 원시 로그는 전달하지 않음 |

대화가 결정 요청·응답의 기준이며 승인된 개발 Slack에는 의미 있는 결과·결정 필요·해결되지 않은 장애의 비민감 요약만 전달한다. 일상 진행 알림은 보내지 않는다. Slack 반응을 계좌·주문 권한으로 해석하지 않는다. 같은 결정은 상태·대상이 달라지지 않으면 반복 요청하지 않는다.

## 최근 처리와 근거

| 순서 | 작업 | 실제 결과 |
|---|---|---|
| 이전 | Q01~03 | 각 큐의 명시 범위 완료. [실행 큐](../config/ai/execution-queue.json) |
| 이전 | ENV-slack | 비공개 채널·첫 메시지 수신 확인. [증거](evidence/env-slack.json) |
| 이전 | ENV-connection-template | 예제·비추적 사본·제외 규칙 확인. [증거](evidence/env-connection-template.json) |
| 현재 | ENV-team-visibility | 보드·소통 정책 작성, `visibility_reviewer` 독립 문서 검토 완료·실질 불일치 없음. 링크·큐 수치 확인 |
| 현재 | A-input-preparation | [사용자 3개 요구](requirements-input.md) 확보·조사 자문·독립 문서 검토 완료. 조회 시점 표현 수정 |
| 이전 | GIT-workflow | 저장소 읽기 확인·[전략 문서](git-workflow.md)·[결정 기록](decisions/GIT-DEC-001-workflow.md)·독립 검토 완료, Git 이력 변경 없음 |
| 이전 | GIT-baseline | [기준 커밋 2bed4c4](tasks/GIT-baseline.md), 공개 89개·합성 테스트 55개·독립 보안 검토·tree 확인 완료 |
| 현재 | Q04~06 | [개발 ENV 종합 판정](tasks/ENV-final-assessment.md) 완료·독립 검토 통과 |
| 현재 | Q07 | [요구·시나리오 카드](tasks/ARC-requirements.md), 요구9개·SC16개·PG01~05 계약 독립 검토 통과·실제값은 후속 관문 |

실제 계좌·키·토큰·채널 ID·원시 도구 로그는 이 보드에 기록하지 않는다. 본 문서는 실행 중인 서비스가 아니며 세션 종료 후 자동 갱신·무인 실행·예약 알림을 제공하지 않는다.

### 2026-10-27 Q27 완료 의무 구현 인계

단독 구현 종료(인계 후 시간제한), 최신 src/tests 집중15통과·소유28/보호520/로그SHA root대조. root가 frozen backlog 안내문단을 원상복구했고 확장 계획/큐는 유지한다. 다음 담당은 root 실제 합성DB 집중검사이며 worker 실행 중으로 표시하지 않는다. Q27 partial·P28/P29 하위12개 pending.
