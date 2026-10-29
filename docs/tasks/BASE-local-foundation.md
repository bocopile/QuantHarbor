# BASE-local-foundation — Q13 로컬·합성 기반

- 상태: 완료 — Q13 명시 합성 기반 범위
- 단계·선행조건: Q12 통합 통과, C01·02·03·05, SG03 적용 범위 확인
- 요청 근거·실행 범위: 전체 순차 구현 및 필요한 로컬 합성 검증
- 담당·독립 검토 여부: foundation_implementer 소스 작성 완료, root 컨테이너·DB 통합, qh_reviewer 코드 검토 통과·qh_validator 독립 검증 통과
- 입력 계약·설정 버전: docs/contracts/baseline-v1.json 및 연결 문서
- 소유 파일: root src/quantharbor·tests/product·pyproject·config/runtime*·containers·migrations·scripts 제품개발도구·개발문서·본 카드·큐/보드/status. 기존 ENV scripts/tests 보존
- Git 기준: head2fa8f1d, codex/arc-contracts 기존 checkout. 미커밋·PR/merge 없음
- 허용 도구·외부 변경 범위: 공식 공개 의존성 metadata/라이선스 읽기·고정 이미지 다운로드·로컬 합성 컨테이너/DB·소스/테스트. 기존 사용자 컨테이너/데이터·계좌·키·외부 API/게시 변경 없음
- 검증 요청 범위: 기본형·canonical·설정 오류·기동/DB migration 재현/rollback·합성 실패 검증. 금융 시스템 전체 검증 아님
- 시간·비용 제약: 기존 Docker/개발 구독, 신규 유료0. 전용 합성 DB·무네트워크·메모리/시간 제한

## 산출물과 완료 기준

고정 런타임·의존성/라이선스 manifest·기동 가능한 Python 프로젝트·안전한 synthetic 기본 설정·기본형/canonical·모듈 경계·합성 PostgreSQL migration/복구·재현 명령과 독립 코드 검토/검증 증거. 컨테이너 정의만으로 완료하지 않는다. DB/볼륨은 합성 전용이며 실제 운영 환경은 Q14 이후다.

## 인계

- 실제 변경: src 기본형/직렬화/설정/CLI·전용 테스트22개, 고정 이미지/라이선스 inventory, Docker/Compose, migration·재현 검증기·개발 가이드.
- 실제 확인: 구현자 호스트 테스트22개 통과. root 고정 컨테이너 재현 검사8개 통과, 제품22개 discovery/run 확인, DB 소수 정확 저장·migration 멱등/변경거부·실패 rollback·dump/restore 및 자기 프로젝트 정리 성공(6.942초).
- 첫 실행 실패: sandbox의 사용자 홈 buildx activity 쓰기 거부. BUILDX_CONFIG만 임시 경로로 분리한 후 재현 통과. 전역 설정 변경 없음.
- 검토 수정: runtime 소스 ignore 예외, 테스트0개 오탐 방지, 원본/복원 값 고정 예상값 대조, 예상 SQL 오류 원인·cleanup 실패 반영.
- 독립 검증: env_final_validator가 컨테이너8/8·제품22/22·호스트22/22를 재현, exit0·정리 성공·입력 불변 확인. [검토](../evidence/base-foundation-review-2026-10-23.json), [검증](../evidence/base-foundation-validation-2026-10-23.json).
- 미실행: Q14 실제 연구 격리/자원 초과·금융 서비스·실계좌.
- 다음: Q14 권한·환경 격리 구현.
