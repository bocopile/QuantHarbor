# ENV-bootstrap — 개발 AI 환경 착수

- 기준일: 2026-10-20
- 상태: 완료 — 2026-10-23 Q06 개발 ENV 명시 범위 통과. 운영 금융 환경은 후속
- 요청 근거: 전체 순서 확정 후 사용자의 “진행시켜” 요청
- 담당: orchestrator가 통합하고 전문 역할을 한 명씩 순차 위임. 초기 착수 이후 사용자 팀 요청을 반영
- 입력: AGENTS.md, docs/plan.md, docs/security.md, ENV-DEC-001
- 범위: ENV 작업 기준·역할·Skills·도구 목록·인계·시작 안내 설정
- 소유 파일: AGENTS.md, README.md, docs/status.md, docs/ai-environment.md, docs/development-environment.md, docs/templates/*, docs/decisions/ENV-DEC-001-development-bootstrap.md, 이 카드, config/ai/development-policy.toml, .codex/config.toml, .codex/hooks.json, .codex/agents/qh_*.toml, .agents/skills/qh-*/SKILL.md
- 외부 변경: 없음. 프로젝트 보호 설정 경로 배치는 승인된 쓰기 실행으로 수행
- 검증 범위: 초기 정적 확인 이후 명령 프로필 합성 검증과 실제 팀 순차 위임·독립 검토·팀 테스트까지 수행. 후속 대표 흐름은 [종합 판정](ENV-final-assessment.md)에서 개발 범위 통과

후속 업데이트: 설정 로드는 [ENV-controls](ENV-controls.md), 실제 합성 검증은 [ENV-validation](ENV-validation.md), Slack은 [ENV-slack](ENV-slack.md)에 기록했다. 아래 실제 확인 목록과 미실행 문단은 초기 착수 시점의 기록이며, 항목별 상태표는 최신 결과를 반영한다.

## 항목별 상태

| ID | 상태 | 확보한 산출물·근거 | 남은 작업 |
|---|---|---|---|
| ENV-01 | 기준 정의 완료 | 개발 환경 문서의 저장소/운영정보 경계 | 실제 운영 저장소는 후속 단계에서 별도 구성 |
| ENV-02 | 지침 정리 완료 | AGENTS의 개발 환경·카드 연결 | ENV-11 개발 범위 통과; 운영 흐름은 후속 |
| ENV-03 | 계약·프리셋·명시 위임 확인 | 활성 역할 6개 TOML, 6명 순차 위임·인계, TEAM-bootstrap | 사용자 정의 역할 자동 발견은 별도 미확인 |
| ENV-04 | 개발 정책 확인 | 역할별 모델·추론 명시, 부모 기본값 로드 확인, 기존 구독·신규 지출 0·서비스 한도 시 중단 정책 | 계정 전체 청구 상한의 기술적 강제는 제공하지 않음; 운영 AI 평가는 후속 단계 |
| ENV-05 | 파일·발견·명시 적용 확인 | 프로젝트 Skill 3개 활성 발견, 제한된 부모 환경의 실제 읽기·합성 분류 10개 | 자동 선택의 일반화 보장 아님 |
| ENV-06 | 로컬 역할 경로 확인 | root 코드 탐색 11개·그래프 조회, 별도 부모의 MCP 4개 disabled·도구/오류 0, ENV-DEC-004 역할 경로 | 새로운 앱·도구 필요 시 영향 범위 재확인 |
| ENV-07 | 명시 개발 범위 완료 | 고정 검사 감사·합성 검증, 2026-10-23 정상 신뢰6개·실제6종 이벤트·재개·독립 검토 | 지원 밖 도구 통제·unknown 결과·임시보존 한계 유지 |
| ENV-08 | 개발 부모 프로필 접근 확인 | 기존 명령 경계 10/10, 두 실제 모델 프로필의 접근 3종씩·읽기 역할 업무 확인 | 현재 direct child 권한 불변; 운영 환경은 후속 단계 |
| ENV-09 | 기록 체계 완료 | 작업/결정 템플릿·본 카드·결정 기록·status | ENV-11 정상 CLI 재개 확인 완료 |
| ENV-10 | 승인된 수동 연결 확인 완료 | AP-01 명시 승인, 비공개 채널 생성·합성 메시지 1건 전송/읽기·참가자 1명 확인 | 2026-10-23 Q05 범위 판정 완료; 예약 실행·투자 보고 미승인 |
| ENV-11 | 개발 범위 통과 | CLI0.163.0 프로필10개·제한 부모2개·MCP 목록·Hook6종·재개·수동Slack, 독립 종합 검토 | 운영 격리·계좌·금융 검증은 후속 단계 |

## 실제 확인

- 로컬 CLI 버전: 0.162.1. 프로젝트 전용 파일이 없음을 확인하고 기존 파일을 덮어쓰지 않고 설치했다.
- 프로젝트 TOML 8개(역할 6·Codex 설정 1·작업 정책 1)를 Python 3.12.5 표준 TOML 파서로 읽었다.
- Hook JSON과 명령에 포함된 정적 JSON payload를 파싱했다. Hook은 실행하지 않았다.
- Skill 문서 3개의 필수 name/description과 참조 경로를 문서 수준에서 확인했다. Skill의 실제 선택·행동 검증은 수행하지 않았다.
- `codex --strict-config features list`는 이 하위 명령에서 strict-config를 지원하지 않아 종료 코드 1이었다. 실제 CLI 설정 검증 통과로 기록하지 않는다. TOML 문법 확인과 런타임 적합성은 별개다.
- 기존 사용자 변경을 보존했다. 전역 설정·인증·모델 선택·원격 저장소는 수정하지 않았다.

## 초기 착수 시점의 미실행

테스트 추가·실행, subagent, 모델 API 호출, 컨테이너·운영 저장소, 계좌·키·Slack 연결, 실제 Hook 신뢰/실행, commit·push는 하지 않았다.

## 최신 인계

2026-10-23 기존 ENV 선행조건을 유지한 채 Q01~06 개발 범위를 완료했다. [종합 판정](ENV-final-assessment.md)에 실제 검증·독립 검토·범위 한계를 연결했다. Q07 요구·시나리오를 시작하며 금융 코드 구현은 ARC 확정 후다.
