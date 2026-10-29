# SEC-local-boundaries — Q14 권한·환경 격리

- 상태: 완료 — Q14 명시 로컬 합성 경계
- 단계·선행조건: Q13 독립 검토/재현 통과, operations-v1·execution-v1·baseline-v1
- 요청 근거·범위: 사용자 전체 순차 구현·로컬 합성 검증. 실제 paper/live 연결·자격증명 변경 없음
- 담당: foundation_implementer 단독 코드 작성, root 공통 문서 통합, 보안→일반→독립 실행 검증 순차
- 소유 파일: src/quantharbor/runtime의 새 isolation/boundary 모듈, tests/product 및 tests/isolation, scripts/check_isolation.py. 기존 공통 계약·기본형·Q13 migration/runner는 보존
- Git 기준: codex/arc-contracts HEAD2fa8f1d, 기존 checkout·미커밋, 원격 변경 없음
- 도구·환경: 기존 고정 Python Docker 이미지, UUID 합성 컨테이너·tmp fixture, 비특권·network none·host mount 없음. 기존 컨테이너·실제 비밀파일 접근 금지
- 검증: 합성 역할/바인딩 거부·private 경로 검증·실제 연구 격리·자원 초과/출력 상한·liveness 차단. API 주문·원장·사용자 금융 인증은 후속Q26/27
- 비용: 신규 유료0, 자동 retry0, 동시성1, 명시 짧은 timeout

## 산출물과 완료 기준

합성 연구 코드/데이터만 stdin으로 전달하는 비특권 고정 이미지 runner, 부모 환경 미상속·Docker socket/host filesystem/네트워크 접근 거부, input/output/CPU/memory/wall/disk/process 한도와 강제 종료·자기 컨테이너 정리. 읽기 데이터와 문자열 지시는 실행 권한으로 승격하지 않는다.

환경/role/binding validator·runtime private 경로 검사·수동 liveness 조건을 결정론적으로 검사한다. actual paper/live는 미승인 상태로 거부한다. 연구 코드와 trusted host controller의 경계가 실제 Docker로 검증돼야 한다. Python 객체·문서 정책만으로 보안을 주장하지 않는다. 악성 host 관리자/데몬 침해는 신뢰 경계 밖이다.

## 인계

- 실제 변경: boundary/isolation 모듈·제품 단위테스트·실제 Docker검사·개발 가이드. 구현자 소유 범위 단독 작성 후 root가 CPU 범위 주석과 공유 기록을 통합했다.
- 실제 자기 검증: 제품39개·Docker12개 통과. 최초2회 network interface개수 가정 실패 후 실제 설정·route·연결거부 검증으로 수정. [구현 증거](../evidence/sec-local-implementation-2026-10-23.json).
- 한도 의미: CPU hard2초는 프로세스별, CPU quota1·실행 wall5초가 별도다. 전체CPU합산2초나 함수전체5초를 보장하지 않는다.
- 독립 보안/코드 검토·독립 재현 통과. 실제 paper/live 자원·금융인증/주문 통합은 미실행.
- 보안 수정: P1 Docker proxy 자동env 주입, P2 stale marker 대상 미결속. 빈 전용config/HOME·exactEnv·endpoint/daemon fingerprint를 적용했고 단위23·Docker13개 자기 회귀 통과. [초기 검토](../evidence/sec-local-security-initial-2026-10-23.json), [수정](../evidence/sec-local-fixes-2026-10-23.json).
- 다음: Q15 로컬 품질·보안 검사와 비활성 원격CI 정의.

- 추가 수정: create 결과불명 시 최초absence만으로marker해제하지 않도록 보수적 차단, 지연 생성 회귀를 추가해 보안재검토 통과. 실제13개회귀에서 테스트finally의 중복cleanup가정이 실패해 marker가 남은 경우만 정리하도록 고쳤다.
- 통합 수정: Dockerfile·context에 공개runtime-lock을 포함해 새단위테스트의runtime_lock_invalid를 해소, foundation8검사+제품46개 통과(후속start수정전 버전).
- 일반 검토: startclient오류/neverstarted+defaultexit0 성공오판을 발견·수정, 상태exited와client/actualexit을 함께확인한다. 경계단위25개 통과, 최종Docker회귀/독립검증 대기.

- 최종 독립 판정: 보안3건·일반1건 수정 후 통과. validator가 호스트47·실제격리13·기반8/제품47을 재현, 정리·입력17개 불변 확인. [보안](../evidence/sec-local-security-final-2026-10-23.json), [일반](../evidence/sec-local-review-2026-10-23.json), [검증](../evidence/sec-local-validation-2026-10-23.json). 위 중간 대기/실패 기록은 당시 상태다.
