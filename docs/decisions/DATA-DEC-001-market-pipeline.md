# DATA-DEC-001 — Q17 합성 시장 자료와 Parquet 저장

- 날짜: 2026-10-23
- 상태: 채택 — 구현/검증 전
- 관련: Q17, E03·05·06·07, SG-02·03
- 담당: root, qh_architect 읽기 자문

## 결정

원천 사실 revision과 재관측을 분리하고, 명시적 선행 관계·지식 경계·품질·현행 권리를 함께 검사한다. [시장 자료 계약](../contracts/market-data-v1.md)을 추가하고 Q12 baseline 7파일은 유지한다. 기존 네 기본형 canonical 결과를 보존하면서 typed 시장 자료만 등록한다.

Q17A 순수 수집/품질/시점 로직을 먼저 구현·검토한 뒤 Q17B Parquet 영속 저장을 구현한다. 연구 자료의 Parquet/manifest 설계를 유지하며 fixture/in-memory만으로 저장 완료를 표시하지 않는다. 금융 원장 PostgreSQL 드라이버는 Q20에서 필요한 경우 도입한다.

PyArrow26.0.0 Linux aarch64 CPython3.13 wheel의 공식 hash·고지 파일과 source tag를 확인했다. 저장 adapter 후보이며 실제 설치/호환 검증 전 채택 완료로 표시하지 않는다. [사전 근거](../evidence/data-storage-package-preflight-2026-10-23.json). Python 패키지 의존성 없음과 wheel에 포함된 native code의 고지/의존성을 구분한다.

## 대안·영향

임시 in-memory 구현은 순수 로직 시험에 사용하되 영속 저장의 대안으로 완료 처리하지 않는다. 별도 PostgreSQL market store는 현 단계에 필요하지 않아 중복 의존성을 피한다. 직접 Parquet 형식을 구현하지 않고 고정된 라이브러리 adapter를 사용한다.

새 shared schema/serializer와 저장 I/O에는 회귀·독립 검토를 연결한다. SG-02가 미완료이므로 실제 공급자 fetch는 비활성이며 실제 금융값·계좌·API 권한은 이 결정으로 추가되지 않는다. 신규 유료 비용은0이다.

## 완료 전 조건

Q17A typed decoder/기존 golden/수집·revision·품질·권리 실패 사례, Q17B SG-03 적용·Parquet 새 프로세스 재읽기·부분 commit/변조/경로 실패, 독립 검토/검증 증거가 필요하다. 현 문서는 그 실행 통과를 뜻하지 않는다.

## 2026-10-24 Q17B 의존성 적용

Q17A 독립 재검토 후 별도 오프라인 저장 이미지에 PyArrow26.0.0을 적용했다. 고정 Python3.13.17 Linuxarm64에서 설치/버전/정확 decimal·UTC의 별도 프로세스 Parquet 재읽기와 제품98개를 확인했다. 설치된 LICENSE/NOTICE 해시·메타데이터 의존성도 확인했다. [실제 근거](../evidence/data-storage-runtime-2026-10-24.json). 현재 저장 adapter 테스트는0개이며 Q17B 완료나 독립 검증 통과가 아니다.

기본 pyproject와 Q13/Q14 실행 환경은 유지하고 저장 전용 lock/Dockerfile/검증기를 추가한다. 전체 native 의존성 취약점 감사·바이너리 재현 빌드 증명·실제자료 권리는 이번 호환 확인에 포함되지 않는다. 공식26.0.0 보안 공지와 reader 경계 자료는 [출처 기록](../evidence/data-storage-official-sources-2026-10-24.json)에 남겼다.
