# QuantHarbor AI 팀 작업 보드

기록일: 2026-10-23 · 단계별 갱신 문서 · 자동 실시간 모니터 아님

## 현재 상황

- 제품 실행 큐: **Q04 — Skills·Hook·감사**
- 큐 완료: **3/36**. Q04 진행 중, Q05~36 미완료. 개수는 작업량 진행률이 아니다.
- 제품 작업의 막힌 조건: AP-02 사용자 직접 Hook 신뢰 등록 후 실제 실행 확인. 2026-10-23 실제 재조회에서 enabled 6·untrusted 6·오류/경고 0을 확인했다.
- 최근 완료 작업: **GIT-baseline — 기준 커밋 2bed4c4 생성**. 공개 파일 89개, 합성 테스트 55개·팀 정합성 PASS, 독립 보안 검토 차단 사항 없음.
- 현재 작업: **Q04 사용자 처리 대기**. 기존 Hook 신뢰 직접 등록 선택에 따라 실제 이벤트 검증이 남아 있다. 기준 커밋으로 ENV 완료 조건을 바꾸지 않는다.
- Git 적용(2026-10-23): branch `codex/env-baseline`, 기준 commit `2bed4c4`, 기본 checkout 1개. 기준 커밋 직후 clean·89개 blob 일치 확인. 이 보드의 완료 갱신은 후속 문서 커밋으로 보존한다. main `ec56042` 유지, 추가 worktree·PR·merge 미생성.
- 실행 원칙: 전문 worker 1명, 작성자 1명. 역할 설정이 있다는 이유로 실행 중으로 표시하지 않는다.

## 담당자별 상태

모델은 저장된 배정값이다. 실제 호출과 결과를 확인한 경우에만 실행으로 기록한다. 아래 표는 마지막 갱신 시점의 상태다.

| 담당자 | 모델 / 추론 | 상태 | 현재 배정·최근 산출물 | 다음 조건 |
|---|---|---|---|---|
| 총괄 root | 프로젝트 설정 Sol / high | 기준 커밋 완료·Q04 대기 조건 확인 | GIT-baseline·검증·tree 확인·인계 기록 | 사용자 직접 Hook 신뢰 등록 후 실제 이벤트 검증 |
| 조사 qh_researcher | Luna / high | 자문 완료 | 실제 agent `requirements_scout`가 1차 응답과 남은 요구 경계 반환 | 다음 공개 조사 배정 |
| 설계 qh_architect | Astra / high | 미배정 | [역할 실행 경로 결정](decisions/ENV-DEC-004-role-execution.md) | 요구·설계 작업의 선행조건 충족 |
| 구현 qh_implementer | Sol / high | 미배정 | [기존 Hook 준비 결과](tasks/ENV-hook-audit.md) | 구현 또는 결함 수정 배정 |
| 일반 검토 qh_reviewer | Sol / high | 검토 완료 | 실제 agent `visibility_reviewer`: Git 전략의 실질 결함 없음 | 후속 검토 배정 |
| 보안 검토 qh_security_reviewer | Astra / high | 검토 완료 | 실제 agent `baseline_security_review`: 공개 후보 차단 사항 없음 | 후속 변경 시 영향 검토 |
| 검증 qh_validator | Luna / high | 미배정 | [기존 감사 실행기 검증](tasks/ENV-durable-audit.md) | Hook 신뢰 반영 후 실제 검증 배정 |

Sol = gpt-6.1-sol, Luna = gpt-6-luna, Astra = gpt-6-astra. root의 실제 대화 모델 변경 여부는 설정값만으로 확인하지 않는다.

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
| 현재 | GIT-baseline | [기준 커밋 2bed4c4](tasks/GIT-baseline.md), 공개 89개·합성 테스트 55개·독립 보안 검토·tree 확인 완료 |

실제 계좌·키·토큰·채널 ID·원시 도구 로그는 이 보드에 기록하지 않는다. 본 문서는 실행 중인 서비스가 아니며 세션 종료 후 자동 갱신·무인 실행·예약 알림을 제공하지 않는다.
