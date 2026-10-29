# DATA-market-pipeline — Q17 시장 자료·품질·시점 저장

- 상태: 완료 — 승인된 로컬 합성 범위
- 선행조건: Q16 독립 검토·고정 환경 검증 완료, data-v1/serialization-v1 기준
- 요청 근거·범위: 승인된 전체 순차 구현과 필요한 합성 검증. E03·05·06·07
- 담당: qh_architect 읽기 자문 → root 계약/의존성 통합 → 단독 implementer → 검토/검증
- 입력: Q12 baseline, Q13 기본형, Q16 catalog/calendar, SG-02·03
- 소유: market_data 도메인/수집/품질/저장·전용 합성 테스트·개발 문서. Q17A는 domain/market_data.py, application/market_ingest.py, 수집 ports/synthetic adapter, 관련 tests/product와 docs/development/market-data.md. serialization.py는 additive 등록을 위해 구현자에게 임시 단독 위임. 공통 계약/의존성/큐/status는 root
- Git: codex/arc-contracts HEAD2fa8f1d, 기존 미커밋 보존. 원격 변경 없음
- 도구·비용: 합성 입력, 신규 유료0. 실제 공급자 API/자료 수집 없음. 새 의존성은 SG-03 버전/해시/고지/호환 확인 후 도입
- 검증: pagination/실패/중복/누락 재수집·정정/PIT·가격조정/FX/기업행동 단위·결측/신선도/권리·저장 재현과 필요한 회귀

## 산출물과 완료 기준

DataEnvelope의 출처·버전·원본/정규화·발표/관측/수집 시각·품질/권리를 구현한다. 성공한 빈 결과와 미수집·부분·실패를 구분한다. 정확한 금액/단위, 원문 hash와 계약 hash를 혼용하지 않는다. 공급자 revision과 당시 이용 가능한 데이터로 재현 가능한 자료 버전을 만든다.

연구 저장 형식은 채택된 Parquet/manifest 설계를 기준으로 필요한 범위를 확인한다. fixture/in-memory만으로 영속 저장·실제 수집 완료를 주장하지 않는다. 금융 원장·승인·주문 DB 구현은 후속 Q20~27이며 연구 자료를 정본 원장으로 사용하지 않는다.

## 인계

- 실제 변경: 착수 범위/카드 작성. Q17 소스 미구현.
- 실제 확인: 공식 패키지 메타데이터와 PyArrow wheel의 hash/포함 고지 파일을 사전 조회했다. [준비 기록](../research/market-storage-preparation-2026-10-23.json). 설치·채택·네이티브 의존성 전체 감사 완료 아님.
- 미실행: Q17 구현/의존성 설치/실제 자료 수집/저장 검증.
- 남은 결정: 실제 공급자/권리 SG-02 미완료. 합성 구현에 실제 자금·위험값을 요구하지 않음.
- 설계 반환: qh_architect 읽기 자문을 root가 market-data-v1과 DATA-DEC-001로 통합했다. 사실 개정/재관측 분리, explicit predecessor, 권리·PIT·페이지 실패 보존, Q17A→Q17B 순서를 채택했다. 설계 반환은 구현 검증 완료가 아니다.
- 다음: Q17A 순수 계약/수집/품질 구현 → 독립 검토 → Q17B 의존성 호환·Parquet 디스크/새 프로세스 재읽기 → 보안 검토/독립 검증.

## 2026-10-24 Q17A 반환

- 고정 시장자료 스키마5개, recursive decoder, 순수 수집/정정/PIT/권리/품질과 Q16 연결, 합성 adapter를 구현했다.
- 구현자 검증: 신규28개 첫 통과, 최종 제품93개·품질209파일 findings0. 독립 실행 판정 아님. [입력 해시와 결과](../evidence/data-market-implementation-2026-10-24.json).
- root 중간 지적의 series별 신선도·PIT 보류·늦은 충돌 인지시점을 보완했다.
- 다음: 일반 독립 검토 후 Q17B. Parquet 저장·충돌 근거 영속·새 프로세스 재읽기·고정환경 검증은 아직 미실행.

## 2026-10-24 독립 검토 중간 지적

- 기업행동 effective_date/effective_at와 Q16 timezone 결속 누락, raw select_view와 검증사용 경계, adjusted 근거 action의 basis/knowledge/venue/unit 경계가 지적됐다.
- 미래 page.received_at/evaluated_at 및 페이지 수신 역행, 재관측 입력순서에 따른 conflict detected_at 차이도 확인됐다. 아직 전체 검토 반환 전이며 Q17B 착수는 보류한다. 테스트 통과를 결함 부재로 취급하지 않는다.

## Q17A 수정 반환

