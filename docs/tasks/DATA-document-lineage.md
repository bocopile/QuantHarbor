# DATA-document-lineage — Q18 문서·뉴스 출처와 시점

- 상태: 완료 — 승인된 로컬 합성 범위
- 선행: Q17 독립검증 완료, Q12 data/serialization baseline 와 Q16 catalog
- 요청 근거: 사용자 전체 순차 구현·필요 합성 검증. E04
- 담당: qh_architect 읽기 자문 → root 계약 통합 → 단독구현자 → 보안/일반검토 → 독립검증
- 입력: data-v1, market-data-v1, SG-02·D06
- 소유: documents 도메인·합성수집·저장·전용회귀와 개발문서; serializer additive 등록 임시위임, 공통계약/큐/status root
- Git: codex/arc-contracts HEAD2fa8f1d, 기존 변경 보존, 새 commit/worktree/원격변경없음
- 도구/비용: 합성자료·표준라이브러리 우선, 신규유료 0. 실제 뉴스/공시 수집·원문 다운로드·외부 AI 제공 없음
- 검증: source/원문 hash/발표·관측·수집 분리, 기업·종목연결 근거, 정정/retraction/conflict/PIT, unknown·부분·실패, 현재 목적별권리, untrusted 본문, canonical 디스크새프로세스재현

## 산출물과 완료 기준

공시·재무보고·뉴스를 연구 입력으로 관리한다. 발표 시각 부재를 수집시각으로 대체하지 않고 당시이용가능성 미확인을 보존한다. 기업 연결은 명시근거와시점만 쓰며 ticker/본문추정으로 확정하지 않는다. 정정전후근거와상충내용을 보존하고 사용권없음은 차단한다. 원문은 비신뢰 자료이며 명령·도구호출·승인으로 실행하지 않는다.

합성 원문과출처 metadata 의 canonical 저장/새프로세스재읽기를 검증한다. 실제 공급자권리 SG02·HTML/PDF 추출·실시간크롤러·AI 해석·투자전략채택은 후속이다. 원문 단위의공시/재무보고관리와재무숫자계산기능은 구분한다.

## 인계

- 실제 변경: 작업카드 작성·설계자 읽기자문 배정.
- 미실행: Q18 구현·회귀·실제 원문/권리확보.
- 다음: 제한된 추가계약/상태/저장범위를 구체화하고 단독구현.

## 설계 통합·구현 배정

- qh_architect 자문을 document-lineage-v1 과 DATA-DEC-002 로 통합했다. 5 개고정형·원문 8KiB/배치 16·명시기업 연결·전체 evidence·현재 권리·표준 lib 저장이다. 기존 Q17/frozen 계약을수정하지않는다.
- 단독구현자 소유: src/quantharbor/domain/documents.py, application/document_ingest.py, adapters/document_files.py, tests/product 의 document 전용 fixture/회귀, docs/development/document-lineage.md. serializer.py additive5 형/중첩복원만임시위임. 필요한새 package __init__ 허용.
- root 공통계약/큐/status·runtime/harness 는수정하지않는다. 구현중 root 는 repo 작성을멈춘다. 필드 변경이 필요하면 구현 전에 root 에게제안한다.

## 구현 반환

- 8 개 파일에 고정 5 형·수집/조회·기업 연결·전체 근거 파일 저장과 전용 회귀를 작성했다. 문서 19 개·전체 제품 125 개·품질 22 개·공개 246 파일 findings 0, 기반 8/제품 125·디스크 제품 125/Q17 저장 12 통과. 새 writer 종료 뒤 reader 에서 정정/충돌/PIT 를 재현했다. [구현 증거](../evidence/data-document-implementation-2026-10-24.json).
- 초기 시험 코드 괄호 오류 1 건 수정. 보안→일반→독립 실행 검증을 진행한다. 실제 원문/권리/API·AI 실행·전원 장애 내구성은 검증하지 않았다.

## 보안 검토 반환

- S3: store-only 권리로 purpose=store·연구 use 를 호출하면 연구 가능 표시가 되는 결함을 채택했다. 연구 use 는 현재 목적에 더해 research 권리를 요구하고 파일 열기 전 검사한다. [검토](../evidence/data-document-security-initial-2026-10-24.json).
- 구현자에게 domain/documents·adapters/document_files·관련 문서시험/개발문서만 단독 수정 배정. quality -I -S 예시와 정확 wheel basename 예시도 정정한다. root 는 반환 전 repo 쓰기를 멈춘다.

## S3 수정 반환

- purpose 와 연구 권리를 함께 확인하며 파일 reader 의 manifest/본문 열기 전 검사를 적용했다. matrix 12 실패 재현 후 문서 21·제품 127·품질 22·공개 248 findings0·디스크제품 127/저장 12 통과. [수정 증거](../evidence/data-document-security-fixes-2026-10-24.json). DB 미변경으로 기반 검사는 반복하지 않았다.

## 보안 재검토 통과

- S3/D1 해소·8파일 해시 일치, 추가 blocker 없음을 확인했다. [재검토](../evidence/data-document-security-final-2026-10-24.json). 일반 검토를 순차 배정했다.

## 일반 검토 통과

- 전체 계보·정정/충돌 시점·기업 연결·권리·완전성·파일 재현을 확인했고 추가 실질 결함 없음, 입력8개 해시 일치. [일반 검토](../evidence/data-document-review-final-2026-10-24.json). 독립 실행 검증을 배정했다.

## 최종 완료 판정

- 보안 S3 수정·재검토와 일반 검토 후 독립 실행 5명령을 통과했다. 제품127(문서21)·품질22·공개251 findings0·디스크제품127/저장12·팀6/36/110, 입력8파일 해시 불변·자기자원 정리 확인. [최종 검증](../evidence/data-document-validation-2026-10-24.json).
- 완료는 합성 원문·계보·정정/충돌/PIT·명시 기업연결·권리·파일 저장 범위다. 실제 source/권리/API·장문파싱·AI/금융 실행·전원 장애는 미완료다. 다음 Q19 조회 어댑터와 연결 준비.
