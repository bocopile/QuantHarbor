# GIT-workflow — Git 운영 전략 수립

- 상태: 완료 — 전략 수립·읽기 검토 범위. 실제 Git 전환 미실행
- 관련 작업·선행조건: ENV-01·02·09 보완, C02·04·06 준비. 금융 구현·C 전체 완료가 아님
- 요청 근거: 사용자의 Git·worktree·커밋·머지 전략 수립 제안
- 담당: root 전략 작성·통합, 별도 공개 문서 검토 담당
- 입력 버전: main ec56042, 공개 Git 상태·worktree 목록·추적 파일, 팀 순차 정책·AP-06·보안 정책
- 소유 파일: docs/git-workflow.md, 본 카드, docs/templates/task.md, README·ai-team·plan·status·team-dashboard의 연결
- 허용 도구·외부 변경: 로컬 Git 읽기, 공식 Git/GitHub 문서 읽기, 문서 작성. Git mutation·credential 조회·원격 설정 변경 없음
- 검증 범위: 문서의 로컬 링크·현재 Git 상태·권한/소유권·누락·실패 경로 대조. 코드 변경·제품 테스트 없음
- 시간·비용: 새 자원·유료 서비스 없음

## 산출물·완료 기준

- 현재 미커밋 작업을 보존하는 기준 커밋 전환 절차, 단기 작업 브랜치, 필요 기반 worktree 정책.
- 논리적 커밋·독립 검토·squash merge·충돌·복구·정리·원격 보호 목표와 실제 적용 상태 구분.
- 전략 수립을 실제 커밋·원격 변경 승인으로 해석하지 않음.

## 실제 확인과 인계

- 기본 checkout 하나, main 초기 커밋 하나, 추적 README 하나와 이후 작업의 미추적 상태를 확인했다. 현재 대화의 관리 worktree 첨부는 없다. origin 이름 존재만 확인했고 원격 URL·권한·보호 규칙은 조회하지 않았다.
- 공식 Git worktree·ignore·revert와 GitHub merge·branch protection 문서를 2026-10-23 조회했다.
- 독립 검토: qh_reviewer 역할의 visibility_reviewer가 공개 문서만 읽고 최초 작업 보존·순차 소유권·squash 정리·단일 계정 승인·권한 경계의 실질 결함 없음을 반환했다. 코드 테스트·Git mutation·외부 호출은 하지 않았다.
- 확인: 연결 문서의 로컬 링크 검사와 diff 공백 검사 성공. 실제 Git 상태 변경이나 CI·브랜치 보호 검증을 수행한 것으로 표시하지 않는다.
- 결과: GIT-DEC-001과 운영 전략, 작업 템플릿 Git 필드·README·계획·팀·승인 목록·보드 연결을 반영했다.
- 다음: 실제 적용 시 대상 파일·변경·검증을 준비하고 AP-06의 로컬 commit과 원격 변경 허용 범위를 연결한다. 현재 Q04는 그대로 유지한다.
