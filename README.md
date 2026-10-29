# QuantHarbor

한국·미국 주식의 자료 수집, 연구, 포트폴리오 관리, 모의·실전 매매, 검토와 보고를 위한 AI 협업 플랫폼.

핵심 가치: **근거 있는 판단, 통제 가능한 실행, 축적되는 학습.**

## 현재 단계

2026-10-20 개발 AI 환경을 순차 구축 중이다. orchestrator와 전문 역할 6개의 모델·추론을 설정하고 실제 순차 위임·독립 검토·보안 검토를 수행했다. 팀·36개 실행 큐·110개 작업 ID 검사가 통과했고 합성 회귀 테스트 13개를 독립 검증했다. Slack·Hook 신뢰·비용 정책·도구 감사·격리 등 ENV 잔여 조건은 진행 중이다. 사용자가 기존 ENV 완료 조건 유지를 선택했다. 투자 시스템·실계좌 연결·주문은 아직 구현하거나 실행하지 않았다.

작업 순서는 **AI 제반환경 구축 → 요구사항과 아키텍처 확정 → 선행조건에 따른 구현 → 모의 검증 → 소액 실전 → 정책 범위 자동운영**이다.

## 문서 안내

| 문서 | 내용 |
|---|---|
| [AGENTS.md](AGENTS.md) | AI 작업 규칙과 새 세션의 읽기 순서 |
| [진행 상태](docs/status.md) | 완료·미착수·미결정 사항과 다음 작업 |
| [제품 철학](docs/vision.md) | 제품 목표, 원칙, 범위 |
| [전체 작업 계획](docs/plan.md) | 단계별 작업 ID, 의존관계, 완료 기준 |
| [전체 세부 작업과 실행 준비사항](docs/execution-checklist.md) | 110개 작업 상세, 36개 순차 묶음, 단계별 결정·자료·권한 |
| [AI 팀과 순차 운영](docs/ai-team.md) | orchestrator·역할별 모델/추론·소유권·인계·승인 방식 |
| [Git 작업 전략](docs/git-workflow.md) | 기준 커밋·작업 브랜치·worktree·검토·머지·복구·권한 |
| [승인·결정 목록](docs/approval-register.md) | 기존 허가와 실제 사용자 결정이 필요한 항목 |
| [AI 제반환경 명세 초안](docs/ai-environment.md) | 역할·모델·Skills·MCP·Hooks·격리·인계 |
| [개발 AI 환경 실행 기준](docs/development-environment.md) | 실제 배치 범위·역할·도구·권한 한계·검증 계획 |
| [ENV 착수 카드](docs/tasks/ENV-bootstrap.md) | ENV-01~11별 산출물·실제 확인·미완료 |
| [ENV 도구·권한 카드](docs/tasks/ENV-controls.md) | MCP 허용 목록·권한 프로필·실제 설정 조회 결과 |
| [ENV 합성 검증 카드](docs/tasks/ENV-validation.md) | 실제 권한 검증 10개와 완료 범위·한계 |
| [ENV Slack 카드](docs/tasks/ENV-slack.md) | 수신 채널·최초 메시지·외부 연결 진행 |
| [개발 환경 최초 결정](docs/decisions/ENV-DEC-001-development-bootstrap.md) | 최초 환경 경계·권한·작성자 선택 근거 |
| [순차 AI 팀 결정](docs/decisions/ENV-DEC-003-orchestrated-team.md) | 역할별 모델·추론·orchestrator 운영·위임 방식 |
| [아키텍처 논의 초안](docs/architecture.md) | 구성요소·데이터·주문·운영 설계 후보 |
| [민감정보 관리 정책](docs/security.md) | 저장소와 운영 정보의 경계 |
| [오픈소스 20개 조사](docs/research/oss-survey.md) | 스타 순위, 차용 설계, 라이선스·운영 한계 |
| [OSS 적용 결정안](docs/research/oss-application-plan.md) | 20개별 적용 모듈·계약·변경점·완료 기준 |
| [증권사 선택 결정안](docs/research/broker-selection.md) | 6개 비교, KIS 권고·키움 전환 조건·운영 관문 |
| [확장 조사 근거](docs/research/github-evidence-2026-10-19.json) | 221개 메타데이터·제외 사유·선정 20개 commit |
| [모델·증권사 조사](docs/research/models-and-brokers.md) | 역할별 모델 초안, 증권사·보고·도구 근거 |

## 시작 원칙

새 대화에서는 AGENTS.md와 docs/status.md를 먼저 읽는다. 제안된 기술을 확정된 결정으로 취급하지 않는다. 문서 작성 완료를 환경 설치나 구현 완료로 표시하지 않는다.

실제 키·계좌정보·거래내역·개인 보고서·운영 로그·DB·백업은 이 저장소 밖에 보관한다. 설정 예제와 검증용 데이터에는 가짜 값만 사용한다. 상세 기준은 [민감정보 관리 정책](docs/security.md)을 따른다.
