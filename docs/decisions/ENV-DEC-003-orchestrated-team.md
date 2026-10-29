# ENV-DEC-003 — 역할별 모델을 사용하는 순차 AI 팀

- 날짜: 2026-10-20
- 관련 작업: ENV-03·04·09·11, TEAM-bootstrap
- 상태: 채택 — 사용자의 명시적 팀 구성 요청
- 대체 범위: ENV-DEC-001의 모델/추론 일괄 상속과 위임 방식·대화 상한. 권한·provider 상속과 정보 경계는 유지

## 요구와 확인 사실

사용자는 주 담당에게 orchestrator 역할, AI 팀 생성, 역할별 모델·Reasoning Level 설정, 잔여 작업의 순차 구성, 필요 시 사용자 승인 취합을 요청했다. 기존 ENV 완료 조건 유지 선택은 변경하지 않았다.

로컬 모델 목록과 위임 도구는 gpt-6-luna, gpt-6.1-sol, gpt-6-astra의 high 조합을 제공한다. [공식 Subagents 문서](https://learn.chatgpt.com/docs/agent-configuration/subagents)는 사용자 정의 역할의 model/model_reasoning_effort와 부모 권한 상속을 설명한다.

## 선택과 이유

- orchestrator 기본: gpt-6.1-sol/high. 현재 대화 모델이 변경됐다고 표시하지 않는다.
- 조사·검증: gpt-6-luna/high. 구현·일반 검토: gpt-6.1-sol/high. 설계·보안 검토: gpt-6-astra/high.
- 전문 역할 6명, 활성 worker 1명, 작성자 1명. 열린 하위 대화 상한은 6개이며 동시 작업 상한과 구분한다.
- 기존 qh_explorer 파일은 호환용으로 보존하되 활성 팀에는 포함하지 않는다. 탐색 책임은 qh_researcher로 통합하고 qh_architect를 추가한다.
- 현재 세션에서 새 사용자 정의 `agent_type`이 보이지 않으면 default에 같은 역할 지침과 명시 모델/추론을 전달해 위임한다. TOML 자동 발견과 이 방식의 위임 성공을 혼동하지 않는다.
- 반복 로컬 작업은 재허가 없이 배정하고 실제 외부·비용·계좌·신뢰 결정은 orchestrator가 취합한다.

## 영향과 미확인

전문 agent는 개별 모델 사용량을 소비한다. 별도 유료 API runner·추가 과금은 생성하지 않았으며 기존 구독 사용·한도 정책은 AP-09로 확인한다. 모델 배치는 초기 운영안이며 금융 성능·비용 우열을 실측한 결과는 아니다.

권한은 부모 환경에서 상속하므로 읽기 지침과 기술적 격리를 구분한다. 독립 검토는 실제 별도 agent 결과가 있을 때만 기록한다. 전체 ENV 관문은 유지한다.
