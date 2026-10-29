# BASE-DEC-001 — Q13 합성 런타임 고정

- 날짜: 2026-10-23
- 관련 작업: Q13 C01/02/03/05, SG-03
- 상태: 채택 — 로컬 합성 개발 범위
- 결정 담당·근거: root, 승인된 순차 구현·로컬 합성 검증

## 요구와 확인 사실

금액·직렬화 계약과 SQL transaction을 재현할 런타임이 필요하다. 호스트 Python 3.13.12, Docker 28.3.2, Compose 2.38.2의 가용성을 확인했다. Python 공식 [3.13.17 보안 릴리스](https://www.python.org/downloads/release/python-31317/)와 PostgreSQL 공식 이미지 18.6을 2026-10-23 확인했다. 고정 arm64 이미지에서 실제 버전과 Debian 패키지·저작권 고지를 읽었다.

## 선택과 이유

Python 3.13.17 및 PostgreSQL 18.6 bookworm의 platform manifest digest를 [lock](../../config/runtime-lock.json)에 고정한다. 호스트 전역 업그레이드 없이 컨테이너로 실행한다. 현재 외부 Python 패키지는 필요 없으며 향후 Parquet·LEAN·API client 도입 때 SG-03을 다시 적용한다. SQLite는 운영 설계 PostgreSQL의 transaction·numeric 동작을 대체하지 않으므로 이 검증에는 사용하지 않는다.

Python [라이선스와 포함 고지](https://docs.python.org/3.13/license.html), [PostgreSQL License](https://www.postgresql.org/about/licence/), Docker recipe MIT와 OS별 라이선스를 구분한다. 전체 이미지가 MIT인 것은 아니다. Python 97개·PostgreSQL 147개 OS 패키지 버전과 포함 고지 hash를 [inventory](../evidence/base-runtime-inventory-2026-10-23.json)에 기록했다. [Debian copyright 규칙](https://www.debian.org/doc/debian-policy/ch-docs.html#copyright-information)에 따른 각 패키지 고지를 보존한다. 외부 배포는 수행하지 않았다.

고정 recipe: [Python](https://raw.githubusercontent.com/docker-library/python/e316b6c5b88b7c8e4806aa7626060c9bd8227e66/3.13/slim-bookworm/Dockerfile), [PostgreSQL](https://raw.githubusercontent.com/docker-library/postgres/e00e1bd34ec5c8a8e7ad89b273b3d42efaf6d5bc/18/bookworm/Dockerfile). 실행 정의는 [Compose 문서](https://docs.docker.com/reference/compose-file/services/), SQL 실패 검사는 [psql 문서](https://www.postgresql.org/docs/18/app-psql.html)를 참조했다.

## 미확인과 재검토 조건

초기 SG-03 런타임 범위만 확인한다. 전체 엔진·데이터 라이브러리의 호환성, 실제 계좌, 제품 AI, x86 실행, 취약점 전체 검사와 외부 배포 조건은 완료하지 않았다. 이미지 보안 업데이트·아키텍처 변경·패키지 추가 시 새 digest·고지·실행 결과를 검토한다. 새 유료 자원은 만들지 않았다.