- 수정 전4개 테스트7개 assertion 실패로 지적을 재현했다. 수정 후시장33·제품98·품질212파일 findings0 통과. [수정 증거](../evidence/data-market-fixes-2026-10-24.json).
- domain raw PIT와 application 검증view, full ActionRef·시각/단위 결속, receipt 미래/역행 거부, 전체evidence 충돌재계산을 적용했다. 독립 재검토 전이며 Q17B는 아직 미착수다.

## Q17A 재검토 통과·Q17B 착수

- env_final_reviewer가 R1~R4 수정과7파일 해시를 확인해 범위 통과했다. [재검토](../evidence/data-market-review-final-2026-10-24.json).
- root가 별도 오프라인 고정 저장 환경·SG-03 호환을 확인한 뒤 구현자에게 Parquet adapter/회귀를 배정한다. 현재 독립 실행 검증·Q17 전체 완료·실제 SG-02는 미완료다.

## Q17B 배정

- 고정 저장 환경 실제호환을 root가 확인했다(별도writer/reader exactdecimal·UTC, 제품98). 저장회귀0개인 preflight이며 [근거](../evidence/data-storage-runtime-2026-10-24.json).
- qh_architect 추가 읽기 자문을 market-storage-v1으로 통합했다. 기존5스키마 유지+저장4스키마, 전체evidence/페이지trace/현재권리 결속을 채택했다.
- 구현자 단독소유: domain/market_storage.py, adapters/parquet_market_store.py, tests/storage, storage개발문서 구현절; market_data.py reducer facts, market_ingest.py boundedtrace, serialization.py additive4등록/decoder와 관련제품회귀 임시위임. root의 Docker/lock/검증harness/quality/공통계약/큐/status는 수정하지 않는다.
- root는 구현 중 repo작성을 멈춘다. 반환후 보안검토→수정→일반검토→독립실행 순서로 진행한다.

## Q17B 구현·디스크 통합 반환

- 구현자 제품104·저장12(2회) 통과. root가 own named volume/TMPDIR=/store·정확wheel명·비어있는저장suite거부를 통합했다.
- root 실제 디스크 검증: 제품104·저장12,16.457초, 자기container/volume/image정리 확인. 품질19개·공개228개findings0. 첫 편집의 IndentationError는 Docker 실행 전에 수정했다. [증거](../evidence/data-storage-implementation-2026-10-24.json).
- 보안→일반→독립실행 검증 순으로 진행한다. 실제자료/권리SG02·전원장애내구성은 미검증이다.

## 2026-10-24 Q17B 보안2건 수정

- 독립 검토 P1 비공개 후보 복사·P2 FIFO open 대기를 합성3개 테스트(실패2·timeout1)로 재현한 뒤 수정했다. Git 공개 후보/ignore/보호분류 후 dirfd 읽기, nonblocking 정규파일 검사를 적용했다. 실제 private 자료를 열지 않았다.
- 수정 후 품질22개·공개230파일 findings0, 디스크 제품104/저장12와 자기자원 정리 통과. 보안 재검토→일반→독립실행 전이며 Q17 미완료다.

## Q17B 일반 검토 반환

- R5 본문생략 rejection의 request/scope/cursor/clock 결속 누락, R6 FIFO회귀의 Docker CLI 의존을 수정한다. 17개 입력hash 일치, 추가 실질결함 없음. [검토](../evidence/data-storage-review-initial-2026-10-24.json).
- 단독구현자에게 domain market_storage 및 관련product/storage회귀, root소유 harness와 tests/quality/test_market_storage_harness.py의 해당검사순서만 임시위임한다. root는 반환 전 repo작성을 멈춘다.

## 일반 수정 반환

- R5 metadata변조16assertion·R6 Docker없는FIFO실패를 먼저 재현했다. 공통reducer metadata거부사유대조·wheel경계뒤Docker탐색으로 수정했다.
- 제품106·품질22·공개233 findings0, 고정디스크제품106/저장12·정리통과. [수정](../evidence/data-storage-general-fixes-2026-10-24.json). 재검토·독립실행 전이다.

## 일반 재검토 통과

- R5/R6 수정·17파일hash일치·추가blocker없음을 독립확인했다. [재검토](../evidence/data-storage-review-final-2026-10-24.json). validator에게 최종제품/품질/고정저장/기반/팀·입력불변 검증을 순차배정했다.

## 최종 완료 판정

- Q17A 일반4건·Q17B 보안2건/일반2건 수정·재검토 통과 후 독립 실행을 마쳤다. 제품106·품질22·디스크저장12·기반8과고정제품106·팀6/36/110 통과. 입력17hash 불변·wheelhash 일치·자기자원 정리 확인. [최종 증거](../evidence/data-market-validation-2026-10-24.json).
- 완료는 합성 가격/FX/기업행동·수집/품질/권리/PIT·Parquet 저장 재현이다. 실제 source/권리SG02·raw원문재파싱·power-loss는 미완료다. 다음 Q18 E04 문서/뉴스로 이동한다.
