# DATA-catalog-calendar — Q16 종목·시장 달력

- 상태: 완료 — 합성 종목·달력 구현/검증 범위
- 선행조건: Q15 로컬 품질 관문, Q12 data/operations 계약 v1
- 요청 근거·범위: 승인된 순차 구현과 로컬 합성 검증. 실제 종목/달력 자료 채택은 SG-02
- 담당: foundation_implementer 단독 작성, root 통합, 일반 독립 검토와 독립 실행 확인
- 입력: baseline-v1의 종목 ID·시점·통화/시장·세션 계약, Q13 기본형
- 소유: src/quantharbor/domain/catalog.py, calendar.py; 시간대 변환 adapter; 전용 tests/product; docs/development/catalog-calendar.md. root 공유 카드/큐/status/증거
- Git: codex/arc-contracts, HEAD2fa8f1d. 기존 미커밋 보존, 원격 변경 없음
- 도구·비용: 표준 라이브러리·합성 fixture. 신규 패키지·유료 자원·실제 API 호출 없음
- 검증 범위: 시점별 코드 매핑·상장폐지·ticker 충돌·일반 ETF 분류 unknown, 휴장/조기폐장·DST·날짜/세션 경계와 결측 거부. 호스트·고정 컨테이너에서 필요한 제품 회귀

## 산출물과 완료 기준

버전·근거·효력 시점이 있는 불변 종목/매핑과 명시적 coverage의 달력을 제공한다. 누락을 휴장이나 유효 종목으로 추정하지 않는다. 정규장만 초기 실행 허용하며 시간외의 표현과 실행 허용은 구분한다. UTC 시각과 현지 거래일을 별도로 유지한다.

시간대 변환은 명시한 규칙 버전·내용 hash에 바인딩하며 호스트 기본 tzdb에 조용히 의존하지 않는다. 합성 fixture의 시험을 실제 한국·미국 전체 달력 확보나 공급자 자료 권리 확인으로 표시하지 않는다. 실제 자료 사용 전 SG-02와 공급자 검증이 필요하다.

## 인계

- 실제 변경: 작업 카드·인계 범위 확정, 구현 배정.
- 실제 확인: Python 공식 zoneinfo 문서의 명시 bytes 입력 방식을 사전 확인했다.
- 미실행: Q16 구현·제품 검증·실제 시장 자료 수집.
- 남은 결정: 실제 공급자/권리는 후속 SG-02, 합성 구현에는 실제 금융값이 필요하지 않음.
- 다음: 구현→독립 일반 검토→독립 실행 확인.

## 구현 반환

- 종목·달력 domain, 명시 TZif adapter와 합성 fixture/테스트·개발 문서8개를 작성했다. 주 조회는 ExplicitTimezone.lookup_calendar다.
- 구현자 제품65개(신규18)·공개193개 findings0, exit0. 최초 실패 없음. [자기 검증 증거](../evidence/data-calendar-implementation-2026-10-23.json).
- 독립 일반 검토에 인계했다. Docker·독립 실행 확인은 남아 있으며 실제 자료/권리는 미확보다.

## 독립 일반 판정

- 읽기 검토에서 실질 blocker 없음, 범위 통과. [검토 증거](../evidence/data-calendar-review-2026-10-23.json).
- validator에게 호스트제품·품질·고정컨테이너기반/제품·팀 검사와 입력8개 불변 확인을 배정했다.

## 최종 완료 판정

- 독립 실행에서 호스트제품65개·공개195개 findings0·고정컨테이너8검사/제품65개·자기프로젝트정리·팀정합성 통과. 입력8개 불변. [증거](../evidence/data-calendar-validation-2026-10-23.json).
- 실제 자료·권리/공급자 채택은 SG-02에 남는다. 다음 Q17 시장 자료/품질/시점 저장으로 이동한다.
