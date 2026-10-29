# DEV-quality-gates — Q15 로컬 품질·보안 검사

- 상태: 완료 — 로컬 검사·비활성 CI 정의 범위
- 선행조건: Q14 독립 검토·검증 통과, C04/C06의 로컬 검사·CI 정의 범위
- 요청 근거: 전체 순차 작업·필요한 로컬 합성 검증. 실제 비밀파일·Git 과거 이력 감사는 제외
- 담당: foundation_implementer 단독 코드 작성, root 공통 문서/CI 정의, 보안·일반·독립 검증 순차
- 입력: Q12 계약 baseline, Q13 runtime lock/inventory, Q14 확정 소스
- 소유: scripts/check_quality.py, tests/quality, docs/development/quality.md. root 비활성 CI template·공유 카드/큐/status
- Git: codex/arc-contracts HEAD2fa8f1d, 기존 checkout 미커밋. push/PR/merge/remote 설정 없음
- 범위: 공개 Git 후보 파일의 syntax·구조/계약/lock·고신뢰 secret pattern·보호 경로 검사. ignore 실제설정/운영자료를 읽지 않고 path 위반만 거부. 원시 탐지값 출력 없음
- 검증: 탐지·symlink/경로우회·출력마스킹·계약 drift의 합성 실패 검증과 실제 공개후보 검사. 원격 workflow/보호규칙은 AP06 별도
- 비용: 신규 유료0·추가 의존성 설치 없음

## 완료 기준

재현 가능한 로컬 검사 명령·합성 실패 테스트·기존 코드와 계약 정합성 결과, 비활성 CI 정의 및 활성화 전 권한/비용/플랫폼 조건. 검사 정의와 실제 원격 실행을 구분한다. 단순 regex 통과를 모든 비밀정보 부재나 전체 취약점 감사로 표현하지 않는다.

## 인계

- 실제 변경: 공개 후보 검사기·전용 합성 테스트·사용 문서, 비활성 CI 예제와 정의/공식 action 근거.
- 자기 검증: quality14개·공개 후보178개 findings0, exit0. 독립 보안 검토 배정.
- 미실행: 독립 실행 검증·원격 CI. 기존 product/isolation/Docker 회귀는 Q15에서 아직 미실행.
- 다음: 구현→보안/일반 검토→독립 로컬 검증.

## 보안 지적 수정

- P1 Python 초기 import 실행 경로, P2 특수 공백/실행 지시문을 제거하는 정규화 문제를 수정했다.
- 최종 자기 검증: 전용18개·공개180개 findings0, exit0. [수정 증거](../evidence/dev-quality-fixes-2026-10-23.json).
- 독립 재검토·일반 검토·독립 실행 확인은 남아 있다.

## 일반 검토·독립 실행 배정

- 고정 action SHA를 임의 다른40자리값으로 바꿔도 통과하는 일반검토 지적을 수정했다. root 전용18개·공개182개 findings0 통과 후 독립 일반 재검토 통과.
- 보안2건·일반1건 해소. validator에게 품질 검사·전용18개·제품 회귀·팀/큐 정합성과 입력 불변 확인을 배정했다. Docker는 Q14 이후 관련 소스 변경이 없어 반복하지 않는다.

## 최종 독립 검증과 완료 판정

- validator가 품질18개·제품47개·공개후보182개 findings0·팀6/큐36/ID110 정합성을 확인했다. 모두exit0, 입력6개 불변. [독립 증거](../evidence/dev-quality-validation-2026-10-23.json).
- 보안·일반 검토 지적을 수정했고 로컬 품질 관문을 완료했다. 원격 CI 활성화/실행·보호설정·전체 비밀/취약점 감사는 완료 범위가 아니다.
- 다음: Q16 종목·시장 달력 합성 구현.
