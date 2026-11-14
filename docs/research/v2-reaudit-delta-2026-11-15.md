# v2 재감사 델타 분석과 작업 재조정 (2026-11-15)

기준: `main` HEAD `171e3e4`. 입력: 새 `v2/` 문서 2개(`QuantHarbor_main_reaudit_v3_2026-11-15.md`, `QuantHarbor_재분석_보고서_main_5ff8e29.pdf`). 이전 라운드 산출물([작업 목록](../v2-work-list-2026-11-14.md), [검증 전수 기록](v2-claim-verification-2026-11-14.md), [후속 조사](v2-followup-research-2026-11-14.md))을 전제로 한 **변경분(델타)** 이다. Claude Workflow 11개 에이전트(문서 검증 2·작업 재조정 1·문서 증식 감사 1·GitHub 조사 3·독립 재검증 2·비평 1·종합 1)를 읽기 전용으로 돌렸다. **정적 분석이며 테스트·DB·Docker를 실행하지 않았다.** 아래 제안은 큐의 완료 판정을 바꾸지 않으며 순서 변경(REORDER)과 정책 값은 사용자 결정 전 미확정이다.

구분: **확인된 사실**(SHA·파일·줄 근거) / **설계 제안**(NZ 작업·NX 변경) / **미결정**(결정 항목). 재검증은 R1 6건·R2 3건에만 적용했고(반박 1건) 나머지 findings 51건은 `not_checked`다.

## 1. 핵심 확인 사실

- [SHA 혼동] v3 MD 는 기준선을 80403ab 로 적지만 Q27 pending-hold 수정, P28-01/02 artifact_ready, P28-03 착수는 7ba3c88(PR#4) 이후에만 있다. 80403ab:postgres_execution.py:538-540 은 무조건 holds.pop 이고 171e3e4:538-546 은 pending 완료 예산을 보존한다. 라벨은 틀리고 내용은 HEAD 에서 참이다(R1-01·R1-02 upheld, 정적 판독).
- [변화량] 80403ab..5ff8e29 는 27커밋, 184파일, +25,037/-105, src 73→77파일(19,141→20,855줄), def test 949→1,067이다. 마지막 src/tests 커밋은 ba5b52d(2026-10-30)이고 5ff8e29→171e3e4 는 v2/ 4파일만 바뀐다(R2-01·02·03, 정적 재측정이며 독립 검증은 not_checked).
- [문서 증식] docs/*.md 는 157→206개, 1,334,165→2,287,073B(+952,908B, +71.4%)로 src+tests 증가(+196,377B)의 약 4.9배다(줄 기준은 약 1.2배). 11-14 하루 3문서가 572,365B(증가분 60.1%)이고 필독 4문서 188,046B 중 status.md 가 79.3%다(R4 정적). 단 2b-2a +926줄이 main 밖 PR #7(OPEN)에 있어 '코드가 멈췄다'는 main 한정이다(R2-12·15).
- [Q27] 80403ab·171e3e4 모두 in_progress, q27_complete=true 증거 0건, FUP-Q27-006 diagnosing, 009~014 queued 다. 836/86 PASS 는 8a27220 고정 root 자기보고이며 독립 검증이 아니고 runner 가 저장소에 없다. '3.8시간'은 두 실행의 합 13,733.5초이고 동시 실행 정황이 있어 벽시계 시간은 다를 수 있다(R1-04 upheld, R2-09·14).
- [PDF 해소 2건] status.md 의 PR#1 미병합 표기 정정(171e3e4:status.md:148)과 Q27 replace_source 예약 보존(af40f9c)은 정적으로 사실이다(R1-13·R2-07 upheld). 반면 PDF 의 절대경로 '121회·16개·감소'는 범위를 바꾼 비교이며 실제는 80403ab·5ff8e29·171e3e4 모두 18파일 128회로 불변이다(R2-25).
- [v3 신뢰도] v3 §2 정정표 최소 5행은 이전 v2 에 없거나 반대로 쓰인 서술을 귀속하고(R1-05 upheld), v3 QH-* ID 는 이전 v2 번호와 같고 의미가 달라 매핑이 틀어진다(R1-27 upheld). v3 는 ID 정본이 아니라 '7ba3c88 이후 상태 반영 재감사'로만 쓰고, kis_read 존재·P28 매핑·Q27 이후 커밋 반영만 채택한다(R1-07).
- [실데이터 스파이크 불가] PDF 권고 2 는 지금 열 수 없다. environment 는 market_data.py:44-48,493,834 에서 synthetic 단일값, envelope 128건 상한, src 에 HTTP 클라이언트 0건, 승인 레지스터에 범위 없음, SG-02 미충족이다. 약관은 FSC 주식시세정보(15094808) 제4유형(변경금지·제3자 제공 금지), Alpha Vantage 무료는 full 일봉 불가, Tiingo 무료는 내부 사용 한정이다(R2-29 upheld, 약관 확인 2026-11-15).
- [Q27 의존 모양] work-list 선행 열 파싱(R3, 정적)에서 NX 53개 중 NX-BASELINE-01 직접 의존 9개, 전이 22개(41%)다. 직접 9개 중 기술 의존 5개, 절차 의존 4개이며 PortfolioConstructor·시도 원장·정책 스키마는 새 모듈이라 기술적으로 Q27 과 독립이다(EXEC-DEC-003:16 start_dependencies 규약).
- [비평가 신규 공백] 저장소는 이미 GitHub PUBLIC 인데 NX-DOCS-PROCESS-03 은 '공개 전'으로 서술한다(gh 읽기 전용 조회 2026-11-15, 이번 종합에서 재확인 안 함). 장중 15분 루프 가격 소스, 독립 검토 정의, 자동운영 승인 모델, 경제성 기준, v2/ 의 공개 후보 게이트 거부(classify() 단독 호출, 전체 게이트 미실행)가 어떤 NX/ND 에도 없다(CG-01~08).
- [순서 변경 판정] PDF 권고 1~6 중 사용자 순서 변경(REORDER)이 필요한 것은 2번(실데이터 스파이크) 하나뿐이다. 3·5번은 같은 순차 구현 단계 안의 additive 신규 파일이라 순서 변경이 아니라 채택 범위(ND-18) 문제이고, 4·6번은 개정 창과 문서 정리다. 위임 판단 ND-05/06/07/08b 는 재질의하지 않는다.

## 2. 계획 대비 실행 평가와 최소 경로

PDF의 '계획이 실행보다 빠르다'는 부분적으로 맞다. 맞는 부분: main 기준 src·tests·scripts·config·migrations·containers의 마지막 변경은 2026-10-30(ba5b52d)이고 이후 16일간 코드 변경이 없다. 그동안 docs/*.md는 157개에서 206개로(+952,908B, +71.4%) 늘었고 바이트 기준 src+tests 증가(+196,377B)의 약 4.9배다. 11-14 하루에 들어온 3문서(1,858줄·572,365B)가 증가분의 60.1%다. NX 53개는 아직 하나도 큐에 채택되지 않았고 25개가 docs_only이며 ND 17개(제안 ND-17·18 포함 시 19개)가 한 명의 사용자에게 걸려 있다. Q27은 FUP-Q27-006 diagnosing과 009~014 queued로 아직 열려 있다. 정정이 필요한 부분: (1) 코드는 멈추지 않았다. 11-14 23:13에 2b-2a 구현 926줄이 브랜치와 PR #7에 있다(R2-12·R2-15). (2) 바이트 비교는 문서가 줄이 길어 과대하다. 줄 기준 증가는 약 1.2배다. (3) 병목의 원인 진단이 다르다. 문서는 AI가 하루 만에 쓸 수 있어 작성 속도 자체는 병목이 아니다. 실제 제약은 ① 사용자 결정 용량(ND 17+), ② 검증 용량(증거가 전부 root 자기보고, 시험 836·86개 합산 3.8시간급, AGENTS.md '시험은 요청 시' 규칙), ③ 필독 부담(필독 4문서 188,046B, 그중 status.md 79.3%)이다. (4) PDF 권고 중 순서 변경이 필요한 것은 2번(읽기 전용 실데이터 스파이크) 하나뿐이다. 3번(PortfolioConstructor 병행)은 같은 '순차 구현' 단계 안이라 순서 변경이 아니라 채택 범위(ND-18) 문제다. 4·5·6번도 순서 변경이 아니다. (5) 스파이크는 범위 정의조차 안 된다. 계약은 environment=synthetic 단일값이고 KR·US 일봉에 약관이 깨끗한 공급원이 없으며 승인 레지스터에 범위가 없다. 허용해도 얻는 것이 적고, 운영 루프의 가격 소스 문제(CG-02)는 일봉 스파이크로 풀리지 않는다.

AGENTS.md 순서와의 관계: 현재 단계는 AGENTS.md 순서의 3단계 '순차 구현'(합성 한정: Q27→P28→P29→RETURN-01)이다. 2단계 '요구사항·아키텍처 확정'은 정책 값이 PG-01~05로 의도적으로 미뤄진 채 꼬리가 열려 있다. NX의 docs_only 정책 구조 작업은 이 꼬리를 닫는 설계 작업이며 ND-05 위임이 '설계 한정'으로 허용한 범위라 순서 위반은 아니다. 다만 그만큼 계획 부피가 늘었다. 4단계 '모의 검증'은 RETURN-02(실제 조회·모의 통합) 이후다. 사용자 순서 변경 결정이 필요한 것은 (a) 실데이터 읽기 스파이크를 RETURN-02보다 앞당기는 것(제안 ND-17), (b) KIS 모의 연결 앞당김(ND-08b, 이미 거절 판단)뿐이다. 새 코드(PortfolioConstructor·Trial Ledger)를 Q27 판정 전에 병행하는 것은 순서 변경이 아니지만 ND-05가 설계 한정이므로 ND-18 채택 범위 결정이 필요하다. 5~7단계(소액 실전·자동운영)는 AP-07·AP-08과 PG-05가 이미 사용자 명시 승인을 요구하며 이번 권고로 앞당기지 않는다.

권장 최소 경로:
0. 0. 사용자 질의 1회, 최대 5개 묶음(문서 증식 없이): ND-18(채택 범위), ND-04(reduce-only), ND-09(본인 계좌 단독·전문가 확인 시점·계좌 유형 CG-10), ND-01 방식(값 제외), 저장소 공개 상태·이력 스캔 승인(CG-01). 새 NX·ND·조사 문서는 이 질의가 끝날 때까지 만들지 않는다. [순서 변경 아님]
1. 1. 즉시 정리 1건(문서·로컬, 순서 변경 아님): README 현재 단계 한 문단, status.md 상단 '현재 표'(기준 SHA·큐 위치·열린 PR·미실행 목록·ND 17개 정정), md 절대경로 15개 상대 링크화(증거 JSON 3개는 해시 확인 후). 원격 push·PR은 AP-06이라 사용자 승인 후. 같은 변경에서 NX-DOCS-PROCESS-03의 '공개 전' 서술을 정정한다.
2. 2. Q27 마감(NX-BASELINE-01, 기존 사용자 지시 범위 EXEC-DEC-002/003): FUP-Q27-006·009~014를 닫고 같은 고정 입력으로 실제 DB 판정과 독립 재확인. 이어서 PR #7(NX-BASELINE-02) 수용 판정과 브랜치 위상 정리(CG-07, 삭제·병합은 사용자 승인). [순서 변경 아님]
3. 3. 결정 기록 3건만 추가(docs_only, 구현 없음): 독립 검토 정의(CG-03), 자동운영 승인 모델 설계 입력(CG-04), 운영 가격 소스 결정표(CG-02). 모두 계약 개정 창 전에 필요하다. [순서 변경 아님. CG-02의 요구 단순화는 사용자 결정]
4. 4. Q27 판정 직후 P28-04 착수 전에 target-local-v2 단일 개정 창: reduce-only와 비율형 비용 구조(요율 값 제외), 이행 계획, qh-contract-change 독립 일반·보안 검토. ND-04·ND-13(시험 시간 예산) 선행. 다중 실패 수집은 읽기 전용 진단 함수로 분리해 이 창에서 제외한다. [순서 변경 아님, 순차 구현 안]
5. 5. P28-04~08 → P29-01/02 → RETURN-01을 기존 큐대로 합성 한정으로 마감한다. 같은 기간 ND-18이 채택한 범위만 additive 합성 코드(PortfolioPolicy 별도 타입, Constructor, Trial Ledger)로 병행하되 활성 worker 한 명·작성자 한 명 규칙을 지키고 application/target.py·domain/target.py는 수정하지 않는다. [채택 범위 결정 ND-18 필요, 순서 변경 아님]
6. 6. RETURN-02 진입 점검표 1개 표(CG-08)로 PG-01·SG-02·AP-05 범위·ND-09·NX-SECURITY·가격 소스·독립 검토·공개 상태·경제성(CG-05)을 집계한다. 이 표가 채워지기 전에는 실제 조회·모의 연결·실데이터 수집을 시작하지 않는다. [AGENTS.md 4단계 진입 관문]
7. 7. 실데이터 읽기 스파이크는 열지 않는다. NX-DATA-03 준비 메모(공급원 약관·기술 선행조건·DoD, 계정·키 발급·수집 없음)만 작성한다. 실행하려면 사용자가 ND-17로 순서를 명시 변경하고 SG-02 결정 기록, 계약 개정 또는 별도 연구 모듈 결정, 계정·키 승인(AP-03·05 범위 확장)이 먼저 있어야 한다. [사용자 순서 변경 결정 필요: 이 단계만]
8. 8. 나머지 NX(학습·진위 구현, 정책 비교 시뮬레이션 등)는 소비자(실데이터·실모델·Q30 관찰)가 생길 때 꺼내는 트리거 대기 목록으로 두고 폐기하지 않는다. 문서는 독립 8개 이하로 합치고 상태 요약은 현재 표로 흡수하며 새 독립 문서는 만들지 않는다.

## 3. 새 작업 (NZ, 17개)

| ID | 우선 | 유형 | gate | 크기 | 작업 | 선행 |
|---|---|---|---|---|---|---|
| NZ-BASELINE-01 | P1 | new_build | docs_only | S | 브랜치·PR 위상 점검표 | - |
| NZ-SECURITY-01 | P1 | new_build | docs_only | S | 저장소 공개 상태 정정과 공개 정책 결정 요청 | - |
| NZ-SECURITY-02 | P1 | blocked | synthetic_local | M | 전 이력 비밀정보 읽기 전용 스캔(승인 후) | NZ-SECURITY-01, ND-19 |
| NZ-SECURITY-03 | P2 | new_build | docs_only | S | 실전 관문의 독립 검토 정의 결정 기록 | - |
| NZ-POLICY-01 | P2 | new_build | docs_only | S | 자동운영 승인 모델 설계 입력(ADR) | NX-POLICY-01 |
| NZ-DATA-01 | P2 | new_build | docs_only | S | 실데이터 읽기 전용 스파이크 준비 메모(수집 없음) | NX-SECURITY-02 |
| NZ-DATA-02 | P2 | new_build | docs_only | S | 운영 루프 가격 소스 결정표 | - |
| NZ-DATA-03 | P3 | blocked | public_data | L | 읽기 전용 연구용 실데이터 스파이크(승인 전 차단) | ND-17, NZ-DATA-01, NX-AUTHENTICITY-02, NX-SECURITY-02, SG-02, SG-03 |
| NZ-PORTFOLIO-01 | P1 | new_build | docs_only | M | PortfolioConstructor 사양·불변식·변이 코퍼스(설계 문서, 코드 전) | NX-POLICY-01 |
| NZ-TAX-COST-01 | P2 | new_build | docs_only | S | 경제성·패시브 귀무 기준·프로젝트 중단 기준 점검표 | NX-SECURITY-02 |
| NZ-TEST-STRATEGY-01 | P2 | new_build | docs_only | M | 변경 단위 시험 계층·계약 에포크·부분 실행 증거 표기 설계 | - |
| NZ-TEST-STRATEGY-02 | P2 | blocked | synthetic_local | M | 시험 시간 프로파일 1회와 병렬 안전성 점검(요청 시 실행) | ND-13, NX-BASELINE-01 |
| NZ-TEST-STRATEGY-03 | P3 | new_build | docs_only | S | 속성 시험·가드 변이 시험 ADR(의존성 최소) | NZ-TEST-STRATEGY-01, SG-03 |
| NZ-OPS-INFRA-01 | P2 | new_build | docs_only | S | v2/ 와 공개 후보 게이트 정합 결정 | - |
| NZ-OPS-INFRA-02 | P3 | new_build | docs_only | S | 의존성·OSS 후보 판정표(SG-03 입력, 도입 없음) | - |
| NZ-DOCS-PROCESS-01 | P2 | new_build | docs_only | M | status.md 이력 보관·증거 동결·새 문서 상한 규칙(이력 보존형) | NX-DOCS-PROCESS-01, NX-BASELINE-02 |
| NZ-DOCS-PROCESS-02 | P2 | new_build | docs_only | S | RETURN-02 진입 준비도·트리거 대기 표(새 문서 없음) | NX-DOCS-PROCESS-01 |

### 상세

#### NZ-BASELINE-01 — 브랜치·PR 위상 점검표
- 우선 P1 · new_build · gate `docs_only` · 크기 S · 담당 qh_researcher(조사), orchestrator(통합) · 계약 영향 none
- 내용: 로컬·원격 장기 브랜치 4개(main, codex/qh-local-delivery-20261030, merge/qh-local-delivery-20261030, feat/p28-03-2b2a-wip)의 목적·tip SHA·충돌 지점·운명을 표로 정리한다. codex 브랜치의 cef6a5e 는 main 에서 삭제된 이전 v2 MD·PDF 를 되살리고, PR #5 는 main 이 아닌 base 로 병합됐다. 삭제·병합·push 는 하지 않는다.
- 큐 위치: Δ1, NX-BASELINE-02(PR #7 수용 판정) 이전
- 기존 ID: NX-BASELINE-02, AP-06
- 출처: CG-07, R2-15, R4 브랜치별 상태 기록 분기, PDF N-4, PDF 권고1
- 완료 기준: 브랜치별 목적·tip SHA·main 대비 ahead/behind·충돌 예상 파일을 표로 기록한다.
- 완료 기준: cef6a5e 가 이전 v2 MD·PDF 를 재추가하는지 PR #7 수용 전 점검 항목에 넣는다.
- 완료 기준: 쌓인 PR 은 base 가 main 인지 확인하는 항목을 git-workflow 점검표에 추가한다.
- 완료 기준: 삭제·병합·push·원격 변경은 AP-06 사용자 승인 전에는 실행하지 않는다.
- 근거: R2-15: PR #5 MERGED 이나 base 가 main 아님(gh 읽기 전용, 2026-11-14)
- 근거: CG-07: cef6a5e 는 이전 v2 MD 1,033줄과 PDF 1,645,400B 재추가(git show --stat)
- 근거: 로컬 clone origin/* 참조는 마지막 fetch 시점 불명
- 사용자 결정: ND-25(브랜치 폐기·병합 방침, AP-06)

#### NZ-SECURITY-01 — 저장소 공개 상태 정정과 공개 정책 결정 요청
- 우선 P1 · new_build · gate `docs_only` · 크기 S · 담당 qh_security_reviewer · 계약 영향 none
- 내용: 비평가 보고(gh 읽기 전용 조회, 2026-11-15)로는 저장소가 이미 PUBLIC 인데 NX-DOCS-PROCESS-03 은 '공개 전 점검'으로 쓴다. 서술을 정정하고 공개 유지 여부, LICENSE 정책, 커밋 작성자 메타데이터 정책을 사용자 결정으로 올린다. 원격 설정 변경은 하지 않는다.
- 큐 위치: Δ1, NX-DOCS-PROCESS-01 정리 PR 이전
- 기존 ID: NX-DOCS-PROCESS-03, NX-SECURITY-01, NX-SECURITY-02, AP-06
- 출처: CG-01, security.md 원칙 1·5, PDF N-10, R4 절대경로 지표
- 완료 기준: 가시성은 읽기 전용 조회 날짜와 함께 기록하고 변경은 시도하지 않는다.
- 완료 기준: NX-DOCS-PROCESS-03 의 '공개 전' 문구를 '이미 공개, 이력에 잔존'으로 정정 제안한다.
- 완료 기준: 공개 유지·LICENSE·작성자 이메일 정책을 ND-19 사용자 결정 항목으로 정리한다.
- 완료 기준: 이메일 주소와 도메인명은 문서에 기록하지 않는다.
- 근거: CG-01: gh repo view visibility PUBLIC(이번 종합에서 재확인 안 함)
- 근거: 171e3e4:docs/v2-work-list-2026-11-14.md:183-190(공개 전 서술)
- 근거: git ls-tree HEAD 최상위에 LICENSE 없음(CG-01)
- 사용자 결정: ND-19(공개 유지, 이력 스캔 승인, LICENSE, 작성자 이메일 정책)

#### NZ-SECURITY-02 — 전 이력 비밀정보 읽기 전용 스캔(승인 후)
- 우선 P1 · blocked · gate `synthetic_local` · 크기 M · 담당 qh_security_reviewer · 계약 영향 none
- 내용: security.md 원칙 5 는 이력 비밀정보 검사를 별도 승인 작업으로 둔다. 비평가의 제한 패턴 6종 점검은 일치 0건이었으나 감사가 아니다. 승인 시 값을 출력하지 않고 전 이력 54커밋과 증거 JSON 300개를 점검해 건수·유형만 기록한다. 현재 승인 상태는 NOT_APPROVED 다.
- 큐 위치: Δ1, ND-19 승인 응답 뒤에만 착수
- 기존 ID: NX-SECURITY-01, NX-DOCS-PROCESS-03
- 출처: CG-01, security.md 원칙 5, AGENTS.md 민감정보 규칙
- 완료 기준: 사용자 승인 기록이 없으면 시작하지 않고 blocked 로 둔다.
- 완료 기준: 일치한 값·경로 내용은 출력하지 않고 건수와 유형만 기록한다.
- 완료 기준: 증거 JSON 300개의 의미 검사 포함 여부와 미검사 범위를 명시한다.
- 완료 기준: 발견 시 키 폐기·이력 재작성은 사용자 결정으로 넘기고 직접 수행하지 않는다.
- 근거: CG-01 참고 스캔: 키 패턴 6종, 54커밋, 일치 파일 0(제한 패턴, 감사 아님)
- 사용자 결정: ND-19

#### NZ-SECURITY-03 — 실전 관문의 독립 검토 정의 결정 기록
- 우선 P2 · new_build · gate `docs_only` · 크기 S · 담당 qh_security_reviewer · 계약 영향 none
- 내용: 현재 독립 검토는 같은 orchestrator 아래 하위 역할이며 team.toml 은 직접 하위 격리 미검증을 스스로 밝힌다. PG-05·Q32·RETURN-02 가 인정할 독립 검토(사람이 직접 읽을 모듈, 타 모델 공급자 교차 검토, 외부 감사, 증거 형식)를 정의한다. 자기 검토를 독립 검토로 기록하지 않는다.
- 큐 위치: Δ2, NX-BASELINE-01 독립 재확인 이전이 이상적
- 기존 ID: NX-AI-RUNTIME-03, NX-BASELINE-01, PG-05
- 출처: CG-03, R1-17, 171e3e4:config/ai/team.toml:21-22
- 완료 기준: 사람이 직접 읽을 모듈 후보(execution·approval·egress·broker·정책 검사)를 제시한다.
- 완료 기준: 타 모델 공급자 교차 검토와 외부 감사의 필요 여부를 선택지로 둔다.
- 완료 기준: 증거 형식이 자기보고 한계를 명시하도록 규칙을 쓴다.
- 완료 기준: 결정 전에는 PG-05·Q32 의 독립 검토 충족을 선언하지 않는다.
- 근거: 171e3e4:config/ai/team.toml:21-22 direct_child_isolation_verified=false
- 근거: CG-03: HEAD docs·config 에 외부 보안 검토·침투 시험·외부 감사 0건(git grep)
- 사용자 결정: ND-21

#### NZ-POLICY-01 — 자동운영 승인 모델 설계 입력(ADR)
- 우선 P2 · new_build · gate `docs_only` · 크기 S · 담당 qh_architect · 계약 영향 none
- 내용: A-DEC-002 는 포괄·자동 승인 확대를 금지하고 plan 9단계와 AP-08 은 미승인이다. 자동운영 단계의 사전 승인 봉투(종목·금액·횟수·손실한도·기간), 예외 상향 절차, 후보별 승인과의 additive 호환 여부를 정리해 target-local-v2 창에서 승인 계약을 또 깨지 않을 판단 자료로 쓴다. 값은 정하지 않는다.
- 큐 위치: Δ2, target-local-v2 개정 창(Δ3) 설계 확정 이전
- 기존 ID: NX-POLICY-04, AP-08, PG-05
- 출처: CG-04, 171e3e4:docs/decisions/A-DEC-002-initial-trading-policy.md:24, 171e3e4:docs/plan.md:44
- 완료 기준: 봉투 필드 후보와 예외 상향·중단·재가동 절차를 값 없이 목록화한다.
- 완료 기준: 후보별 승인 계약에 additive 로 얹을 수 있는지 판정하고 근거를 쓴다.
- 완료 기준: 자동운영을 최종 목표로 둘지는 ND-22 사용자 결정으로 분리한다.
- 완료 기준: 구현·계약 변경은 하지 않는다.
- 근거: 171e3e4:docs/decisions/A-DEC-002:24 포괄 승인 확대 금지
- 근거: CG-04: work-list 에 Q34 설계 항목 0건
- 사용자 결정: ND-22

#### NZ-DATA-01 — 실데이터 읽기 전용 스파이크 준비 메모(수집 없음)
- 우선 P2 · new_build · gate `docs_only` · 크기 S · 담당 qh_researcher · 계약 영향 none
- 내용: 시세 수집·계정·키 없이 약관 원문 열람 결과만 문서화한다. 공급원별 저장·재배포·LLM 입력·계정 필요 여부(확인일), 기술 선행조건(environment synthetic 단일값, envelope 128건, pyarrow lock), manifest 필드, 스파이크 완료 기준과 중단 조건을 적는다. 시세 데이터는 받지 않으며 실행 여부는 ND-17 이 정한다.
- 큐 위치: Δ2, ND-17 질의 근거 자료
- 기존 ID: NX-DATA-02, NX-RESEARCH-02, ND-08, SG-02
- 출처: PDF 권고2, PDF N-2, R2-29, R2-13, R3 NX-DATA-03 제안, G1 insights, 약관 검증 2026-11-15
- 완료 기준: 공급원별 약관 원문·확인일·저장/재배포/LLM 입력/계정 분류와 UNVERIFIABLE 항목을 표로 남긴다.
- 완료 기준: 환경 enum 확장, 별도 연구 모듈, 저장소 밖 하네스 선택지를 영향과 함께 비교한다.
- 완료 기준: 완료 기준은 수집 재현성·정합성·약관 태그 작동이며 정책 값 도출은 목표가 아니다.
- 완료 기준: 원본 바이트 보관, 조정값 파생 뷰 분리, 시도 기록 동일 슬라이스 포함을 요구한다.
- 근거: 약관 확인 2026-11-15: ECB 조건부 허용, Fed H.10 공개 도메인(DDP 2027 종료 예정), FSC 15094808 제4유형, Alpha Vantage·Tiingo·EODHD 개인 한정, ECOS·Stooq·Massive UNVERIFIABLE
- 근거: 171e3e4:src/quantharbor/domain/market_data.py:44-48,493,834
- 근거: G1: FX 는 available_at 기준 ASOF 결합과 provider 고정(providers=ecb) 필요
- 사용자 결정: ND-17 이 실행 여부를 정한다

#### NZ-DATA-02 — 운영 루프 가격 소스 결정표
- 우선 P2 · new_build · gate `docs_only` · 크기 S · 담당 qh_architect · 계약 영향 none
- 내용: 장중 15분 분석(AP-04, operations-v1)이 쓸 가격·환율 소스와 신선도 정의가 계획에 없다. 일봉 공급원은 지연된다(FSC 주식시세정보는 영업일 하루 뒤 오후 1시 이후 갱신). 후보(증권사 시세 조회, 지연 일봉, 사용자 수동 입력)별 권리·신선도 한도·불가 시 BLOCKED 동작·AP-05 범위 확장 필요를 표로 정리한다.
- 큐 위치: Δ2, NX-POLICY-09(15분 slot 설계) 이전
- 기존 ID: NX-DATA-01, NX-BROKER-01, NX-POLICY-09, PG-01, AP-05
- 출처: CG-02, 171e3e4:docs/approval-register.md:13-14, 171e3e4:docs/contracts/operations-v1.md:52, G1 FSC 갱신 주기
- 완료 기준: 후보별 권리(LLM·보고 사용)와 신선도 한도, 소스 불가 시 BLOCKED 동작을 표로 쓴다.
- 완료 기준: AP-05 범위 확장이 필요한 후보를 표시하고 직접 확장하지 않는다.
- 완료 기준: 15분 요구 유지 여부는 ND-20 사용자 결정으로 분리한다.
- 완료 기준: 스파이크 질문 목록에 운영 가격 소스 항목을 추가한다.
- 근거: 171e3e4:src/quantharbor/application/target.py:373-375 가격·FX 나이 검사
- 근거: CG-02: work-list 안 실시간·분봉 소스 NX 0건(git grep)
- 사용자 결정: ND-20

#### NZ-DATA-03 — 읽기 전용 연구용 실데이터 스파이크(승인 전 차단)
- 우선 P3 · blocked · gate `public_data` · 크기 L · 담당 qh_implementer · 계약 영향 unknown
- 내용: KR·US 소수 종목 1~2년 일봉과 환율을 연구 전용으로 받아 수집 재현성·정합성·약관 태그를 검증한다. 현재 NOT_APPROVED: 승인 레지스터에 범위가 없고 SG-02 미충족이며 계약은 synthetic 단일값이다. ND-17 이 (b)로 답하고 전제가 충족되기 전에는 시작하지 않는다.
- 큐 위치: Δ6 트리거 대기. AGENTS.md 4단계 앞당김이라 REORDER(ND-17) 응답 전에는 시작 불가
- 기존 ID: NX-DATA-02, NX-RESEARCH-02, ND-08
- 출처: PDF 권고2, PDF N-2, R2-29, R3 approval_state, 약관 검증 2026-11-15
- 완료 기준: 공급원별 SG-02 결정 기록과 계정·키 승인(AP-03·AP-05 범위 확장)이 먼저 있다.
- 완료 기준: 시도 원장 기록과 약관 태그(llm_input 금지)를 같은 슬라이스에 넣는다.
- 완료 기준: 수집 직후 스키마·범위·달력 검증 보고서 해시를 manifest 에 넣는다.
- 완료 기준: 결과 해석은 구조·재현성 검증으로 한정하고 정책 값 확정에 쓰지 않는다.
- 근거: R3 approval_state: 공개 시세 수집 NOT_APPROVED(approval-register 에 범위 없음)
- 근거: G1: ECB 공개 CSV 이상 행 사례(2010-02-12 이후 없음, 일요일 행)로 수집 직후 검증 필요성 확인
- 사용자 결정: ND-17(순서 변경), 계정·키 발급은 사용자 별도 승인

#### NZ-PORTFOLIO-01 — PortfolioConstructor 사양·불변식·변이 코퍼스(설계 문서, 코드 전)
- 우선 P1 · new_build · gate `docs_only` · 크기 M · 담당 qh_architect · 계약 영향 none
- 내용: build_target 앞단 순수 함수의 입출력, 7단계 파이프라인, 사후 불변식 I1~I12, 변이 코퍼스 M1~M6 을 문서로 고정한다. ND-05 위임(설계 한정) 범위다. 출력 기준은 quantity, 사전 검사는 builder 거울, 같은 단계 매도대금 재사용 금지, 조용한 재정규화 금지다. 정책 값과 코드는 포함하지 않는다.
- 큐 위치: Δ2, NX-PORTFOLIO-01 코드 착수(ND-18) 이전
- 기존 ID: NX-PORTFOLIO-01, NX-POLICY-05, NX-POLICY-06, NX-PORTFOLIO-04
- 출처: PDF 권고3, v3 QH-PORT-02, v3 QH-PORT-03, R1-15, R3 seam PortfolioConstructor, G2 insights
- 완료 기준: 입력·출력 타입, Rejection 사유 코드, stage2_deferred 의미를 값 없이 정의한다.
- 완료 기준: builder 사전검사 목록과 'constructor 수락이면 builder 비차단' 차등 시험 사양을 쓴다.
- 완료 기준: 미결정 4건(보고서 해시 결속, floor 양자화 helper, mode/omission, band_unfixable)을 설계 결정으로 분리한다.
- 완료 기준: 자체 실험 수치는 합성 분포 가정이며 독립 검증이 아님을 표기한다.
- 근거: 171e3e4:src/quantharbor/domain/valuation.py:33-42 quantize 는 half-even 이라 별도 floor helper 필요
- 근거: 171e3e4:src/quantharbor/application/target.py:505-535,754 builder 사전검사 기준
- 근거: G2 자체 실험(저장소 외 스크립트, 합성 분포): 내림만 한 경우 잔차 1% 초과 368/500 — 위험 크기 참고용

#### NZ-TAX-COST-01 — 경제성·패시브 귀무 기준·프로젝트 중단 기준 점검표
- 우선 P2 · new_build · gate `docs_only` · 크기 S · 담당 qh_researcher · 계약 영향 none
- 내용: 운영 고정비(LLM·데이터, 수수료·거래세·해외 양도세)를 감당하는 최소 자본, 지수 ETF 보유 대비 순성과 귀무 기준, 무거래·패시브 정상 결론 경로, 프로젝트 중단·축소 기준이 어느 문서에도 없다. 구조만 표로 만들고 값은 사용자 입력과 전문가 확인 뒤에 채운다.
- 큐 위치: Δ5, RETURN-02 진입 점검표(NZ-DOCS-PROCESS-02)의 한 절
- 기존 ID: NX-LEARN-06, NX-TAX-COST-02, ND-10
- 출처: CG-05, 171e3e4:docs/plan.md:128, 171e3e4:docs/research/v2-followup-research-2026-11-14.md:19
- 완료 기준: 자본 규모별 고정비 대비 손익분기 초과수익 표의 구조만 만들고 값은 비워 둔다.
- 완료 기준: 패시브 대안 대비 순성과 귀무 기준과 무거래 정상 결론 경로를 정의한다.
- 완료 기준: 프로젝트 중단·축소 기준 항목을 사용자 입력란으로 둔다.
- 완료 기준: 세율·세무 판단은 전문가 확인 전 확정하지 않는다.
- 근거: CG-05: 손익분기·최소 자본 검색 HEAD 0건
- 사용자 결정: ND-23

#### NZ-TEST-STRATEGY-01 — 변경 단위 시험 계층·계약 에포크·부분 실행 증거 표기 설계
- 우선 P2 · new_build · gate `docs_only` · 크기 M · 담당 qh_architect · 계약 영향 none
- 내용: 3.8시간은 8a27220 고정 두 실행의 합(13,733.5초)이고 현재 tests/product 는 898개(정적 계수)다. 계약 호환 등급 선언(additive/breaking), T0~T4 계층, 계약 개정을 한 에포크로 묶는 규칙, 부분 실행을 PARTIAL + 시험 ID 목록 해시 + 입력 manifest SHA 로만 기록하는 증거 표기를 설계한다. 실행은 하지 않는다.
- 큐 위치: Δ2, target-local-v2 개정 창(Δ3)의 시간 예산 입력
- 기존 ID: NX-OPS-INFRA-01, NX-OPS-INFRA-02, ND-13
- 출처: PDF N-3, R2-14, G3 insights, 약관·사실 검증 시험 시간 항목
- 완료 기준: 호환 등급(additive/breaking)과 소비자 목록을 qh-contract-change 항목 초안으로 쓴다.
- 완료 기준: T0~T4 계층별 입력(비Python 입력 지도 포함)과 지도 밖 변경의 상위 계층 승격 규칙을 정의한다.
- 완료 기준: 부분 실행을 전체 통과로 합산하지 않는 증거 형식을 정한다.
- 완료 기준: 모든 시간 수치는 가설로 표기하고 측정 전 목표로 쓰지 않는다.
- 근거: 171e3e4:docs/evidence/execution-final-current-product-2026-10-30.json elapsed 6800.646초, ...database... 6932.892초
- 근거: G3: DB 86개 시나리오 평균 80.6초·최대 189.4초(평탄), 4병렬 약 29분은 가설

#### NZ-TEST-STRATEGY-02 — 시험 시간 프로파일 1회와 병렬 안전성 점검(요청 시 실행)
- 우선 P2 · blocked · gate `synthetic_local` · 크기 M · 담당 qh_validator · 계약 영향 none
- 내용: 모든 시간 절감안의 첫 단계다. unittest --durations 로 개별 시험 시간 분포를 1회 측정하고 두 실행이 동시였는지 확인하며, /tmp/quantharbor-q25 고정 경로 같은 병렬 불안전 지점을 정적 점검한다. 시험 실행은 사용자 요청과 ND-13 시간 예산 승인 뒤에만 한다. 호스트 python3 는 3.14.6 이라 3.13 을 명시해야 한다.
- 큐 위치: Δ3 초입, NX-BASELINE-01 판정 이후이고 계약 개정 창 시작 전
- 기존 ID: NX-OPS-INFRA-01, NX-OPS-INFRA-02, ND-13
- 출처: PDF N-3, G3 insights, R2-14
- 완료 기준: 사용자 요청과 시간 예산 승인 기록이 없으면 실행하지 않는다.
- 완료 기준: Python 3.13 으로 실행하고 호스트 기본 3.14.6 사용 여부를 기록한다.
- 완료 기준: 시험별 시간 분포는 저장소 밖 결과로 남기고 신규 스크립트는 별도 요청한다.
- 완료 기준: 공유 경로·setUpClass 점검은 정적 판독이며 실행 확인과 구분한다.
- 근거: G3: test_investment_ai_evaluation.py:22 고정 OUT 경로, test_investment_ai_review.py:151 setUpClass 직접 호출(정적)
- 근거: AGENTS.md: 시험 추가·실행은 사용자 요청 시
- 사용자 결정: ND-13(신규 부분)

#### NZ-TEST-STRATEGY-03 — 속성 시험·가드 변이 시험 ADR(의존성 최소)
- 우선 P3 · new_build · gate `docs_only` · 크기 S · 담당 qh_architect · 계약 영향 none
- 내용: 무작위·속성 기반 시험은 0건(정적 grep)이다. Hypothesis 를 dev 전용 해시 고정 휠로 쓸지(MPL-2.0, 네이티브 cp313 aarch64 휠, sortedcontainers), 외부 변이 도구 대신 ast 가드 변이 하니스를 쓸지 ADR 로 비교한다. 구현은 소비자(NX-PORTFOLIO-01 불변식, P29-02)가 생길 때 연다.
- 큐 위치: Δ5, 소비자 트리거 대기
- 기존 ID: NX-OPS-INFRA-02, ND-12
- 출처: G3 insights, R3 NX-OPS-INFRA-02 쪼개기, PDF N-3
- 완료 기준: 새 의존성은 SG-03 ADR 전에는 도입하지 않는다는 전제를 명시한다.
- 완료 기준: dev 컨테이너 격리와 해시 고정 휠 설치 선례(pyarrow)를 따르는 방식을 비교한다.
- 완료 기준: 변이 도구 채택 대신 가드 변이 하니스의 대상 가드 후보 10~20개를 목록화한다.
- 완료 기준: 도입 시점에 라이선스 본문·릴리스·휠 형태를 재확인하는 절차를 넣는다.
- 근거: G3: .hypothesis/·mutants/ 가 .gitignore 에 없고 check_quality 는 알 수 없는 확장자 거부
- 근거: G3: mutmut 은 pytest·fork 필요, cosmic-ray 는 디스크 원본 직접 변이(입력 불변 규칙과 충돌)

#### NZ-OPS-INFRA-01 — v2/ 와 공개 후보 게이트 정합 결정
- 우선 P2 · new_build · gate `docs_only` · 크기 S · 담당 qh_architect · 계약 영향 none
- 내용: classify() 단독 호출에서 v3 MD 는 unclassified_candidate, 한글 이름 PDF 는 unsafe_path 로 거부됐다. 전체 게이트는 실행하지 않아 fail 은 추정이다. 처리안(공개 루트+ASCII 파일명, 입력 보관소 제외 규칙, 현상 유지)과 CI 활성화 때 함께 바꿀 항목을 정리한다. 사용자 파일명은 바꾸지 않는다.
- 큐 위치: Δ5, NX-OPS-INFRA-01(CI) 설계와 함께
- 기존 ID: NX-OPS-INFRA-01, NX-DOCS-PROCESS-01, AP-06
- 출처: CG-06, R4 check_quality classify 호출 결과, 171e3e4:scripts/check_quality.py:47,103-136
- 완료 기준: 전체 게이트 단독 실행은 사용자 승인 후로 두고 현재 판정은 추정으로 표기한다.
- 완료 기준: 세 안이 check_quality 수정·Q27 고정 입력·파일명 변경에 주는 영향을 비교한다.
- 완료 기준: CI 활성화 때 protected_path 규칙과 ci-definition 문서를 함께 개정해야 함을 명시한다.
- 완료 기준: check_quality.py 수정은 Q27 판정 이후로 미룬다.
- 근거: R4: classify() 호출만 실행, 전체 inspect_repository 미실행
- 근거: 171e3e4:scripts/check_quality.py:124 .github/workflows protected_path
- 사용자 결정: ND-24

#### NZ-OPS-INFRA-02 — 의존성·OSS 후보 판정표(SG-03 입력, 도입 없음)
- 우선 P3 · new_build · gate `docs_only` · 크기 S · 담당 qh_researcher · 계약 영향 none
- 내용: 이번 조사의 OSS 판정을 SG-03 입력표 한 장으로 정리한다. 연구·dev 한정 채택 후보는 exchange_calendars, DuckDB(읽기 전용), Hypothesis 이고 pyarrow 는 기존 고정을 유지한다. GPL(cvxportfolio, py-vallocation), BSL(ArcticDB), 소유 이동(OpenBB)은 회피한다. 스타 수는 쓰지 않는다.
- 큐 위치: Δ5, 소비자(데이터 어댑터·ADR) 착수 직전
- 기존 ID: NX-DATA-02, NX-RESEARCH-02, NX-PORTFOLIO-04, NX-OPS-INFRA-02, ND-12
- 출처: G1 repos, G2 repos, G3 repos, BASE-DEC-001 SG-03 재적용 원칙
- 완료 기준: 후보마다 라이선스 본문 우선 판정·확인일·Python 3.13 신호·adopt/borrow/benchmark/avoid 를 적는다.
- 완료 기준: dependencies=[] 유지와 오프라인 해시 고정 휠 선례를 전제로 쓴다.
- 완료 기준: 실제 도입은 SG-03 ADR 전에 하지 않는다.
- 완료 기준: ArcticDB 라이선스 불일치는 NEEDS_PROFESSIONAL_CHECK 로 남긴다.
- 근거: 171e3e4:pyproject.toml:6 dependencies = []
- 근거: G1: ArcticDB README 와 LICENSE.txt 의 production 정의 불일치
- 근거: G1: OpenBB 는 소유 조직 이동 경위 미확인

#### NZ-DOCS-PROCESS-01 — status.md 이력 보관·증거 동결·새 문서 상한 규칙(이력 보존형)
- 우선 P2 · new_build · gate `docs_only` · 크기 M · 담당 orchestrator · 계약 영향 none
- 내용: 필독 4문서 188,046B 중 status.md 가 79.3% 이고 69.3% 가 10-27 이전 과거 로그다. 삭제·이동 대신 현재 표 추가, 과거 로그를 보관 파일로 복사 또는 git mv(경로 docs/status.md 유지), 증거 JSON 300개·연구 원자료 동결과 색인, 새 독립 문서 상한을 정한다. 하드코딩 경로와 해시 고정 문서 7개는 건드리지 않는다.
- 큐 위치: Δ2, PR #7 처리 뒤 한 PR 로 정리
- 기존 ID: NX-DOCS-PROCESS-01, NX-DOCS-PROCESS-03
- 출처: R4 consolidation_plan 1~8, PDF N-1, PDF 권고6, G3 문서 거버넌스
- 완료 기준: 보관 방식 (a) git mv+얇은 새 status, (b) 복사+포인터 중 사용자 선택을 기록한다.
- 완료 기준: 기존 문서·증거 JSON 은 삭제·이동하지 않고 '당시 기록' 머리말과 SHA 로 동결한다.
- 완료 기준: 새 독립 문서는 상한과 '절 추가 우선' 규칙으로 제한한다.
- 완료 기준: PR #7 처리 뒤 status.md·큐 JSON 충돌을 확인하고 정리는 한 PR 로 묶는다.
- 근거: R4: status.md 경로는 development-policy.toml:31·.codex/agents·SKILL.md·qh_hook_audit.py 에 하드코딩
- 근거: R4: baseline-v1.json 이 문서 7개 해시 고정, status.md:줄번호 인용 45회는 SHA 한정
- 근거: R4: 증거 JSON 300개 중 242개가 다른 문서에서 참조
- 사용자 결정: ND-26

#### NZ-DOCS-PROCESS-02 — RETURN-02 진입 준비도·트리거 대기 표(새 문서 없음)
- 우선 P2 · new_build · gate `docs_only` · 크기 S · 담당 orchestrator · 계약 영향 none
- 내용: '실제 연결 전 재평가'로 미룬 항목(CRIT-16/17, 지원 호스트, psql ADR)과 이번 델타의 트리거 대기 NX(AUTH-03/04/05/06/08, LEARN-03/04/06, RESEARCH-02, DATA-02)를 항목·트리거·소유자·상태 표 한 개로 모은다. PG-01·SG-02·AP-05 범위·ND-09·독립 검토·공개 상태·가격 소스·경제성을 포함한다. status 현재 표나 PRODUCT 카드 안에 둔다.
- 큐 위치: Δ5, RETURN-02 진입 전 관문
- 기존 ID: RETURN-02, PG-01, SG-02, NX-DOCS-PROCESS-02
- 출처: CG-08, R3 트리거 대기 분류, 171e3e4:docs/v2-work-list-2026-11-14.md:814
- 완료 기준: 각 항목에 트리거·소유자·상태(충족/미충족/UNVERIFIABLE)를 적는다.
- 완료 기준: 트리거 대기로 내린 학습·진위 항목이 소비자 조건과 함께 남아 있어야 한다.
- 완료 기준: 새 독립 문서는 만들지 않고 status 현재 표나 PRODUCT 카드의 한 표로 둔다.
- 완료 기준: 표가 비어 있는 동안 실제 조회·모의 연결·실데이터 수집을 시작하지 않는다.
- 근거: CG-08: RETURN-02 선행조건이 '기존 승인과 PG/SG 확인'뿐
- 근거: 171e3e4:docs/product-delivery-plan.md:30

## 4. 기존 NX·ND 변경 (45건)

| 대상 | 변경 | 내용 | 이유 |
|---|---|---|---|
| NX-BASELINE-01 | keep | P0 임계 경로 유지. FUP-Q27-006(diagnosing)·009~014(queued) 마감과 고정 입력 실제 DB 판정은 기존 사용자 지시 범위(EXEC-DEC-002:16, EXEC-DEC-003)라 재요청하지 않는다. DoD 에 '836/86 PASS 는 8a27220 고정 root 자기보고, 독립 검증 아님, runner 저장소 부재' 를 명시한다. 최종 SHA 재검증 필요 여부는 사용자 결정. | [PDF 권고1, N-3] R1-04, R2-09. Q27 은 POLICY-04·TAX-COST-01 계약 개정과 SAFETY-01 시험 편입의 기술 선행이다(R3). |
| NX-BASELINE-02 | modify | PR #7 수용 판정을 gh 조회 head SHA(4c24015, 조회 시점 값)로 고정하고 독립 일반·보안 검토 뒤에만 병합을 판단한다(AP-06). 쌓인 PR base 확인 항목과 status.md 'PR #7 대기' 한 줄을 추가한다. R3 의 'W2 관문 분리·P2 강등'은 보류하고 선행 열 재파싱 확인 뒤 결정한다. P1 유지. | [PDF 권고1, N-4] R2-15 확인. R2-27 은 verification=refuted 라 근거로 쓰지 않고, 같은 취지의 R3 주장도 별도 재확인 전에는 제안으로만 취급한다. |
| NX-DOCS-PROCESS-01 | modify | 범위 확장·P1 권고. README 현재 단계 한 문단, status 상단 현재 표(큐 포인터는 offline Q27·product P28-03·후속 큐 함께, 큐 상태 번역 pending/artifact_ready_pending_acceptance, 미실행 목록), ND 16→17·REORDER 3→4 정정, 입력 인용 SHA 주석(이전 v2 MD·첫 PDF 는 04812f4/5ff8e29 보존, 171e3e4 삭제), v3 QH-*→NX 대응표 1회, 31행 재판정표 정본, 집계 단위 병기, product-read-v1.md:3 머리글 정정(artifact 해시 고정 여부 확인 후). v2/ 입력 원본은 수정하지 않고 정정 박스에 쓴다. | [v3 QH-MAIN-01 신규 ID 없이 흡수, v3 implementation-status.md 신설은 현재 표로 대체, PDF 권고6, N-1, N-9] R1-12, R1-22, R1-30, R2-04, R2-20, R2-23, R4. 우선순위 P0/P2 논쟁은 ND-26. |
| NX-DOCS-PROCESS-03 | merge | NX-DOCS-PROCESS-01 과 한 정리 PR 로 합친다. 마크다운 15개(검증 기록의 자리표시자 6회 제외)만 상대 링크로 치환하고 증거 JSON 3개 13회는 해시·불변 보존 확인 전 제외한다. 'PDF 121회·16개·감소'는 인용하지 않는다. '저장소 공개 전' 서술은 이미 PUBLIC 이므로 NZ-SECURITY-01 로 정정한다. 원격 push·PR 은 AP-06. | [PDF 권고6] R2-25, R4 절대경로 지표, CG-01. 실제 값은 80403ab·5ff8e29·171e3e4 모두 18파일 128회. |
| NX-DOCS-PROCESS-02 | demote | P3 으로 낮춘다. 스크립트 신규 작성과 completion_kind 필드 추가는 사용자 요청 시로 미루고, 큐 간 정합은 정리 PR 에서 수동 표 1회로 갈음한다. R4 의 check_docs.py 신규 제안도 같은 이유로 보류한다. | EXEC-DEC-001/002 가 이중 범위를 의도된 설계로 보고 AGENTS.md 가 시험·스크립트 추가를 요청 시로 한정한다(R3 delta, R4 step 9). |
| NX-POLICY-02/NX-POLICY-03 | accelerate | 별도 additive PortfolioPolicy 타입과 완전성·모순 검증기로 Q27 판정 전에 착수한다(ND-18 채택 뒤). SyntheticTargetPolicy 필드 추가는 canonical 해시를 바꾸는 breaking 이라 금지한다. 선행 열의 NX-BASELINE-01 은 착수 의존에서 빼고 통합·완료 의존으로만 두며 start/completion 열을 분리한다. 정책 값은 넣지 않는다. | R3 seam: 별도 타입이면 Q27 과 기술 독립, EXEC-DEC-003:16 start_dependencies 규약, policy-gates.md:19 구조/값 구분. |
| NX-POLICY-03/NX-POLICY-04/NX-POLICY-06 | modify | 다중 실패 수집을 target-local-v2 breaking 묶음에서 분리해 저장소에 쓰지 않는 읽기 전용 진단 함수(diagnose_target)로 만든다. 03 검증기와 06 드라이런의 구현 수단으로 쓴다. 04 의 범위는 reduce-only 결정론 정의와 목표·실행 4곳 동일 규칙으로 좁힌다. | [PDF 권고4 부분 정정] R3: failures 는 이미 sequence 이고 첫 실패 중단은 builder 동작일 뿐이다(정적). 해시·골든을 건드리지 않는다. |
| NX-POLICY-04/NX-TAX-COST-01/NX-PORTFOLIO-02 | merge | 세 항목을 target-local-v2 단일 개정 설계(결정 기록 1건, 영향 조사 1건)로 합친다. 구조는 reduce-only 정의, 비율형 비용 구조(요율 값 제외), 이월 baseline 용량(MAX_INPUTS 128 대 원장 4096). 설계는 지금 시작하고 구현·전체 회귀는 Q27 판정 직후 P28-04 이전에 1회, qh-contract-change 독립 검토와 Q23 24실행 골든 불변 확인 방법을 기록한다. | [PDF 권고4] R3: OrderTerms·원장 입력 한도의 canonical 해시가 바뀌고 product_artifacts 가 target v1 타입에 묶여 있어 개정이 늦을수록 비용이 커진다. NX-TAX-COST-01 은 이미 같은 schema_version 묶음을 계획했다(R2-30). |
| NX-POLICY-05/NX-POLICY-06 | modify | 05 에 정의 고정 표를 추가한다(밴드 절대/상대, 현금 포함 여부, 회전율 편도 대 총합과 윈도, 쿨다운은 명시 입력, 1 lot 비중보다 작은 폭은 band_unfixable). 값은 넣지 않는다. 06 드라이런에 정책 후보×보유 상태별 차단율과 max_rounding_error 상시 차단 위험을 포함한다. | G2 insights, R2-10(허용 폭 '모순'은 '종목 단위 절대 폭 무력화+단위 미정'으로 표현), NZ-PORTFOLIO-01. G2 수치는 합성 분포 가정이라 근거로만 쓴다. |
| NX-POLICY-07 | modify | 2단계 리밸런싱을 stage2_deferred 와 predecessor_plan_ref 기반 재호출로 설계한다(미래 매도대금으로 매수 여력을 만들지 않는 규칙 유지). 계약 영향은 additive 로 유지하고 PDF 의 '계약 변경 없이'는 정정한다. | R2-06, G2 insights(읽은 구현은 모두 같은 단계 자금 재사용을 가정). |
| NX-POLICY-08 | modify | 선행 목록에 NX-AUTHENTICITY-02(시도 원장)를 추가한다. 정책 변형 비교 한 번마다 시도 이벤트를 남긴다. 값 선택의 근거 등급을 명문화한다(합성=구조 검증만, 값은 SG-02 이후 실데이터 비교). 합성 결과는 정책 채택 근거가 아니다. | [PDF N-2] R3(선행 열에 간선 누락), R2-13(작업 목록에 이미 있는 긴장의 재진술). |
| NX-POLICY-10 | modify | 유니버스·중복 노출 분석의 구현 후속(실데이터 필요)을 덧붙인다. 현재 범위는 문서(ETF 허용 방식·필터 필드·중복 노출 한도 키)로 유지하고 분석 구현은 SG-02 트리거 대기로 둔다. | [v3 QH-PORT-01] R1-23: NX-POLICY-10 은 정책 문서만 다뤄 부분 대응이다. |
| NX-PORTFOLIO-01 | accelerate | Q27 판정 전 착수(ND-18 채택 뒤, 새 파일만, application/target.py·domain/target.py 수정 금지). 사양은 NZ-PORTFOLIO-01. 출력 기준은 quantity, 사전 검증은 SyntheticTargetRepository 같은 인메모리 저장소로 build_target 드라이런(클래스 존재만 확인, 동작 미확인). DoD 에 불변식 I1~I12 중 핵심과 '수락이면 builder 비차단' 차등 시험을 추가한다. 활성 worker·작성자 한 명 규칙 안에서 시간 분할한다. | [PDF 권고3, v3 QH-PORT-03] R3 seam: build_target 앞단의 새 모듈이라 Q27 과 기술 독립(execution 이 target 을 import 하는 하류 구조). ND-05 위임은 설계 한정이라 코드 착수는 ND-18 필요. |
| NX-PORTFOLIO-03 | modify | 정정 이벤트 추가 경로를 application/target.py 수정이 아닌 새 모듈(replay 기반)로 만든다. 기존 파일 수정이 필요하면 Q27 이후로 둔다. Q24 재현 골든은 보존한다. | R3: application/target.py 는 execution 이 import 하는 공유 모듈이라 수정하면 Q27 최종 입력이 변한다(조건부 의존). |
| NX-PORTFOLIO-04 | modify | 최적화 알고리즘 비교 후속을 ADR 범위에 덧붙인다(ND-07 위치 유지). float 최적화 결과는 Fraction 변환·양자화 경계 계약으로만 받고, cvxportfolio·py-vallocation(GPL)은 코드 복사·링크 없이 개념 참고만 한다. 의존성 도입은 SG-03 전 금지. | [v3 QH-PORT-02] R1-23, G2 repos(GPL 2건 benchmark_only, 나머지는 float·무거운 필수 의존). |
| NX-AUTHENTICITY-01/NX-LEARN-01 | keep | 지금 문서로 쓴다. AUTH-01 은 증거 등급 매트릭스, 학습 입력 방화벽, 자동 배포 금지 목록을 담고 LEARN-04 금지 목록·AUTH-04 label·replay 설계·LEARN-06 사전 등록 원칙을 절로 흡수한다. LEARN-01 은 표본 산식과 가정을 재현 가능하게 적고 합성 12시점은 통계 입력 불가로 명시한다. 합성 stub 예측은 학습·성과 증거로 승격하지 않는다. | 사용자 요구 '지속 학습·진위 판별' 유지: 소비자 없이 의미 없는 구현은 미루되 원칙·산식·금지 목록은 지금 고정한다. R3. |
| NX-AUTHENTICITY-02 | accelerate | Trial Ledger 를 ExperimentRegistry 확장이 아닌 병행 신규 타입으로 설계·구현한다(ND-18 채택 뒤). 이벤트에 spec hash·변형·구간·결과 hash·폐기 여부를 담고 평가셋 조회·홀드아웃 열람도 시도로 기록한다. 저장은 ai_state 와 분리하고 삭제 API 를 두지 않으며 통계 임계값은 넣지 않는다. 기록되지 않은 시도는 잡지 못한다는 한계, 마이그레이션 번호 충돌과 PR #7 영향을 착수 전에 확인한다. | [PDF 권고5, N-7] 평가: 시도 원장 선행은 채택(의존은 Q27 이 아니라 저장 위치). '나머지 지연'은 소비자 트리거로 부분 채택. R2-18, R2-29(스파이크가 먼저면 시도 기록도 같은 슬라이스), R3. |
| NX-LEARN-02 | merge | 학습 원장 저장 모델 결정을 NX-AUTHENTICITY-02 설계 절에 병합한다. 별도 문서·큐 항목을 만들지 않는다. 인용은 'SQL 128건·checkpoint 32MiB, Python byte_capacity 8MiB'로 정정한다. | [PDF N-8] R2-19, R3: 저장 모델 결정의 소비자가 Trial Ledger 하나뿐이고, 병합하면 NX-BASELINE-02 가 W2 를 막는 간선이 사라진다. |
| NX-AUTHENTICITY-03 | demote | W2·W3 에서 빼고 NX-RESEARCH-02 직전 트리거 대기로 옮긴다. 트리거는 SG-02 결정 기록과 다년 실데이터 존재다. DSR 입력은 시도 원장 출력이므로 AUTH-02 가 먼저다. | 소비처 없이 구현하면 논문 예제 검증만 남고 합성 12시점·fit=none 입력은 설계상 거부 대상이다(R3, G3 insights). |
| NX-AUTHENTICITY-04 | demote | provenance_class·learning_eligible 구현은 NX-DATA-02 실데이터가 생길 때까지 트리거 대기. 합성 결과는 v1 artifact 의 environment='synthetic' 으로 이미 구분된다. label·replay 설계 문서는 AUTH-01 절로 흡수한다. | R3 demote 근거. 트리거는 NZ-DOCS-PROCESS-02 표에 남겨 소실을 막는다. |
| NX-LEARN-03 | demote | Forecast·Outcome·ScoreCard 결정론 채점은 실제 LLM client 또는 모의 예측이 생길 때까지 트리거 대기. LLM 이 supported/refuted 를 판정하지 않는 결정론 설계 원칙은 AUTH-01 에 기록한다. | [v3 QH-LEARN-01, PDF N-7] R1-26: 가설 사후 평가는 LEARN-03/04 가 더 상세히 포함. R2-18: Hypothesis.assessment 를 바꾸는 코드는 src 에 없음(정적). |
| NX-LEARN-04 | merge | 학습 루프 9단계·VersionRegistry 문서의 자동 배포 금지 목록(전략·정책·위험 한도·주문 경로·평가셋·ROLE_QUERIES·Skill)을 NX-AUTHENTICITY-01 결정 기록 절로 흡수한다. 나머지는 트리거 대기. | [v3 QH-LEARN-01] R3. 학습 기능을 약화하지 않고 문서 수만 줄인다. |
| NX-LEARN-06 | merge | 모의 합격 기준·AI 기여 중단은 PG-04 준비에 흡수한다. 경제성·패시브 귀무·중단 기준은 NZ-TAX-COST-01 로 분리한다(RETURN-02 전에 필요하고 Q30 관찰 뒤로 미룰 수 없다). | R3 demote 와 CG-05 충돌 해소: 성과 기준 포함 여부는 사용자 결정(ND-10/ND-23). |
| NX-AUTHENTICITY-05/NX-AUTHENTICITY-06/NX-AUTHENTICITY-08 | merge | SG-04 와 NX-AI-RUNTIME-01 시점에 하나의 '실모델 준비' 문서 절로 묶는다. 합성 stub 의 탐지율은 증거로 승격하지 않는다. | R3: 실모델 소비자가 없으면 canary·보정·감쇠 임계의 검증 기준이 없다. |
| NX-AI-RUNTIME-01/NX-AI-RUNTIME-03/NX-SKILLS-01 | merge | 실모델 준비 문서 한 개로 합쳐 SG-04 직전에 둔다. 입력은 ClientIdentity(evaluation_kind=synthetic·model_id 없음)·합성 상한(호출 4회, 마감 60초)이다. 실제 LLM adapter·Tool Gateway 구현은 SG-04/AP-03 전 금지. 개발 AI/투자 AI 분리 서술에 '정책 수준 분리일 뿐 기술 격리 미검증'을 덧붙인다. | [v3 QH-AI-01, PDF N-6] R1-17, R1-25, R2-17. |
| NX-OBS-UI-01 | merge | P28-01 수용 검토에 흡수한다. 영속 상태 enum 교체 없이 폴링 투영으로 시작하고, run/task/role/version 이벤트 저장(v3 QH-AI-02)은 계약 개정 결정 뒤로 미룬다. | [v3 QH-AI-02] R1-25: 이벤트 저장은 기존 계약이 금지. |
| NX-RESEARCH-02 | keep | blocked 유지(SG-02 데이터 권리 대기). configured_n/executed_n/valid_n/failed_n 분리 기록 유지. v3 QH-RES-01/02 가 이미 포함되고 대량 탐색 엔진(QH-RES-03)은 AUTH-02/03 완료 뒤 후속 후보로만 기록한다. | [v3 QH-RES-01, QH-RES-02] R1-24. 앞당김은 ND-08 이 아니라 ND-17 로 올린다. |
| NX-DATA-01 | modify | 재조사 없이 v2-followup-research §2(시간·틱·제한폭·휴장·T+N·수능일)를 레지스터 표로 옮긴다. 출처·확인일·확신도·'확인 못 함'을 유지하고 ETF 틱·공식 휴장 목록은 UNVERIFIABLE. 값은 코드가 아니라 외부 데이터 항목이라는 원칙을 첫 줄에 쓴다. | R3: 내용 대부분이 이미 조사돼 있어 재조사는 문서만 늘린다. |
| NX-DATA-02 | keep | blocked 유지(SG-02 전 금지). 후보 판정 입력: exchange_calendars adopt_dependency(SG-03 ADR 후, XKRX 2026·2027 휴장 포함이나 사람이 유지하는 목록), pyarrow 기존 고정 유지, DuckDB 연구 환경 읽기 전용, pandera 패턴 차용. Yahoo·KRX 자동 수집과 FRED 캐시·LLM 입력은 약관상 제외. | G1 repos, 약관 검증 2026-11-15. 후보 상세는 NZ-OPS-INFRA-02. |
| NX-SECURITY-01/NX-SECURITY-02 | accelerate | Δ1 로 앞당긴다(선행 없음 문서). NZ-SECURITY-01 의 공개 상태 항목과 ND-09 확장(계좌 유형: 일반 위탁 대 세제 혜택 계좌, 계좌별 KIS API 지원은 UNVERIFIABLE)을 같은 문서에 담는다. 법률·세무 판단은 AI 가 확정하지 않는다. | [PDF N-10] R2-21, CG-10. |
| NX-TAX-COST-02 | modify | 기존 보유 도입 시 원가 입력 모델 절을 추가한다(lot 단위 대 평균, 출처, 누락 시 unknown 처리). 비교 모델은 제로 오프닝 포지션만 지원하고 평가 계약은 costing_spec_pending_q23 이다. 세무 원가법 선택은 전문가 확인 항목으로 둔다. blocked 유지. | CG-09: P28-04 초기 보유·원가 출처는 합성 범위에 한정. |
| NX-SAFETY-01 | modify | NX-BASELINE-01 마감 뒤 후속 시나리오 편입으로 두고 작성자는 check_execution.py 현 담당 한 명으로 한다. 시험 추가·실행은 사용자 요청 범위로 한정한다. | R3: 구현이 Q27 과 같은 산출물에 얹힌 기술 의존. AGENTS.md 시험 규칙. |
| NX-OPS-INFRA-01 | modify | CI 활성화는 AP-06 보류 유지. 설계에 사실 5개를 반영한다. job 상한 6시간 대 템플릿 15분 정책, 서비스 컨테이너 --network 미지원(compose 단계 유지), paths 필터 skip 은 필수 검사 Pending, check_quality protected_path 동시 개정, 저장소 공개 여부(NZ-SECURITY-01)에 따른 무료 조건. 문서 검사는 DB 불필요한 빠른 job 으로 분리한다. | G3 CI 사실(GitHub docs 원문 2026-11-15), R4, 약관·사실 검증. |
| NX-OPS-INFRA-02 | modify | 쪼갠다. 시나리오 시작 record 수를 계상하는 fixture 용량 예산 빌더(FUP-Q27-007/014 원인 128 record)는 유지하고, 차등·변이·상태기계 시험은 P3 으로 낮춰 P29-02 입력으로 미룬다. '3.8시간'은 두 실행의 합이며 동시 실행 정황이 있어 벽시계는 약 1.9시간일 수 있다고 표기한다(미확인). | [PDF N-3] R2-14, R3, NZ-TEST-STRATEGY-01/03. |
| NX-OPS-INFRA-03 | accelerate | 합성 수직 슬라이스 설계의 착수 의존에서 NX-BASELINE-01 을 뺀다. 설계 문서까지만 하며(ND-06 위임) 경계 불일치 목록(용량 128, 환경 고정, T+0 가정)을 산출물로 삼는다. | R3: 설계만 할 때는 Q27 과 무관하다. |
| NX-BROKER-01/NX-BROKER-02 | keep | ND-08b 거절 판단을 유지한다. KIS 모의 연결과 environment=paper 개방은 앞당기지 않는다(breaking: policy·facts·candidate 의 환경 고정 enum, approval·execution 개정). kis_read 는 비전송 decoder 이므로 'KIS 구현됨'으로 보고하지 않는다. | R1-19, R3, PDF 평가(비채택 타당). |
| NX-LEARN-05/NX-AUTHENTICITY-07/NX-TAX-COST-02/NX-DATA-02/NX-RESEARCH-02/NX-BROKER-02 | keep | W5 차단 상태를 유지한다. 열리는 조건은 SG-02·SG-04·PG 관문과 NZ-DOCS-PROCESS-02 표의 트리거다. | R3 delta keep, AGENTS.md 순서. |
| NX-POLICY-01/NX-POLICY-09/NX-POLICY-10/NX-DATA-01/NX-SECURITY-01/NX-SECURITY-02/NX-BROKER-01/NX-OBS-UI-01/NX-OPS-INFRA-01/NX-AI-RUNTIME-01/NX-AI-RUNTIME-03/NX-SKILLS-01 | merge | docs_only 25개를 독립 문서 8개 이하로 합친다. (1) 정책 구조(policy-gates.md 절+결정 기록 1건), (2) 법·전문가 확인 레지스터(+공개 상태), (3) 학습·진위, (4) 시장 규칙·데이터 레지스터(+NZ-DATA-01/02), (5) 정리 PR(+NZ-DOCS-PROCESS-01), (6) 시험 계층 설계, (7) 포트폴리오 구성기 사양, (8) 실행 전 점검표. 기존 문서에는 절로 추가하고 삭제하지 않는다. | [PDF N-1 문서 증식] R4 consolidation_plan, R3. PDF 의 '새 문서를 만들면 기존 하나를 줄인다'는 이력 보존과 충돌해 '새 독립 문서 상한' 규칙으로 대체한다. |
| W1~W5 | modify | 웨이브를 델타 Δ1~Δ6 으로 재편한다. Δ1 정정·결정·노출면, Δ2 Q27 임계 경로+설계·additive 병행, Δ3 Q27 직후 target-local-v2 단일 창, Δ4 P28~P29 합성 마감과 정책 비교, Δ5 RETURN-02 진입 점검, Δ6 트리거·승인 대기. 즉시 착수 범위는 ND-18 응답에 따른다. | R3 트랙 재편, R2-22(W1 14개 중 docs_only 11개). AGENTS.md 최상위 순서는 변경하지 않는다. |
| ND-05/ND-06/ND-07/ND-08b | retire | 사용자 질의 목록에서 뺀다. ND-05 채택(설계 한정), ND-06 채택(설계만), ND-07 위치 유지(ADR 선행), ND-08b 거절. 판단과 근거는 v2-followup-research §8 에 유지한다. work-list 정정 박스에 '위임 결정'으로 반영한다. | 재질의 금지 원칙. 위임 사용자 원문은 문서 기록 외 확인 불가(R4 unchecked). |
| ND-08 | modify | 선택지 'PDF 후보(pykrx·yfinance)를 연구 전용으로 먼저 사용'을 삭제하고 공급원별 약관·권리 확인(SG-02 결정 기록)을 선행 작업으로 분리한다. ND-17 승인 전까지 질의하지 않는다. | Yahoo 자동 수집·상업 이용 금지, KRX 자동화 수집·재배포 금지, FRED LLM·캐시 금지(follow-up §3, R3). '연구 전용'은 yfinance README 문구이지 약관이 아니다. |
| ND-01/ND-03/ND-11 | modify | 결정을 구조와 값으로 쪼갠다. ND-01 은 방식(사용자 지정 고정 비중+허용 폭, 종목 동일 비중 기준선, 기준통화 KRW)과 값(KR·US·현금 비중), ND-03 은 단위·결합 규칙(구획 절대 %p, 종목 상대 %)과 값(허용 폭·최소 거래금액·회전율), ND-11 은 보존 속성(append-only, 열람 승인자)과 통계 임계값. 값은 사용자·시뮬레이션 뒤. ND-03 설명은 '모순'이 아니라 '종목 단위 절대 폭 무력화+단위 미정'으로 고친다. | policy-gates.md:19, R2-10, R3. 구조 반쪽을 설계 위임으로 처리해도 되는지는 ND-27. |
| ND-04 | keep | P1 유지. 긴급 사유를 'paper 개방(NX-BROKER-02) 선행 조건'으로 표기한다(합성 단계라 운용 노출은 없다). 낙폭 단계 수·임계값은 값이라 질의에서 제외하고 PDF 의 -8/-12/-15% 는 미검증으로 둔다. | R2-30, policy-gates.md:14(손실 행동은 사용자 확정). |
| ND-09 | modify | 질의를 확장한다. 본인 계좌 단독 가정, 전문가 확인 시점, 사용할 계좌 유형(일반 위탁 대 세제 혜택 계좌). 계좌별 API 지원·상품 범위는 증권사 공식 문서와 전문가 확인 전까지 UNVERIFIABLE. | [PDF N-10] R2-21, CG-10. |
| ND-13 | modify | Q27 마감용 실행은 기존 지시로 이미 허가돼 재질의 대상이 아니다. 남은 질의는 신규 시험 추가 허가, target-local-v2 전체 회귀 시간 예산, CI 활성화(AP-06), 지원 호스트(macOS arm64) 범위다. 호스트 기본 python3(3.14.6)와 프로젝트 요구 3.13 불일치를 표기한다. | R3 approval_state, 약관·사실 검증(호스트 Python), R2-16(arm64 고정은 P28-07 흡수). |

## 5. 재편 웨이브 (Δ1~Δ6)

### Δ1 사실 정정·결정 수집·노출면 점검(문서, 순서 변경 없음)
stale 기록과 SHA 혼동을 정정하고 사용자 결정 묶음 A를 받으며 이미 공개된 저장소의 노출면 점검 범위를 확정한다.

- 작업: NX-DOCS-PROCESS-01, NX-DOCS-PROCESS-03, NZ-BASELINE-01, NZ-SECURITY-01, NZ-SECURITY-02, NX-SECURITY-01, NX-SECURITY-02, NX-POLICY-01, NX-DATA-01, NX-AUTHENTICITY-01, NX-LEARN-01
- 종료 기준: 정정 목록(ND 17개, README 단계, v3 기준선 SHA 해석표, v3 QH 대 NX 대응표, 집계 단위)이 SHA와 정적/실행 구분과 함께 기록된다.
- 종료 기준: ND-18·ND-04·ND-09·ND-01 방식·ND-19 응답이 문서에 남거나 '미응답'으로 표기되며 미응답 항목의 작업은 시작하지 않는다.
- 종료 기준: NZ-SECURITY-02 는 승인 기록 없이 시작하지 않았고 미실행이면 미실행으로 기록한다.
- 종료 기준: status 현재 표에 실행하지 않은 시험·게이트 목록이 있으며 미실행을 통과로 쓴 곳이 없다.

### Δ2 Q27 임계 경로와 합성 설계·additive 병행
Q27 마감과 PR #7 판정을 진행하면서 같은 순차 구현 단계 안에서 설계 문서와 additive 신규 파일 작업을 활성 worker 한 명 규칙으로 병행한다.

- 작업: NX-BASELINE-01, NX-BASELINE-02, NZ-PORTFOLIO-01, NX-POLICY-02, NX-POLICY-03, NX-AUTHENTICITY-02, NX-LEARN-02, NX-PORTFOLIO-01, NX-OPS-INFRA-03, NZ-POLICY-01, NZ-SECURITY-03, NZ-TEST-STRATEGY-01, NZ-DATA-01, NZ-DATA-02, NZ-DOCS-PROCESS-01
- 종료 기준: FUP-Q27-006/009~014 가 큐 JSON 에서 resolved 이거나 사유와 함께 남고 q27_complete 는 실제 판정 증거 전에는 false 로 유지된다.
- 종료 기준: 병행 코드는 신규 파일만 추가하고 application/target.py·domain/target.py 를 수정하지 않았음이 diff 로 확인된다(정적).
- 종료 기준: 병행 코드의 시험 추가·실행은 사용자 요청 범위로 한정되고 미실행이면 미실행으로 기록된다.
- 종료 기준: PR #7 수용 판정과 NX-BASELINE-02 선행 열 재파싱 결과가 고정 SHA 와 함께 기록되고 독립 일반·보안 검토 전에는 병합 판단을 하지 않는다.

### Δ3 Q27 판정 직후 target-local-v2 단일 개정 창
breaking 개정을 한 에포크로 묶어 P28-04 착수 전에 한 번만 전체 회귀 비용을 치른다.

- 작업: NX-POLICY-04, NX-TAX-COST-01, NX-PORTFOLIO-02, NX-POLICY-06, NX-SAFETY-01, NX-PORTFOLIO-03, NX-OPS-INFRA-02, NZ-TEST-STRATEGY-02
- 종료 기준: ND-04 와 ND-13 신규 부분 응답 뒤에만 시작하고 qh-contract-change 독립 일반·보안 검토 기록이 있다(자기 검토를 독립 검토로 기록하지 않는다).
- 종료 기준: Q23 24실행 골든과 평가 spec raw SHA 불변을 확인 방법과 함께 기록하며 확인하지 못했으면 UNVERIFIED 로 둔다.
- 종료 기준: 부분 실행은 PARTIAL + 시험 ID 목록 해시 + 입력 manifest SHA 로만 기록하고 전체 통과로 합산하지 않는다.
- 종료 기준: 요율 값은 전문가 확인 전에 확정하지 않는다.

### Δ4 P28-04~P29·RETURN-01 합성 마감과 정책 비교
기존 큐대로 합성 한정 구현을 마감하고 정책 비교를 시도 원장 기록과 함께 수행한다.

- 작업: NX-POLICY-05, NX-POLICY-07, NX-POLICY-08, NX-POLICY-09, NX-POLICY-10, NX-RESEARCH-01, NX-PORTFOLIO-04, NX-OBS-UI-01
- 종료 기준: 정책 비교 결과는 '합성=엔지니어링 비교'로 라벨되고 비교마다 시도 이벤트가 기록되며 정책 값 선택 근거로 쓰지 않는다.
- 종료 기준: P28~P29 상태는 artifact_ready_pending_acceptance 와 completed 를 구분하고 독립 검토 충족 전에는 completed 로 쓰지 않는다.
- 종료 기준: 정책 값이 사용자 결정 전 확정되지 않았다는 점이 기록된다.
- 종료 기준: 트리거 대기로 내린 학습·진위 항목이 NZ-DOCS-PROCESS-02 표에 남아 있다.

### Δ5 RETURN-02 진입 점검(실제 조회 전, 순서 변경 없음)
실제 조회·모의 연결 전에 흩어진 선행 조건과 결정을 한 표로 집계하고 비어 있으면 진입하지 않는다.

- 작업: NZ-DOCS-PROCESS-02, NZ-TAX-COST-01, NZ-OPS-INFRA-01, NZ-OPS-INFRA-02, NZ-TEST-STRATEGY-03, NX-OPS-INFRA-01
- 종료 기준: 진입 점검표의 모든 칸이 충족·미충족·UNVERIFIABLE 중 하나로 표기되고 추정은 추정으로 쓰인다.
- 종료 기준: 표에 미충족이 있으면 실제 조회·모의 연결·실데이터 수집을 시작하지 않았다는 기록이 있다.
- 종료 기준: CI 활성화·원격 변경은 AP-06 승인 기록 없이는 수행되지 않았다.
- 종료 기준: 전체 게이트 실행 여부와 결과를 실행·미실행으로 구분해 적는다.

### Δ6 트리거·승인 대기(blocked)
소비자나 승인이 생기기 전에는 열지 않는 항목을 폐기 없이 조건과 함께 보관한다.

- 작업: NZ-DATA-03, NX-DATA-02, NX-RESEARCH-02, NX-BROKER-02, NX-LEARN-05, NX-AUTHENTICITY-03, NX-AUTHENTICITY-04, NX-LEARN-03, NX-TAX-COST-02
- 종료 기준: 각 항목에 열리는 트리거와 승인 근거가 기록되고 미충족이면 blocked 를 유지한다.
- 종료 기준: NZ-DATA-03 은 ND-17 (b) 응답, SG-02 결정 기록, 계정·키 승인 전에는 시작하지 않았다.
- 종료 기준: KIS 모의 연결과 paper 개방은 PG/SG/AP 관문 전에 시작하지 않았다.
- 종료 기준: 합성 단계 결과를 실데이터·실모델 성과로 승격한 기록이 없다.

## 6. 사용자 결정 항목

- **ND-17** [묶음 B, REORDER(사용자 결정)] 읽기 전용 실데이터 스파이크를 RETURN-02 보다 앞당길 것인가? AGENTS.md 4단계(모의 검증) 앞당김이라 사용자 명시 순서 변경이 필요하다.
  - 권고: (a). 계약은 synthetic 단일값, 승인 범위와 SG-02 가 없고 KR·US 일봉 공급원 약관이 깨끗하지 않다. 실행을 원하면 (b)의 전제를 모두 충족한 뒤 응답한다.
  - 선택지: (a) 현재 순서 유지, NZ-DATA-01 준비 메모만 작성 / (b) 조건부 허용: 공급원별 SG-02 결정 기록, 용도 store/research 한정, AI·보고 입력 격리, 계좌·주문·AP-05 분리, additive 계약 또는 별도 연구 모듈 결정 후, 계정·키 별도 승인, 시도 기록 동일 슬라이스 / (c) 즉시 허용(비권고)
  - 막는 작업: NZ-DATA-03, NX-DATA-02, ND-08
- **ND-18** [묶음 A, 순서 변경 아님] NX 53개 중 큐에 채택할 범위는? 현재 NX·ND 는 모두 제안 상태이며 ND-05 위임은 설계 한정이라 새 코드 착수에는 채택 범위가 필요하다.
  - 권고: (a). 단 새 파일만 추가하고 application/target.py·domain/target.py 는 수정하지 않으며 활성 worker·작성자 한 명 규칙을 지킨다. 채택은 기존 큐 ID·완료 판정을 바꾸지 않는 연결 추가로 한다.
  - 선택지: (a) 문서·설계 즉시 착수 + additive 합성 코드 3종(NX-POLICY-02/03, NX-AUTHENTICITY-02(+LEARN-02), NX-PORTFOLIO-01) 병행 / (b) 문서·설계만 채택하고 코드는 Q27 판정 뒤 / (c) NX 전체 채택
  - 막는 작업: NX-POLICY-02, NX-POLICY-03, NX-PORTFOLIO-01, NX-AUTHENTICITY-02
- **ND-04** [묶음 A] 한도 초과 시 줄이는 매도(reduce-only) 허용과 자동 청산 여부는? 손실 행동은 사용자 확정 사항이다.
  - 권고: work-list 권고안(reduce-only 허용, 자동 청산 없음)을 질의한다. 최종 선택은 사용자이며 단계 수와 낙폭 임계값은 값이라 질의에서 제외한다.
  - 선택지: reduce-only 허용, 자동 청산 없음 / reduce-only 불허 / 보류
  - 막는 작업: NX-POLICY-04, NX-BROKER-02
- **ND-01(방식)** [묶음 A] 자산배분 방식을 '사용자 지정 고정 비중 + 허용 폭, 종목은 동일 비중 기준선, 기준통화 KRW'로 확인하는가? KR·US·현금 비중 값은 이 질문에서 제외한다.
  - 권고: 저장소 권고와 PDF 가 일치하는 방식 확인만 요청하고 값은 PG-03 사용자 결정으로 유지한다.
  - 선택지: 방식 확인 / 다른 방식 지정 / 보류
  - 막는 작업: NX-PORTFOLIO-01, NX-POLICY-02
- **ND-09(확장)** [묶음 A] 본인 계좌 단독 가정, 세무·법률 전문가 확인 시점, 사용할 계좌 유형(일반 위탁 대 세제 혜택 계좌)은?
  - 권고: 사실 확인(계좌별 지원·상품 범위)은 증권사 공식 문서와 전문가 확인으로만 하고 AI 는 확정하지 않는다. 가정은 사용자가 선택한다.
  - 선택지: 본인 계좌 단독·일반 위탁 가정으로 진행하고 확인 시점 지정 / 세제 혜택 계좌 포함 검토(계좌별 API 지원 확인 필요, UNVERIFIABLE) / 보류
  - 막는 작업: NX-SECURITY-01, NX-SECURITY-02, NX-TAX-COST-02, NZ-TAX-COST-01
- **ND-19** [묶음 A] 저장소 공개 상태(비평가 보고상 이미 PUBLIC)를 유지할 것인가, 전 이력 비밀정보 읽기 전용 스캔을 승인할 것인가, LICENSE·커밋 작성자 이메일 정책은?
  - 권고: 소액 실전 전 노출면 축소를 위해 이력 스캔 승인을 권고한다. 공개 여부와 LICENSE 는 사용자 판단이며 AI 는 원격 설정을 바꾸지 않는다.
  - 선택지: 공개 유지 + 이력 스캔 승인 + LICENSE·작성자 정책 별도 결정 / 비공개 전환 요청(원격 변경은 AP-06, 사용자가 직접) / 스캔 보류
  - 막는 작업: NZ-SECURITY-01, NZ-SECURITY-02, NX-DOCS-PROCESS-03
- **ND-13(신규 부분)** [묶음 B] 신규 시험 추가 허가, target-local-v2 전체 회귀 시간 예산, CI 활성화(AP-06), 지원 호스트 범위는? Q27 마감용 실행은 재질의 대상이 아니다.
  - 권고: 시간 예산은 NZ-TEST-STRATEGY-02 의 1회 측정 뒤에 정하는 순서를 권고한다.
  - 선택지: 시험 프로파일 1회와 계약 창 회귀 1회까지 허가 / Q27 마감까지만 허가 / 보류
  - 막는 작업: NZ-TEST-STRATEGY-02, NX-OPS-INFRA-02, NX-POLICY-04
- **ND-27** [묶음 B] 정책 구조(단위·결합 규칙·필드)를 아키텍처 설계로 위임 처리하고 값만 사용자 결정으로 남겨도 되는가?
  - 권고: policy-gates.md:19 가 구조와 값을 구분하므로 위임을 권고한다. 위임 여부는 사용자 확인 전에는 제안일 뿐이다.
  - 선택지: 위임(구조는 설계, 값은 사용자) / 구조도 매번 사용자 확인 / 보류
  - 막는 작업: NX-POLICY-02, NX-POLICY-03, NX-POLICY-05
- **ND-21** [묶음 B] 실전 관문에서 인정할 독립 검토의 정의(사람 직접 검토 범위, 타 모델 공급자 교차 검토, 외부 감사 예산)는?
  - 권고: 최소 사람 직접 검토 범위를 정하고 증거에 자기보고 한계를 표기한다. 예산은 사용자 몫이다.
  - 선택지: 사람이 안전 핵심 모듈을 직접 읽는다 / 타 모델 공급자 교차 검토 추가 / 외부 감사 포함 / 정의 보류
  - 막는 작업: NZ-SECURITY-03, PG-05
- **ND-24** [묶음 B] v2/ 디렉터리의 공개 후보 게이트 처리 방식과 한글 이름 PDF 파일명 변경 허용 여부는?
  - 권고: 전체 게이트 단독 실행 승인을 먼저 받아 fail 여부를 확인한 뒤 선택한다. 파일명 변경은 사용자 파일이므로 사용자 결정이다.
  - 선택지: 공개 루트 추가 + PDF 를 ASCII 이름으로 변경 / 입력 보관소로 분류해 게이트 범위에서 제외 / 현상 유지
  - 막는 작업: NZ-OPS-INFRA-01
- **ND-25** [묶음 B] 장기 브랜치 4개의 병합·폐기 방침(AP-06 범위)은? 특히 cef6a5e 가 되살리는 이전 v2 원본의 처리.
  - 권고: 삭제·병합은 파괴적이므로 NZ-BASELINE-01 표를 본 뒤 결정한다.
  - 선택지: PR #7 만 검토 후 병합, 나머지 보존 / 불필요 브랜치 폐기 / 보류
  - 막는 작업: NZ-BASELINE-01, NX-BASELINE-02
- **ND-26** [묶음 B] 문서 정리 방식 선택: status 이력 보관 (a) git mv+얇은 새 status 대 (b) 복사+포인터, NX/ND 기계 판독 색인 JSON 신설, 필독 합계 예산, AGENTS.md 규칙 반영, NX-DOCS-PROCESS-01 우선순위(v3 P0 대 NX P2).
  - 권고: (b) 복사+포인터로 이력 100% 보존을 권고하고 JSON 색인은 단방향 생성일 때만 승인한다. 예산 수치(R4 제안 60KB)는 근거 없는 값이라 사용자 결정이다. NX-DOCS-PROCESS-01 은 P1 을 권고한다. AGENTS.md 수정은 사용자 승인 필요.
  - 선택지: (a) / (b) / JSON 색인 신설 / 보류
  - 막는 작업: NZ-DOCS-PROCESS-01, NX-DOCS-PROCESS-01
- **ND-20** [묶음 C] 장중 15분 분석 요구를 유지할 것인가, 일 1회 또는 월 1회 점검으로 단순화할 것인가?
  - 권고: 소스·권리·신선도 표(NZ-DATA-02)를 본 뒤 결정한다. 일봉 공급원은 영업일 하루 뒤 갱신이라 15분 루프를 지원하지 못한다(FSC 사례).
  - 선택지: 15분 유지(가격 소스 결정 필요) / 일 1회 점검 / 월 1회 점검
  - 막는 작업: NZ-DATA-02, NX-POLICY-09, PG-01
- **ND-22** [묶음 C] 자동운영(AGENTS.md 마지막 단계)을 최종 목표로 계속 둘 것인가, 영구 후보별 승인으로 둘 것인가?
  - 권고: 결정 전에는 승인·실행 계약을 후보별 승인 기준으로 두고 NZ-POLICY-01 의 additive 호환 판정을 근거로 쓴다.
  - 선택지: 자동운영 유지(승인 봉투 설계 필요) / 후보별 승인 영구 유지
  - 막는 작업: NZ-POLICY-01, AP-08
- **ND-23** [묶음 C] 투입 규모, 프로젝트 목적(학습 대 수익), 중단·축소 기준은?
  - 권고: 값은 사용자 입력이다. 패시브 보유가 정상 결론일 수 있다는 경로를 점검표에 두는 것을 권고한다.
  - 선택지: 학습 목적 중심 / 수익 목적 중심 / 보류
  - 막는 작업: NZ-TAX-COST-01, PG-04

## 7. 비평가가 찾은 신규 공백

| ID | 영역 | 공백 | 중요성 | 저장소 현황 | 심각도 | 제안 |
|---|---|---|---|---|---|---|
| CG-01 | 보안/저장소 공개 | 저장소는 이미 GitHub PUBLIC이다. 그런데 계획은 공개를 미래 사건으로 서술한다. 이력 포함 비밀·개인정보 검사, 공개 유지 여부 결정, LICENSE 정책이 어떤 NX·ND에도 없다. NX-DOCS-PROCESS-03은 HEAD의 절대경로 치환만 계획한다. 54개 커밋 이력에는 이미 남아 있어 치환으로 제거되지 않는다. | 소액 실전 이전에 실제 키·계좌가 생기면 공개 저장소가 노출면이 된다. security.md 원칙 5는 이력 비밀정보 검사를 별도 승인 작업으로 규정하는데 미수행이다. 설계·정책 구조·증권사 선택·승인 정책이 공개 상태이고, 작성자 메타데이터에는 회사 도메인 이메일 6커밋이 있다. 이는 사용자 결정 사안이다. | planned_but_incomplete | P1 | NX-SECURITY-03 신설(문서·점검 한정). (1) 사용자 결정: 공개 유지 vs 비공개 전환과 LICENSE 정책(원격 변경은 AP-06이라 AI가 실행하지 않는다). (2) security.md 원칙 5에 따른 읽기 전용 이력 스캔 승인 요청(값 비출력, 증거 JSON 포함). (3) NX-DOCS-PROCESS-03의 '공개 전' 서술을 '이미 공개됨, 이력 잔존'으로 정정. (4) 작성자 메타데이터 정책 결정. RETURN-02 점검표(CG-08)에 편입. |
| CG-02 | 데이터/운영 루프 | 장중 15분 분석 루프(AP-04, operations-v1)가 쓸 가격 소스·권리·신선도 정의가 없다. 계획된 데이터 작업은 모두 일봉 공급자(NX-DATA-02)이고 PDF 스파이크도 일봉이다. 일봉 공급원은 지연된다(FSC 주식시세정보는 영업일 하루 뒤 오후 1시 이후 갱신). AP-05 범위에는 시세 조회가 열거돼 있지 않다. | 코드는 가격·FX 나이 검사를 요구한다. 지정가 기준가·후보 생성·stale 차단에 현재가가 필요하다. 소스가 없으면 15분 슬롯은 영원히 BLOCKED이거나 요구사항 자체를 재검토해야 한다. 이 질문은 스파이크 범위와 PG-01 입력을 바꾼다. | mentioned_not_planned | P1 | NX-DATA-04(docs_only): 운영 루프 가격 소스 결정표. 후보는 증권사 시세 조회, 지연 일봉, 사용자 수동 입력이다. 각 후보별 권리(LLM·보고 사용), 신선도 한도, 소스 불가 시 BLOCKED 동작, AP-05 범위 확장 필요 여부를 적는다. 실데이터 스파이크 질문 목록에 '운영 가격 소스'를 포함한다. |
| CG-03 | 검증 독립성 | 실전 관문 전에 안전 핵심 코드(execution·approval·egress·broker·정책 검사)를 누가 독립 검토하는지 정의가 없다. 현재 '독립 검토'는 같은 orchestrator 아래 하위 역할이다. 사람·타 모델 공급자·외부 감사 요구는 저장소 문서에 없다. '다른 모델 계열·사람 샘플링'은 투자 AI 학습 루프 문맥에만 있다. | artifact_ready의 근거가 전부 같은 시스템의 자기 검토다. team.toml은 격리 미검증을 스스로 밝힌다. 자금이 걸리는 단계에서 독립성의 정의가 없으면 PG-05·Q32의 '독립 검토 통과'가 형식 충족이 된다. | mentioned_not_planned | P1 | 결정 기록 하나(docs_only): 실전 관문(PG-05·Q32·RETURN-02)에서 인정하는 독립 검토의 정의. 사람이 직접 읽을 모듈 목록, 타 모델 공급자 교차 검토 여부, 외부 감사 여부, 증거 형식을 포함한다. 자기 검토를 독립 검토로 기록하지 않는 AGENTS.md 규칙과 연결한다. |
| CG-04 | 승인 모델/최종 단계 | AGENTS.md 최상위 순서의 마지막 단계 '정책 범위 자동운영'의 승인 모델이 정의되지 않았고, 현재 구속 결정과 충돌한다. 현행 결정은 포괄 승인·자동 승인으로의 확대를 금지하고 N건 리밸런싱을 N번 승인으로 본다. work-list에는 Q34 설계 항목이 없다. | 승인 계약(후보 결속)이 target-local-v2 개정 창에서 굳어질 예정이다. 사전 승인 봉투(종목·금액·횟수·손실한도·기간)가 나중에 필요하면 승인·실행 계약을 또 breaking으로 바꿔야 한다. 지금은 설계 입력만 받아 두면 비용이 작다. | mentioned_not_planned | P2 | docs_only ADR(설계 입력만, 구현·값 없음): 자동운영 승인 모델. 봉투 필드, 예외 상향 절차, 후보별 승인과의 호환(additive 가능 여부)을 정리한다. target-local-v2 개정 창에 넣을지 판단 자료로 쓴다. |
| CG-05 | 경제성/중단 기준 | 운영 고정비(LLM·데이터 AP-03, 수수료·거래세·해외 양도세 22%)를 감당하는 최소 자본과, 패시브 대안(KR·US 지수 ETF 보유) 대비 순성과 귀무 기준, 프로젝트 수준 중단·축소 기준이 없다. NX-LEARN-06은 모의 합격 기준과 AI 기여를 다루지만 이 세 항목은 없다. | 소액 실전 규모에서는 고정비와 세금이 기대 초과수익을 넘을 수 있다. '아무것도 하지 않음 또는 패시브 보유가 정상 결론'이라는 경로가 없으면 플랫폼 구축이 결과에 대한 매몰비용 압력을 만든다. 규모와 목적은 사용자만 정할 수 있다. | planned_but_incomplete | P2 | NX-LEARN-06에 세 항목을 추가한다(docs_only). (a) 자본 규모별 고정비 대비 손익분기 초과수익 표(값은 사용자 입력), (b) 패시브 대안 대비 순성과 귀무 기준과 무거래 정상 결론 경로, (c) 프로젝트 중단·축소 기준. 세율 값은 전문가 확인 전 확정하지 않는다. |
| CG-06 | 품질 게이트/v2 디렉터리 | v2/ 디렉터리가 공개 후보 게이트(check_quality.py)의 허용 루트에 없다. 이 문제를 소유한 NX가 없다. 소스상 v3 MD는 unclassified_candidate로, 한글 파일명 PDF는 unsafe_path로 거부될 것으로 읽힌다. | 공개 후보 검사가 완료 증거에 쓰이는데, 5ff8e29와 171e3e4에서 이 검사가 실패한다는 사실이 어떤 문서에도 없다. 전체 게이트는 실행하지 않았으므로 fail 여부는 추정이다. 방치하면 CI 활성화(AP-06) 시 첫 실행이 즉시 실패한다. | absent_in_repo | P2 | 사용자 결정 요청 1건과 문서화: v2/ 처리 3안(공개 루트 추가+ASCII 파일명 / 입력 보관소 제외 규칙 / 현상 유지). check_quality.py 수정은 Q27 판정 이후로 미룬다. 이 문서의 파일명 변경은 사용자 파일이므로 사용자 결정이다. |
| CG-07 | Git 위상/PR | 브랜치·PR 위상을 정리할 담당 작업이 없다. 로컬·원격에 장기 브랜치 4개가 나뉘어 있다. NX-BASELINE-02는 PR #7 수용만 다룬다. codex 브랜치의 cef6a5e('v2 전수조사')는 main의 171e3e4와 제목이 같고 삭제된 이전 v2 MD와 1.6MB PDF를 되살린다. | 어떤 브랜치가 병합되면 main에서 지운 v2 원본이 되살아나거나 status.md 상단·큐 JSON에서 충돌한다. PR #5는 main이 아닌 base로 병합돼 main에 도달하지 못했다(R2-15). 브랜치 삭제는 파괴적이라 사용자 승인이 필요하다. | absent_in_repo | P2 | NX-GIT-01(점검 문서): 브랜치별 목적·최종 운명(병합/폐기/보존)·충돌 지점 표. PR #7 수용 전 cef6a5e 제외 확인, 쌓인 PR의 base 확인 항목을 git-workflow 점검표에 추가한다. 삭제·병합·push는 AP-06 범위라 사용자 승인 뒤에만 한다. |
| CG-08 | 실제 연결 준비도 | 상한 때문에 NX로 만들지 않고 'RETURN-02 전 재평가'로 미룬 항목의 트리거·소유자 레지스트리가 없다. 예로 호스트 시계·절전(CRIT-16), 이미지 패치 주기(CRIT-17), 지원 호스트·psql 하위 프로세스 ADR이 있다. RETURN-02 선행조건은 '기존 승인과 PG/SG 확인'뿐이다. | 여러 문서에 흩어진 '실제 연결 전' 조건(PG-01, SG-02, ND-09, 가격 소스 CG-02, 독립 검토 CG-03, 공개 상태 CG-01, 경제성 CG-05)을 한 번에 점검하는 표가 없으면 보류 항목이 소실된다. 상태 문서가 이미 945줄이라 새 문서 대신 표 1개로 흡수해야 한다. | mentioned_not_planned | P2 | RETURN-02 진입 준비도 점검표(docs_only, status.md 상단 표 또는 PRODUCT 카드 안 한 표): 모든 '실제 연결 전' 조건을 항목·트리거·소유자·상태로 집계한다. 새 독립 문서는 만들지 않는다. |
| CG-09 | 원장/세무 원가 | 기존 보유 포지션의 취득원가 도입 방식이 비교 모델과 원장 계약 사이에 결정돼 있지 않다. 비교 모델은 원가 계산이 '제로 오프닝 포지션만 지원'이다. 평가 계약은 원가를 costing_spec_pending_q23으로 둔다. P28-04의 '초기 보유·원가 출처'는 합성 계좌 범위다. 세무 원가(선입선출 또는 이동평균)와 장부 원가법의 정합 결정이 없다. | 실계좌 도입 시 기존 보유 lot 이력이 필요하다(거래내역은 Git 금지). 원가법을 나중에 정하면 원장 계약을 추가 개정해야 한다. NX-TAX-COST-02는 차단 상태다. | planned_but_incomplete | P3 | NX-TAX-COST-02 사전 문서(docs_only)에 '기존 보유 도입 시 원가 입력 모델(lot 단위 vs 평균, 출처, 누락 시 unknown 처리)' 절을 추가한다. 세무 판단은 전문가 확인 항목으로 둔다. |
| CG-10 | 계좌 유형/세제 | 계좌 유형(일반 위탁 vs ISA·연금저축 등 세제 혜택 계좌) 선택이 저장소 어디에도 없다. 현재 가정은 AP-04의 '현금계좌'뿐이다. | 세금·거래세 모델과 비용 구조의 전제를 바꾼다. 계좌 유형별 KIS API 지원과 거래 가능 상품 범위는 확인하지 못했다(UNVERIFIABLE). 소액에서는 세제 계좌가 비용 구조를 지배할 수 있어 가정이 틀리면 CG-05 경제성 계산이 무효가 된다. | absent_in_repo | P3 | ND-09 확장 질문 1개로 올린다(계좌 유형·세제 계좌 사용 여부). 사실 확인(계좌별 API 지원·상품 범위)은 증권사 공식 문서와 전문가 확인으로 한다. 값 확정은 AI가 하지 않는다. |

## 8. 흡수하지 않은 제안

- v3 QH-* ID 체계를 작업 정본으로 사용 — 이전 v2 ID 와 번호는 같고 의미가 다르며 이전 QH-POL/SEC/DATA/INT/OBS/UI/OPS 가 사유 없이 사라졌다(R1-27 upheld). NX 정본 유지, v3 11개는 NX 변경으로 흡수하고 대응표는 NX-DOCS-PROCESS-01 에 1회 기록한다.
- v3 §11.3 실행 순서와 '새 업무 Q27 병렬 착수' — 저장소가 허용한 병렬은 계획된 P28 준비뿐이다(EXEC-DEC-003, R1-29). 순서는 Δ1~Δ6 과 PG/SG/ND 가 정본이다.
- v3 §3.3 implementation-status.md 신설 / QH-MAIN-01 신규 ID — PDF N-1·N-9, follow-up §8, NX-DOCS-PROCESS-01 이 같은 처방을 가져 중복이다. status.md 상단 현재 표로 흡수한다. 우선순위(P0 대 P2)는 ND-26 에서 사용자가 정한다(R1-22).
- v3 QH-RES-03 대량 탐색 엔진(10k 조합) — 탐색 엔진 NX 가 없고 통제 장치(Trial Ledger, DSR/PBO)만 있다. NX-AUTHENTICITY-02/03 완료 뒤 후속 신규 후보로만 기록하고 지금 ID 를 부여하지 않는다(R1-24). configured_n/executed_n/valid_n/failed_n 분리 기록은 유지.
- v3 QH-RL-01 격리 강화학습 — v2 도 P3·최후순위였다. 실데이터·위험엔진·평가 게이트 이후 후보로만 두고 ID 를 부여하지 않는다(R1-26). 사양 요건(학습·검증·테스트 분리, 베이스라인 동시 평가)만 보존.
- PDF 권고 2 지금 실행(읽기 전용 실데이터 스파이크) — REORDER 이며 승인 레지스터에 범위가 없고 SG-02·계약·공급원이 막혀 있다. NZ-DATA-01 준비 메모와 ND-17 로 대체한다.
- PDF 권고 3 'Q27 과 병행'을 그대로 채택 — 부분 채택. 설계 문서는 ND-05 위임 범위라 즉시 진행하고, 코드는 ND-18 채택 뒤 additive 신규 파일로만 한다. 활성 worker·작성자 한 명 규칙 때문에 시간 분할이다.
- PDF 권고 5 중 '나머지 지연' — 부분 채택. 시도 원장·AUTH-01·LEARN-01 은 지금 하고 나머지 학습·진위 구현은 소비자 트리거 대기로 두되 폐기하지 않고 NZ-DOCS-PROCESS-02 표에 트리거·소유자를 남긴다.
- PDF 권고 6 중 증거 JSON 3개 절대경로 치환 — 해시·불변 이력 확인 전 보류. 마크다운 15개만 상대 링크로 치환한다. '새 문서를 만들면 기존 하나를 줄인다' 규칙도 이력 보존 충돌로 기각하고 '새 독립 문서 상한' 규칙으로 대체한다.
- PDF N-5 arm64 종속의 별도 작업 — 신규 작업 불요. P28-07 지원 호스트 범위 결정에 흡수한다. 사실은 맞으나 출처 표기 '신규'는 '레포 발견'으로 정정한다(R2-16).
- ND-08b KIS 모의 연결 앞당김 — 거절 유지. paper 개방은 breaking 이며 PG/SG/AP 관문 전 금지. PDF 도 비채택을 타당하다고 평가했다.
- ND-05/ND-06/ND-07 재질의 — 위임 판단이 기록돼 있어 다시 묻지 않는다. 정책 값은 위임 범위 밖이라 AI 가 확정하지 않는다.
- R4 scripts/check_docs.py 신규 작성 — AGENTS.md 가 시험·스크립트 추가를 요청 시로 한정하고 NX-DOCS-PROCESS-02 와 중복이다. 사용자가 요청할 때 추가한다.
- pytest 계열 도입(xdist·testmon·mutmut·pytest-timeout) — unittest ID·증거 JSON test_results_sha256·CI 템플릿이 unittest 형식에 묶여 있어 pytest 도입 ADR 이 선행이다. testmon 은 정적 입력(계약 JSON, migrations)을 추적하지 않아 회피(G3).
- 외부 변이 도구(mutmut, cosmic-ray)와 mutatest·MutPy 채택 — mutmut 은 첫 통계 수집이 전체 시험 1회(113분 이상)이고 fork 위험, cosmic-ray 는 디스크 원본 직접 변이로 입력 불변 규칙과 충돌, mutatest·MutPy 는 릴리스 정체(G3). 패턴만 차용.
- 문서 사이트·ADR 도구(MkDocs, Material, Sphinx, adr-tools GPL, log4brains Node) — 문서 사이트가 지금 필요하지 않고 문서량 문제의 해결책이 아니다. 생태계 전환기이거나 라이선스·휴면 문제(G3). 생성 블록 --check 와 상태 분리가 맞다.
- GPL 저장소 코드 사용(cvxportfolio, py-vallocation)과 ArcticDB(BSL), OpenBB(소유 이동 미확인), pandas-datareader, nshare-calc — 라이선스 전이·불일치·공급망·유지보수 위험. 개념 참고만 허용하고 도입하지 않는다. 라이선스는 본문 우선이며 ArcticDB 는 NEEDS_PROFESSIONAL_CHECK.
- Yahoo·KRX 자동 수집 래퍼(yfinance, pykrx 등)와 qlib 수집기 — 약관상 자동 수집·재배포 금지(follow-up §3, G1). 연구 전용 표현은 README 문구이지 약관이 아니다.
- JSON Schema 호환성 도구(jsoncompat, jsonschema-diff, oasdiff, buf) — QH 계약은 Markdown 산문과 JSON 픽스처라 적용 대상이 없다. 호환 등급 어휘만 qh-contract-change 에 차용한다.
- CI 활성화, 원격 push·PR, 브랜치 삭제 — AP-06 사용자 승인 필요. 이번 델타는 문서·설계·점검 한정.
- GitHub 스타 수 기반 판정 — 품질·수익성·안전성의 근거가 아니다. 모든 판정에서 사용하지 않았다.

## 9. 반증된 판정과 논쟁

- R2-27 (PDF 권고 1 '2b-2a 수용이 계약 개정(W2)을 푼다'를 의존 오독으로 보는 판정): verification=refuted 라 근거로 쓰지 않았다. 같은 취지의 R3 선행 열 파싱 주장(2b-2a 는 NX-LEARN-02 만 막는다)도 별도 재확인 전에는 제안으로만 취급하고 NX-BASELINE-02 를 강등하지 않았다.
- v3 L6-8·L412-418·§14: 'Q27 수정·P28-01/02 artifact_ready·P28-03 착수를 80403ab 기준 현재 main 에서 확인' — 80403ab 에는 그 내용이 없고 7ba3c88 이후에만 있다(R1-01 upheld). §14 링크 80403ab 고정은 주장과 반대 내용을 보여준다(R1-21).
- v3 §2 정정표: 기본 구조·원장·개발 AI·상태 문서·CI 행이 이전 v2 에 없거나 반대로 쓰인 서술을 귀속한다(R1-05 upheld). v3 QH-* ID 를 정본으로 쓰는 것은 이전 v2 ID 와 의미가 달라 부적절하다(R1-27 upheld).
- v3 §3.1 'docs/architecture.md 가 Domain/Application/Ports/Adapters, trust boundary 를 정의한다': 49줄 문서에 해당 용어 0건(R1-10, not_checked, 정적 grep). 계층은 src 디렉터리에서만 확인된다.
- v3 §11.3 '새 P1/P2 업무를 Q27 관문과 병렬 착수 가능': 저장소가 병렬을 허용한 것은 이미 계획된 P28 준비뿐이다(EXEC-DEC-003, R1-29).
- PDF 절대경로 '121회·16개·감소': 이전(전 파일 범위)과 현재(md 한정) 범위를 바꿔 비교한 오류이고 실제는 18파일 128회 불변이다(R2-25, not_checked 정적 재현).
- PDF ND '16개'(p.2) 대 17개(p.1·6·8)의 내부 불일치, status.md 의 '16개·REORDER 3건'도 stale 이다(R2-23, R2-26).
- PDF N-5 '신규' 출처 표기: 같은 사실이 이전 라운드 C2-17·work-list §6 에 기록돼 있고 PDF 자신도 p.4 에서 '비채택'으로 분류했다(R2-16).
- PDF '마크다운 157→163개 오류 정정': 157개는 docs/ 한정, 163개는 저장소 전체 집계로 범위 차이일 뿐 오류가 아니다(R2-11).
- PDF '허용 폭 절대 ±5%p 또는 상대 25% 내부 모순': 산술은 맞으나 충돌이 아니라 종목 단위 절대 폭 무력화와 단위 미정이 정확하다(R2-10).
- PDF 'ND-04 가장 급하다': 합성 단계라 운용 노출이 없어 긴급성 근거가 없고 paper 개방 선행 조건으로서 중요하다(R2-30).
- PDF '3.8시간': 두 실행의 합이며 동시 실행 정황이 있어 벽시계 시간이 아니다(R2-14).
- PDF 권고 2 '기존 MarketFetchPort 와 Parquet 저장소를 그대로 쓴다': environment 가 synthetic 단일값이고 128건 상한·HTTP 클라이언트 0건이라 부정확하다(R3, 약관·사실 검증 VERIFIED).
- PDF 권고 2 'ND-08 지금 허용' 의견: 약관(자동 수집·제3자 제공 금지)과 SG-02 미충족으로 현재 근거로는 안전하지 않다(R2-29 upheld).
- PDF·work-list 'src 에 rebalanc 0건': research 에 equal_weight_rebalance 전략이 있고 plan_orders 는 2종목·45% 하드코딩이다(R3 정적 grep, 독립 검증 없음).
- R4 '전체 게이트 fail': classify() 단독 호출에서 도출한 추정이며 전체 inspect_repository 는 실행하지 않았다(미검증).
- (재검증 반박) R2-27 (PDF p.9 권장 순서 1 '2b-2a 브랜치 정리를 끝내야 계약 개정(W2)이 풀린다'): 표 수준의 사실은 모두 맞다. 그러나 '하나뿐'이라는 결론과 FALSE 판정은 지나치다. 맞는 부분: work-list 표(68-120)의 선행 열을 awk로 구문 분석한 결과 NX-BASELINE-01을 선행으로 가진 행은 정확히 9개다(SAFETY-01, POLICY-02, POLICY-04, PORTFOLIO-01, PORTFOLIO-03, TAX-COST-01, OPS-INFRA-02, OPS-INFRA-03, AUTHENTICITY-02). NX-BASELINE-02를 선행으로 가진 행은 NX-LEARN-02(줄 108) 하나다. 줄 126도 확인했다('이 관문 전에는 위험 의미를 바꾸는 계약 변경을 시작하지 않는다'). PDF 권장 4 자신이 target-local-v2 묶음을 'Q27 판정 후'로만 적었으므로 PDF 권장 1의 '두 가지가 끝나야 계약 개정(W2)이 풀린다'는 PDF 내부에서도 어긋난다. 틀린 부분: (a) 표의 선행 열에는 P28-03을 선행으로 둔 NX-AI-RUNTIME-01, NX-AI-RUNTIME-02도 있다(줄 451-466). 상세는 각각 'P28-03 내부2b-2b 완료 후', 'P28-03 내부2b-2b 이후'이고, NX-AI-RUNTIME-01은 계약 영향이 breaking(ai-local-v2)인 W2 항목이다. BASELINE-02 상세(줄 139)는 2b-2a 수용이 '2b-2b 다리 앞'이라고 적었다. 그래서 2b-2a 수용은 NX-LEARN-02와 NX-AI-RUNTIME-01·02로 이어지는 사슬의 앞단이다. W4 표제도 'P28-03 2b-2b 이후'다(줄 48). (b) NX-LEARN-02 상세(줄 581)는 'P28-03 2b-2b 이후 설계'라고 적었는데 표의 선행 열은 NX-BASELINE-02만 적어서 work-list 자체가 2b-2b 의존을 표에서 축약했다. 클레임은 이 축약된 표를 그대로 근거로 삼았다. (c) 따라서 '2b-2a 수용은 계약 개정이 아니라 학습 원장·시도 원장 사슬만 푼다'는 target-local-v2 계열 계약 개정에는 맞지만, ai-local-v2(breaking)에는 맞지 않는다. PDF의 '계약 개정(W2)'를 wave 단위로 읽으면 PDF 문장이 완전히 틀리지는 않고, 정확히는 모호하다. 권장 수정 문장: 'Q27 마감(BASELINE-01)이 target-local-v2 계약 개정(POLICY-02/04, TAX-COST-01 등 9개)을 풀고, 2b-2a 수용(BASELINE-02) 뒤 2b-2b 완료가 ai-local-v2(AI-RUNTIME-01/02)와 학습 원장(LEARN-02, AUTHENTICITY-02)을 푼다.' 두 판정이 서로 독립이라 같은 PR로 묶을 필요가 없다는 결론은 유지된다. 5ff8e29와 171e3e4의 work-list는 동일하다.

## 10. 문서 자체의 오류·모호함

- v3 MD: 기준 SHA 혼합. 헤더는 80403ab로 고정하면서 Q27 수정·P28-01/02 artifact_ready·P28-03 착수를 '현재 main에서 확인'이라 쓰나 그 내용은 7ba3c88 이후(5ff8e29·171e3e4)에만 있다. §14 링크가 80403ab로 고정돼 주장과 반대 내용을 보여준다. §13의 'HEAD SHA 기록' 규칙을 v3 자신이 어긴다(R1-01·R1-21·R1-29).
- v3 MD §2 정정표: 최소 5행이 이전 v2에 없거나 반대로 쓰인 서술을 귀속한다(R1-05). v3의 QH-* ID는 이전 v2 ID와 번호는 같고 의미가 다르며 이전 QH-POL/SEC/DATA/INT/OBS/UI/OPS 등은 사유 없이 사라졌다. 이전 라운드 work-list의 출처 컬럼은 이전 v2 ID를 인용하므로 v3 ID를 쓰면 매핑이 틀어진다(R1-27).
- v3 MD §3.1: docs/architecture.md가 Domain/Application/Ports/Adapters와 trust boundary를 정의한다고 쓰나 해당 용어는 문서에 없다. 계층은 src 디렉터리 구조에서만 확인된다(R1-10).
- PDF 내부 불일치: ND 16개(p.2)와 17개(p.1·6·8), '코드가 멈췄다'(p.1·N-1)와 '926줄 존재'(N-4), 'ND 4개가 정해져야'라면서 표는 5행, 정정표 11행인데 지시·질문은 7행, N-5를 '신규'로 표기하면서 같은 항목을 p.4에서 '비채택' 분류(R2-26). '절대경로 121회·16개·감소'는 범위를 바꿔 비교한 오류다(실제 18개 128회 불변, R2-25). 마크다운 157→163개는 '오류 정정'이 아니라 집계 범위(docs 한정 vs 전체) 차이다(R2-11).
- 이전 산출물 정정 미반영: status.md:7 '사용자 결정 16개·REORDER 3건'은 work-list의 ND 17개·REORDER 4건과 다르다(R2-23). status.md 기록 기준일은 2026-10-30인데 본문 최신은 2026-11-14이고 '현재 우선 지시' 제목이 2개 공존한다. status.md:9의 PR 병합 서술은 현재 main과 어긋난다(R4).
- work-list와 follow-up 간 모순: work-list는 ND-05·06·07·08b를 '사용자 결정 필요(REORDER)'로 두고 W1 종료 기준에도 ND-05를 포함하지만, follow-up §8은 같은 날 채택·유지·거절 위임 판단을 기록했다(R4). 거래세 '1차 원문 미확인' 서술도 정정 박스가 없다. 위임 판단의 사용자 원문 인용이 문서에 없어 위임 범위 해석 위험이 있다(R4 unchecked).
- 인용 재현성: work-list·verification이 171e3e4에서 삭제된 이전 v2 MD·첫 PDF를 줄 단위로 인용한다. 'audit_report.txt:NNN' 인용 대상은 저장소에 추적되지 않는 추출본이다. 기준 SHA가 문서마다 edd018a·80403ab·5ff8e29로 달라 SHA 없이는 재현되지 않는다(R2-04).
- NX-DOCS-PROCESS-03이 절대경로 치환을 '저장소 공개 전 필수 점검'으로 서술하나 저장소는 이미 PUBLIC이다(gh repo view, 2026-11-15). HEAD 치환으로는 이력의 노출이 제거되지 않는다. 같은 작업의 '128회(PDF 기준)·HEAD 계수 81건'은 발생 수와 줄 수 단위가 섞여 있다.
- 집계 단위·수치 모호: work-list의 'status.md 943줄 148,613B'는 현재 945줄·149,123B와 다르다. '3.8시간'은 두 실행의 합이고 동시 실행 정황이 있어 벽시계는 약 1.9시간일 수 있는데 합산임을 밝히지 않는다(R2-14). 'NX 등록 24'에는 NX가 아닌 기존 큐 흡수 행(Slack·대시보드·CLI 등)이 섞여 있다(R2-06).
- ID 네임스페이스 과밀: work-list 한 문서 안에서 NX(284회)·QH(79)·PG(78)·ND(67)·SG(51)·CRIT(27)·FUP(26)·AP(25)·RETURN(17)·PDFG(13)·PDFP(12) 등 12개 이상 접두가 쓰이고 단일 용어집·ID 색인이 없다. v3의 QH-*가 이전 v2의 QH-*와 충돌한다.
- 정본·제안 혼재와 처방 충돌: 1,345줄 work-list가 제안·정본·미흡수 제안·증거 부록을 겸하고 follow-up §8의 '표 위주 요약본'은 미작성이다. v3는 implementation-status.md 신설을 권하고 PDF는 '새 문서를 만들면 기존 하나를 줄인다'를 권해 처방이 충돌한다. 새 v2 두 파일은 어떤 문서에서도 링크되지 않는다(R4).
- AGENTS.md '테스트 추가·실행은 사용자가 요청한 경우'와 계획의 다수 검증 작업(NX-SAFETY-01, NX-OPS-INFRA-02, Q27 마감)이 충돌한다. EXEC-DEC-002/003의 상시 허가가 어느 시험까지 덮는지 목록이 없고 ND-13이 미결이다.
- 선행 간선 누락·인용 줄 어긋남: NX-POLICY-08은 DoD가 시도 횟수 기록을 요구하지만 선행 열에 NX-AUTHENTICITY-02가 없다(R3). work-list가 인용한 pyproject.toml:5는 현재 6행이다(G3). R2-27(PDF 권고 1 의존 오독)은 검증에서 refuted라 이번 비평의 근거로 쓰지 않았다.
- 진입 문서가 가리키는 정본의 시점 불일치: AGENTS.md가 '현재 개발 환경의 실제 상태' 정본으로 지명한 development-environment.md는 2026-10-23 '투자 애플리케이션 구현 전' 서술이고 README는 2026-10-20·합성 회귀 13개 서술이다. 둘 다 '당시 기록' 라벨이 없다(R4, R2-20).

## 11. 주장 검증 findings (60건)

| ID | 출처 | 판정 | 심각도 | 재검증 | 주장 | 근거(첫 항목) |
|---|---|---|---|---|---|---|
| R1-01 | v3 L4·L6-8(기준선 80403ab)·L412-418(§9.1)·L576-612(§14 링크 80403ab 고정) | PARTIALLY_TRUE | P1 | upheld | v3 는 코드 기준선을 main 80403ab(2026-10-29)로 적고 Q27 수정·P28-01/02 artifact_ready·P28-03 착수를 '현재 main 에서 확인'이라 쓴다. 그러나 그 내용은 80403ab 에 존재하지 않고 7ba3c88(PR#4, 2026-11-14 23:12) 이후 main(5ff8e29, 171e3e4)에만 있다. 80403ab 라벨은 틀리고 내용은 HEAD 에서 참이다. | 80403ab:src/quantharbor/adapters/postgres_execution.py:538-540 — invalidated 직후 무조건 s['holds'].pop(identity,None). 수정 전 상태 |
| R1-02 | v3 §4.1 L133-148(코드 발췌)·§1.1 L39 | CONFIRMED_AT_HEAD | P1 | upheld | Q27 pending-hold 수정(_pending_budget 로 재계산 후 있으면 holds 유지, 없으면 pop)이 현재 main 에 있고 v3 발췌가 실제 코드와 같다. 171e3e4 에서는 참이다. 80403ab 에서는 거짓이다(무조건 pop). 이전 v2 가 지적한 holds.pop 은 80403ab 기준으로는 정확했다. | 171e3e4:src/quantharbor/adapters/postgres_execution.py:538-546 — approval.state in ('pending','approved') → _change(...'policy_changed') → pending=self._pending_budget(s,identity); pending[0] 이면 s['holds'][identity]=pending, 아니면 pop. v3 발췌와 논리 동일 |
| R1-03 | v3 §4.2 L150-158 | CONFIRMED_AT_HEAD | P2 | not_checked | tests/product/test_execution_control.py 에 5종 회귀(예약 보존, 거절 영수증, 반복 원천 변경, 저장 실패 롤백, 완료 후 정리)가 있다. 5종 모두 HEAD 에 있다. 단 반복 원천 변경 시험은 af40f9c 에서 신설됐고, 이 시험 파일은 실제 PG 가 아닌 메모리 대역을 쓴다. | 171e3e4:tests/product/test_execution_control.py:116 — test_P2_source_invalidation_retains_exact_pending_completion_budget. replace_source 후 holds[ap]==(required,required*65536), receipt ('rejected', 'version_conflict' 또는 'expired'), 완료 뒤 required 감소 단언. 80403ab 에도 같은 줄에 존재 |
| R1-04 | v3 §4.3 L160-172·§1.1 L39·§13 지시 3(L563) | PARTIALLY_TRUE | P1 | upheld | v3 §4.3 은 실제 PostgreSQL 회귀, 중단·재기동·COMMIT 응답 유실, 독립 검토, 전체 회귀를 NOT_VERIFIED 로 두고 이를 Q27 의 남은 과제로 제시한다. 저장소에는 root 직접 실행 증거가 있다. 합성 PG 3사례 PASS, 8a27220 기준 86/86 PASS, 836 PASS 이다. 이 증거는 독립 검증이 아니고 runner 가 저장소에 없다. 실제 잔여는 고정40 real_gap 6건과 최종 판정이다. v3 의 목록은 부분적으로만 맞다. | 171e3e4:docs/evidence/execution-resume-pending-database-2026-10-30.json — 합성 PG 3사례 PASS, persisted_hold [4,262144]/[4,262144]/[19,1245184]. 그러나 execution_owner=root, independent_validation=false, raw_logs_in_git=false, runner 는 runner_sha256 만 있고 저장소에 없음 |
| R1-05 | v3 §2 L68-88 정정표(15행. 16행이 아님) | FALSE | P2 | upheld | v3 §2 표는 이전 v2 가 이렇게 말했다고 적지만 최소 5행은 이전 v2 에 없거나 반대로 쓰인 서술을 귀속한다. 기본 구조 'HLD/코어부터 새로 구축', 원장·평가 '새 원장·성과 계산 필요', 개발 AI '새 팀 설정/스킬 모두 필요', 상태 문서 '그대로 신뢰 가능', CI 'GitHub Actions 완성' 이다. | 04812f4:v2/QuantHarbor_Integrated_Audit_Architecture_Agent_Skills_v2.md:38,40 — '현행 저장소는 빈 프로젝트가 아니다… 재사용 자산을 보유', '금융 코어를 재작성하기보다 기존 계약을 보존'. 기본 구조 행과 반대 |
| R1-06 | v3 §2 L72-86 중 연구·포트폴리오·AI 에이전트 3행 | PARTIALLY_TRUE | P3 | not_checked | v3 §2 의 '백테스트 엔진 전무', '범용 목표안 생성 신규', '6역할 개념 설계뿐' 은 이전 v2 가 이미 Q23·Q24·Q25 존재를 인정한 서술과 어긋난다. v3 의 '정정'은 이전 v2 입장과 거의 같다. | 04812f4:…v2.md:125 — '백테스트 / 합성 비교 / 실제 과거 데이터/오류 회피/OOS'. 합성 비교 존재를 인정 |
| R1-07 | v3 §2 L72-86 중 Q27·KIS·데이터·설치·P28 4행 | PARTIALLY_TRUE | P3 | not_checked | Q27·KIS·데이터 저장·설치복원 행은 이전 v2 서술을 대체로 정확히 옮겼거나 부분적으로 정확하다. 정정 내용이 유효한 것은 kis_read 의 존재와 설치복원의 P28-05/07 매핑이다. P28 UI/API/제품실행 3행은 이전 v2 에 해당 서술이 없다. | 04812f4:…v2.md:95-102 — QH-SAFE-01 'replace_source()… s[holds].pop(identity,None) 호출이 존재', '정적 코드·PR 리뷰에 근거한 P0 조사/재현 대상'. 80403ab 기준으로 정확했고 v3 가 '잘못 판정'이라 쓴 것은 틀렸다 |
| R1-08 | v3 L6·L35-43(§1.1)·L622-631(최종 변경 원칙) | PARTIALLY_TRUE | P2 | not_checked | v3 의 핵심 논지는 이전 v2 가 이미 구현된 것을 신규 개발로 잘못 분류했고 v3 가 그것을 교정한다는 것이다. 과장이다. 이전 v2 는 재사용·기존 ID 연결을 스스로 규정했다. v3 와 이전 v2 의 실질 차이는 이후 커밋이 만든 상태 차이(Q27 수정, P28 산출물, kis_read 존재)다. | 04812f4:…v2.md:139 — '기존 작업 ID(Q23~Q29, P28/P29, GAP-01~09 등)와 중복되는 항목은 신규 이슈로 중복 완료 처리하지 말고 연결해 관리해야 한다' |
| R1-09 | v3 §3.1 L96-114(인벤토리 17행. 15행이 아님) | CONFIRMED_AT_HEAD | P3 | not_checked | 인벤토리 17행 중 16행은 파일 존재와 서술이 맞고 80403ab 와 171e3e4 에서 바이트가 동일하다. 예외는 R1-10(architecture.md)과 R1-11(P28)이다. market_ingest, parquet store, reporting, synthetic_investment_ai, KIS decoder, team.toml, Skill 3종, CI 예제, compose 모두 확인된다. | 171e3e4:src/quantharbor/application/market_ingest.py:1 — 'Q17A explicit-time bounded orchestration; synthetic fetch only, zero retries' |
| R1-10 | v3 §3.1 L98 Architecture 행 | PARTIALLY_TRUE | P3 | not_checked | v3 는 docs/architecture.md 가 'Domain/Application/Ports/Adapters, trust boundary 정의'를 담는다고 쓴다. 이 문서는 49줄이고 해당 계층 용어가 0건이다. 계약 4종·흐름도·'책임·실패 경계'만 서술한다. 계층 구조는 src/quantharbor/{domain,application,ports,adapters} 디렉터리에서만 확인된다. | 171e3e4:docs/architecture.md:1-49 — 80403ab 와 동일. 'Domain/Application/Ports/Adapters' 문자열 0건. L13-18 계약표, L20-33 mermaid 흐름, L37-43 '책임·실패 경계' |
| R1-11 | v3 §3.1 L112(P28 Product)·§9.1 L412-419·§12.3 | CONFIRMED_AT_HEAD | P2 | not_checked | P28-01/02 artifact_ready, P28-03 일부 착수, completed 0/12 라는 v3 서술은 HEAD 에서 참이다. 80403ab 에서는 거짓이다(전부 pending). 큐 필드 상태는 artifact_ready 가 아니라 status=in_progress 에 stage 로 표현된다. v3 인벤토리는 post-80403ab 코드(product_* 어댑터 4개 1,646줄, migrations/product 2개, compose.product.synthetic.yaml)를 언급하지 않는다. | 171e3e4:docs/product-delivery-plan.md:76 — 'P28-01… artifact_ready, FUP-P28-002 와 Q27 최종 관문은 남는다. P28-02 revision5… artifact_ready. P28-03 내부1/6 DB수명관리 구현 착수. completed0/12' |
| R1-12 | v3 §3.3 L124 README | CONFIRMED_AT_HEAD | P3 | not_checked | README 가 초기 '아직 구현 전' 설명을 담아 코드와 모순된다. | 171e3e4:README.md:9 — '2026-10-20 개발 AI 환경을 순차 구축 중… 투자 시스템·실계좌 연결·주문은 아직 구현하거나 실행하지 않았다'. 80403ab 와 바이트 동일 |
| R1-13 | v3 §3.3 L125 status.md PR #1 | FIXED_AT_HEAD | P3 | upheld | docs/status.md 가 PR #1 미병합 상태를 유지한다. 80403ab 에서는 참이다. 171e3e4 에서는 ac3a278 이 '로컬 실제 상태: main 80403ab, PR #1 병합 메시지와 두 부모' 를 추가하고 옛 서술을 '당시 기록'으로 재라벨했다. 병합 사실은 HEAD 에서 반영됐다. | 80403ab:docs/status.md:17 — '현재: PR #1 준비 완료, main 머지는 자동 승인 심사에서 실행 전에 거부되어 미실행이다. 사용자 명시 승인 대기'. main 자체가 PR #1 병합 커밋(80403ab)인데 미병합으로 기술 |
| R1-14 | v3 §3.3 L126(execution-queue.json 일부 단계 표시)·§11.1 | PARTIALLY_TRUE | P2 | not_checked | v3 는 'config/ai/execution-queue.json 일부 단계 표시도 이후 구현과 비교해야 한다'고만 쓴다. 구체적으로는 이중 범위 표기 때문에 오독하기 쉽다. 그리고 실제 개발 포인터(offline-execution-queue.json)와 실패 후속 큐는 v3 에 언급이 없다. | 171e3e4:config/ai/execution-queue.json:6 — current_queue_item=Q19(blocked). Q20~Q26 은 status='pending'이면서 local_status='completed'(이중 범위). 80403ab 와 바이트 동일 |
| R1-15 | v3 §6.1 L224-231 Q24 기능 목록 | CONFIRMED_AT_HEAD | P3 | not_checked | Q24 가 목표 비중·수량(TargetRequest/build_target), source-bound 입력 완전성, 최소 현금·종목/시장/통화 노출·가격/환율 시점·주문 단위·비용 제약, 승인 이전 주문 후보와 실패 사유를 갖고, optimizer 는 없다. | 171e3e4:src/quantharbor/application/target.py:754 — def build_target(request, inputs, repository). :811 render_candidate. 80403ab 와 동일 |
| R1-16 | v3 §7.1 L277-279·§3.1 L104·§3.2 L118 | CONFIRMED_AT_HEAD | P3 | not_checked | Q23 에 cash·buy_hold·equal_weight_rebalance 합성 비교와 24개 결과의 고정 비교가 있고, 2×45% 는 합성 비교 전략의 구현이다. | 171e3e4:src/quantharbor/domain/research.py:12 — STRATEGIES = ('cash','buy_hold','equal_weight_rebalance'). 전략 이름 정의는 strategies.py 가 아니라 domain/research.py |
| R1-17 | v3 §8.1 L311-321 개발 AI 팀·Skill | CONFIRMED_AT_HEAD | P3 | not_checked | config/ai/team.toml 에 Orchestrator 와 전문 6역할이 있고 순차 실행 조건이 있으며, .agents/skills 에 qh-task-handoff·qh-evidence-decision·qh-contract-change 3종이 있다. v3 는 team.toml 의 격리 미검증 플래그를 언급하지 않는다. | 171e3e4:config/ai/team.toml:6,8 — max_active_workers=1, recursive_delegation=false. execution_mode=sequential |
| R1-18 | v3 §8.2 L323-334 allowed_queries 와 InvestmentAIClient | CONFIRMED_AT_HEAD | P3 | not_checked | domain/investment_ai.py 에 역할별 allowed_queries 가 있고 InvestmentAIClient 포트가 있다. 코드와 일치한다. 단 포트는 domain 이 아니라 ports/ 에 있고, 역할별 허용 범위는 서로 크게 다르다(collector 는 document_view 하나, risk·report 는 5종 전부). v3 표는 이 매트릭스를 보여주지 않는다. | 171e3e4:src/quantharbor/domain/investment_ai.py:13 — ROLES = (collector, study, strategy, portfolio, risk, report) |
| R1-19 | v3 §10.2 L459-466 KIS/증권사·§1.1 L43 | CONFIRMED_AT_HEAD | P3 | not_checked | kis_read.py 모듈 문서가 vendor 실행 코드·인증·host·HTTP 기능이 없다고 명시하므로 KIS API 연결이 구현된 것이 아니다. | 171e3e4:src/quantharbor/adapters/kis_read.py:1-5 — '공식 고정 KIS 명세의 비전송 계획과 합성 source 관측 decoder… vendor 실행 코드/인증/host/HTTP 기능은 없다'. 80403ab 와 동일(diff 0) |
| R1-20 | v3 §10.3 L468-473 CI·compose | CONFIRMED_AT_HEAD | P3 | not_checked | config/ci/quality.workflow.example.yml 은 비활성 예제이고 활성 .github/workflows 가 없다. containers/compose.synthetic.yaml 은 네트워크 차단 합성 검증 환경이다. 둘 다 존재한다. 171e3e4 에는 v3 가 언급하지 않는 containers/compose.product.synthetic.yaml 이 추가됐다. | 171e3e4:config/ci/quality.workflow.example.yml:1-4 — 'Q15 inactive template: not in .github/workflows; no remote run was authorized', on: workflow_dispatch. 80403ab 동일 |
| R1-21 | v3 §14 L574-618 증거 링크 | PARTIALLY_TRUE | P2 | not_checked | §14 의 링크 대상 경로는 80403ab 와 171e3e4 에 모두 존재해 링크 자체는 열린다. 그러나 80403ab 로 고정된 두 링크(product-delivery-plan.md, postgres_execution.py)는 v3 주장(P28 artifact_ready, Q27 수정)과 반대 내용을 보여준다. 링크 존재가 주장 증거가 되지 않는다. | git cat-file -e 80403ab:<경로> — README.md, docs/status.md, docs/architecture.md, target.py(application·domain), research/strategies.py, application·domain investment_ai.py, synthetic_investment_ai.py, postgres_execution.py, test_execution_control.py, kis_read.py, parquet_market_store.py, market_ingest.py, compose.synthetic.yaml, team.toml, .agents/skills, docs/development/{execution,target,investment-ai,research}.md, docs/product-delivery-plan.md, config/ci/quality.workflow.example.yml, pyproject.toml 모두 존재. 171e3e4 도 모두 존재 |
| R1-22 | v3 §11.2 L496 QH-MAIN-01(P0) | PARTIALLY_TRUE | P2 | not_checked | v3 가 '진짜 추가'로 분류한 QH-MAIN-01(정합성 레지스터)은 이미 NX-DOCS-PROCESS-01/02 와 이전 v2 의 QH-AUD-01 에 있다. 의도는 완전 대응이다. 다만 v3 는 P0, NX 는 P2 이고, v3 의 선행조건('80403ab 기준 점검')은 R1-01 때문에 무효다. v3 의 수용 기준('모든 주장에 파일·버전·미실행 명시')은 NX-DOCS-PROCESS-01 의 SHA·확인방법 항목별 표기와 같다. | 171e3e4:docs/v2-work-list-2026-11-14.md:71 — NX-DOCS-PROCESS-01 P2 docs_only S, 기존 ID QH-AUD-01·GAP-09·RETURN-01 (재판정표 정본화, 항목마다 SHA·정적/실행 표기) |
| R1-23 | v3 §11.2 L497-499 QH-PORT-01~03 와 §6.2 | PARTIALLY_TRUE | P2 | not_checked | QH-PORT-01(유니버스·중복노출)은 NX-POLICY-10 이 정책 문서만 다루므로 부분 대응이다. QH-PORT-02(최적화)는 NX-PORTFOLIO-04(ADR, P3)와 NX-PORTFOLIO-01(사용자 지정·동일비중 기준선만)으로 부분 대응이다. QH-PORT-03(Proposal→Q24 변환)은 NX-PORTFOLIO-01 로 완전 대응이다. | 171e3e4:docs/v2-work-list-2026-11-14.md:83,295-305 — NX-POLICY-10 P2 docs_only: ETF 허용 방식·필터 필드·중복 노출 한도 키 정의. 값은 PG-03 에서 확정. 분석 구현 없음 |
| R1-24 | v3 §11.2 L500-501,504 QH-RES-01~03 와 §7.2-7.4 | PARTIALLY_TRUE | P2 | not_checked | QH-RES-01(실데이터 walk-forward)과 QH-RES-02(다자산 MC 10,000회)는 NX-RESEARCH-02 가 완전히 포함하지만 P3·blocked(데이터 권리 SG-02 대기)다. QH-RES-03(대량 탐색 10k 조합)은 탐색 엔진 NX 가 없고 NX-AUTHENTICITY-02/03 의 통제 장치(Trial Ledger, DSR/PBO)만 있어 부분 대응이다. v3 의 '10,000' 은 NX 에서 configured_n/executed_n/valid_n/failed_n 분리 기록으로 대체되어 있다. | 171e3e4:docs/v2-work-list-2026-11-14.md:89,361-372 — NX-RESEARCH-02 P3 blocked public_data L: 일봉·다년 백테스트·RiskMetrics·몬테카를로(모형 3종, seed·표준오차). 선행 NX-DATA-02, NX-AUTHENTICITY-02/03, NX-RESEARCH-01/03. 완료 기준에 configured_n/executed_n/valid_n/failed_n 분리 |
| R1-25 | v3 §11.2 L502-503 QH-AI-01~02 와 §8.6 | PARTIALLY_TRUE | P2 | not_checked | QH-AI-01(실제 LLM adapter와 Tool Gateway)은 NX-AI-RUNTIME-01/03 이 결정·선행조건 문서만 다루고 구현은 SG-04/AP-03 으로 막혀 있어 부분 대응이다. QH-AI-02(workflow 관측 이벤트)는 NX-OBS-UI-01 의 파생 상태 투영(폴링)만 있다. v3 가 요구하는 run/task/role/version 이벤트 저장은 기존 계약이 금지한다. | 171e3e4:docs/v2-work-list-2026-11-14.md:97,451-462 — NX-AI-RUNTIME-01 P2 docs_only: ai-local-v2 결정(model_id, 가격, 상한, 재시도). 실모델 호출은 SG-04·AP-03 전 금지. ND-14 |
| R1-26 | v3 §11.2 L505-506 QH-LEARN-01·QH-RL-01 | PARTIALLY_TRUE | P3 | not_checked | QH-LEARN-01(가설 사후 평가·스킬 승격)은 NX-LEARN-03/04 가 더 상세히 포함하므로 완전 대응이다. QH-RL-01(격리된 강화학습)은 이전 라운드가 의도적으로 흡수하지 않아 미대응이다. v3 도 P3 이다. | 171e3e4:docs/v2-work-list-2026-11-14.md:109-110,589-610 — NX-LEARN-03 P2 synthetic_local L(Forecast·Outcome·ScoreCard 사후 채점), NX-LEARN-04 P2 docs_only M(학습 루프 9단계·VersionRegistry). 선행 NX-AUTHENTICITY-01/04/05, NX-LEARN-02 |
| R1-27 | v3 §11.2 L494-506(신규 ID)·§10 L450-473 | FALSE | P2 | upheld | v3 의 QH-* ID 는 이전 v2 ID 와 번호는 같고 의미는 다르다. 이전 v2 의 QH-POL/SEC/DATA/INT/OBS/UI/OPS/AI-03/04 는 사유 없이 사라졌다. v3 §10 이 서술한 실공급자 데이터 어댑터와 KIS 모의 연결에 대응하는 v3 업무 ID 가 없다. v3 는 PG/SG/AP/ND 관문을 한 번도 언급하지 않는다. 이전 라운드 NX 목록은 이전 v2 ID 를 출처로 인용하므로 v3 ID 를 쓰면 매핑이 틀어진다. | 04812f4:…v2.md:828-847 — QH-PORT-01 유니버스·02 Builder MVP·03 Optimizer·04 Q24 연결·RES-01 백테스트·RES-02 매개변수 탐색·RES-03 몬테카를로·AI-02 Workflow Orchestrator·OBS-01 이벤트·UI-01·LEARN-01·OPS-01·POL-01·SEC-01·DATA-01 |
| R1-28 | v3 §11.1 L479-490·§9.2 L421-434 | CONFIRMED_AT_HEAD | P3 | not_checked | v3 가 '기존 계획에 이미 있는 업무'로 든 Q26/Q27, P28-01~08, P29-01/02, RETURN-01/02, 개발 팀/Skill 은 모두 큐 JSON 과 파일에 있다. 80403ab 에서도 계획 행으로는 있었다(상태는 pending). v3 §9.2 의 일부 표현은 큐 제목과 다르다. | 171e3e4:docs/tasks/product-delivery-queue.json — 12항목: P28-01~03 in_progress, P28-04~08·P29-01/02·RETURN-01/02 pending. 제목 P28-05 '전달·감시·백업 복원', P28-06 '로컬 조회 대시보드 구현', P28-08 '용량 기준·사용 안내·오류 해결' |
| R1-29 | v3 L4(기준선)·L559(§13 'HEAD SHA 기록')·L508·L563-568(§11.2·§13 우선순위) | PARTIALLY_TRUE | P2 | not_checked | v3 에 내부 모순과 순서 충돌이 있다. (a) 헤더는 기준선을 80403ab 로 고정하지만 §13 은 '현재 체크아웃된 main HEAD 를 SHA 로 기록'하라고 하고 그 HEAD 에서만 참인 Q27 수정을 '현재 존재'라 쓴다. (b) §3.3 은 80403ab 시점 status.md 를, §9.1 은 그 이후의 product-delivery-plan.md 를 근거로 쓴다. (c) §11.2 가 새 P1/P2 업무를 Q27 관문과 병렬 착수 가능하다고 쓰지만, 저장소가 병렬을 허용한 것은 이미 계획된 P28 준비뿐이다. | v3 L4 '코드 기준선: main 의 확인된 merge commit 80403ab' vs L559 '현재 체크아웃된 main HEAD 를 반드시 SHA 로 기록한다' vs L563 'Q27 pending holds 수정은 현재 존재한다' |
| R1-30 | v3 §3.3 L122-127(문서 정합성)·§9.1(P28-02 revision5 artifact_ready) — v3 가 놓친 불일치 | CONFIRMED_AT_HEAD | P3 | not_checked | v3 §3.3 의 문서 불일치 목록에는 없는 항목이다. P28-02 계약 문서 docs/contracts/product-read-v1.md:3 머리글은 'root revision5이며 독립 최종 확인 전이다'로 남아 있다. 계획·상태·증거 문서는 같은 revision5 가 독립 보안·일반 검토 지적 0 이라고 기록한다. v3 는 계획 문서만 근거로 artifact_ready 를 인용했다. | 171e3e4:docs/contracts/product-read-v1.md:3 — '상태: root 설계 초안… revision5이며 독립 최종 확인 전이다'. 마지막 수정 b745a28(2026-10-30) |
| R2-01 | PDF p.1 '기준과 방법' 지표표 + 요약 첫 단락(커밋 27·파일 184·+25,037/-105) | CONFIRMED_AT_HEAD | P3 | not_checked | PDF 수치(80403ab..5ff8e29 커밋 27, 변경 184파일 +25,037/-105, src 73개 19,141줄 -> 77개 20,855줄, 테스트 949 -> 1,067, docs 마크다운 1.33MB -> 2.29MB, docs/evidence JSON 300)는 읽기 전용 재측정으로 정확히 재현된다. 171e3e4 의 src/tests/docs 는 5ff8e29 와 동일하다. | git rev-list --count 80403ab..5ff8e29 = 27 (비병합 21 + 병합 6); git diff --shortstat 80403ab 5ff8e29 = 184 files, +25,037/-105 (정적 git 읽기) |
| R2-02 | PDF p.1-2 '코드로 해결된 것은 거의 없다·마지막 코드 커밋 2026-10-30·4개 파일 한 줄도 안 바뀜' | CONFIRMED_AT_HEAD | P2 | not_checked | main 기준 마지막 src·tests 커밋은 2026-10-30(ba5b52d)이고 application/target.py, domain/target.py, research/strategies.py, domain/research.py 는 80403ab 이후 0줄 변경이다(171e3e4 에서도 동일). 단 '포트폴리오·목표 코드는 바뀌지 않았다'는 문장은 도메인·응용 로직에 한정해야 맞다. adapters/synthetic_target.py 는 6c8786f 에서 영속 연결과 검증 함수 추출로 바뀌었다(목표 계산 로직은 불변). | git log -1 -- src tests @5ff8e29 및 @171e3e4 = ba5b52d 2026-10-30 feat(p28-03) (정적 git 읽기) |
| R2-03 | 레인 지시 1) 현재 main(171e3e4)과 5ff8e29 의 차이 | CONFIRMED_AT_HEAD | P3 | not_checked | 5ff8e29 -> 171e3e4 의 차이는 v2/ 교체 4파일뿐이다. 설계서 MD(1,033줄)와 첫 PDF 삭제, v3 재감사 MD(631줄)와 재분석 PDF 추가이며 src, tests, docs, config, migrations 는 한 줄도 다르지 않다. | git diff --name-status 5ff8e29 171e3e4: D v2/QuantHarbor_Integrated_Audit_Architecture_Agent_Skills_v2.md, A v2/QuantHarbor_main_reaudit_v3_2026-11-15.md, A v2/QuantHarbor_재분석_보고서_main_5ff8e29.pdf, D v2/QuantHarbor_전수조사_보고서.pdf |
| R2-04 | 레인 지시 1) 5ff8e29 와 171e3e4 차이 + 저장소 내 인용 점검 | CONFIRMED_AT_HEAD | P2 | not_checked | 171e3e4 가 삭제한 v2 원본(설계서 MD, 첫 PDF)을 저장소 문서가 여전히 입력 근거로 줄 단위 인용한다. 또 PDF 줄 번호 인용(audit_report.txt:NNN)이 가리키는 추출본은 저장소에 추적되지 않아 재현할 수 없다. | 171e3e4:docs/v2-work-list-2026-11-14.md:3,894,1057,1319 — 삭제된 v2/QuantHarbor_Integrated_Audit_Architecture_Agent_Skills_v2.md 와 v2/QuantHarbor_전수조사_보고서.pdf 를 입력·근거로 인용 |
| R2-05 | PDF p.3-5 '이전 지적 재판정표' 및 도입 문단(31개 중 해소 2·NX 24·비채택 5) | CONFIRMED_AT_HEAD | P3 | not_checked | 재판정표는 포트폴리오 P-1~P-11 11행, 인프라·연결 12행, 운영·문서 8행으로 총 31행이다. 해소 2행(status PR#1, Q27 replace_source), 비채택 5행(psql, arm64, 포매터, 금융 로직 검토자, KIS 모의 앞당기기), 나머지 24행이 NX 등록으로 집계되며 대응 NX ID 는 모두 v2-work-list 에 실재한다. 31이라는 총계는 PDF 자체 합산이고 저장소 문서에는 없다. | PDF p.3-5 표 행 수 직접 계수: P 11 + 인프라 12 + 운영 8 = 31; 상태 '해소' 2, '비채택' 5 |
| R2-06 | PDF p.3-5 재판정표 개별 행(P-4, Slack·대시보드, CLI, 상태·NX 대응) | PARTIALLY_TRUE | P3 | not_checked | 재판정표 행 단위 불일치가 있다. (a) P-4 를 '계약 변경 없이 운용 계층에서'라 했으나 work-list 는 NX-POLICY-07 의 계약 영향을 additive 로 적는다. (b) Slack·대시보드 행은 대응 NX 없이 '일부 진행'이고 실제 흡수처는 기존 큐 P28-05/06 이다. (c) CLI·스케줄러 행의 NX-POLICY-09/NX-OPS-INFRA-03 은 설계·스모크이고 실행 명령 구현은 기존 P28-03 내부 5·6 흡수다. 그래서 'NX 등록 24'에는 NX 가 아닌 흡수 3행 안팎이 섞인다. (d) 'PR#1 해소'는 맞지만 status.md 에 squash merge 계획 문구가 잔존한다. | 171e3e4:docs/v2-work-list-2026-11-14.md:261 — NX-POLICY-07 '계약 영향 additive'(PDF p.3 P-4 행은 '계약 변경 없이') |
| R2-07 | PDF p.4-5 재판정표 '해소' 2행(status PR#1, Q27 replace_source) | FIXED_AT_HEAD | P2 | upheld | 해소 2건은 정적으로 사실이다. 80403ab 의 replace_source 는 무조건 holds.pop 이었으나 171e3e4 는 pending 완료 예산이 있으면 보존한다(af40f9c). status 의 PR#1 미머지 표기는 정정됐다. 다만 Q27 실제 DB·전체 제품 PASS 는 8a27220 고정 소스 한정 증거이며 이번 판독이 재실행한 것은 아니다. | 80403ab:src/quantharbor/adapters/postgres_execution.py:540 — approval 무효화 직후 s['holds'].pop(identity,None) 무조건 해제 |
| R2-08 | PDF p.5-6 '이전 보고서의 오류 정정' 표 중 코드·문서로 확인 가능한 행(실제 표는 11행, 과제 문구의 '7행'과 다름) | CONFIRMED_AT_HEAD | P3 | not_checked | 정정표 11행 중 저장소로 확인 가능한 행은 맞다. P-2/3/4/7 은 target-local-v1 이 명시한 보수 계약이고 '검토자가 놓쳤다'는 서술은 부적절하다. P-4 현금 검사는 매도 비용 상한도 부담에 포함하며 매도 대금만 가용금에 안 들어간다. 합성 평가 24사례는 80403ab 에도 있었다. 역변동성 '1차 채택'은 같은 장의 '비교 후 사용자 채택'과 모순이다. 수치 파라미터는 근거 없는 후보값이고 일정은 완료 날짜 약속 금지 규칙과 어긋난다. | 171e3e4:docs/contracts/target-local-v1.md:29,31,35,37 — 자동축소·반대주문상계 금지·후보 1개라도 실패하면 전체 blocked, 미래 매도 전제 한도위반 해소 금지, 고정비+주당비용 상한, 미래 매도대금으로 매수 여력 불가 |
| R2-09 | PDF p.3,p.6 Q27 행·'Q27 미완료로 개발 중단' 정정·p.1 'Q27은 2주째 미완료' | CONFIRMED_AT_HEAD | P2 | not_checked | Q27 은 80403ab 와 171e3e4 모두 in_progress 이며 '중단'은 틀리다는 정정이 맞다. 완료 증거는 0건이다(q27_complete=true 없음, FUP-Q27-006 diagnosing, 009~014 queued). 10-30 의 17커밋은 80403ab(10-29 16:47) 이후의 별도 브랜치 작업이라 main 시점에서는 보이지 않았다. 10-30 이후 main 에 코드 커밋이 없다는 서술도 맞다. | 80403ab 및 5ff8e29:docs/tasks/offline-execution-queue.json — Q27 status in_progress, Q28 pending (정적 JSON 판독) |
| R2-10 | PDF p.6 정정표 '허용 폭 절대 ±5%p 또는 상대 25% 내부 모순(KR 40%를 10~15종목에 나누면 2.7~4%)' | PARTIALLY_TRUE | P2 | not_checked | 산술은 맞다(40/15=2.67%, 40/10=4.0%). 그러나 '내부 모순'보다는 '종목 단위에서 절대 5%p 기준이 구속력이 없다(하한은 음수, 상한은 평균의 약 2~3배)'가 정확하다. '또는'이 둘 중 하나면 상대 25%가 발동하고, '작은 쪽'이면 상대 기준이 지배하므로 어느 해석이든 절대 기준이 무력할 뿐 충돌하진 않는다. 구획 대 종목 단위가 미정이라는 지적은 맞다. | scratchpad audit_report.txt:564,575-576 — 종목 수 10~15, '월 1회 정기 + 허용 폭(절대 ±5%p 또는 상대 25%)', 구획·종목 구분 없음(첫 PDF 추출본) |
| R2-11 | PDF p.6 정정표 '마크다운 157개·1.3MB -> 163개·1,350,087바이트로 재측정' | PARTIALLY_TRUE | P3 | not_checked | 측정값은 맞지만 '이전 보고서의 오류'가 아니다. 첫 PDF 의 'docs/ 마크다운 157개 약 1.3MB'는 docs/ 한정 집계로 80403ab 에서 157개 1,334,165B 로 정확히 맞고, 163개·1,350,087B 는 저장소 전체 md(README, AGENTS, config 등 포함) 집계다. 저장소 문서가 UNVERIFIABLE 로 남긴 집계 범위 차이가 이로써 해소된다. | 80403ab:docs/**/*.md = 157개 1,334,165B; 저장소 전체 *.md = 163개 1,350,087B (git ls-tree + git cat-file -s 재측정) |
| R2-12 | PDF p.1 요약 4·p.6 N-1 '코드 진행이 멈추고 계획만 늘었다(출처: 신규)' | PARTIALLY_TRUE | P2 | not_checked | main 기준으로는 맞다(마지막 코드 10-30, 문서 +0.95MB). 그러나 전체 저장소 기준으로는 코드가 멈추지 않았다. 11-14 23:13 에 2b-2a 구현 커밋(src+tests +926줄)이 브랜치와 오픈 PR #7 에 있다. 문서 증가의 40%(+0.38MB)는 10-30 에 코드와 함께 늘었고 11-14 의 순수 분석·계획 문서는 +0.57MB 다. 문서 비대 자체는 저장소가 CRIT-15 로 이미 지적해 '신규'가 아니다. | origin/feat/p28-03-2b2a-wip: 396c85d 2026-11-14 23:13:22 feat(p28-03) AI 예산 factory·복구 core 구현(2b-2a, 수용 전); git diff --numstat ea76cb3 origin/feat/p28-03-2b2a-wip -- src tests = +926/-20 |
| R2-13 | PDF p.7 N-2 '실데이터가 계획의 맨 끝에 있다. 정책값은 합성 12시점 시뮬레이션으로 정하기 어렵다(출처: 신규)' | CONFIRMED_AT_HEAD | P2 | not_checked | 계획 구조 진단은 맞다. NX-DATA-02, NX-RESEARCH-02, NX-BROKER-02 는 W5 차단이고 W1~W4 는 합성·문서뿐이다. 비교 입력은 합성 12시점(24실행 골든)이며 저장소도 합성 결과를 전략 채택 근거로 쓰지 않는다고 못 박는다. 다만 이 긴장은 work-list 안에 이미 있고(ND-03 '값은 시뮬레이션 후', NX-POLICY-08 '합성은 채택 근거 아님'), 확정은 PG-03 사용자 선택 이후라서 '신규' 발견은 아니고 재진술이다. | 171e3e4:docs/v2-work-list-2026-11-14.md:59 W5 작업 NX-DATA-02, NX-RESEARCH-02, NX-TAX-COST-02, NX-BROKER-02, NX-LEARN-05, NX-AUTHENTICITY-07 |
| R2-14 | PDF p.7 N-3 '제품 시험 836개 6,801초, 실제 DB 86개 6,933초(약 3.8시간)·무작위·속성 기반 시험 0건·CI 없음' | PARTIALLY_TRUE | P2 | not_checked | 초 단위 수치와 0건 주장은 증거로 확인된다(6,800.646초, 6,932.892초, 8a27220 고정). 그러나 '약 3.8시간'은 두 실행의 합(13,733.5초)이고 시작 기록에서 두 실행이 동시에 RUNNING 이었으므로 벽시계 비용은 약 1.9시간에 가깝다. 이 시간은 Q27 최종 판정용 전체 실행 1회분이며 계약 변경마다 매번 물어야 하는 비용이라는 가정은 저장소 근거가 없다(집중 시험 3개는 519초). | docs/evidence/execution-final-current-product-2026-10-30.json:15 elapsed_seconds 6800.646, tests_run 836, base_commit 8a27220 |
| R2-15 | PDF p.7 N-4 '2b-2a 작업이 main 밖에 있다: feat/p28-03-2b2a-wip, src·tests 926줄' | CONFIRMED_AT_HEAD | P2 | not_checked | 171e3e4 main 에는 2b-2a 구현이 없다. 926줄(+20 삭제)은 4개 src·tests 파일의 증가분으로 정확하다. 현재 코드는 GitHub 오픈 PR #7 (head merge/qh-local-delivery-20261030, +1,459/-35, 18파일)에 있다. 그리고 PR #5 는 GitHub 상 MERGED 이지만 main 이 아니라 쌓은 base 브랜치로 병합돼 main 에 도달하지 않았다(PDF 가 언급하지 않은 함정). main 의 status.md 는 여전히 2b-2a 를 '아직 미실행'으로 적어 문서·코드 불일치가 이미 존재한다. | git merge-base --is-ancestor 396c85d main -> 아님; origin/feat/p28-03-2b2a-wip tip cb35adb, merge-base(main)=ea76cb3 |
| R2-16 | PDF p.7 N-5 'arm64 종속이 코드로 굳어졌다(출처: 신규)' 및 p.4 재판정표 arm64 '비채택' | CONFIRMED_AT_HEAD | P3 | not_checked | 사실은 맞다. product_database.py 는 이미지 Architecture 가 arm64 가 아니면 거부하고 새 compose 도 linux/arm64 고정이다. 둘 다 80403ab 에는 없던 신규 파일이다. 그러나 '신규'라는 출처 표기는 틀리다. 같은 사실이 저장소의 C2-17 과 work-list §6 에 edd018a 기준으로 이미 기록돼 있고, PDF 자신도 같은 항목을 재판정표에서 '비채택'으로 분류해 두 곳에서 다르게 취급한다. arm64 고정은 runtime/isolation.py, check_market_storage.py, CI 예시에도 오래전부터 있다. | 171e3e4:src/quantharbor/adapters/product_database.py:333 — self.image['Architecture'] != 'arm64' 이면 _deny('product_image_mismatch') |
| R2-17 | PDF p.7 N-6 'ClientIdentity 는 evaluation_kind=synthetic·model_id 없음만 허용, 마감·호출·가격 상한도 합성 기준' | CONFIRMED_AT_HEAD | P2 | not_checked | 코드로 확인된다. ClientIdentity 는 model_id: None 이고 spec 이 evaluation_kind 를 'synthetic' 하나로 고정한다. 예산 정책은 (input_rate, output_rate, fixed_call_cost)=(1,2,1) 만 허용하고 요청 호출 상한 4회, 시도 호출 1회, deadline-evaluated_at<=60초이며 응답은 dispatch 후 10초 이상이면 deadline 처리한다. 파일은 80403ab 이후 변경이 없다. | 171e3e4:src/quantharbor/domain/investment_ai.py:226-229 class ClientIdentity(invocation_id, evaluation_kind: str, model_id: None); :381 SPECS[ClientIdentity]=dict(...evaluation_kind=enum('synthetic'), model_id=absent) |
| R2-18 | PDF p.7 N-7 '실험 exploration_ref 고정 문자열, Hypothesis.assessment 를 바꾸는 코드가 없다' | CONFIRMED_AT_HEAD | P2 | not_checked | 코드로 확인된다. ExperimentRegistry 는 strategies·fit='none'·exploration_ref 가 상수와 일치해야만 통과하므로 시도 횟수가 기록되지 않는다. Hypothesis.assessment 는 enum 에 supported/refuted 가 있으나 src 에서 Hypothesis 를 생성하거나 assessment 를 설정하는 코드가 정의 외에 없다. | 171e3e4:src/quantharbor/domain/research.py:226 exploration_ref: str, :235 (strategies, fit, exploration_ref) != (STRATEGIES,'none','PG02:RESEARCH-DEC-001:fit-none') 이면 거부 |
| R2-19 | PDF p.7 N-8 'ai_state 128건 제한, 오래된 기록 정리 규칙 없음(0002_ai.sql)' | CONFIRMED_AT_HEAD | P2 | not_checked | 128건 제한과 정리 규칙 부재는 맞다. 단 저장소 문서의 '8MiB(0002_ai.sql:11-14)'는 부정확하다. SQL 은 checkpoint 를 32MiB 까지 허용하고 8MiB 는 Python 쪽 byte_capacity 상한이다. 그리고 128 은 레코드 수이며 보류 예약(holds) 1건이 3슬롯을 차지하므로 실효 용량은 더 작다. | 171e3e4:migrations/product/0002_ai.sql:13 record_count BETWEEN 0 AND 128; :31 processed marker 128 초과 시 예외; :58 records_count BETWEEN 0 AND 128 |
| R2-20 | PDF p.7 N-9 'README 현재 단계가 2026-10-20 ENV 구축 기준이고 합성 회귀 13개라고 적혀 있다' | CONFIRMED_AT_HEAD | P2 | not_checked | 사실이다. README.md:9 는 80403ab 이후 한 줄도 바뀌지 않았고 2026-10-20 ENV 단계, 합성 회귀 테스트 13개, '투자 시스템·실계좌 연결·주문은 아직 구현하거나 실행하지 않았다'를 적는다. 현재는 src 20,855줄, 테스트 1,067개, 합성 제품 DB가 있어 진입 문서가 현재 상태를 과소 서술한다. | 171e3e4:README.md:7-9 '현재 단계' 2026-10-20, 합성 회귀 테스트 13개, 투자 시스템 미구현 서술 |
| R2-21 | PDF p.7 N-10 '이용 범위·법적 경계 문서 없음(본인 계좌 단독 여부, 세무·법률 확인 시점)' | CONFIRMED_AT_HEAD | P2 | not_checked | 결정 문서로서는 없다. 본인 계좌 단독·타인 자금·투자자문 경계를 정한 문서는 vision/security/plan/status/requirements-input/decisions 어디에도 없고 관련 용어는 2026-11-14 v2 분석 3문서에만 있다. 단 follow-up 조사 §4 가 법 경계를 비결정 조사로 정리했고(변호사 확인 전 확정 금지) ND-09·NX-SECURITY-01 이 결정 대기 항목이다. | 171e3e4: docs README.md AGENTS.md config 전체에서 '본인 계좌·투자자문·투자일임·법적 경계·이용 범위' 검색 시 일치 파일은 v2-work-list, v2-claim-verification, v2-followup-research 3개뿐(정적 grep) |
| R2-22 | PDF p.8 'v2-work-list 평가' 위험 표(작업 53개 중 docs_only 25·합성 23·실제 연결 5, 결정 17개, W1 14개 대부분 문서) | CONFIRMED_AT_HEAD | P3 | not_checked | 수치는 work-list 와 정확히 맞는다. 작업 53개 gate 분포는 docs_only 25, synthetic_local 23, public_data 3, paper_broker 2(실제 연결 5)이고 ND 는 ND-01~16 과 ND-08b 로 17개다. W1 14개 중 docs_only 11개로 '대부분 문서'가 맞다. 다만 W1 의 8개는 크기 S 이고 P0·L 인 NX-BASELINE-01 은 문서가 아니라 Q27 실행 마감이라 '범위가 너무 많다'는 평가는 W1 에 한해 과장이다. | 171e3e4:docs/v2-work-list-2026-11-14.md:68-120 표 행 53개; gate 열 계수 docs_only 25 / synthetic_local 23 / public_data 3 / paper_broker 2; 유형 new_build 34·modify_existing 12·blocked 6·reuse 1; 우선순위 P0 2·P1 18·P2 27·P3 6 |
| R2-23 | PDF p.2 '무엇이 반영됐나' 표(ND 결정 16개) 대 p.1·p.6·p.8(17개); 레인 질문 status.md '16개' | CONFIRMED_AT_HEAD | P3 | not_checked | status.md 의 '사용자 결정 16개'는 work-list 와 불일치한다. work-list 는 ND-01~ND-16 + ND-08b 로 17개이고 REORDER 도 ND-05, 06, 07, 08b 로 4건인데 status.md 는 '16개·REORDER 3건'이라 적는다. ND-08b 추가가 반영되지 않은 것으로 보인다. PDF 도 p.2 표에서 '16개'를 그대로 옮겼다가 p.1·p.6·p.8 에서는 17개라 PDF 내부도 불일치한다. | 171e3e4:docs/status.md:7 'NX 작업 53개와 사용자 결정 16개 ... 순서 변경(REORDER 3건)'; 5ff8e29 도 동일 |
| R2-24 | PDF p.8 위험 표 '문서 증식: 1,345줄 작업 목록·384줄 검증 기록·1,033줄 설계서가 한날 추가, 상태 문서는 945줄' | PARTIALLY_TRUE | P3 | not_checked | 줄 수는 모두 맞다(1,345 / 384 / 1,033 / 945). 그러나 1,033줄 설계서는 저장소 팀이 만든 문서가 아니라 분석 대상 원본(입력)을 보존한 것이라 '증식'에 넣는 것은 부적절하다. 더구나 171e3e4 에서 삭제돼 현재 트리에는 없다. 상태 문서는 805줄(118,540B)에서 945줄(149,123B)로 늘었다. | wc -l: docs/v2-work-list-2026-11-14.md 1,345, docs/research/v2-claim-verification-2026-11-14.md 384, docs/research/v2-followup-research-2026-11-14.md 129(PDF 미언급), docs/status.md 945 |
| R2-25 | PDF p.5 재판정표 '로컬 절대경로 노출: 문서 16개에 121회 남아 있음(이전 18개·128회)' | PARTIALLY_TRUE | P2 | not_checked | 121회·16개는 '/Users/' 일반 패턴으로 md 만 센 값으로 재현되지만 감소가 아니다. 실제 로컬 사용자 경로는 80403ab, 5ff8e29, 171e3e4 모두 18개 파일 128회(md 15개 115회 + 증거 JSON 3개 13회)로 불변이다. 121에는 v2-claim-verification 이 패턴을 설명하며 쓴 자리표시자('/Users/<사용자>') 6회가 섞였고, PDF 는 이전 값(전 파일 범위)과 현재 값(md 한정)의 범위를 바꿔 비교했다. 가정 '이전 18->16 해소'는 거짓이다. | git grep -o '/Users/' 5ff8e29 -- '*.md' ':(exclude)v2' = 16개 파일 121회(PDF 와 일치); 같은 명령을 전 파일에 적용하면 19개 134회 |
| R2-26 | PDF 전체 내부 일관성(p.1, p.2, p.6, p.7, p.9) | CONFIRMED_AT_HEAD | P3 | not_checked | PDF 에는 내부 불일치와 표기 오류가 있다. (1) ND 16개(p.2)와 17개(p.1·6·8). (2) p.1·N-1 '코드가 멈췄다'와 N-4 '11-14 구현 926줄 존재'. (3) p.9 '아래 4개가 정해져야'라면서 표는 5행(ND-01~04 + ND-08). (4) 정정표는 11행인데 요약 지시와 질문은 7행으로 센다. (5) N-5 를 '신규'로 표기하면서 같은 항목을 p.4 에서 '비채택'으로 분류했다. (6) 인용한 '이전 PDF 31개' 총계의 원문 근거 표가 없다. | PDF p.2 'ND 결정 16개' vs p.1 요약 1 '사용자 결정 17개'(R2-23) |
| R2-27 | PDF p.9 권장 순서 1 '2b-2a 브랜치 정리를 끝내야 계약 개정(W2)이 풀린다' | PARTIALLY_TRUE | P3 | refuted | 의존 관계 오독이다. work-list 에서 계약 개정(NX-POLICY-02/04, NX-TAX-COST-01 등)을 푸는 선행은 NX-BASELINE-01(Q27 마감)이고, 2b-2a 수용(NX-BASELINE-02)이 선행인 작업은 NX-LEARN-02 하나뿐이다. 따라서 2b-2a 수용은 계약 개정이 아니라 학습 원장 저장 결정과 시도 원장 사슬(LEARN-02 -> AUTHENTICITY-02)의 선행이다. | 171e3e4:docs/v2-work-list-2026-11-14.md:108 NX-LEARN-02 선행 NX-BASELINE-02(표에서 BASELINE-02 를 선행으로 가진 유일한 행) |
| R2-28 | PDF p.8-10 위험·권장 3 'PortfolioConstructor 는 Q27 과 병행'·'2번과 3번은 ND-05·ND-06 의 앞당김 선택지와 방향이 같다, 채택은 사용자가 정하면 된다' | PARTIALLY_TRUE | P2 | not_checked | 일부만 맞다. 순수 함수·additive 라서 Q27 뒤일 필요가 없다는 기술적 지적은 합리적이다(NX-BASELINE-01 은 위험 의미 변경 계약만 막는다). 그러나 (a) NX-PORTFOLIO-01 은 정책 스키마(NX-POLICY-02/03)와 ND-01·ND-16 값이 필요하고, (b) team.toml 과 AGENTS.md 는 활성 worker·작성자 1명 순차 운영이라 '병행'은 규칙 개정 없이는 못 하며 PDF 는 이를 다루지 않는다, (c) ND-05·ND-06 은 이미 11-14 사용자 위임으로 채택됐고 범위가 문서·설계 한정(ND-06 은 합성 설계만)인데 PDF 는 이를 읽지 않은 채 '사용자가 정하면 된다'고 썼다. | 171e3e4:docs/v2-work-list-2026-11-14.md:84 NX-PORTFOLIO-01 선행 NX-POLICY-02, NX-POLICY-03, NX-BASELINE-01; :316 사용자 결정 ND-01; :791 ND-16 이 NX-PORTFOLIO-01 을 막음 |
| R2-29 | PDF p.9-10 권장 2(읽기 전용 실데이터 스파이크, ND-03 값의 근거)·ND-08 '지금 허용' 의견·권장 5(시도 원장은 나중) | PARTIALLY_TRUE | P1 | upheld | 실데이터 스파이크 권고는 현재 근거로는 안전하지 않다. (1) 저장소의 약관 조사가 Yahoo·KRX 계열은 자동 수집·무허락 복제를 금지한다고 기록했으므로 '읽기 전용·격리·재배포 없음'만으로 ND-08 을 지금 허용하기엔 부족하다(원문 확인은 미완료·전문가 확인 필요). (2) ND-06 은 합성 한정이므로 실데이터 스파이크를 ND-05/06 의 방향과 같다고 볼 수 없고 SG-02 데이터 권리 관문이 남아 있다. (3) PDF 가 ND-03 값을 실데이터로 정한다면 그것이 시도 반복의 시작인데, 시도 원장은 권장 5 로 뒤에 둔다. 자기 논리(시도 횟수는 실험 첫날부터 필요)와 순서가 어긋난다. MarketFetchPort 와 Parquet 저장소가 있다는 전제는 맞다. | 171e3e4:docs/research/v2-followup-research-2026-11-14.md:48-53 §3 — OpenDART 키 제3자 이용 금지, Yahoo '자동 수집·상업 이용·무허락 복제 금지(일부만 읽음)', KRX '자동화 수집·복제·배포 금지(약관 미확인 부분)', LLM 입력은 대부분 침묵 |
| R2-30 | PDF p.8-9 권장 4(계약 개정 한 묶음)·ND 표 'ND-04 가장 급하다'·'양이 너무 많다' | PARTIALLY_TRUE | P3 | not_checked | PDF 평가에는 이미 계획된 것을 새 제안처럼 쓴 부분과 근거 없는 긴급성 표현이 있다. (a) reduce-only, 비율 비용, 다중 실패를 한 schema_version 으로 묶자는 권장 4 는 work-list 의 NX-TAX-COST-01 이 이미 'NX-POLICY-04 와 같은 schema_version 묶음으로 통합'한다고 적었다. (b) 'ND-04 가장 급하다. 낙폭 한도를 넘으면 줄일 방법이 없다'는 합성 단계라 운용 노출이 없어 실제 긴급성이 아니라 NX-BROKER-02(paper 개방)의 선행 조건으로서의 중요성이다. (c) 'W2 대부분이 Q27 판정에 묶였다'는 W2 13개 중 직접 7개, 전이 8개로 대체로 맞다. | 171e3e4:docs/v2-work-list-2026-11-14.md:386 NX-TAX-COST-01 '큐 위치: PG-01 모의 연결 전. NX-POLICY-04 와 같은 schema_version 묶음으로 통합한다' |

## 12. 문서 증식 감사 (R4)

PDF의 N-1(계획이 실행보다 빠르게 늘어남)과 N-9(진입 문서가 낡음)는 둘 다 정적 측정으로 사실로 확인됐다. 둘 다 읽기 전용 명령으로 확인했고 테스트·게이트는 돌리지 않았다. (1) 증식: main 의 코드(src·tests·scripts·config·migrations·containers)는 2026-10-30(ba5b52d) 이후 16일간 변하지 않았다. 그 사이 docs/*.md 는 157개에서 206개로(+49), 1,334,165B 에서 2,287,073B 로(+952,908B, +71.4%) 늘었다. PDF 의 '0.96MB'는 0.95MB 와 거의 일치한다. 11-14 하루에 들어온 문서 3건(작업 목록·검증 기록·후속 조사, 1,858줄, 572,365B)이 증가분의 60.1%다. 바이트 기준 docs 증가는 src+tests 증가의 4.9배다. (2) 진입 문서: AGENTS.md 필독 4문서는 188,046B(1,409줄)이고 status.md 가 그중 79.3%다. status.md 는 헤더 기록 기준일이 10-30인데 본문 최신 기록은 11-14다. '현재 우선 지시' 제목이 2개, 본문에 '현재' 단정이 3곳 더 있다. 구성은 신규순 블록 → 고정 섹션 → 역순 블록 → 시간순 로그가 섞여 있고, 69.3%(694줄)가 10-27 이전 과거 로그다. README 는 2026-10-20 단계와 '합성 회귀 13개'를 그대로 두고 있으며 80403ab 이후 한 글자도 바뀌지 않았다. 새로 발견한 구조 문제는 다섯 가지다. 첫째, scripts/check_quality.py 의 classify() 를 직접 호출하니 v2/ 의 MD 는 unclassified_candidate, 한글 이름 PDF 는 unsafe_path 로 거부됐다. 전체 게이트는 돌리지 않았지만, main 의 공개 후보 게이트는 v2/ 때문에 fail 일 가능성이 높다. 둘째, .github/workflows 는 어느 SHA·브랜치에도 없고 classify() 가 그 경로를 protected_path 로 막는다. 셋째, 새 v2 두 문서(v3 MD·새 PDF)는 어떤 문서에서도 링크되지 않는다. 반면 작업 목록·검증 기록은 이미 트리에서 삭제된 이전 v2 MD 를 경로:줄로 인용한다. 넷째, 후속 조사 §8 의 위임 판단(ND-05·06·07·08b)이 작업 목록에는 아직 '사용자 결정 필요'로 남아 있다. 다섯째, status.md 의 '사용자 결정 16개'는 실제 17개와 다르다. 정리안은 삭제·이동보다 추가(현재 표)·동결·파생을 우선한다. 증거 JSON 300개는 242개 파일이 참조하고 baseline-v1.json 이 문서 7개의 해시를 고정하며 status.md 경로는 hook·skill·정책에 하드코딩돼 있어, 이동 계열 정리는 제약이 크다. 다음 항목은 모두 정적 측정이다. 확인 못 한 것은 unchecked 에 남겼다.

| 지표 | 값 | 방법 |
|---|---|---|
| docs/*.md 개수·총 바이트 (80403ab → 5ff8e29 = 171e3e4) | 157개 / 1,334,165B → 206개 / 2,287,073B (+49개, +952,908B, +71.4%). 저장소 전체 md 는 163개 / 1,350,087B → 213개 / 2,345,496B(171e3e4; 5ff8e29 는 2,364,284B). 5ff8e29 와 171e3e4 의 docs 트리는 동일하다(diff 는 v2/ 4파일뿐). docs 하위별 md: research 23→51개(268,545→649,848B), docs 루트 18→21개(315,928→709,738B), tasks 47→56, contracts 16→19, decisions 32→34, development 19→20, product 0→1, templates 2→4 | python3 -I 로 git ls-tree -r -l -z <SHA> 를 NUL 파싱(한글 경로 인용 문제 회피). 정적 측정, 실행 없음 |
| docs 전체 파일·바이트 / 줄수 / 코드 줄수 | docs 전체 379개 / 3,621,176B → 529개 / 5,162,133B (+150개, +1,540,957B, +42.6%). docs md 줄수 10,070 → 14,599 (+4,529, +45.0%). src .py 줄수 19,141 → 20,855 (+9.0%), tests .py 줄수 17,044 → 19,101 (+12.1%). src 파일 73→77개, tests 79→82개 | git cat-file blob 으로 줄 수 집계(80403ab vs 171e3e4) |
| git diff --numstat 80403ab..171e3e4 요약 (184개 파일) | src +1,742/-28 (11개), tests +2,079/-22 (7개), scripts +94/-8 (2개), migrations +152 (2개), containers +44 (1개), docs/*.md +4,566/-26 (56개), docs/evidence +12,329 (98개 신규), docs 기타(큐 JSON·acceptance-matrix·wireframes html) +2,998/-21 (5개), v2 +631 (5ff8e29 기준 +1,033). 5ff8e29→171e3e4 구간은 v2/ 4파일(+631/-1,033)만 바뀜 | git diff --numstat -z 를 최상위 디렉터리별로 python3 -I 집계 |
| 문서 대 코드 증가 비율 (N-1 검증) | 바이트 기준 docs md +952,908B 대 src+tests +196,377B(src +89,729B, tests +106,648B)로 4.9배. 줄 기준 md +4,566줄 대 src+tests +3,821줄(약 1.2배). 단 md 는 줄이 길다(작업 목록 평균 약 223B/줄). PDF 의 '문서 약 0.96MB 증가'는 0.95MB(952,908B)와 거의 일치. 정확한 정의는 PDF 에서 확인 불가(UNVERIFIABLE) | 위 두 집계의 차. 판정은 '일치'이며 PDF 정의는 추정 |
| 코드 마지막 변경 / main 이후 커밋 성격 (N-1 검증) | src·tests·scripts·config·migrations·containers 의 마지막 변경은 ba5b52d(2026-10-30). edd018a..main 사이 코드 diff 는 0줄(변경 파일 6개는 docs 4 + v2 2). 80403ab..main 비병합 커밋 22개는 10-30 17개, 11-14 4개, 11-15 1개. 10-30→11-15 는 16일이며 이후 커밋은 모두 docs/v2 다. PDF 의 '10-30 이후 코드 커밋 없음'은 사실 | git log -1 -- <코드경로>, git diff --stat edd018a main -- <코드경로>(출력 없음), git log --no-merges 80403ab..main |
| 11-14 하루 추가 문서 3건의 비중 | v2-work-list 1,345줄 / 299,837B, v2-claim-verification 384줄 / 251,767B, v2-followup-research 129줄 / 20,761B. 합 1,858줄 / 572,365B 로 docs md 증가분(952,908B)의 60.1%. 상위 3대 문서(work-list·verification·status)는 합 700,727B 로 docs md 의 30.6%. 세 문서는 모두 2026-11-14 커밋(3e5798d·5022d00·78d8182) | wc, git ls-tree 크기, git log 날짜 |
| 가장 큰 문서 상위 15개 (docs/*.md, 171e3e4, 바이트) | 1 v2-work-list-2026-11-14 299,837 / 2 research/v2-claim-verification 251,767 / 3 status.md 149,123 / 4 development/execution.md 51,366 / 5 execution-checklist.md 40,486 / 6 team-work-list.md 38,836 / 7 plan.md 31,739 / 8 research/oss-application-plan.md 31,188 / 9 contracts/product-read-v1.md 31,025 / 10 research/execution-storage-design-input-2026-10-25 30,448 / 11 research/execution-design-input-2026-10-25 30,137 / 12 tasks/EXECUTION-resume-2026-10-29 27,822 / 13 tasks/EXECUTION-local 27,146 / 14 development/cmux-team-analysis-2026-10-29 25,653 / 15 development/target 24,731 | python3 -I 로 git ls-tree 크기 내림차순 |
| 날짜 접미사 문서 수 | 파일명에 YYYY-MM-DD 를 가진 docs md: 22개 → 57개(206개의 27.7%, 963,784B = md 바이트의 42.1%). 날짜 접미사 파일 전체 358개 = md 57 + evidence JSON 293 + research JSON 8. 신규 날짜 md 의 분포는 10-30 27개·10-29 7개·11-14 3개 | 정규식 20\d\d-\d\d-\d\d 를 파일명에 적용(171e3e4 트리) |
| docs/evidence JSON 수·바이트·참조 | 202개 / 1,414,403B → 300개 / 1,852,745B (+98개, +438,342B). 신규 98개는 전부 2026-10-30 접미사다. 중앙값 1,899B, p90 12,855B, 최대 165,741B(execution-control-partial-2026-10-25). 다른 파일에서 이름이 참조되는 증거 287개, evidence 외 문서가 참조하는 증거 242개, 그중 큐 JSON 참조 132개, status.md 참조 138개, md 참조 213개. 어디서도 참조되지 않는 증거 13개(83,169B) | git ls-files + basename 부분문자열 역참조(오탐 가능성 있음). 정적 |
| docs/status.md 크기 추이 | 80403ab 805줄 / 118,540B → 5ff8e29·171e3e4 945줄 / 149,123B (+140줄, +30,583B, +25.8%). 중간값은 edd018a 937줄 / 147,198B, ea76cb3 943줄 / 148,823B, 4879a09 945줄. 작업 목록 NX-DOCS-PROCESS-01 의 '943줄 148,613B'는 현재 main 과 다름. ## 섹션 119개(날짜 포함 111개). 가장 긴 줄 826B | git show <SHA>:docs/status.md / wc -lc, python3 -I 구간 집계 |
| status.md 구간 구성 (171e3e4) | L1-4 제목 204B(0.1%) / L5-11 11-14 v2 블록 1,924B(1.3%) / L13-114 '현재 우선 지시 10-30'+실제 실행 관측 23,046B(15.5%) / L116-162 10-29 지시·이전 지시·목록·분석·통합 당시 기록 8,024B(5.4%) / L163-250 고정 섹션(합의·완료·진행 중·미착수·미결정·다음 작업·세션·갱신 형식) 12,633B(8.5%) / L252-338 10-23~10-19 역순 블록 17,425B(11.7%) / L339-945 10-20~10-27 시간순 로그 85,864B(57.6%). 과거 로그(L252-945)는 694줄 / 103,289B 로 69.3%. 날짜 헤더 순서가 4번 뒤바뀌어 '맨 위=최신'이 성립하지 않음 | python3 -I 줄 구간별 바이트 집계 + 헤딩 날짜 순서 점검 |
| status.md '현재 우선 지시' 구간 수와 '현재' 단정 위치 | '현재 우선 지시' 제목 2개(L13 10-30, L116 10-29), '이전 지시' 1개(L125), '당시 기록' 제목 1개(L155). 11-14 블록(L5)은 라벨 없음. '현재' 위치 단정은 L19(P28-03 2b-1 납품, 다음 2b-2a 미실행) / L196('현재 Q19 실제 연결 대기·Q27 집중검증', 10-27 시점) / L233('현재는 Q27→Q28→Q29 진행') 3곳이 더 있음. 기록 기준일(L3)은 2026-10-30, 본문 날짜 중 최신은 2026-11-14(L5), 마지막 커밋은 11-14 병합(4879a09) | grep -n 및 python3 -I 날짜 추출 |
| AGENTS.md 필독 문서 총량 | 무조건 필독 4개(status 149,123B + vision 3,606B + plan 31,739B + security 3,578B) = 188,046B / 1,409줄 / 101,309자, 이 중 status.md 가 79.3%(문자 기준 81.2%). 80403ab 에서는 status 118,540 + vision 3,606 + plan 30,787 + security 3,578 = 156,511B 였음(+20.2%). 조건부 지명: ai-environment 5,559B + architecture 4,797B(합 10,356B). 개발 환경 정본으로 지명된 development-environment 13,617B + ENV-bootstrap 5,246B(합 18,863B). 기타 인용: ai-team 13,882B, templates 2종, execution-queue.json. 지명 경로 합계 278,376B(AGENTS+README 포함). '조사 문서'는 목록이 없고 docs/research 는 51개 / 649,848B. SessionStart hook 도 status.md 읽기를 매 세션 상기시킴 | wc -lc, python3 -I 문자 수. 모델 토큰 수는 측정 불가(UNVERIFIABLE) |
| 작업 레지스트리 수치(큐 JSON 집계 = 문서 수치 일치 여부) | 실행 큐 36개(completed 18·pending 17·blocked 1, current=Q19) / 로컬 큐 10개(completed 7·in_progress 1·pending 2, current=Q27) / 제품 큐 12개(completed 0·in_progress 3·pending 9, current=P28-03) / 후속 큐 28개(resolved 20·queued 7·diagnosing 1) / 체크리스트 ID 110개(중복 없음, 큐 36개가 110개 전체 포괄). status.md·team-dashboard.md·failure-followup-queue.md 의 수치와 JSON 집계는 일치. NX 53개(docs_only 25·synthetic_local 23·public_data 3·paper_broker 2; P0 2·P1 18·P2 27·P3 6)와 ND 17개(ND-01~16+ND-08b)는 마크다운에만 있고 JSON 큐가 없음. 큐 JSON 3종(offline·product·followup)이 80403ab 이후 바뀜. execution-queue.json 은 불변 | python3 -I json 집계, 체크리스트 정규식은 scripts/check_ai_team.py 와 동일, grep -c '^- \*\*ND-' |
| 마크다운 링크 상태 (정적) | md 213개의 코드 블록 밖 상대 형식 링크 1,058개 중 943개가 해석됨(:줄번호 접미는 제거 후 검사). 115개는 사용자 홈 절대경로 링크로 15개 md 에 있음(다른 머신 경로). 해석 불가 상대 링크 0개. 외부 URL 263개와 앵커는 미검사. 앵커 링크 status.md#… 는 0개 | python3 -I 정규식 링크 추출 + os.path.exists. 작업 트리 기준(171e3e4) |
| 사용자 홈 절대경로 노출 | @171e3e4 '/Users/' 포함 134회 / 19개 파일(검증 기록 자체 6회 포함). 작업 목록 편입 후 제외하면 128회 / 18개 파일(md 15개 115회 + evidence JSON 3개 13회)로 80403ab·5ff8e29 와 같음. 단위가 다른 세 숫자가 공존함: 128회(발생), 81줄(grep -c 합), PDF 의 121(md만 발생 수, 검증 기록 6회 포함). 모두 한 개의 사용자 홈 접두사. 별도로 /private/tmp·/home 임시경로 238회(evidence JSON 위주) | git grep -o -I '/Users/' <SHA> 로 SHA별 재현 |
| 공백·형식 검사 현황 | git diff --check 80403ab 171e3e4 (v2 제외): trailing whitespace 22건 / 5개 파일(research 4개 + team-work-list 1개, 마크다운 강제 줄바꿈 두 칸으로 보임). 작업 트리 md 중 줄 끝 공백 63줄 / 11개 파일. v2/ 는 0건 | git diff --check, python3 -I 줄 끝 공백 계수 |
| CI 워크플로 존재 여부 | .github/ 항목 0개: 80403ab·5ff8e29·171e3e4 트리와 origin/codex/qh-local-delivery-20261030·origin/feat/p28-03-2b2a-wip 에서 모두 0. 유일한 CI 정의는 config/ci/quality.workflow.example.yml(주석에 'inactive template', workflow_dispatch 전용, timeout-minutes 15, runs-on ubuntu-24.04-arm). 문서 기록상 제품 836개 6,800.646초와 실제 DB 86개 6,932.892초(약 113분)는 이 15분 제한과 양립하지 않음(NX-OPS-INFRA-01 이 이미 지적). 실제 GitHub 원격 상태(PR #7·Actions)는 이 읽기 범위에서 확인 못 함 | git ls-tree -r --name-only <SHA> / grep '^\.github/', 예제 파일 정적 판독 |
| scripts/ 문서·저장소 검사 도구의 검사 범위 | check_quality.py(601줄): 공개 후보(git ls-files --cached --others)의 경로 분류·보호 경로, 파일 형식·크기(파일당 1MiB·총 16MiB·4,096개), UTF-8·제어문자, 비밀 패턴 6종, Python 문법과 domain import·IO 경계, baseline-v1.json 의 문서 7개 SHA-256 고정, runtime-lock·Dockerfile·compose·CI 예제 드리프트. 마크다운 링크·절대경로·공백·상태 정합성·README 날짜는 검사하지 않음. check_ai_team.py: 팀 설정 + execution-queue.json + 체크리스트 110개 ID + 승인 목록 + 증거 파일 존재(절대경로·'..' 거부). 나머지(check_execution·check_ledger·check_foundation·check_isolation·check_market_storage·validate_*·run_local_check·bootstrap_paper_storage·qh_hook_audit)는 DB·Docker·권한·Hook 검사이며 문서 검사 아님. 링크·공백 검사는 작업 카드에 적힌 일회성 스크립트와 git diff --check 로 수행돼 왔고 저장소에는 없음 | scripts/*.py 정적 판독(check_quality.py:36-136,316-335,458-523,542-583) |
| check_quality classify() 실제 호출 결과 (실행 확인, 부분) | python3 -I -B 로 모듈을 import 해 classify() 만 호출(파일·git 접근 없음, __pycache__ 미생성, git status clean 유지): v2/QuantHarbor_main_reaudit_v3_2026-11-15.md → unclassified_candidate / v2/QuantHarbor_재분석_보고서_main_5ff8e29.pdf → unsafe_path(비ASCII 이름) / .github/workflows/ci.yml → protected_path / docs/archive/*.md·scripts/check_docs.py·docs/evidence/*.json → 통과. 전체 inspect_repository 는 실행하지 않았으므로 '게이트 fail'은 추정이다 | importlib 로 classify 만 호출. 전체 게이트·단위시험 미실행 |
| 자동 검사 접점·제약 | 저장소 총 추적 바이트 8,812,873B(740파일)로 check_quality 총량 한도 16,777,216B 의 52.5%. v2/ 를 제외하면 약 7.9MB(47%)이고 한도 대비 약 8.9MB 여유 — 증가 속도는 추정 불가. baseline-v1.json 이 해시 고정한 문서 7개(architecture.md, contracts/serialization-v1.md, implementation-backlog.md, ARC-DEC-004, contracts/data-v1.md, contracts/execution-v1.md, contracts/operations-v1.md)는 편집 금지. docs/status.md 경로는 development-policy.toml:31·.codex/agents/*.toml·SKILL.md·qh_hook_audit.py REMINDER 에 하드코딩. hooks.json 은 qh_hook_audit.py 의 SHA-256 을 고정하므로 hook 은 수정 불가. status.md:줄번호 인용 45회 / 7개 파일(검증 기록 38회) | python3 -I 추적 파일 크기 합, grep, 정적 판독 |
| 진입 문서 도달성 | README 문서 표는 docs 22개만 링크(전체 206개의 10.7%)하며 v2 문서 3종·team-work-list·contracts·product 는 없음. 작업 목록·검증 기록·후속 조사는 status.md 만 링크함(plan.md·README·AGENTS 에는 링크 없음). v2/ 의 v3 MD 와 새 PDF 는 docs·README·AGENTS 어디에서도 참조되지 않음(0건). README·AGENTS·plan·status 가 직접 참조하는 docs md 는 71/206. 인바운드 0인 md 는 2개(tasks/PRODUCT-delivery.md, PRODUCT-gap-review.md, basename 기준 약한 신호) | python3 -I 역참조 집계 |
| 문서 간 중복(의미 중복 근사) | 작업 목록과 검증 기록은 문장 중복이 거의 없고(8단어 shingle 겹침 8개, 0.0%) ID 단위로 연결됨: 검증 기록의 finding·출처 ID 148개 중 134개(90.5%)를 작업 목록이 재인용. 즉 중복이라기보다 상호 색인이며 하나만 읽어서는 근거에 닿지 못함. 이전 v2 MD 와 v3 MD 는 전면 재작성이라 문장 겹침 0% | python3 -I 정규식·shingle. 의미 판독은 하지 않음 |
| v2/ 디렉터리 변화 (트리) | 5ff8e29: 이전 v2 MD 1,033줄 61,289B + 첫 PDF 1,645,400B = 1,706,689B → 171e3e4: v3 MD 631줄 42,501B + 새 PDF 870,329B = 912,830B(트리 -793,859B). 이전 MD·PDF 는 git 이력(04812f4, 5ff8e29)에 보존. 저장소 pack 1.62MiB(첫 PDF 포함) | git ls-tree -l, git count-objects -vH |
| 브랜치별 상태 기록 분기 | main 의 status.md 는 945줄. origin/feat/p28-03-2b2a-wip(main 보다 2커밋 앞, 7커밋 뒤)은 949줄이며 상단 '현재 우선 지시'·큐 JSON·dashboard 를 갱신했고 검증 기록 문서는 없음. 브랜치 대 main 의 src +340/-19, tests +586/-1 로 추가 926줄(PDF N-4 의 926줄 일치). status.md 상단과 큐 JSON 이 양쪽에서 갱신돼 병합 시 충돌 가능. 로컬 codex/qh-local-delivery-20261030 은 main 보다 5커밋 앞서고 이전 v2 MD·PDF 를 다시 추가하는 cef6a5e('v2 전수조사')를 포함해 main 의 171e3e4(같은 제목, 삭제·교체)와 충돌함. PR #7 이 어느 브랜치인지는 로컬만으로 확정 불가 | git rev-list --count, git diff --numstat main origin/…, git log main..<branch> |
| 정적 시험 정의 수 (참고, 실행 아님) | def test_ 정의 수: 80403ab 949개(tests/product 782) → 171e3e4 1,067개(tests/product 898). 898 = 문서 기록 836 + P28-03 집중 62 와 일치하는 정적 합. README 의 '합성 회귀 테스트 13개'는 2026-10-20 값이며 통과 여부는 실행하지 않아 확인 못 함 | git grep -c -E '^[[:space:]]+def test_'. 실행 없음 |

### 문서 간 수치 불일치

- 사용자 결정(ND) 개수: 문서=status.md:7 '사용자 결정 16개'(NX 53개와 함께) / 실제=v2-work-list §4 는 ND-01~ND-16 + ND-08b = 17개이고 PDF 도 17개. NX 53개는 일치. status.md 수치만 stale(ND-08b 추가 전 값). 작업 목록 자체에는 개수 표기가 없어 17개는 목록 줄 수 계수로만 확인됨
- 문서 수 157개 / 163개: 문서=PDF: '마크다운 157개·1.3MB' 를 '163개·1,350,087바이트로 재측정' / 실제=둘 다 80403ab 에서 재현된다. 157개 / 1,334,165B = docs/*.md, 163개 / 1,350,087B = 저장소 전체 md. 집계 범위만 다르고 모순이 아니다. 현재(171e3e4)는 docs 206개 / 2,287,073B, 전체 213개 / 2,345,496B 이므로 두 숫자 모두 현재 값으로는 낡음
- status.md 의 기록 기준일과 기준 SHA: 문서=L3 '기록 기준일: 2026-10-30'. L7 'HEAD edd018a 기준 정적 분석'. L9 '분석·조사 PR 의 merge 여부는 검토자 결정', '원 작업 브랜치의 17커밋은 별도 병합 PR 로 올리며' / 실제=본문 최신 기록은 2026-11-14(L5)이고 마지막 status 커밋도 11-14 병합이다. main 은 171e3e4(11-15)이며 PR #2·#3·#4·#6 이 이미 병합됨(edd018a 는 ea76cb3 로 main 에 들어옴). 11-15 의 v2 교체(171e3e4), 5ff8e29 기준 PDF, v3 MD 는 status.md 에 기록되지 않음. L9 의 PR 서술은 현재 main 과 어긋남
- README 현재 단계: 문서=README.md:9 '2026-10-20 개발 AI 환경을 순차 구축 중… 합성 회귀 테스트 13개… ENV 잔여 조건은 진행 중… 투자 시스템… 아직 구현하거나 실행하지 않았다' / 실제=status.md:181 은 ENV Q01~06 명시 범위 완료로 기록한다. 코드는 src 77개 .py / 20,855줄, 정적 def test_ 1,067개(tests/product 898), 합성 원장·목표·승인·실행·제품 DB 구현이 있고 문서 기록상 제품 836개·실제 DB 86개 PASS(8a27220 한정, 이번에 재현 안 함). README 는 2bed4c4(10-23) 이후 한 번도 바뀌지 않아 80403ab 와 동일(PDF N-9 와 v3 §3.3 확인). 실계좌·주문 미구현이라는 문장 자체는 여전히 참
- 개발 환경 실제 상태 정본의 시점: 문서=AGENTS.md:14 가 development-environment.md 와 ENV-bootstrap.md 를 '현재 개발 환경의 실제 상태' 정본으로 지명. development-environment.md:3 '최신 갱신: 2026-10-23… 투자 애플리케이션 구현 전이다' / 실제=두 파일 마지막 수정은 3c7f22a(2026-10-29)이고 문구는 10-23 상태. 이후 Q20~Q27·P28-01~03 의 합성 구현·증거가 있어 '구현 전'은 당시 기록. 갱신 책임자와 라벨(당시 기록)이 없음
- status.md 의 '현재'가 가리키는 위치: 문서=L13 '현재 우선 지시 10-30'(P28-03 2b-2a 배정 준비), L116 '현재 우선 지시 10-29'(Q27 보존분), L196 '현재 Q19 실제 연결 대기·Q27 집중검증', L233 '현재는 Q27→Q28→Q29 진행'. 큐 JSON 의 current 는 execution-queue Q19 / offline Q27 / product P28-03 / 실제=서로 다른 시점의 '현재'가 한 문서에 공존한다. 일부는 EXEC-DEC-001 의 범위 분리로 설명되지만(전체 Q19 vs 로컬 Q27) L116·L196·L233 은 과거 시점 서술에 '현재'가 남은 stale. 독자는 갱신일 헤더도 신뢰할 수 없어 최신 상태를 선택할 기준이 없다
- 순서 변경 판단(ND-05·06·07·08b)이 결정됐는가: 문서=작업 목록: §4 에서 ND-05·06·07·08b 를 'REORDER(사용자 결정 필요)' 미결정으로 두고, W1 종료 기준에 'ND-01~ND-05… 결정 요청 전달'을 포함하며 NX 상세 4곳(L195·342·442·534)이 '사용자 결정 필요'로 표기 / 실제=후속 조사 §8 은 같은 날 '사용자 위임 판단'으로 ND-05 채택(설계 한정)·ND-06 채택(설계만)·ND-07 유지·ND-08b 거절을 기록하고 '큐 반영은 별도 작업'이라 적었다. 작업 목록은 정정되지 않아 두 문서가 모순. 정책 값은 두 문서 모두 미결정으로 일치. 위임이라는 사용자 원문은 문서 기록 외에 확인 불가
- 거래세·양도세 등 정정 반영 여부: 문서=후속 조사 §0: 이전 작업 목록의 거래세 '자료 간 표기 불일치'와 '해외주식끼리만 손익통산'은 정정 대상이며 거래세 합계 0.20%는 1차 확인됨. §8: '표 위주 요약본을 별도로 만들고 본문은 부록으로 둔다(미작성)' / 실제=작업 목록은 그대로다: L392 '거래세 0.20% 등 요율은 1차 원문 미확인', L1006-1007 이 2차 출처 서술을 유지하고 정정 박스·참조가 없다. 요약본도 아직 없다. 정정은 별도 문서에 있어 독자가 두 문서를 대조해야 한다
- v2 입력 문서 경로 인용: 문서=작업 목록 L3·894·1057 과 검증 기록 L58 이 v2/QuantHarbor_Integrated_Audit_Architecture_Agent_Skills_v2.md(줄번호 포함)와 v2/QuantHarbor_전수조사_보고서.pdf 를 입력으로 인용 / 실제=171e3e4 가 두 파일을 트리에서 삭제하고 v3 MD·새 PDF 로 교체했다(이력의 04812f4·5ff8e29 에는 존재). 작업 목록·검증 기록의 기준 SHA 는 edd018a, PDF 는 5ff8e29, v3 MD 는 80403ab 로 서로 다르며, 새 두 문서를 링크하는 곳은 없다. 이 문서들의 인용은 SHA 를 붙여야만 재현된다
- v3 MD 의 '상태 문서가 PR 병합 사실을 반영 못함': 문서=v3 MD §2 표와 §3.3: 'docs/status.md 는 PR #1 미병합 상태를 유지하지만 GitHub 에서는 80403ab 병합 사실이 확인된다' / 실제=SHA 별로 다르다. 80403ab 에서는 참(status.md:17 '현재: PR #1 준비 완료, main 머지는… 미실행'). 171e3e4 에서는 거짓: L148 이 main 80403ab 병합 커밋을 기록하고 L155-157 이 '당시 기록'으로 라벨링됨. 반면 v3 가 말한 '이후 구현과 비교해야 할 큐 표시'(Q19 vs Q27)는 여전히 유효
- v3 MD 의 해결책('implementation-status.md 같은 현재 기준선 인벤토리 신설'): 문서=v3 MD §3.3: 현재 기준선 인벤토리 문서를 새로 둔다 / 실제=PDF N-1·N-9, 후속 조사 §8, 작업 목록 NX-DOCS-PROCESS-01, v3 §3.3 네 곳이 같은 처방(현재 표/요약본)을 서로 다른 모양으로 제안하고 있고 어느 것도 구현되지 않았다. v3 의 '신규 문서' 안은 PDF 의 '새 문서를 만들 때 기존 문서 하나를 줄인다'는 규칙과 충돌하므로 신규 파일 대신 status.md 상단 표로 흡수하는 쪽이 정합적
- 공개 후보 게이트(check_quality)와 v2/ 디렉터리: 문서=status·작업 카드 다수: 커밋 후보 공개 파일 검사 통과(10-29~10-30 시점). v3 MD 는 CI 예제가 비활성임을 지적 / 실제=v2/ 는 PR #3(c9496a6, 11-14)에서 추가돼 _PUBLIC_ROOTS 에 없고 한글 파일명이라 classify() 가 거부한다(호출로 확인). 즉 5ff8e29·171e3e4 에서 공개 후보 게이트는 fail 일 가능성이 높으며 문서 어디에도 이 사실이 없다. 전체 게이트는 실행하지 않았으므로 추정
- PDF N-1 '0.96MB 증가'·'1,345줄·384줄·1,033줄 한날 추가': 문서=PDF 위험표: 작업 목록 1,345줄·검증 기록 384줄·설계서 1,033줄이 한날 추가되고 상태 문서는 945줄 / 실제=수치는 재현됨(작업 목록 1,345줄, 검증 기록 384줄, 설계서 1,033줄 @5ff8e29, status 945줄, 세 문서 모두 11-14 커밋). 증가 0.96MB 는 docs md +952,908B(0.95MB)에 가까움. 단 1,033줄 설계서는 171e3e4 에서 이미 631줄 v3 MD 로 교체돼 현재 트리에는 없음
- PDF '절대경로 121회'와 작업 목록 '18개 파일 128회·HEAD 81건': 문서=PDF 권장 6: 절대경로 121회. 작업 목록 NX-DOCS-PROCESS-03: 18개 파일 128회(PDF 기준)·HEAD 계수 81건 / 실제=세 숫자는 단위 차이다. 128회 / 18개 파일(80403ab·5ff8e29, 발생 수), 81줄(git grep -c 줄 합), 121(5ff8e29 의 docs/*.md 만 발생 수, 검증 기록 6회 포함). 각 문서가 집계 단위를 적지 않아 그대로는 대조할 수 없다. 작업 카드의 'md 15개 / JSON 3개'는 재현됨
- 작업 카드의 status.md 크기: 문서=NX-DOCS-PROCESS-01 근거: 'docs/status.md 943줄 148,613바이트' / 실제=현재 main(5ff8e29·171e3e4)은 945줄 / 149,123B(+2줄 +510B). 검증 기록 문단(L11)과 병합 후 값 차이로 보이며 이 정확한 시점의 원인은 확인 못 함
- 진행 상태 체크리스트의 범위 표기: 문서=status.md:215-221 '[ ] 컨테이너·실전 서버·비밀정보 저장소·CI 구축', '[ ] 애플리케이션·데이터 파이프라인·원장·주문·보고 구현', '[ ] 테스트·통합 검증·실계좌 검증' / 실제=합성 범위에서는 containers/(Dockerfile·compose 합성), src 77개 .py, 합성 원장·보고·목표·승인·실행 구현과 836개 제품 시험 기록이 있다. 체크 항목이 '실제/운영'인지 '합성 포함'인지 범위가 적혀 있지 않아 독자가 stale 로 읽게 된다(문서 스스로 '체크 항목은 해당 산출물만 의미'라고 단서를 달았음)

### 이력 보존형 정리 절차

- 0. 순서와 승인 정리: PR #7(P28-03 2b-2a) 수용 판정과 구조 변경의 선후를 먼저 정하고, 문서 정리는 별도 단기 브랜치·PR 하나로 묶는다. 정리 착수·commit·push 는 사용자 지시를 받은 뒤에만 한다. 이 레인은 아무것도 수정하지 않았다. — 규칙: AGENTS.md: 사용자 변경·.git 이력·원격 설정 보존, commit/push/PR 권한은 조사·문서 요청에서 추정 금지. status.md 상단은 2b-2a 브랜치와 겹쳐 충돌하므로 PR #7 처리 후 착수하거나 충돌 해소를 같은 PR 에 포함. (이력 보존: True; 위험: PR #7 이 먼저 병합되면 status.md·큐 JSON 충돌, 반대로 정리가 먼저면 2b-2a 브랜치가 충돌. 로컬 codex 브랜치의 cef6a5e 는 v2/ 를 되살리므로 병합 전 확인 필요.)
- 1. status.md 상단에 한 화면 '현재 표'(60줄 이내) 추가: 기준 main SHA·코드 마지막 변경 SHA, 기록 기준일, 큐 4종 현재 위치와 JSON 집계 수치(36/10/12/28)와 NX 53·ND 17 포인터, 열린 PR·브랜치 상태, 현재 유효한 사용자 지시, 검증 상태(실행 vs 정적, 미실행 목록), 다음 작업, 미결정 요약. 기존 '현재 우선 지시' 둘과 L116·L196·L233 의 '현재'에는 '당시 기록 — 현재 표가 우선' 머리말만 덧붙인다. 새 파일을 만들지 않는다(v3 의 implementation-status.md 안은 이 표로 흡수). — 규칙: NX-DOCS-PROCESS-01 완료 기준을 그대로 이행. AGENTS.md 4번(종료 시 완료·미확인·장애·다음 작업 갱신)과 '사실·제안·미결정 구분'을 표의 칼럼으로 고정. 표의 수치는 JSON 에서 산출한 값임을 적는다. (이력 보존: True; 위험: 표와 본문이 충돌하면 이중 진실이 생기므로 '표 우선' 규칙과 산출 방법을 명시. 수치를 사람이 손으로 옮기면 ND 16 대 17 같은 오차 재발(7단계의 검사로 방지). 줄번호 인용 45건은 SHA 한정이라 영향 없음을 머리말에 적는다.)
- 2. 과거 로그 보관: status.md 의 L252-945(694줄, 103,289B) 시간순·역순 로그와 L116-162 당시 기록을 docs/archive/ 의 보관 파일로 옮긴다. 방법은 같은 PR 안에서 (a) git mv docs/status.md docs/archive/status-history-as-of-<SHA>.md 후 얇은 새 docs/status.md 를 같은 경로에 작성하거나, (b) 원본 전체를 변경 없이 복사하고 머리말에 원본 SHA·경로를 적은 뒤 status.md 에서는 포인터 한 줄로 대체한다. 어느 쪽이든 삭제하지 않는다. — 규칙: AGENTS.md: .git 이력 보존, 인계 기록 의무. (a) 는 rename 추적이 되지만 squash merge 에서는 끊길 수 있다. (b) 는 100% 보존이나 중복 크기가 생긴다. 사용자가 선택해야 한다. (이력 보존: True; 위험: docs/status.md 경로는 development-policy.toml:31·.codex/agents·SKILL.md·qh_hook_audit.py 에 하드코딩돼 경로 변경 금지(내용만 슬림화). 줄번호 인용 45건은 SHA 한정이므로 인용문 수정 금지·머리말에 'edd018a 기준 줄번호' 명시. check_quality 는 docs/archive/ 경로를 수용한다(classify 호출 확인). 보관 후에도 상태 갱신 의무가 슬림 status.md 에 남아야 함.)
- 3. 진입 문서 정정: README 현재 단계를 날짜 비의존 한 문단으로 바꾸고 정본이 status.md 현재 표임을 밝힌다(NX-DOCS-PROCESS-01). README 문서 표에 현재 표·v2 작업 목록/검증/후속 조사·team-work-list 를 추가한다. development-environment.md 의 '투자 애플리케이션 구현 전' 문장에는 '당시 기록(2026-10-23)' 라벨을 붙이고 AGENTS.md:14 와의 정합을 확인한다. — 규칙: AGENTS.md 문서 규칙(사실·제안·미결정 구분, 날짜·출처 표기). README·development-environment·ENV-bootstrap 은 baseline-v1.json 의 고정 7개 문서에 없으므로 편집 가능. (이력 보존: True; 위험: AGENTS.md 자체의 수정은 사용자 승인 필요(에이전트 메시지로 승인 불가). baseline 고정 7개 문서(architecture.md, serialization-v1.md, implementation-backlog.md, ARC-DEC-004, data-v1.md, execution-v1.md, operations-v1.md)는 건드리지 않는다. 건드리면 check_quality 가 baseline_hash_mismatch.)
- 4. 정정 전파와 결정 동기화: status.md:7 'ND 16'을 17로, L9 의 PR 서술을 병합 완료로 정정하고, 작업 목록 상단에 '정정 및 결정 기록' 박스(후속 §0 정정·§8 위임 판단 ND-05·06·07·08b, W1 종료 기준 변경, 거래세 1차 확인)를 추가한다. 본문 서술은 삭제하지 않고 취소선 또는 '정정됨' 표시로 둔다. 큐 반영(REORDER)은 별도 작업으로 유지한다. — 규칙: AGENTS.md '설계 변경 시 이유·영향·대안·관련 작업 ID 기록'. '위임 판단'은 사용자 원문 없이 문서 기록으로만 확인되므로 '위임 결정(근거: 후속 §8)' 라벨을 유지하고 정책 값은 미결정으로 둔다. (이력 보존: True; 위험: 위임 범위 해석 오류 시 AI 가 사용자 결정을 대신한 기록이 된다(원문 확인 UNVERIFIABLE). 박스 추가는 문서를 또 늘리므로 5·6단계와 묶어 순증가를 0 이하로 맞춘다.)
- 5. 숫자 단일 출처: NX 53·ND 17 의 기계 판독 색인(ID·우선·gate·크기·선행·ND 연결·상태)을 작업 목록 표에서 파생하는 JSON 으로 둘지 사용자에게 올린다(큐 통합이 아님). 문서 본문에서는 수치 대신 'JSON 집계' 참조를 쓰고, 파생 사본(failure-followup-queue.md 등)에는 '생성물, 정본은 JSON' 머리말을 붙인다. 8개 사본 문서의 현재 상태 서술은 현재 표 링크로 대체한다. — 규칙: NX-DOCS-PROCESS-02(큐 정합 점검·completion_kind 필드, 큐 통합 비채택 EXEC-DEC-002 준수). 새 JSON 파일은 새 산출물이므로 사용자 승인 필요. (이력 보존: True; 위험: 표와 JSON 이 둘 다 정본이 되면 새 이중 진실. 단방향(표→JSON) 생성과 검사 필수. 완료 규칙 문구(artifact_ready≠completed)를 사본 정리 중에 약화하면 안 된다. check_ai_team·run_local_check 가 읽는 execution-checklist.md·approval-register.md 형식은 보존.)
- 6. 증거 JSON 보관 정책(이동 금지·동결): 300개를 이동·삭제하지 않고 읽기 전용 동결을 선언한다. 신규 증거는 작업당 1개로 합치고(10-30 하루 98개 생성), 비참조 13개(83,169B)를 점검해 색인에 표시하며, 증거 색인 1개(날짜·작업 ID·sha256)를 두되 같은 변경에서 다른 문서를 줄여 순증가를 상쇄한다. 절대경로가 있는 증거 JSON 3개는 해시 영향 확인 후 처리 방식을 기록한다(NX-DOCS-PROCESS-03). — 규칙: AGENTS.md: 실제 증거를 지우거나 고쳐 통과로 보이게 하지 않는다, 이력 보존. 증거 JSON 은 242개 문서·132개 큐 항목이 참조하고 check_ai_team 이 증거 경로 존재를 검사하며 check_quality 가 docs/evidence/*.json inventory 경로 정규식을 사용한다. (이력 보존: True; 위험: 이동하면 참조·큐 증거 경로 검사·해시 고정이 깨진다. 해시가 고정된 증거는 내용 치환 불가. 색인이 새 문서가 되므로 규칙 R-1 과 충돌하지 않게 상쇄 필요.)
- 7. 연구 원자료(research raw review·security·input·design 38개, 248,449B)는 이동하지 않고 '동결·색인' 처리하며 필독·조건부 읽기 목록에서 제외한다. 이동은 인바운드 97건 중 증거 JSON 30건 때문에 비권장이다. — 규칙: AGENTS.md: 조사 결과는 근거 링크와 간결한 결론으로 인계, 이력 보존. status 의 '최종 결론 + 근거 링크' 형식만 필독 쪽에 남긴다. (이력 보존: True; 위험: 동결만으로는 저장소 크기·탐색 비용이 줄지 않는다(줄이는 것은 필독량). 이동을 원하면 링크 갱신과 증거 JSON 해시 처리가 선행되어야 함.)
- 8. 새 규칙 R-1~R-6 명문화: R-1 새 문서 PR 은 대체·축소 대상 문서 또는 보관 이동을 같은 변경에 명시한다(사용자 요청 산출물은 예외 표기). R-2 진행 기록 갱신 시 현재 표를 먼저 고치고 상세는 작업 카드·증거에 둔다. R-3 상태 수치는 JSON 파생이며 본문에 손으로 쓰지 않는다. R-4 감사·분석 문서는 기준 SHA 와 정적/실행 구분을 항목마다 적는다. R-5 새 md 는 상대 링크만 쓰고 사용자 홈 절대경로를 쓰지 않는다. R-6 필독 4문서 합계는 예산(예: 60KB 이하)을 둔다. 위치는 docs/templates/task.md 체크 항목을 우선하고 AGENTS.md 에는 사용자 승인 후에만 반영한다. — 규칙: AGENTS.md 문서 규칙. AGENTS.md 변경은 사용자 승인이 필요하며 에이전트 메시지는 승인이 아니다. 새 규칙은 사실·제안·미결정으로 구분해 제안으로만 기록. (이력 보존: True; 위험: 규칙이 많으면 오히려 준수 비용 증가. R-6 의 예산 수치는 근거 없는 값이므로 사용자 결정으로 올릴 것(현재 188,046B, 정리 후 약 45~50KB 추정).)
- 9. 자동 검사 접점: 새 읽기 전용 스크립트(예: scripts/check_docs.py)로 R-3~R-6 을 검사한다. 항목은 (a) status 기록 기준일 ≥ 본문 최신 날짜 (b) 현재 표의 큐 수치 = JSON 집계 (c) md 절대경로 0(증거 JSON 3개는 허용 목록) (d) 상대 링크 해석(:줄번호 접미 허용) (e) status.md 줄 수 예산 (f) README 날짜 비의존. 현재 기준선은 (a) fail(10-30 < 11-14), (b) pass(28/20/1/7), (c) fail(128회), (d) 943/1,058 해석(115 절대경로), (e) fail(945줄)이다. check_quality.py 는 수정하지 않고 별도 도구로 둔다. — 규칙: AGENTS.md: 테스트 추가·실행은 사용자가 요청한 경우에만 수행. scripts·tests 추가는 사용자 승인 사항(ND-13 과 연결). (이력 보존: True; 위험: scripts/ 변경이 Q27 고정 입력(8a27220 의 708개 추적 파일) 재검증의 '입력 불변' 주장과 충돌할 수 있어 Q27 판정 이후 또는 별도 입력으로 분리. qh_hook_audit.py 는 hooks.json 이 SHA-256 을 고정하므로 hook 에 넣지 않는다. 검사기는 마크다운 인라인 링크만 보고 앵커·참조형 링크·HTML 링크는 검사하지 못한다.)
- 10. 공개 후보 게이트와 v2/ 정합: v2/ 가 check_quality 에서 거부되는 상태(v3 MD unclassified_candidate, 한글 이름 PDF unsafe_path)를 해소하는 방안을 사용자에게 올린다. 안 (a) v2/ 를 _PUBLIC_ROOTS 에 추가하고 PDF 는 ASCII 이름으로 git mv, 안 (b) v2/ 를 입력 보관소로 분류해 게이트 범위에서 제외하는 규칙을 문서화, 안 (c) 현재 방치. 어느 쪽이든 CI 활성화(AP-06·ND-13) 때 .github/workflows 의 protected_path 규칙·ci-definition.md 의 위치 단언·check_runtime 의 비활성 예제 비교(inactive_ci_policy_drift)를 함께 개정해야 한다. 문서 검사는 DB·Docker 불필요한 빠른 job 으로 분리해 15분 timeout 안에 둔다(NX-OPS-INFRA-01). — 규칙: AGENTS.md: 사용자 파일명·이력 보존(사용자가 커밋한 PDF 이름 변경은 사용자 결정), 외부 시스템 mutation 은 명시 승인 후만. 원격 CI 활성화·push 권한은 추정 금지. (이력 보존: True; 위험: check_quality.py 수정은 해당 파일을 해시 고정한 증거 manifest 와 Q27 고정 입력 주장에 영향. PDF 이름 변경은 외부 링크를 끊을 수 있다. 전체 게이트는 이 레인에서 실행하지 않았으므로 실제 fail 여부는 사용자 승인 후 단독 실행으로 확인 필요.)

## 13. 작업 재조정 상세 (R3)

R3 결론. (1) PDF의 정량 진술은 정적으로 대체로 재현된다. src 73파일 19,141줄에서 77파일 20,855줄, docs 마크다운 157개 1,334,165바이트에서 206개 2,287,073바이트, 테스트 def 1,067개다. target·market_data·catalog·calendar·research 계열 파일은 80403ab 이후 diff가 없다(git diff --stat 공백). 절대경로는 171e3e4에서 마크다운 16개와 증거 JSON 3개, 총 134회다. 실행 검증은 하지 않았다. (2) PDF 권고 6개 중 사용자 순서 변경이 필요한 것은 2번(읽기 전용 실데이터 스파이크) 하나뿐이다. 나머지는 같은 '순차 구현' 단계 안의 순서이거나 문서 정리다. 다만 NX 53개는 아직 큐에 채택되지 않은 제안이고 ND-05 위임이 '설계 한정'이라서, 새 코드 착수(3·5번)에는 채택 범위 결정이 필요하다. (3) 2번은 지금 열 수 없다. 승인 레지스터에 해당 범위가 없고 SG-02가 미충족이다. ARC-DEC-001과 DATA-DEC-001이 실데이터 확인과 실공급자 fetch를 막고 있다. 코드도 막혀 있다. FetchRequest·RightsGrant·MarketEnvelope·Catalog·Calendar의 environment가 'synthetic' 단일값이고 envelope당 128건 상한이 있으며 src에 HTTP 클라이언트가 없다. 그래서 PDF의 '기존 MarketFetchPort와 Parquet 저장소를 그대로 쓴다'는 부정확하다. 약관이 깨끗한 KR·US 일봉과 환율 공급원도 저장소 근거에는 없다. 금융위 주식시세정보는 공공누리 제4유형(상업적 이용금지·변경금지)이고 serviceKey 발급이 필요하다. (4) Q27 의존은 작업 목록 선행 열 기준으로 NX 53개 중 직접 9개, 전이 포함 22개(41%)다. 직접 9개 중 기술 의존은 5개(NX-POLICY-04, NX-TAX-COST-01, NX-SAFETY-01, NX-OPS-INFRA-02 구현부, 조건부 NX-PORTFOLIO-03)이고 절차 의존은 4개(NX-POLICY-02, NX-PORTFOLIO-01, NX-AUTHENTICITY-02, NX-OPS-INFRA-03)다. 기술 의존의 이유는 execution·approval·product_artifacts가 domain/target 타입을 import하고 Q27 고정 입력(8a27220, 708개)이 target v1 해시에 묶여 있기 때문이다. PortfolioConstructor·시도 원장·정책 스키마·시장 규칙 레지스터는 upstream의 새 모듈이라 Q27과 기술적으로 독립이다. (5) PDF 권고 4(계약 한 묶음)는 부분만 맞다. 다중 실패 수집은 스키마상 이미 가능하고 builder의 첫 실패 중단 동작일 뿐이라 breaking이 아니며, 읽기 전용 진단 함수로 분리할 수 있다. 진짜 breaking은 reduce-only와 비율형 비용 둘이다. 개정 창은 Q27 판정 직후, P28-04 이전이 좋다(product_artifacts가 이미 target 타입에 묶였다). (6) 학습·진위 14개는 맹목 수용하지 않고 소비자 유무로 나눴다. 지금 할 것은 AUTH-01(축소)·LEARN-01·AUTH-02(LEARN-02 병합) 3개다. 소비자(실데이터·실모델)가 생길 때까지 미룰 것은 8개이고 블록 유지가 2개다. (7) 작업목록과 PDF 모두의 보정점이 있다. 'src에 rebalanc 0건'은 부정확하다. research에 equal_weight_rebalance 전략이 있고 plan_orders는 2종목·45%로 하드코딩돼 있다. NX-POLICY-08에는 시도 기록 요구가 있는데 NX-AUTHENTICITY-02 선행 간선이 빠져 있다. ExperimentRegistry는 exploration_ref가 고정값이 아니면 거부하므로 시도 원장은 확장이 아니라 새 타입이어야 한다. (8) 작업량 축소안. 즉시 착수 13개(NX 약 25%), Q27 이후 계약 묶음 3~4개, 나머지는 소비자·관문 트리거 대기로 둔다. docs_only 25개는 독립 문서 8개 이하로 합치고, 이력 파괴 없이 append-only 요약, 마크다운 경로만 치환, 증거 JSON은 제외한다. 신규 사용자 결정 ND-17(실데이터 스파이크 순서 변경)과 ND-18(NX 채택 범위)을 제안한다.

### Q27 의존 접점 분석

- PortfolioConstructor 순수 함수(TargetRequest 변환): Q27 기술 의존=False — 기술적으로 독립이다. build_target 앞단의 새 모듈이고 출력은 기존 TargetRequest와 SyntheticStrategyProposal이다. application/target.py는 execution을 import하지 않고, execution과 approval이 target을 import하는 하류 구조다. TargetRequest는 이미 target_basis='quantity'/'weight', mode full/partial, omission_rule을 지원한다. 허용 폭은 대역 안 종목을 현재 수량으로 명시 출력하는 방식으로 계약 변경 없이 처리된다. 잔여 현금 재분배는 quantity 기준으로 변환하면 가능하다. 위반 한 건에 전체가 막히므로 사전 검증은 SyntheticTargetRepository 같은 인메모리 저장소로 build_target을 드라이런해야 한다(동작은 미확인, 클래스 존재만 확인). work-list가 NX-BASELINE-01을 선행으로 둔 이유는 절차다. EXEC-DEC-003:16은 독립 착수 조건(start_dependencies)과 통합·완료 의존을 분리하고, P28-01의 start_dependencies도 'Q27:contract-v1'이다. 제약은 세 가지다. application/target.py와 domain/target.py를 건드리지 않고 새 파일로만 만들 것(execution이 둘 다 import). 작성자 한 명 규칙을 지킬 것. 입력은 ResearchPointInput과 MAX_INPUTS=128 한도 안일 것. 기술 결합이 아니라 절차 결합이다.
- 정책 스키마·검증기(NX-POLICY-02/03): Q27 기술 의존=False — 별도 additive 타입(PortfolioPolicy)으로 만들면 Q27과 독립이다. SyntheticTargetPolicy의 필드를 추가하면 정책 hash와 canonical 직렬화가 전부 바뀌어 breaking이다(SPECS 닫힌 필드표, spec()이 필드 불일치 시 RuntimeError). 따라서 의존 여부는 별도 타입이냐 기존 타입 수정이냐로 갈린다. work-list의 'Q27 판정 이후에만 계약을 바꾼다'는 기존 타입 수정에만 해당한다. 정책 구조는 policy-gates.md:19가 ARC 단계의 버전 계약으로 고정한다고 해서 사용자 정책 값과는 구분된다.
- 시도 원장(Trial Ledger): Q27 기술 의존=False — 기술 의존이 없다. 새 append-only 이벤트 타입이다. 기존 ExperimentRegistry는 __post_init__이 exploration_ref가 'PG02:RESEARCH-DEC-001:fit-none'이 아니거나 strategies·fit이 고정값이 아니면 거부한다. 그래서 확장이 아니라 병행 신규 타입이어야 하고, v1 24실행 골든은 불변이다. 저장소는 ai_state를 쓸 수 없다(record_count 0..128, book=1 단일 행). 별도 영역이 필요한데 그 결정이 NX-LEARN-02이며 문서 작업이다. 진짜 선행은 Q27이 아니라 저장 위치 결정과 소비처다. 합성 단계의 첫 소비처는 NX-POLICY-08 정책 비교 시도다.
- 읽기 전용 실데이터 스파이크(PDF 권고 2): Q27 기술 의존=False — Q27 코드와는 무관하다. 그러나 다른 막힘이 셋 있다. (a) 계약: FetchRequest.environment, RightsGrant.environment, MarketEnvelope header, Catalog.environment, TradingCalendar.environment가 모두 'synthetic' 단일값이라 실데이터를 담으려면 additive 환경 값(해시 영향) 또는 market-data-v1 밖의 별도 연구 전용 모듈이 필요하다. envelope당 MAX_RECORDS=128, IngestLimits는 max_pages≤16·max_records≤128이다. 10~15종목 1~2년 일봉은 약 2,520~7,560봉(환율 별도)이라 envelope 20~60개 분량이다. src에 HTTP 클라이언트 import가 0건이다. pyarrow lock은 '합성 로컬 Parquet 한정, 실데이터 권리 주장 없음'이라고 명시한다. (b) 승인: 승인 레지스터에 공개 시세 수집 범위가 없고 SG-02는 확인되지 않은 용도의 수집·보존·전송을 금지한다. (c) 공급원: Yahoo·KRX 자동 수집은 약관상 후보에서 제외됐고 FRED는 LLM·저장·캐시를 금지한다. 금융위 주식시세정보(data.go.kr 15094808)는 공공누리 제4유형이고 serviceKey 발급이 필요하며 이력 깊이는 미확인이다. 미국 일봉과 환율 공급원은 확인된 것이 없다. 따라서 기존 MarketFetchPort를 그대로 쓴다는 PDF 서술은 부정확하다.
- 계약 개정 묶음 중 reduce-only(NX-POLICY-04): Q27 기술 의존=True — 기술 의존이다. 목표 단계 노출 검사(high=현재+매수분, 매도 감소 미반영)와 execution 재검사(groups=current+buys, sells>current면 거부)를 같은 규칙으로 함께 바꿔야 한다. domain/execution과 domain/approval이 domain/target 타입을 import하고, Q27 고정 입력(base 8a27220, tracked 708개, manifest fc210b11)이 이 해시에 묶여 있다. 변경하면 Q27 판정이 무효가 되어 재실행해야 한다. 게다가 product_artifacts가 이미 TargetPlan·OrderCandidate·TargetBuildResult를 저장한다. 매도 주체가 위험을 줄이는 매도를 막는다는 PDF·work-list 주장은 코드로 재확인됐다(정적, 80403ab=171e3e4).
- 계약 개정 묶음 중 비율형 비용(NX-TAX-COST-01): Q27 기술 의존=True — 기술 의존이다. SyntheticCostRule에 fee_rate·tax_rate·min_fee를 더하면 닫힌 필드표가 바뀌고 OrderTerms.cost_rule을 담은 plan·candidate·approval·execution의 canonical 해시가 달라진다. 새 클래스를 병존시키지 않으면 breaking이다. 요율 값은 세무 확인 전이라 확정할 수 없으므로 이번에 개정하는 것은 구조(필드·유효기간·반올림)뿐이다. 값 입력은 NX-TAX-COST-02와 NX-SECURITY-02 이후다.
- 계약 개정 묶음 중 다중 실패 수집(PDF 권고 4): Q27 기술 의존=False — breaking이 아니다. TargetPlanBody.failures와 TargetResultBody.failures는 이미 sequence이고 검증은 bool(failures)==blocked만 요구한다. 첫 실패 중단은 builder 동작(_Blocked 예외 후 failures=(error.failure,))일 뿐 스키마 제약이 아니다. 저장소에 쓰지 않는 읽기 전용 진단 함수로 분리하면 기존 해시와 골든을 건드리지 않는다. 그러므로 target-local-v2 묶음에 넣을 이유가 없고, 묶음은 reduce-only와 비율형 비용 둘로 줄일 수 있다. 진단 함수는 NX-POLICY-03 검증기와 NX-POLICY-06 드라이런의 구현 수단이다.
- 시장 규칙 레지스터(NX-DATA-01): Q27 기술 의존=False — 문서(docs_only) 작업이며 선행이 없다. 코드는 종목·세션별 capability(tick·lot·min_notional·session_kind)를 이미 합성 사실로 받는다. 레지스터는 외부 사실의 출처·확인일·유효기간을 표로 관리하는 일이라 Q27과 무관하다. 내용의 상당 부분은 v2-followup-research §2에 이미 있어 재조사 대신 옮겨 적으면 된다. 작업량은 작다.
- 정정 이벤트 추가 경로(NX-PORTFOLIO-03): Q27 기술 의존=True — 조건부 의존이다. application/target.py를 수정하면 execution이 import하는 공유 모듈이 바뀌어 Q27 최종 입력이 변한다. 새 모듈(예 replay 기반 builder)로 additive하게 만들면 독립이다. 기존 Q24 재현 경로와 골든은 보존해야 한다. 선택에 따라 의존 여부가 갈리므로 새 모듈 방식을 권고한다.
- NX-SAFETY-01·NX-OPS-INFRA-02(시험 편입·설계): Q27 기술 의존=True — 구현은 Q27과 같은 산출물에 얹힌다. check_execution.py와 tests는 FUP-Q27-014 담당 작성자 한 명이 소유한다. NX-OPS-INFRA-02의 설계 문서 부분은 독립이다. AGENTS.md가 시험 추가·실행을 사용자 요청 시로 한정하므로 절차 의존도 있다. SAFETY-01은 BASELINE-01 마감 뒤 후속으로 두는 것이 맞다. 128 record 용량 때문에 fixture가 두 번 실패한 원인(FUP-Q27-007/014)을 직접 겨냥하는 용량 예산 빌더 부분만 가치가 크다.
- PR #7(2b-2a, 수용 전)과 계약·데이터 접점: Q27 기술 의존=False — PR #7은 src/tests 4파일(product_ai.py, synthetic_investment_ai.py, test_product_ai.py, test_product_ai_core.py, 926줄)만 바꾸고 target·market_data·execution과 겹치지 않는다. PDF의 'Q27 마감과 2b-2a 정리 두 가지가 끝나야 계약 개정이 풀린다'는 절반만 맞다. 계약 개정의 선행은 Q27이고 2b-2a는 work-list에서 NX-LEARN-02(학습 원장 저장 결정)만 막는다. 그 결정을 NX-AUTHENTICITY-02에 병합하면 2b-2a가 W2를 막는 관문이 아니다.
- Q27 의존의 전체 모양(work-list 선행 열): Q27 기술 의존=True — 작업 목록 선행 열을 파싱하면 NX 53개 중 NX-BASELINE-01을 직접 선행으로 둔 것이 9개이고 전이 폐쇄는 22개(41%)다. 직접 9개는 기술 5(NX-POLICY-04, NX-TAX-COST-01, NX-SAFETY-01, NX-OPS-INFRA-02 구현부, 조건부 NX-PORTFOLIO-03)와 절차 4(NX-POLICY-02, NX-PORTFOLIO-01, NX-AUTHENTICITY-02, NX-OPS-INFRA-03)다. W2 13개 중 8개가 Q27 폐쇄 안에 있어(62%) PDF의 '대부분의 W2가 Q27 뒤'는 정확하다. 그러나 절차 의존 4개는 EXEC-DEC-003의 start_dependencies 규약으로 풀 수 있다. Q27 자체는 FUP-Q27-006 diagnosing과 009~014 queued 상태다. 시험을 포함한 마감이라 사용자 지시 범위 내(EXEC-DEC-002:16)에서 진행한다.

### 승인 상태

- 읽기 전용 공개 시장 데이터 수집(외부 네트워크)의 현재 허용 여부: 허용되지 않음(NOT_APPROVED). 승인 레지스터(AP)에 공개 시세 수집 범위가 없고 SG-02도 미충족이며, 계약과 코드는 synthetic 전용이다. 필요한 것은 네 가지다. (1) 사용자의 명시적 순서 변경(제안 ND-17). (2) SG-02 결정 기록으로 공급원별·용도별(저장·연구만) 권리를 확인하고 ND-08을 재정의한다. (3) 기본값 synthetic을 바꾸는 additive 계약 개정 또는 별도 연구 전용 모듈과 그 결정 기록. (4) 계정·키 발급이 필요한 공급원은 AP-05 범위 확장 또는 신규 승인과 SG-03(의존성)이 필요하다.
- PDF 권고 1: Q27 마감 + 2b-2a 정리: 순서 변경 불요. Q27 실행·시험은 기존 사용자 지시로 이미 허가돼 있어 재요청이 필요 없다. PR #7 수용·병합은 NX-BASELINE-02의 독립 일반·보안 검토가 선행이고, 병합과 push는 AP-06 원격 변경 범위라 사용자·검토자 결정이다. FUP-Q27-009~014를 위한 시험 추가는 AGENTS.md 시험 규칙상 기존 허가 범위(EXEC-DEC-002/003)로 읽히나, 신규 시험 작업(NX-OPS-INFRA-02)에는 별도 요청이 필요하다.
- PDF 권고 2: 읽기 전용 실데이터 스파이크(Q27과 병행): 사용자 순서 변경 필요(AGENTS.md 최상위 순서와 RETURN-02 위치를 옮김). 사용자가 위임한 ND-05·06·07·08b 판단의 논리로는 정당화되지 않는다. ND-06 채택 논리가 '실제 연결·권한을 추가하지 않아 최상위 순서를 바꾸지 않는다'였는데 이 스파이크는 실제 네트워크 접속이다. 위임 범위에 ND-08은 없었다. 제안 ND-17로 올려야 하며, 사용자가 허용하더라도 SG-02·계약·공급원이 먼저 필요하다.
- PDF 권고 3: PortfolioConstructor를 Q27과 병행: 순서 변경은 불요(같은 '순차 구현' 단계 안, 새 모듈, 기존 계약 유지). 다만 두 가지가 필요하다. (1) NX 53개가 아직 제안이고 큐 반영(REORDER)은 별도 작업이므로 사용자의 채택 범위 결정(제안 ND-18)이 필요하다. (2) ND-05 위임은 '문서·설계 한정'이라 코드 착수까지 포함하지 않는다. 병행은 활성 worker 한 명·작성자 한 명 규칙 안에서 시간 분할로 해야 하며, Q27 고정본 시험은 별도 결과 영역에서 계속할 수 있다(EXEC-DEC-003:18).
- PDF 권고 4: 계약 개정 한 묶음(target-local-v2), Q27 판정 후: 순서 변경 불요. 필요한 것은 ND-04(reduce-only와 한도 초과 대응)와 시험 시간 예산(ND-13의 신규 부분), qh-contract-change 절차의 독립 일반·보안 검토다. Q27 판정이 선행이고, 합산 시험 시간은 약 3.8시간(6,800.646초+6,932.892초=13,733.5초, 병렬 여부 미확인)이다.
- PDF 권고 5: 시도 원장만 먼저: 순서 변경 불요. 새 additive 코드이므로 ND-18 채택이 필요하다. ND-11의 임계값 부분은 불필요하고 append-only 보존 속성만 필요하다. 저장 위치 결정(NX-LEARN-02)은 NX-AUTHENTICITY-02에 병합하는 안을 제안한다.
- PDF 권고 6: 정리 작업 하나(README 현재 단계·절대경로·상태 요약): 순서 변경 불요(문서). 로컬 편집은 가능하나 push·PR은 AP-06 별도다. 증거 JSON 3개는 불변 이력으로 두고 마크다운 16개만 치환하는 안이 AGENTS.md의 이력 보존과 양립한다. '새 문서 하나를 만들면 기존 하나를 줄인다'는 규칙은 이력 보존과 충돌해 채택하지 않는다.
- NX 53개·ND 17개의 큐 채택 여부: 미채택(제안 상태). 사용자 결정 전 큐·계약·코드는 바뀌지 않는다. 제안 ND-18로 채택 범위를 묻는다.
- 정책 값(자산배분 비율·허용 폭·회전율·낙폭 단계·통계 임계값): 미결정이고 위임 범위 밖이다. 구조·단위·결합 규칙은 policy-gates.md:19가 ARC 설계 단계 계약으로 정하라고 해서 값과 구별된다. 이 구분이 ND-01·ND-03을 쪼개는 근거다.

### ND 상태

- ND-01: ready_for_user — 자산배분 방식(사용자 지정 고정 비중+허용 폭, 종목은 동일 비중 기준선, 기준통화 KRW)은 저장소 권고와 PDF가 일치해 확인 질문 하나로 줄일 수 있다. KR·US·현금 비중 값은 사용자 결정으로 남는다. 방식과 값을 분리해 질의한다.
- ND-02: blocked — 최종 선택은 NX-POLICY-08 비교 결과와 PG-03 뒤다. 비교 후보 집합(하이브리드·중간 복귀·현금흐름 우선 포함)은 저장소와 PDF 권고가 같아 사용자 입력 없이 NX-POLICY-05 사양에 파라미터로 넣을 수 있다.
- ND-03: blocked — 값(허용 폭·최소 거래금액·회전율)은 시뮬레이션 뒤다. 단위·결합 규칙(구획 절대 %p, 종목 상대 %)은 policy-gates.md:19에 따라 아키텍처 설계 계약으로 정할 수 있는 구조 반쪽이라 사용자 질의에서 뺄 수 있다(사용자 확인은 아직 없음).
- ND-04: ready_for_user — 가장 시급하다. target-local-v2 계약 개정(reduce-only)의 선행 결정이고 손실 행동은 사용자 확정 사항이다(policy-gates.md:14). reduce-only 허용·자동 청산 없음 권고안을 질의한다. 단계 수와 낙폭 임계값은 사용자 결정이며 PDF의 -8/-12/-15%는 미검증이다.
- ND-05: answered_by_delegation — 채택. 정책 구조·비교안 준비를 P28-04 전으로 앞당긴다. 문서·설계 한정이고 값 확정은 PG-03이다. 코드 착수까지 포함하지 않는다(v2-followup-research §8).
- ND-06: answered_by_delegation — 채택. 합성 수직 슬라이스는 설계만 P28 중간으로 앞당긴다.
- ND-07: answered_by_delegation — 유지. 고급 최적화·몬테카를로 위치는 그대로 두고 라이브러리 ADR만 선행한다.
- ND-08: blocked — 공급원 약관·권리 확인(SG-02 결정 기록)이 선행이다. 선택지 'PDF 후보를 연구 전용으로 먼저 사용'은 후속 조사로 근거가 약해졌다. 신규 ND-17(스파이크 순서 변경) 승인 전에는 질의하지 않는다.
- ND-08b: answered_by_delegation — 거절. KIS 모의 연결·environment=paper 개방은 앞당기지 않는다. PDF도 비채택을 타당하다고 평가했다.
- ND-09: ready_for_user — 본인 계좌 단독 가정의 확인과 전문가 확인 시점 질의다. NX-SECURITY-01·02(문서, 선행 없음)와 NX-TAX-COST-02의 입력이다. 세무·법률 확정은 AI가 하지 않는다.
- ND-10: blocked — 증거 등급 원칙은 AUTH-01 초안으로 제시할 수 있으나 관찰 기간·최소 표본·보정 임계는 LEARN-01 표본 메모 뒤다. 두 문서(선행 없음)를 먼저 쓰면 질의할 수 있다.
- ND-11: blocked — 통계 승격 임계값·홀드아웃 길이는 시도 원장과 표본 메모 이후다. 시도 원장 구현에는 append-only 보존 속성만 필요하므로 임계값 질의 없이 진행할 수 있다.
- ND-12: ready_for_user — 직접 구현 우선 권고는 BASE-DEC-001의 SG-03 재적용 원칙과 같아 질의 가능하나 소비처(NX-AUTHENTICITY-03, NX-PORTFOLIO-04)가 트리거 대기라 시급하지 않다. 다른 질의와 묶어 낮은 우선순위로 질의한다.
- ND-13: ready_for_user — Q27 마감용 실행은 기존 사용자 지시(EXEC-DEC-002:16, EXEC-DEC-003)로 이미 허가돼 있어 재질의 대상이 아니다. 남은 질의는 신규 시험 추가, target-local-v2 전체 회귀 시간 예산, CI 활성화(AP-06)와 지원 호스트(macOS arm64) 범위다.
- ND-14: blocked — 실제 LLM 연결 전 사항이라 P28-03 2b-2b와 NX-AI-RUNTIME-01 시점 전에는 질의 시기상조다. 신규 지출(AP-03)은 요구 없이는 열지 않는다.
- ND-15: blocked — NX-POLICY-09 설계(P28-03 내부 6 slot 입력)가 선행이다. 미국 정규장 사용자 가용 창 질의는 그 설계 뒤 질의한다.
- ND-16: ready_for_user — ETF 허용 목록·거래 상태 불명 종목 제외·세금 표시 전용 권고는 질의 가능하나 NX-PORTFOLIO-01 1차 범위에는 필요하지 않아 시급하지 않다. 미국 단주 지원은 B01(UNVERIFIABLE) 때문에 이 질문에서 빠진다.

## 14. 새 GitHub 자료 판정 (46개, 확인일 2026-11-15)

| 레인 | 저장소 | 상태 | 라이선스 | 판정 | 이유 |
|---|---|---|---|---|---|
| G1 | unionai-oss/pandera | ok | MIT (LICENSE.txt 본문 'MIT License, Copyri | borrow_pattern | 일봉 검증 항목(OHLC 불변식, 중복, 범위, 세션 일치)은 순수 함수 몇 개로 충분하고 현 저장소는 dependencies=[]·해시 고정 오프라인 런타임 정책이라 새 의존성은 SG-03 ADR 이 선행돼야 한다. 스파이크 전용 격리 환경에서 선택적으로 쓸 수는 있으나 제품 의존성으로 채택하지 않는다 |
| G1 | fivetran/great_expectations (구 great-expectations/great_expectations) | ok | Apache-2.0 (LICENSE 본문 Apache License 2. | benchmark_only | 스파이크 규모(수만 행)에는 과도하게 무겁다. 저장소 소유 조직이 fivetran 으로 리디렉션돼 있어 향후 유지·라이선스 방향을 별도 확인해야 한다. 기대치 스위트를 데이터셋 버전에 묶는 개념만 참고한다. |
| G1 | duckdb/duckdb | ok | MIT (LICENSE 본문 Copyright 2018-2026 Stic | adopt_dependency | 연구 분석 환경에 한정해 채택을 권고한다. ASOF JOIN 이 '가용 시점 기준 직전 값' 조회를 한 줄 SQL 로 해결해 PIT 정합 점검에 맞다. 제품 런타임은 기존 pyarrow 해시 고정 저장소를 유지하고, 제품에 넣으려면 SG-03 ADR 이 필요하다. |
| G1 | man-group/ArcticDB | ok | Business Source License 1.1 (LICENSE.txt | avoid | README 는 '프로덕션(상업·비즈니스 환경 포함) 사용은 유료 라이선스'라고 하고 LICENSE.txt 의 Additional Use Grant 는 Database Service 만 제한해 문구가 서로 다르다. 자동 운영까지 가는 플랫폼의 의존성으로는 라이선스 위험이 크다. 변경일(릴리스 후 2년)에 |
| G1 | gerrymanoim/exchange_calendars | ok | Apache-2.0 (이전 조사에서 본문 확인, 이번 API·PyPI 일 | adopt_dependency | 이전 판정(adopt_dependency)을 유지한다. 이번 추가 근거는 XKRX 가 2026·2027년 개별 휴장까지 담고 있다는 점이다. 단 사람이 유지하는 목록이므로 공급자 데이터의 실제 거래일과 교차 점검해야 하고, 도입은 SG-03 ADR 을 거친다. |
| G1 | microsoft/qlib | ok | MIT (LICENSE 본문 'MIT License Copyright ( | borrow_pattern | 복원계수 컬럼 규약과 정지일 NaN 규약만 차용한다. 데이터 수집기는 Yahoo 계열이라 이전 조사의 약관상 금지 출처와 겹치므로 쓰지 않는다. |
| G1 | stefan-jansen/zipline-reloaded | ok | Apache-2.0 (LICENSE 본문 Apache License 2. | borrow_pattern | 원시 가격과 기업행동을 분리 저장하고 효력일 기준으로 조정을 적용하는 스키마를 차용한다. 엔진 자체는 도입하지 않는다. |
| G1 | lineofflight/frankfurter (구 hakanensari/frankfurter) | ok | MIT (LICENSE 본문 '(The MIT License) Copyr | benchmark_only | ECB·Fed 원천을 직접 쓰면 되므로 중간 계층이 필요 없다. blended 가 약관이 다른 공급자(FRED 포함)와 마카오 금융당국 환율을 섞을 수 있어 재현성과 약관 추적에 불리하다. 교차검증용으로 providers=ecb 한정 호출만 허용한다. |
| G1 | apache/arrow (pyarrow) | ok | Apache-2.0 (LICENSE.txt 본문 확인) | adopt_dependency | 이미 채택된 경로다. 스파이크 Parquet 쓰기는 기존 어댑터 패턴(해시·row_count·manifest)을 따르면 새 의존성이 없다. 다만 어댑터는 synthetic 고정이라 실데이터 쓰기에는 계약 개정이나 별도 연구용 쓰기 경로가 필요하다. |
| G1 | treeverse/dvc (구 iterative/dvc) | ok | Apache-2.0 (LICENSE 본문 확인) | benchmark_only | '데이터는 Git 밖, manifest 는 Git' 구조는 우리 설계와 같지만 저장소가 이미 자체 manifest·불변 버전 모델을 갖고 있어 도구를 더할 이유가 약하다. 개념 비교용으로만 둔다. |
| G1 | pydata/pandas-datareader | ok | BSD-3-Clause (LICENSE.md 본문은 pandas BSD  | avoid | 추가 가치가 없고 지원 출처 중 Stooq 는 자동 수집 관문이 있으며 Yahoo·FRED 는 이전 조사에서 약관 제한이 있다. 출처별 약관을 흐리는 추상화다. |
| G1 | OpenBB-finance/OpenBB (현재 openbq-org/OpenBB 로 301 이동) | ok | LICENSE 본문 Apache License 2.0 (Copyright | avoid | 공급자별 약관을 가리는 집계 계층이며 스파이크 규모에 과도하다. 또 공식 org(OpenBB-finance, 2021-03 생성)의 저장소가 2026-09-11 생성·미검증·설명 없는 openbq-org 로 이동해 있다. 같은 저장소 ID 로 리디렉션되고 README 는 기존 org 를 가리키지만 이전  |
| G2 | cvxgrp/cvxportfolio | ok | GPL-3.0 | benchmark_only | GPL-3.0이고 pandas·numpy·matplotlib·cvxpy<1.7·curl_cffi 필수 의존, 기본 시장데이터가 Yahoo 다운로더(약관 문제), float 연속 비중이라 QH(dependencies=[], 정확 산술, 정수 원)에 맞지 않는다. 가치는 개념뿐이다: 회전율 정의(편도=½L1 |
| G2 | pmorissette/bt | ok | MIT | borrow_pattern | MIT·Python 3.13 classifier 신호가 있어 패턴 차용 여지가 가장 크다. 그러나 가변 temp dict·Cython·float·ffn(pandas/scipy) 의존이라 의존성 도입은 맞지 않는다. 가치는 두 가지다. ① 단계 합성 구조를 순수 함수 파이프라인(타입 있는 단계 간 값)으로 |
| G2 | QuantConnect/Lean | ok | Apache-2.0 | borrow_pattern | Apache-2.0이고 구조가 가장 정돈되어 있으나 C#/.NET 코어(decimal)라 QH(Python, dependencies=[])에 의존으로 넣을 수 없다. 이전 조사(oss-survey #18)가 이미 선택한 '목표·위험·실행 분리' 패턴을 constructor 단계 분해(리밸런스 여부→대상  |
| G2 | PyPortfolio/PyPortfolioOpt | ok | MIT | benchmark_only | 기존 판정(W1 benchmark_only)을 유지한다. 알고리즘이 30줄 수준이라 정확 산술로 재구현하는 편이 낫고, 의존성(cvxpy)·혼합정수 솔버 의존·float은 QH와 맞지 않는다. 추가로 읽은 결함 후보가 시험 설계에 쓸모가 있다. |
| G2 | microsoft/qlib (order_generator.py, backtest/exchange.py) | ok | MIT | borrow_pattern | MIT이지만 Position·Exchange·mlflow 등 무거운 프레임워크에 결합되어 있고 Python 3.13 classifier가 없다. 패턴으로만 쓴다: 현금 한도에서 최소 수수료 구간을 가진 최대 수량 역산, 청산 예외, 예약현금 비율. 반면교사: 조용한 재정규화와 전량 매도. |
| G2 | ArthurBernard/Fynance | ok | MIT | borrow_pattern | MIT이고 3.13 classifier가 있으나 numba·torch>=2.0·polars·seaborn 필수 의존이라 의존성으로는 부적합하다. 작고 문서화가 좋은 허용 폭 mode 구분(full/edge), 회전율 축소 방식, 이산화 한계의 반례가 NX-POLICY-05와 시험 설계에 유용하다. |
| G2 | enexqnt/py-vallocation | ok | GPL-3.0-or-later | benchmark_only | GPL-3.0-or-later이고 0.x Beta이며 cvxopt·scipy 의존이다. PyPI 최신 0.4.0(2026-02-01)과 읽은 main HEAD(v0.6.0, 2026-03-31)가 달라 설치 가능한 코드와 읽은 코드가 불일치한다. 코드는 복사하지 않고 결과 계약과 탐욕 종료 보장 방식만  |
| G2 | JonnyAis/balancer | ok | MIT | borrow_pattern | 1 star·단일 작성자·float·py38 target이라 의존으로는 부적합하다. 그러나 N≤5 정수 배분의 정확 전수 탐색이 짧고 읽기 쉬워 QH의 시험용 오라클(정확 산술 재구현)의 형태를 보여 준다. 반면교사: 최적화 뒤 소액 제거가 현금 제약을 깨뜨릴 수 있다. |
| G2 | yfiua/nshare-calc | ok | Apache-2.0 | avoid | 릴리스 2개(0.1.1, 0.1.2, 2023-04), 마지막 커밋 2023-04-23, Python 3.13 신호 없음, 잔여현금 벌점 없음, 차원 오류·불가능 풀이를 조용히 처리(fail-open)한다. PyPortfolioOpt LP와 같은 정식화라 새 정보가 거의 없다. |
| G3 | HypothesisWorks/hypothesis | ok | MPL-2.0 | adopt_dependency | dev 전용 조건부 채택 권고. 저장소 시험은 def test_ 1,067개인데 random·Hypothesis·fuzz 사용이 0건(정적 grep)이고 NX-OPS-INFRA-02가 요구하는 시드 고정 보존식 상태기계 시험·차등 시험에 가장 직접 맞는다. unittest로 그대로 실행되어 pytest  |
| G3 | python/cpython (표준 라이브러리 unittest --durations) | ok | PSF-2.0(표준 라이브러리, 새 의존성 아님) | adopt_dependency | 의존성 추가 0으로 가장 먼저 할 일이 가능하다. 836개 제품 시험의 개별 시간 분포가 어디에도 기록돼 있지 않으므로(증거 JSON은 합계만), 모든 시간 절감 계획의 첫 단계는 1회 프로파일이다. 이 실행은 AGENTS.md 규칙상 사용자 요청·시간 예산 승인(ND-13) 뒤에만 한다. 이 조사는 실 |
| G3 | craigahobbs/unittest-parallel | ok | MIT | investigate_further | unittest 체계를 유지한 채 병렬화하는 가장 가까운 기성품이다. 순수 휠(10 kB)이고 직접 의존성은 coverage 하나다. 다만 같은 효과를 표준 라이브러리 subprocess 샤딩 스크립트(약 60줄)로 낼 수 있어 의존성 0 방안이 먼저다. 둘 다 병렬 안전성(아래 위험)을 먼저 해결해야  |
| G3 | pytest-dev/pytest | ok | MIT | investigate_further | xdist·testmon·mutmut이 모두 pytest를 요구한다는 점이 분기점이다. 저장소 시험은 subTest를 199곳(48개 파일)에서 쓰므로 pytest 9의 내장 subtests 덕에 pytest-subtests 플러그인 없이 수집은 가능할 것으로 보인다(실행 미검증). 그러나 증거 JSON |
| G3 | pytest-dev/pytest-xdist | ok | MIT | benchmark_only | pytest 도입이 전제라 unittest-parallel이나 표준 라이브러리 샤딩보다 한 단계 뒤다. 공식 분산 문서는 unittest.TestCase 클래스와 공유 외부 자원(DB)을 다루지 않는다. 기본 load 모드는 같은 클래스의 setUpClass를 여러 워커에서 중복 실행할 수 있어 load |
| G3 | tarpas/pytest-testmon | ok | MIT | avoid | 계약 개정 게이트 용도로는 회피한다. 이 저장소 시험은 정적 입력을 직접 읽는다: ai-evaluation-spec-v1.json(test_investment_ai_evaluation.py:196), baseline-v1.json과 docs/development/investment-ai.md(같은 파일  |
| G3 | pytest-dev/pytest-subtests | archived | MIT | avoid | 저장소가 archived(GitHub API 2026-11-15)이고 기능은 pytest 9에 흡수됐다. 새로 설치할 이유가 없다. |
| G3 | pytest-dev/pytest-timeout | ok | MIT | benchmark_only | pytest 도입이 전제다. 개별 시험 시간 분포를 측정한 뒤에만 필요 여부를 판단할 수 있다. unittest 체계에서는 같은 목적을 TextTestResult·샤딩 스크립트의 모듈 단위 timeout으로 대체할 수 있다(설계 제안). |
| G3 | coveragepy/coveragepy | ok | Apache-2.0 | investigate_further | 시험별 컨텍스트로 '소스 모듈 → 시험 모듈' 지도를 한 번 만들어 영향 시험 선택의 근거로 쓸 수 있다. 다만 공식 문서는 unittest 메서드 지원을 명시하지 않고(함수 이름이 test로 시작하면 된다는 정의만), 비Python 입력은 어차피 별도 지도가 필요하다. 지도 생성은 전체 시험 1회 +  |
| G3 | boxed/mutmut | ok | BSD-3-Clause | borrow_pattern | 도구 채택보다 패턴 차용이 맞다. 첫 통계 수집이 전체 시험 1회(저장소는 113분 이상)이고 pytest가 필수이며 의존성이 무겁다(click, coverage, libcst, setproctitle, textual 등, 전이 의존 미측정). 차용할 것은 '함수 단위 변이 + 호출 시험만 실행 + 스택 |
| G3 | sixty-north/cosmic-ray | ok | MIT | benchmark_only | unittest와 직접 호환되는 점은 장점이다. 그러나 (1) 변이마다 지정한 시험 명령 전체를 돌리고 시험 선택 기능이 없어 전체 3.8시간급 시험에는 쓸 수 없고 모듈 단위 명령으로 좁혀야 한다. (2) 변이를 디스크의 원본 파일에 직접 적용하므로 추적 입력 보존 규칙과 충돌한다. (3) 직접 의존이 |
| G3 | mutatest · MutPy (PyPI 패키지) | ok | 미확인(이번에 라이선스 본문을 읽지 않음) | avoid | 릴리스가 3~7년 전에 멈췄다. 3.13 호환 신호가 없고 신규 의존성 후보로 부적합하다. |
| G3 | ostrowr/jsoncompat | ok | MIT | benchmark_only | 저장소 계약 JSON 5개에는 $schema·properties·additionalProperties가 없고(정적 grep) 계약 본문은 Markdown 산문이라 지금은 적용 대상이 없다. 0.x 초기 단계이고 비표준 도구라 계약을 JSON Schema로 정형화하기로 결정한 뒤에만 검토한다. |
| G3 | Miskler/jsonschema-diff | ok | MIT | benchmark_only | 2025년에 시작된 0.1.x 프로젝트이고 QH 계약은 JSON Schema가 아니어서 적용 대상이 없다. |
| G3 | Confluent Schema Registry 호환성 문서(어휘 참조) | ok | 미확인(문서 참조만, 서버 코드 라이선스는 읽지 않음) | borrow_pattern | qh-contract-change 절차에 호환 등급 선언 항목으로 빌려 쓴다. 이 저장소 decoder는 닫힌 codec(미지 필드·일반 restore 거부)이므로 필드 추가도 구 reader에는 FORWARD 비호환이다(설계 추론). 그래서 '추가형'이라도 reader 이중 읽기 기간이나 새 schem |
| G3 | bufbuild/buf (buf breaking 규칙 분류) | ok | Apache-2.0 | borrow_pattern | Protobuf 전용 Go 도구라 도입 대상이 아니다. '엄격도 단계를 이름 붙인 범주로 선언하고 최소 수준을 고정한다'는 구조만 계약 호환 등급 정의에 참고한다. |
| G3 | oasdiff/oasdiff | ok | Apache-2.0 | benchmark_only | QH에는 HTTP API와 OpenAPI 명세가 아직 없다(P28-02는 조회 계약만). 읽기 전용 HTTP가 생기고 OpenAPI로 정형화할 때 재검토한다. |
| G3 | nedbat/cog | ok | MIT | borrow_pattern | status.md의 요약 블록을 execution-queue.json에서 생성하고 --check로 드리프트를 막는 의미론을 그대로 빌려 표준 라이브러리 스크립트(check_quality에 편입)로 구현하는 것이 의존성 0이다. 생성 스크립트가 복잡해지면 cogapp(순수 휠, 의존 없음)를 dev 전용으 |
| G3 | adr/madr | ok | MIT OR CC0-1.0 | borrow_pattern | 도구가 아니라 템플릿이다. 이미 docs/templates/decision.md와 decisions 34건이 있다. MADR의 status·결정자·고려한 선택지 필드를 대조해 부족한 항목만 보강하고 status 값 어휘를 표준화한다. |
| G3 | npryce/adr-tools | ok | GPL-3.0 | avoid | GPL-3.0이고 마지막 push가 2024-04-25로 휴면에 가깝다. 번호 생성·목록은 표준 라이브러리 스크립트 수십 줄로 충분하다. 별도 CLI로 호출만 하는 dev 도구라 GPL 전염 문제는 작으나 얻는 이득도 작다. |
| G3 | thomvaill/log4brains | ok | Apache-2.0 | avoid | Node >=18 도구체인이 Python 단일 dev 환경과 맞지 않는다. 결정 기록이 34건 규모라 사이트 빌드의 이득이 작다. npm 최신 릴리스가 2024-12-17이다. GitHub 페이지에서 archived 표시는 보이지 않았으나 최신 커밋 날짜는 확인하지 못했다. |
| G3 | mkdocs/mkdocs | ok | BSD(Tom Christie, 2014-present) | avoid | 문서 사이트가 지금 필요하지 않다(GitHub이 마크다운을 렌더링). 생태계가 전환기다: 안정판 정체, 2.0 개발판, Material for MkDocs는 critical maintenance가 2027-05-05까지로 연장되었다(zensical.org). 문서량 폭증(PDF 측정 +0.96MB/2주) |
| G3 | squidfunk/mkdocs-material | ok | MIT | avoid | 공식 안내(zensical.org/upcoming-changes)가 critical maintenance를 2027-05-05까지 6개월 연장한다고 밝혔다. 신규 도입 시점부터 유지보수 종료가 가깝다. 사이트 자체가 현재 필요 없다. |
| G3 | zensical/zensical | ok | MIT | benchmark_only | 0.1.x 단계이고 공식이 인터페이스 변경 가능성을 명시한다. 문서 사이트 요구가 생기면 그때 재평가한다. |
| G3 | sphinx-doc/sphinx | ok | BSD-2-Clause | avoid | 의존이 17개 안팎(docutils, babel, requests 등)이고 reStructuredText 중심이라 한국어 마크다운 중심 문서군에 이득이 작다. 3.13을 최소 버전으로 요구하는 점은 호환상 맞지만 필요가 없다. |

### 공통 인사이트

- G1: 계정 없이 약관이 명확한 출처는 환율에만 있고(Fed H.10 공개 도메인, ECB 조건부 허용) KR·US 일봉에는 없다. 그래서 PDF 스파이크의 첫 관문은 구현이 아니라 사용자의 계정·키 발급 승인이다. 나는 가입·키 발급을 시도하지 않았다(규칙). ND-08b(KIS 모의 연결 앞당김 거절)와 별개로 'ND-08a 읽기 전용 연구 데이터 계정 허용'을 분리해 받는 편이 PDF 권고와 AGENTS.md 순서를 둘 다 지킨다.
- G1: PDF 의 '기존 MarketFetchPort·Parquet 저장소를 쓴다'는 전제는 현 계약과 맞지 않는다. environment 가 ('synthetic',) 로 고정이고(80403ab·5ff8e29·171e3e4 동일) pyproject 는 dependencies=[]·해시 고정 오프라인 런타임이다. 실데이터 쓰기는 계약 개정(environment 확장, RightsGrant 목적 분리) 또는 저장소 밖 연구 하네스가 필요하다. 후자가 Q27·계약 개정 묶음(W2)과 충돌하지 않는다.
- G1: 모든 공급자 약관이 LLM 입력에 침묵하고, 개인 라이선스 상당수가 '타인·타 조직에 표시·공유 금지'(Tiingo), '제3자 제공 금지'(FSC), 'allows individuals or entities other than User to access'(Alpha Vantage 상업 정의)를 둔다. 외부 클라우드 LLM 프롬프트에 원본 시세를 넣는 것은 위반으로 읽힐 수 있으므로 연구 데이터의 use_tags.llm_input 을 forbidden_until_cleared 로 두고 AI 입력과 분리하라는 PDF 권고를 약관 근거로 뒷받침한다.
- G1: KOGL 4유형(FSC 주식시세정보)의 '변경금지'는 수정주가 처리와 충돌 소지가 있다. 원본 응답을 바이트 그대로 보관하고 조정값은 별도 파생 뷰로만 만들며, 원시가격+기업행동 테이블+복원계수를 분리하는 zipline·qlib 패턴이 약관과 PIT 양쪽에 맞는다.
- G1: Frankfurter 의 blended 기본값은 약관이 다른 공급자(FRED, 마카오 금융당국)를 섞고 마지막 소수 자리가 바뀔 수 있다고 FAQ 가 밝힌다. 한국은행 공급자는 없다. 재현 manifest 에는 provider key 를 고정(providers=ecb)하고 공급자별 terms_url 을 기록해야 한다.
- G1: FX 시점 규칙: ECB 합의는 약 14:10 CET(KST 약 22시), 갱신은 약 16:00 CET(KST 다음날 0시)라 KR 장 마감(15:30 KST=07:30 CET) 시점의 당일 ECB 값은 아직 없다. 또 TARGET 휴무일엔 발표가 없다. FX 는 available_at 기준 ASOF 결합과 명시적 이월 규칙을 manifest 에 기록해야 한다. H.10 은 주간 발표(현재표 Release Date 2026-11-09)라 같은 원리가 적용된다.
- G1: 공개 CSV 한 개(ECB eurofxref-hist.csv)에서 이 환경이 2010-02-12 까지만 있고 일요일 날짜 행과 정수형 값 행이 섞인 파일을 받았다. 원인(상류 문제인지 중간 계층인지)은 모르지만, 수집 직후 스키마·범위·달력 검증이 없었다면 그대로 저장됐을 사례다. 같은 도메인의 SDMX 응답은 정상이었다. 검증 보고서 해시를 manifest 에 넣는 설계의 근거로 쓸 수 있다.
- G1: 1~2년 일봉은 수집·정합·PIT 배관 검증에는 충분하나 ND-03 같은 정책 값을 통계적으로 정할 표본이 아니다(단일 국면, 종목당 최대 약 500 수익률). 스파이크의 완료 기준은 '정책 값 도출'이 아니라 '수집 재현성·정합성·약관 태그 작동'으로 두어야 하며, 이는 NX-LEARN-01 의 표본 현실성 메모와 같은 방향이다.
- G1: KR 기업행동은 FSC 주식권리일정정보(2유형)와 OpenDART 로 나뉘고 액면분할 포함 여부가 불명이다. 가설(미검증): KRX 기준가 조정이 반영된 '대비'·등락률 필드를 이용해 원시 종가 불연속에서 조정계수를 역산하고 기업행동 목록과 대조한다. 스파이크의 검증 질문으로 넣고 결과가 나오기 전에는 사실로 쓰지 않는다.
- G2: Q24 앞단 순수 함수 입출력 타입(설계 제안이며 사용자 결정이 아님). 시그니처: construct_portfolio(inp: ConstructionInput) -> Proposal / Rejection. 모든 타입은 frozen dataclass(slots=True)이고 내부 수치는 int/Fraction만 쓴다(float 리터럴·true division·round() 금지). ConstructionInput 필드: policy: ConstructionPolicy(abs_band/rel_band: Fraction/None, cash_floor_ratio, min_trade_value(통화별), one_way_turnover_cap, cash_penalty_lambda, max_rounding_error, name_weight_cap — 값은 전부 사용자 정책이고 AI가 정하지 않음), now·last_rebalance_at(UTC 문자열; 쿨다운·히스테리시스용 명시 상태), mode('full'/'partial'), nav: Fraction(계좌통화), available_cash: tuple[(ccy, Fraction)](builder 의 A=min(L-H-F, B-U-D) 결과를 그대로 받음, 미래 매도대금 미포함), holdings: tuple[Holding(position: PositionKey, qty: int, ref_price: Fraction, fx: Fraction)], desired: tuple[DesiredWeight(position, weight: Fraction)](동일비중은 Fraction(1,N)·(1-cash_floor_ratio), 고정 배분은 입력 그대로; Σ≤1은 constructor가 검증), rules: tuple[InstrumentRule(position, lot: int, min_qty, max_qty, min_notional, max_notional, max_order_qty 등 builder가 검사하는 값 전체)], cost: 매수·매도별 단조 비용 함수(QH SyntheticCostRule 의 fee_fixed/fee_per_share/tax_fixed/tax_per_share 와 money_quantum ceiling 을 domain/target.py cost_bounds 에서 재사용). 모든 tuple은 PositionKey.key 오름차순·중복 거부(builder _positions 정렬과 동일). Proposal: targets: tuple[TargetValue,...](target_basis='quantity', value는 lot 배수 정수 decimal_string), cash_targets: tuple[CashTarget,...], report: ConstructionReport(종목별 pre_round_qty·final_qty·achieved_w·residual_w·band_state·reason_code, leftover_cash, one_way_turnover, gross_turnover, 목적값 J, stage2_deferred, input_digest). Rejection: reasons: tuple[ReasonCode,...](예: weight_sum_exceeds_one, duplicate_position, cash_floor_infeasible, rounding_error_exceeded, unaffordable_all, band_unfixable_lot_too_large). 조용한 재정규화·자동 전량 청산·빈 결과 반환은 없다. report 를 요청 해시에 묶으려면 TargetRef kind 추가(additive 계약 변경) 또는 SyntheticStrategyProposal 에 해시 삽입 중 하나를 NX-PORTFOLIO-01 착수 시 결정해야 한다(미결정).
- G2: 출력 기준은 target_basis='quantity'가 맞다(정적 근거 + 자체 실험). 이유 ① TargetValue.value 는 decimal_string(소수 18자리 한도, domain/primitives.py:28-39)이고 finite()는 정확 표현이 안 되는 값을 거부(valuation.py:23-30)하므로 1/3 같은 비중은 미리 양자화해야 하고, QH 기존 quantize 는 half-even(valuation.py:33-42)이라 NX-PORTFOLIO-01 'Σ≤1 내림 양자화'에는 별도 floor helper가 필요하다. ② weight 기준이면 builder가 NAV·w/(가격·fx)/lot 을 다시 내림해 이중 내림으로 현금이 더 남고(application/target.py:518-527), 종목별 잔차가 policy.max_rounding_error 를 넘으면 계획 전체를 proposal_infeasible 로 차단한다. 자체 실험(합성 분포, 500건)에서 내림만 한 경우 잔차 1% 초과 368건·2% 초과 268건이므로 소액 계좌에서 weight 기준은 상시 차단될 수 있다. ③ 대역 안 종목을 '현재 수량'으로 두려면 quantity가 필요하다. 단 quantity 기준은 builder의 잔차 검사(L527)를 우회하므로 constructor가 같은 max_rounding_error 정책을 직접 적용해 Rejection 또는 report 경고로 남겨야 정책 의미가 같아진다.
- G2: constructor 는 builder의 사전 검사 거울이어야 한다. builder는 필수 제약을 하나라도 어기면 계획 전체를 blocked·후보 0개로 만든다(target-local-v1.md '후보 한개라도 필수제약 불충족이면 전체 blocked'). constructor 출력이 builder에서 constructor 귀책 사유로 차단되지 않으려면 builder가 검사하는 값을 같은 함수로 미리 검사해야 한다: lot 배수(application/target.py:520,531), min/max 수량·금액(L588), 주문당 수량·거래량 참여(L590), 가격 편차(L584), 통화별 합산 부담 P≤A(L608; 매수는 최악 원금+비용, 매도는 비용만, 매도대금은 가용금에 넣지 않음), 노출·일간 한도. 검증 속성: constructor 가 Proposal 을 반환했는데 build_target 이 {lot_violation, cash_shortfall, proposal_infeasible, exposure_limit, daily_limit, ambiguous_omission} 중 하나로 차단하면 시험 실패(그 외 stale_input·source_incomplete 같은 환경 사유는 제외). 가격·FX·NAV 는 builder 와 같은 snapshot_ref 에서 같은 경로로 가져와야 하며, 차등 시험으로 'floor 단계의 constructor 수량 == builder weight 기준 결과(weight_quantity)'를 종목별로 확인한다.
- G2: 파이프라인 7단계(설계 제안, 각 단계의 OSS 근거 병기). S0 검증·정렬: weight∈[0,1], Σweight≤1 정확 비교, 중복·음수·미허용 종목 거부, scope 밖 보유는 유지; Σ>1을 재정규화하는 구현(Qlib exchange.py L566-L580, py-vallocation L123, nshare-calc)과 반대로 거부하고 Σ<1은 나머지를 현금으로 둔다. S1 리밸런스 여부·허용 폭: 종목별 abs/rel 편차를 Fraction으로 계산하고 현금 비중 검사 포함 여부를 정책 정의로 명시(bt는 포함, cvxportfolio는 현금을 벡터에 포함), 대역 안은 현재 수량 유지, 복귀 지점이 target/edge 중 무엇이든 예산(Σ) 재폐쇄 단계가 필요(fynance edge 예: 합 1.05), 허용 폭은 1주 비중(가격/NAV)보다 작게 잡으면 상시 이탈이 되므로 'band_unfixable' 사유 코드를 둔다. S2 내림 수량화: q0=floor(NAV_investable·w/(price·fx)/lot)·lot, NAV_investable=NAV·(1-cash_floor_ratio)(LEAN FreePortfolioValuePercentage, Qlib 1-risk_degree 와 같은 개념, 값은 사용자 결정). S3 현금 검증: 통화별 Σ매수부담≤A(현재 가용금만, 매도대금 제외); 초과 시 비중이 큰 쪽부터가 아니라 결정론 규칙(deficit 작은 순·키 오름차순)으로 1 lot씩 감소하며 감소 사유를 기록. S4 최소 거래·소액 제거: /Δq/·price<max(min_trade_value, capability.min_notional)인 비청산 거래는 현재 수량으로 되돌리고(전량 청산은 예외, Qlib L904·bt close 와 같은 취지) 되돌림으로 풀린 현금·한도를 반영해 S5 를 다시 돌리는 고정점 반복(되돌림 집합이 단조 증가하므로 최대 N회 종료). S5 잔여현금 극대화: deficit 기준 1 lot씩 매수하되 매 단계에서 종목별 상한·노출 한도·주문 상한·최소/최대 수량·한 건 비용 포함 현금을 검사(제약 인식 탐욕), unaffordable 집합으로 종료 보장, 이어서 1 lot 교환 지역 개선; 결정론 동점 규칙은 PositionKey.key 오름차순. S6 회전율 상한: 편도=½Σ/Δw/를 기본 정의로 하고 초과 시 거래 벡터를 비율 축소 후 정수 재내림(fynance 방식의 정수판)하며 총합 정의와 윈도는 NX-POLICY-05에서 값 없이 고정. 마지막에 사후 조건 검사기(아래 불변식)를 항상 실행하고 위반이면 Rejection.
- G2: 목적함수는 정책 값이며 AI가 정하지 않는다. 정확 유리수 검증(실행): J=Σ/w_i-a_i/+leftover/NAV 는 Σw=1일 때 항등식으로 2×Σmax(w_i-a_i,0)이다(2000건 위반 0). 따라서 PyPortfolioOpt LP(λ=1)는 초과 배분에 벌점이 없고 미달만 줄인다. λ<1 이면 초과가 벌점이 되고 λ>1 이면 현금 보유를 더 꺼린다. QH 는 λ(현금 벌점)와 '초과 허용 여부'를 ConstructionPolicy 필드로 두어 사용자 결정(ND-01 배분 방식 계열)으로 남기고, 보고서에 J와 L1 추적오차, 잔여현금 비율을 함께 표시한다. 자체 실험(합성 분포·seed 20261115·종목 3~7·NAV 1/3/10백만 원, 정확 유리수, 저장소 코드 아님): 내림만 평균 잔여현금 8.24% NAV, 최근접 반올림 252/500건 현금 음수, NAV 기준 탐욕 잔여현금 1.38%·잔차 1% 초과 303/500건(내림만 368건), 소규모(N≤5, floor±2 완전탐색) 오라클 대비 J 격차 평균 0.0142·95/308건 엄격히 나쁨·최대 0.461. 결론: 정수 단위가 지배적이라 탐욕은 잔여현금은 줄여도 종목별 잔차는 거의 못 줄이므로, 허용 폭·max_rounding_error 를 1주 비중보다 작게 잡으면 실무에서 쓰기 어렵다는 점을 NX-POLICY-06 드라이런(정책 후보×보유 상태별 차단율)에 포함해야 한다.
- G2: 속성 기반 불변식(시험 전략, 사후 조건 검사기로도 같은 함수 사용). I1 비중 합: Σ(final_qty·price·fx)/NAV + Σ비용/NAV ≤ 1-cash_floor_ratio 를 Fraction 으로 정확 비교. I2 현금: 통화별 cash_after=A-Σ매수 최악 부담(원금+수수료+세금)-매도 비용 ≥ cash_floor ≥ 0(매도대금 미산입). I3 정수·lot: 모든 final_qty 가 lot 의 음이 아닌 정수 배수, 거래 건은 min_qty≤/Δq/≤max_qty, min_notional≤금액≤max_notional. I4 한도: 종목 비중 상한·exposure_limits·max_order_amount/quantity·일간 한도 준수. I5 결정론: 같은 입력 두 번 호출 시 canonical 직렬화 바이트 동일, 그리고 holdings/desired/rules 입력 순서를 섞어도 출력 동일(순서 불변, metamorphic). I6 멱등·무진동: 출력 수량을 보유로 적용하고 같은 목표·가격으로 다시 호출하면 거래 0(churn 없음). I7 최소 거래: 비청산 거래는 모두 최소 거래금액 이상, 대역 안 종목은 거래 없음. I8 거부 vs 근사: 종목 잔차가 max_rounding_error 를 넘으면 조용히 근사하지 않고 Rejection 또는 사유 코드. I9 재정규화 금지: Σdesired>1 또는 범위 밖 weight 는 Rejection, Σ<1 이면 나머지는 현금(스케일 업 금지). I10 극대성: 종결 시 deficit>0이고 한 건 비용 포함 현금으로 살 수 있으며 한도를 지키는 종목이 남아 있지 않다. I11 단조: 가용 현금을 늘려도 편입 가능한 lot 수가 줄지 않는다(탐욕 단조성 약식 검사). I12 정적 float 금지: 모듈 AST 에서 float 리터럴·float()·round()·ints 간 / 연산 사용 0건. 생성기는 stdlib random.Random(고정 seed)로 수만 건을 돌리고 경계(N=1, 1주>목표 금액, lot>가용 현금, 모든 종목 대역 안, 현금 하한 100%, 동점 가격 동일 종목군, MAX_INPUTS=128)를 명시 케이스로 추가한다. hypothesis 같은 외부 시험 라이브러리는 의존성 ADR(SG-03) 이전에는 도입하지 않으며 라이선스·설치 가능성은 이번에 조사하지 않았다.
- G2: OSS 결함 코퍼스를 변이(mutant) 시험으로 쓴다: 각 변이가 위 불변식 중 하나에서 실패해야 시험이 유효하다. M1 최근접 반올림으로 교체(cvxportfolio simulator L227, fynance L481) → I2 실패(자체 실험 252/500건 현금 음수). M2 비중 합으로 나눠 재정규화(Qlib L566-L580, py-vallocation L123) → I9 실패. M3 최적화 뒤 소액 제거에서 현금 재검증 생략(balancer L118, cvxportfolio L325-L334) → I2 실패 가능성이 있는 시드 탐색. M4 dict·입력 순서 의존 동점 처리(bt Rebalance 순회) → I5 실패. M5 반복 횟수 상한으로 중단(PyPortfolioOpt counter==10) → I10 실패. M6 허용 폭 edge 복귀를 종목별 클립만 하고 예산 재폐쇄 생략(fynance edge, 손 계산 합 1.05) → I1 실패. 또 하나의 반면교사: 불가능 제약을 빈 목표로 바꿔 전량 청산(bt LimitWeights L1604, Qlib order_generator L115-L123)하는 변이는 '실패 종목은 현재 수량 유지, 전량 청산 없음' 속성(I9 확장)으로 잡는다.
- G2: 차등·오라클 시험. (a) floor 단계 차등: constructor 의 q0 가 builder 의 weight_quantity/ _positions floor 결과와 종목별로 동일해야 한다(application/target.py:518-527, domain/target.py:572-579). (b) 소규모 완전탐색 오라클: N≤5~6, 각 종목 floor±window(balancer optimizer.py L76 의 곱집합 방식을 정확 산술로 재구현)에서 목적 J 최소 해를 구하고, 운영 탐욕 해의 J 격차를 보고(격차 한도는 정책이 아니라 회귀 감시용 기록값)한다. 운영은 N 10~15 전수 탐색이 불가능((2w+1)^N)하므로 오라클은 시험 전용이다. (c) 비용 오라클: 단조 비용 함수의 정수 이분 탐색 최대 수량을 Qlib 식 닫힌 식(L850-L856)과 비교하는 정확 산술 시험(최소 수수료 구간 경계 포함). (d) skfolio/PyPortfolioOpt 의 float 비중을 Fraction(float) 정확 변환→quantize 한 입력으로 같은 constructor 를 돌려 경계 계약(NX-PORTFOLIO-04) 시험에 재사용한다(외부 라이브러리는 개발 환경 오라클 한정, 의존성 도입은 SG-03 이후).
- G2: 밴드·회전율·최소 거래의 정의가 저장소마다 다르다(NX-POLICY-05 근거). 밴드: bt 상대 편차이며 한 종목만 벗어나도 전체 목표 복귀(edge 없음, 목표 0·보유>0이면 즉시 트리거, 현금 절대 편차 검사 포함), fynance 절대 %p·종목별 최대 편차이며 full/edge 선택, cvxportfolio 현금 포함 2-노름 전부 또는 무거래, balancer 절대 %p+계좌 합계 회전 최소 임계. 회전율: cvxportfolio ½‖Δw‖₁(편도), fynance Σ/Δw/(총합이면서 '편도'라 명명), balancer 주식 수 합과 금액. 최소 거래: cvxportfolio 정수화 뒤 금액 임계, fynance 이전 주수 유지 상태, LEAN NAV 대비 0.1%(마진 증감 기준), balancer 최적화 뒤 건별 제거. 히스테리시스·쿨다운은 어느 저장소에도 없다. 시사점: ① 정의를 코드 전에 값 없이 문서로 고정한다(편도/총합·윈도, 절대/상대, 현금 포함 여부, 임계의 기준 통화). ② 쿨다운은 순수 함수의 명시 입력(last_rebalance_at, now)으로 두고 시각 계산은 호출자(감시 slot)가 한다. ③ 임계는 1주 비중보다 작아지면 의미가 없으므로 유효 허용 폭=max(정책 허용 폭, 해당 종목 1 lot 비중) 규칙 또는 band_unfixable 사유 코드를 정의한다.
- G2: 2단계 리밸런싱과 자금 재사용(NX-POLICY-07 근거). 읽은 구현 전부가 같은 단계에서 매도 대금을 매수 자금으로 재사용한다고 가정한다: Qlib OrderGenWInteract 는 거래 가능 가치에 현금을 합산(order_generator.py L105-L123), bt 는 순차 allocate 의 capital 조정 후 현금 하한 검사 없음, LEAN OrderByMarginImpact 는 축소 주문을 먼저 실행(결제 모델은 읽지 않음), balancer 는 매도 후 현금 새로고침 뒤 매수. 반면 QH 는 '미래 매도대금으로 새 매수 여력을 만들지 않는다'(target-local-v1)이므로 constructor 는 1단계에서 [매도 + 현재 가용 현금만으로 충당되는 매수]만 Proposal 로 내고, 나머지 목표 수량은 report.stage2_deferred 로 남겨 predecessor_plan_ref 기반 2단계 호출(체결·결제·대사 후)로 넘긴다. 같은 함수를 2단계에서 다시 호출할 때 입력(holdings, available_cash)이 갱신되므로 별도 코드가 필요 없다는 점이 순수 함수 설계의 이점이다.
- G2: 비용 모델 표현. 읽은 저장소의 비용: cvxportfolio a/x/+bσ/x/^1.5/√V+cx 와 주당 0.005(float, 매도 세금 없음), bt 사용자 함수 commission_fn(q,p), LEAN 수수료 모델 객체, Qlib 비율×금액과 min_cost 중 큰 값(+거래량 참여 제곱 충격비용), fynance/py-vallocation/PyPortfolioOpt/balancer 비용 없음. QH 현재 규칙은 side별 fee_fixed+fee_per_share·q, tax_fixed+tax_per_share·q 를 money_quantum 올림(domain/target.py:558-564 cost_bounds)이고 NX-TAX-COST-01 에서 비율형·세금이 추가된다. 권고: constructor 는 비용을 side·수량의 단조 비감소 함수 인터페이스로만 받아(구체 형태에 비의존) 정수 이분 탐색으로 '현금 한도 내 최대 lot 수'를 구한다. bt 의 뉴턴식 탐색(반복 1e4 상한과 RuntimeError, L1726-L1768)과 LEAN 의 lot 단위 감소 루프(예외 던짐, L503-L541)는 비용 형태나 정수 가정에 기대는 종료 조건이라 피한다. 세금은 매도에만 걸리고 최소 수수료는 구간 비선형이므로 비용 함수는 side를 인자로 받아야 한다.
- G2: 결정론·재현. 12개 코드 경로 중 bt는 dict 삽입 순서, PyPortfolioOpt 는 pandas 정렬·argmax 동점, py-vallocation 은 idxmax/sort_values 동작, 혼합정수 솔버는 솔버·버전에 따라 해가 달라질 수 있다. QH constructor 는 난수·솔버가 없고 모든 정렬 키가 PositionKey.key 이며 동점 규칙을 명시(deficit 큰 순→키 오름차순)하므로 같은 입력은 같은 바이트(qh-canonical-json-v1)를 낸다. 출력과 입력 digest 를 report 에 넣고 골든 해시 시험(N별 직렬화 바이트 측정 포함, NX-PORTFOLIO-01 완료 기준)을 둔다. 외부 최적화 결과를 입력 비중으로 받을 때는 solver 이름·버전·상태·허용값을 manifest 로 남기되 constructor 자체는 solver 비의존으로 유지한다.
- G2: 라이선스·의존성 결론(정책 결정은 사용자·SG-03). cvxportfolio(GPL-3.0)와 py-vallocation(GPL-3.0-or-later)은 benchmark_only(개념 참고, 코드 복사·링크 금지, 전이는 법률 확인 필요). bt·fynance·Qlib·PyPortfolioOpt·balancer 는 MIT, LEAN·nshare-calc 는 Apache-2.0 이지만 모두 float(LEAN 제외)이고 QH baseline dependencies=[] 와 충돌하는 필수 의존(pandas/numpy/cvxpy/numba/torch/cvxopt 등)이 있어 adopt_dependency 후보가 없다. 코드 수준 차용이 가능한 MIT 저장소도 float 산술을 정확 산술로 다시 써야 하므로 사실상 설계 참조로만 가치가 있다. Python 3.13 신호는 bt(classifier 3.9~3.13), fynance(3.10~3.13), PyPortfolioOpt(3.10~3.14), cvxportfolio(CI build 3.13)만 정적으로 확인했고 설치·실행 검증은 없다. 스타 수는 어떤 판정에도 쓰지 않았다.
- G3: [전체 시험 3.8시간을 계약 개정마다 돌리지 않는 구체안. 전부 설계 제안이며 실행·측정하지 않았고 시험 실행은 ND-13 승인 후에만 한다] 0단계 전제: 3.8시간은 8a27220 고정 증거 두 값의 합(6,800.646 + 6,932.892 = 13,733.5초)이고 현재 HEAD는 제품 시험이 898개로 더 많다. 1단계 호환 등급 선언: qh-contract-change에 항목을 추가해 개정마다 additive(기존 24건 골든 raw SHA 불변, 새 선택 필드만)와 breaking(새 schema_version·이행 계획·독립 검토)을 선언한다. QH decoder는 닫힌 codec이라 필드 추가도 구 reader에는 FORWARD 비호환이므로 additive라도 reader 이중 읽기 기간이 필요하다(Confluent·buf 어휘 차용, 설계 추론). 2단계 계층 실행: T0(수초) 기존 check_quality + 계약 SHA manifest + 시험 인벤토리(ast로 def test_ 수와 ID 해시 대조) + 문서 생성 블록 --check. T1(분 단위) 영향 시험 = 표준 라이브러리 ast import 그래프(소스 모듈→시험 모듈)에 비Python 입력 명시 지도를 더한 것(ai-evaluation-spec-v1.json→test_investment_ai_evaluation, baseline-v1.json·docs/development/investment-ai.md→같은 시험, migrations/*.sql→test_product_database·test_execution_sql). testmon은 이 정적 입력을 추적하지 않아 부적합하다. 지도에 없는 변경은 안전하게 T3로 올린다(fail-safe). T2(수십 분, 미측정) 제품 시험 전체의 모듈 단위 병렬 샤딩(표준 라이브러리 subprocess 스크립트 또는 unittest-parallel --level=module). 선행 조건은 공유 경로 /tmp/quantharbor-q25 분리다. 이상적 N병렬 하한은 가장 느린 모듈 시간이므로 측정 전 추정을 쓰지 않는다. T3 실제 DB 86개는 시나리오에 모듈 태그를 붙여 additive 개정은 관련 시나리오만(시나리오 평균 80.6초이므로 N개=약 80.6×N초) 돌린다. T4 직렬 전체 836(898)+86은 '계약 에포크' 끝에서만 1회. 3단계 에포크 일괄화: breaking 개정(reduce-only, 비율 비용, 다중 실패 수집 등)을 한 에포크로 묶어 T4를 k번이 아니라 1번만 돈다. PDF의 '계약 개정 한 묶음(target-local-v2)' 권고와 같은 방향이다. 4단계 증거 표기: 부분 실행은 'PARTIAL + 실행한 시험 ID 목록 해시 + 입력 manifest SHA'로 기록하고 전체 통과로 합산하지 않는다(v2:108 원칙, 입력 전후 동일 규칙 유지). 5단계 병렬 DB: DB 컨테이너는 cpus 1, 256MB 제한이고 호스트는 10코어/64GiB(sysctl)이나 Docker VM 할당은 미확인이므로 4병렬이면 이상적으로 약 29분(6,933/4)이라는 산술은 시나리오 독립과 자원 충분 가정의 가설이다.
- G3: pytest 도입은 연쇄 결정이다. xdist·testmon·mutmut은 모두 pytest를 요구하지만 저장소의 시험 ID·증거 JSON(test_results_sha256)·CI 템플릿·docs가 unittest 형식에 고정되어 있다(manifest 산출 알고리즘은 알 수 없어 영향 크기는 UNVERIFIABLE). 가장 가벼운 경로는 unittest 유지 + 표준 라이브러리 측정(--durations, 3.12+) + 모듈 단위 샤딩 + Hypothesis(TestCase) 순이다. pytest는 변이·병렬이 이 경로로 해결되지 않을 때만 ADR로 검토한다. 이때 ID 연속성 매핑 규칙이 ADR의 필수 항목이다.
- G3: 병렬 안전성은 도구 선택보다 먼저 풀어야 할 저장소 내부 문제다(정적 판독, 실행 미확인). test_investment_ai_evaluation.py:22의 OUT=/tmp/quantharbor-q25 고정 경로를 test_investment_ai_review.py:151이 FixedEvaluation.setUpClass()로 다시 쓰고, setUpClass가 7개 모듈(총 9곳)에 있다. 병렬 프로세스가 같은 manifest 경로에 쓸 수 있으므로 프로세스별 임시 경로 분리가 병렬 도입의 선행 시험 인프라 변경이다. AGENTS.md상 시험 수정·실행은 사용자 요청이 있을 때만 가능하다.
- G3: Hypothesis 적용 위치와 설정: 첫 대상은 외부 의존이 없는 순수 도메인(domain/execution_math.py, ledger.py, primitives.py, serialization.py)이다. 속성 후보는 Decimal quantize 왕복 정확성, 합계 보존·음수 금지, 정준 직렬화 멱등, 원장 재생 결과가 메모리 모델과 일치(차등/상태기계, NX-OPS-INFRA-02). 설정은 register_profile로 derandomize=True, database=None, deadline=None, 고정 max_examples, print_blob=True를 명시한다. 로컬과 CI 감지 시 기본값이 다르다는 공식 문서 내용 때문이다. 실패 입력은 DB가 아니라 코드의 @example 회귀 사례로 승격한다. .hypothesis/는 현재 .gitignore에 없고 check_quality는 알 수 없는 확장자 파일을 거부하므로 database=None을 쓰거나 .gitignore에 추가해야 한다. 같은 경우 .testmondata, mutants/도 .gitignore에 없다(.pytest_cache, .coverage는 있음).
- G3: dev 전용 의존성 도입 규칙(새 의존성은 ADR 선행): (1) [project].dependencies=[]는 유지하고 도구는 별도 dev 컨테이너에만 둔다. pyarrow 선례(containers/Dockerfile.market-storage의 --no-index --no-deps --require-hashes, 휠 SHA-256 고정)를 따른다. PEP 735 [dependency-groups]는 Final이고 빌드 메타데이터에 안 들어가지만 pip --group 지원 버전은 미확인이고 현 관례와 맞는 것은 requirements 파일이다. (2) Hypothesis는 sortedcontainers 2.4.0(순수, 마지막 릴리스 2021-05-16) + 네이티브 cp313 aarch64 휠 1개라 해시 고정 대상이 2개다. 소스 빌드는 Rust가 필요해 network none 빌드에서 실패한다. (3) pytest 계열은 pytest 외에 iniconfig, packaging, pluggy, pygments가 필요하고 mutmut(textual 포함)·cosmic-ray(aiohttp, sqlalchemy, gitpython 포함)는 전이 의존이 훨씬 무겁다(직접 의존만 확인, 전이 폐쇄는 미측정). (4) 새 Dockerfile·requirements는 scripts/check_quality.py:134-135의 허용 Dockerfile 2종 목록과 컨테이너 정의 드리프트 검사 상수를 함께 바꿔야 한다. 각 ADR은 라이선스 본문·소유자·마지막 릴리스·고정 버전을 도입 시점에 다시 확인한다(oss-survey 승계 금지 원칙).
- G3: 변이 시험은 외부 도구 대신 가드 변이 하니스를 권고한다(NX-OPS-INFRA-02의 요구는 '한도·가드를 변이했을 때 시험이 실패하는가'다). 표준 라이브러리 ast로 이름 붙은 가드 10~20개(위험 한도 비교, 예약 해제 조건, 날짜 경계 등)를 임시 복사본에서 변이하고 소유 시험 모듈만 실행해 '죽음/생존'을 증거로 남긴다. 이유: mutmut은 첫 통계 수집이 전체 시험 1회(113분 이상)이고 pytest·fork가 필요하며 README가 fork 상속 위험(DB 연결·스레드)을 경고한다. cosmic-ray는 변이를 디스크 원본에 직접 적용해 '추적 입력 708개 전후 동일' 증거 규칙과 충돌한다. 두 도구의 only_mutate·max_stack_depth·timeout·baseline 개념만 차용한다.
- G3: CI 활성화에 필요한 사실 정리: (1) GitHub-hosted job 상한은 6시간이고 15분은 템플릿 정책이다. (2) 공개 저장소의 표준 러너(arm 포함, 4 vCPU/16GB)는 무료이며 비공개는 계정 포함 시간을 쓴다. 저장소 공개 여부는 미확인이다. (3) 서비스 컨테이너는 --network 미지원이라 합성 DB 격리와 충돌하므로 docker compose/digest 고정 단계를 유지한다. (4) paths 필터로 건너뛴 워크플로는 필수 검사를 Pending으로 두어 병합을 막으므로 계층 분할은 job 조건이나 집계 job으로 한다. (5) check_quality.py:124가 .github/workflows를 protected_path로 거부하므로 활성화는 AP-06과 함께 check_quality·ci-definition 문서의 동시 변경이 필요하다. (6) 샤딩 matrix의 max-parallel과 fail-fast 키는 존재한다(workflow-syntax). (7) 전 과정은 사용자 승인 없이 workflow를 만들지 않는다는 NX-OPS-INFRA-01 완료 기준을 따른다.
- G3: 문서 거버넌스는 큰 프레임워크 대신 '기계 판독 정본에서 생성 + 드리프트 검사'가 맞다. 근거: docs/status.md는 149,123바이트·945줄이고 구조화 정본 config/ai/execution-queue.json은 35,772바이트이며 상태 필드를 이미 갖는다. 추적 파일은 docs 하위 529개(마크다운 206, 증거 JSON 300, research 59, decisions 34)이고 PDF는 2주간 마크다운 +0.96MB를 측정했다. 권고: (a) status.md를 '현재 상태 요약(생성 블록)'과 '추기 전용 이력'으로 분리하고 요약은 큐 JSON에서 생성한다. cog의 --check(재실행해도 파일이 안 바뀌어야 함)·-c(체크섬으로 수동 편집 감지) 의미론을 표준 라이브러리 스크립트로 구현해 check_quality에 편입한다. (b) 결정 기록은 docs/templates/decision.md를 유지하되 MADR 4의 status 어휘와 선택지 필드만 보강하고 번호·색인은 표준 라이브러리 생성기로 한다. adr-tools(GPL-3.0, 휴면)와 log4brains(Node, 마지막 npm 릴리스 2024-12)는 회피한다. (c) 문서 사이트는 보류한다: MkDocs 안정판 1.6.1이 2024-08 이후 정체, 2.0은 dev 단계, Material for MkDocs는 critical maintenance가 2027-05-05까지, Zensical은 0.1.x다. (d) 절대경로 121회(PDF)와 링크 깨짐은 check_quality 규칙으로 넣으면 NX-DOCS-PROCESS-03을 일회성이 아닌 상시 규칙으로 만든다.
- G3: 계약 호환성 검사는 JSON Schema 도구를 지금 도입할 단계가 아니다. docs/contracts의 JSON 5개에는 $schema·properties·additionalProperties가 없고 계약 본문은 Markdown 산문이다(정적 grep). jsoncompat(MIT, 0.6.0, 2026-11-12)와 jsonschema-diff(0.1.11)는 0.x 초기이고 GSoC 2026 제안서가 표준 도구 부재를 시사한다(검색 요약, 직접 확인 아님). 현실적 방법은 골든 파일 시험의 확대다: 계약별 raw SHA 고정(ai-evaluation-spec-v1.json은 이미 SPEC_SHA 검사), 정준 직렬화 왕복, 과거 버전 골든(24건)을 TRANSITIVE 관점으로 계속 읽는 시험, 계약 문서에 호환 등급·소비자 목록 필수 필드. 계약을 JSON Schema로 정형화하기로 결정하면 그때 jsoncompat·schema-diff를 재평가한다.
- G3: 한국 개인 프로젝트 규모의 최소 구성 제안(우선순위): 1순위 의존성 0 — unittest --durations 프로파일 1회(ND-13 승인), 표준 라이브러리 샤딩 스크립트, ast 기반 영향 지도·시험 인벤토리, 생성 블록 --check, 가드 변이 하니스, 호환 등급 선언. 2순위 dev 전용 1개 — Hypothesis(ADR+SG-03, 해시 고정 휠). 3순위 조건부 — unittest-parallel(샤딩 스크립트가 부족할 때). 4순위 pytest 계열(xdist·testmon·mutmut)은 pytest 도입 ADR이 선행. 문서 사이트·ADR 도구·JSON Schema 비교 도구는 지금은 도입하지 않는다. work-list 연계: NX-OPS-INFRA-01(계층 분류·타임아웃 정책), NX-OPS-INFRA-02(상태기계·변이·차등), NX-DOCS-PROCESS-01~03(생성 블록·절대경로 규칙), ND-13(시험 실행·시간 예산·CI), ND-12(의존성 정책).
- G3: 원 조사(2026-10-19 스타 기반 oss-survey)와 달리 이번에는 스타 수를 판정 근거로 쓰지 않았다. 유지보수 변동성이 크다: pytest-subtests는 archived(기능은 pytest 9로 병합), Material for MkDocs는 maintenance 연장, Hypothesis는 내부를 Rust로 이전해 공급 형태(순수 휠→네이티브 휠)가 바뀌었다. 같은 도구라도 도입 시점에 라이선스 본문·릴리스·휠 형태를 다시 확인하는 절차를 ADR 필수 항목으로 두는 것이 안전하다.

### 좋은 OSS가 없어 자체 구현이 필요한 능력

- G1: 한국 주식 수정주가·기업행동(액면분할·병합·기준가 조정) 통합 처리: 법적으로 깨끗한 원천과 라이선스가 명확한 OSS 조합을 찾지 못함(pykrx 계열은 금지 원천 래퍼).
- G1: 공급자 약관 태그(저장·재배포·LLM 입력·보고)를 데이터셋에 붙여 사용 목적별로 읽기를 차단하는 약관 인지 데이터 게이트웨이: 해당 OSS 없음. 현 저장소의 RightsGrant(purposes)가 가장 가까움.
- G1: 공급자 복원(restatement)을 추적하는 가벼운 PIT 가격 저장: ArcticDB 는 라이선스가 부적합하고 나머지는 직접 구현이 필요. 현 저장소의 불변 dataset_version 체인이 최근접.
- G1: 약관 확인일·약관 본문 해시를 자동 추적하는 도구: 못 찾음(정적 문서 해시 비교 스크립트를 직접 만들어야 함).
- G1: 한국 무료 일봉 중 재배포·LLM 입력 허용이 명시된 원천: 못 찾음(FSC 는 비상업·재배포 금지, KRX 는 금지, 증권사는 계정 필요).
- G2: 정확 산술 정수 lot 배분: Fraction/정수 원 기반으로 lot·현금 하한·최소 거래금액·종목별 상한·한 건 비용(side별 정액+주당+비율+세금, money_quantum 올림)을 한꺼번에 만족하는 구현. 읽은 저장소는 전부 float(LEAN만 C# decimal)이고 비용은 비율/주당 단순형이거나 없다.
- G2: 현재 가용 현금만으로 충당되는 매수 선택과 2단계 이월(stage2_deferred): QH는 미래 매도대금을 매수 여력에 쓰지 않는 규칙이 있으나 읽은 구현은 전부 같은 단계 자금 재사용을 가정한다.
- G2: fail-closed 검증과 사유 코드: 입력 재정규화·불가능 제약의 전량 청산·빈 결과 반환·예외 삼키기 없이 typed Rejection(ReasonCode)과 종목별 '현재 수량 유지' 동작을 가진 구현은 없다.
- G2: builder 사전 검사 거울(pre-flight): 계획 전체 차단 의미론에 맞춰 lot·tick 가격 규칙·min/max 수량·금액·주문당/일간 한도·거래량 참여·통화별 합산 부담 P≤A를 미리 만족시키는 구성기와 'constructor⇒builder 수락' 차등 시험.
- G2: 제약 인식 잔여현금 극대화: 탐욕 배분 중 매 단계 종목 상한·노출 한도·주문 상한·비용 포함 현금을 검사하고 극대성(더 살 수 없음)과 종료를 보장하는 알고리즘. 읽은 탐욕 구현은 목표 비중만 알고 한도를 모른다.
- G2: 허용 폭 정책 전체: 절대+상대 허용 폭, 복귀 지점(target/edge) 후 예산 재폐쇄, 히스테리시스·쿨다운(명시 상태 입력), 1 lot 비중보다 작은 허용 폭의 band_unfixable 판정, 현금 비중 포함 여부 정의. 읽은 구현은 단일 임계 또는 전부-아니면-무거래뿐이다.
- G2: 목적함수 명시와 성능 보고: 현금 벌점 λ·초과 허용 여부를 정책 필드로 노출하고 오라클 대비 격차(J, L1)를 보고하는 구현. 읽은 구현은 목적이 암묵적이다(PyPortfolioOpt LP는 사실상 미달만 벌점).
- G2: 통화별 현금 분리(KRW/USD, 자동 환전 없음)와 시장별 단주 규칙: 읽은 구현은 단일 통화이며 미국 소수점 거래·국내 1주 단위·환전 필요액 안내(수동)를 함께 다루지 않는다. 미국 단주 지원은 B01 확인 전 미가정.
- G2: canonical 직렬화·입력 digest·골든 해시와 결합된 재현 보장: 읽은 구현은 시드·정렬 의존이 암묵적이고 결과의 해시 결속이 없다.
- G2: 정적 float 금지 검사(AST)와 OSS 결함을 변이로 쓰는 속성 시험 하네스: 도메인 특화라 직접 만들어야 한다.
- G3: 증거 결속 부분 실행 판정: 실행한 시험 ID 목록 해시와 입력 manifest SHA, 입력 전후 동일 확인, 'PARTIAL을 전체 통과로 합산 금지'를 강제하는 기성 도구는 확인하지 못했다. testmon·xdist 등은 선택·속도 최적화만 하고 증거 귀속은 다루지 않는다. QH가 표준 라이브러리로 직접 구현해야 한다.
- G3: 비Python 입력(계약 JSON, migration SQL, lock 파일, docs 일부)에서 시험 모듈로의 영향 매핑: testmon 공식 문서가 정적 파일 미추적을 밝히며 이를 해결한 기성 도구를 확인하지 못했다. 명시적 지도가 필요하다.
- G3: network none 합성 DB와 GitHub Actions 서비스 컨테이너의 양립: 서비스 컨테이너는 --network 옵션을 지원하지 않는다. 표준 패턴이 없어 docker compose 단계(현재 템플릿 방식)를 유지해야 한다.
- G3: JSON Schema가 아닌 Markdown 산문 + JSON 픽스처 계약의 호환성 검사: 호환성 도구는 JSON Schema·OpenAPI·Protobuf·Avro 대상이다. QH 계약 형식에는 직접 맞는 도구가 없다.
- G3: 한국 시장 도메인 속성 전략(호가 단위, KRX·미국 거래일 캘린더, KRW 정수 단위·USD 소수 2자리 양자화, 환율 변환 반올림)을 제공하는 Hypothesis 전략 라이브러리: 이번 조사에서 확인하지 못했다. 도메인 전략은 직접 작성해야 한다.
- G3: 한국어 중심 대규모 문서군의 상태 문서 자동 생성·축약(큐 JSON → 현재 상태 요약, 이력 분리)을 위한 기성 도구: cog 같은 범용 생성기 외에는 확인하지 못했다.
- G3: 운영 금융 코드베이스에서 Hypothesis 상태기계를 쓴 검증된 공개 사례: 튜토리얼과 학술 논문 외에는 확인하지 못했다.

## 15. 약관·사실 검증 (VERIFIED 외)

| 판정 | 항목 | 비고 |
|---|---|---|
| UNVERIFIABLE | 한국은행 ECOS 환율 약관(저장·재배포·LLM 입력) | 분류: 침묵 취급. 요약이 맞더라도 환율 시리즈의 작성기관이 한국은행인지 외부 기관인지 확인 못 했다. 키 발급 화면의 약관 동의가 필요하므로 '계정 필요'. 같은 한국은행의 홈페이지 저작권보호방침(menuNo=200228)은 직접 읽어 확인: '출처가 한국은행임을 반드시 밝혀야 하며, 해당 정보를 수정 |
| NEEDS_PROFESSIONAL_CHECK | 공공누리 4유형 '변경금지'가 수정주가·조정계수 파생 계산을 막는가 | 파생 지표 계산이 '변경'에 해당하는지는 약관 문구만으로 판단할 수 없다. 설계 완화책: 원본 응답을 바이트 그대로 보관하고 조정값은 별도 파생 뷰로만 만들며 외부에 내보내지 않는다. 저작권 전문가 확인 전에는 수정주가를 보고서·AI 입력에 쓰지 않는다. |
| UNVERIFIABLE | Twelve Data: 내부 사용 목적 저장 허용이나 캐시 기간이 'Documentation' 참조, 무료 데이터 상업 이용 금지, 해지 후 30일 내 삭제 | 약관 원문 curl 로 확인(정적)했으나 2.3(g)가 가리키는 허용 기간을 docs 페이지에서 찾지 못해 저장 허용 범위는 확정 불가, 침묵 취급. 분류: 저장 조건부(기간 미확인), 재배포 금지, LLM 입력 침묵. 한국 시장 커버리지 미확인. 계정 필요. |
| UNVERIFIABLE | Stooq 일봉: 약관 확인 불가, 자동 취득에 브라우저 검증 관문 존재 | 분류: 침묵·확인 불가. 검증 스크립트를 풀어 우회하는 것은 접근 통제 회피로 보아 하지 않았다. 스파이크 자동 파이프라인에서 제외, 수동 다운로드만 가능성이 남음. |
| UNVERIFIABLE | Massive(구 Polygon) 개인 약관과 무료 등급 | 분류: 침묵·확인 불가. 계정 필요. 미확인 목록에 남김. |
| NEEDS_PROFESSIONAL_CHECK | ArcticDB 라이선스는 README 와 LICENSE 의 production 정의가 다르다 | 본문 우선 규칙에 따라 BSL 1.1 로 분류하되 두 문서가 불일치해 보수적 해석을 따르고 제품 채택은 법률 확인 후로 둔다. 연구용 비프로덕션 사용은 BSL 기본 허가 범위에 들어가는 것으로 읽히나 전문가 확인 전에는 쓰지 않는다. |
| INCORRECT | GitHub Actions 서비스 컨테이너로 PostgreSQL을 쓰면 합성 DB의 network none 원칙을 유지할 수 있다 | 저장소 compose는 network_mode: none, listen_addresses 비움, Unix 소켓 전용이다(containers/compose.product.synthetic.yaml:8). 서비스 컨테이너는 이 구성을 못 만든다. 현재 템플릿처럼 docker 단계(digest 고정 이미지)로 |
| INCORRECT | 호스트 기본 python3와 프로젝트 Python 요구가 일치한다 | dev 도구를 호스트에서 돌릴 때는 python3.13을 명시해야 한다. CI 템플릿은 python3.13을 명시한다. 이 조사의 분석 스크립트는 python3 -I(3.14)로 실행했으며 저장소 코드를 실행하지 않았다. |
| UNVERIFIABLE | 금융 원장 불변식에 Hypothesis 상태기계를 적용한 공개 사례 | 운영 금융 코드베이스의 검증된 적용 사례는 확인하지 못했다. 보존·음수 금지·차변=대변·재생 일치 같은 속성은 일반 속성 시험 문헌에서 통용되는 패턴이고 QH 적용은 설계 제안이다. |
| UNVERIFIABLE | 이 저장소 코드베이스에서 변이 시험·속성 시험·병렬 시험의 실제 실행 시간 | 어떤 도구도 설치·실행하지 않았다. 모든 시간 수치는 증거 JSON의 기록값과 산술에서 나온 가설이다. 제품 836개의 개별 시험 시간은 기록이 없다(평균 6,800.646/836=8.13초만 계산 가능). |

## 16. 분석 한계

- 이번 종합은 새 저장소 읽기·명령 실행 없이 입력 findings 를 합성했다. 테스트·DB·Docker·품질 게이트는 실행하지 않았고 836/86 PASS 는 8a27220 고정 root 자기보고 인용일 뿐 재현하지 않았다. codebase-memory-mcp 는 쓰지 않았다.
- 검증 상태가 upheld 인 finding 은 R1-01·02·04·05·13·27, R2-07·29 뿐이다. 나머지는 not_checked(정적 측정)이며 R2-27 은 refuted 라 근거로 쓰지 않았다. 재검증 상한 때문에 전수 검증이 아니다.
- v3 MD 는 일부 레인이 §1·§3·§11 중심으로만 읽었고 PDF 는 텍스트 추출본이라 표 열이 깨져 문맥으로 재구성한 셀이 있다. 이전 v2 설계서·첫 PDF·검증 기록 전문은 정독하지 않았다.
- R3 의 선행 열 파싱(직접 9, 전이 22, 41%)과 import 방향 판단은 정적이며 동적 호출은 보지 않았다. build_target 드라이런 오라클(SyntheticTargetRepository)은 클래스 존재만 확인했다.
- 비평가의 저장소 PUBLIC 상태는 gh 읽기 전용 단발 조회(2026-11-15)이고 이번 합성에서 재확인하지 않았다. 이력 스캔은 제한 패턴 6종 일치 0건일 뿐 감사가 아니다.
- PR #7 의 head·상태는 로컬 clone origin/* 참조와 gh 조회가 섞여 있고 fetch 시점이 불명하며 이후 변동했을 수 있다. v2/ 게이트 거부는 classify() 단독 호출 기반 추정이다.
- 약관 일부는 WebFetch 소형 모델 요약(Tiingo, FSC 일부)이고 원문 대조가 없다. ECOS·Stooq·Massive 는 UNVERIFIABLE, KR·US 일봉의 깨끗한 공급원은 찾지 못했으며 이는 전수 증명이 아니다. 계정 가입·키 발급은 하지 않았다.
- G2 자체 실험(합성 분포, 저장소 외 스크립트)과 G3 시간 산술(4병렬 약 29분 등)은 독립 검증이 아닌 가설이다. 시험 시간·작업 크기 수치는 증거 합 또는 work-list 값이며 신규 NZ 크기는 추정이다.
- OSS 판정은 정적 메타데이터와 문서 읽기이며 설치·실행하지 않았다. Python 3.13 호환은 분류자·휠 목록 신호이고 도입 시점에 라이선스 본문·릴리스·휠 형태를 재확인해야 한다.
- 위임 판단(ND-05/06/07/08b)의 사용자 원문은 문서 기록 외에 확인할 수 없다. 정책 값·세율·법률 판단은 AI 가 확정하지 않았고 ND-27 의 구조/값 위임도 사용자 확인 전에는 제안이다.
- product-read-v1.md 머리글 정정이 P28-02 artifact 해시 고정에 영향을 주는지는 확인하지 못했다. 증거 JSON 중 어떤 파일이 어떤 소스 sha256 을 고정하는지도 전수 확인하지 않았다.
- PDF N-1 의 '원인이 문서 작성 속도가 아니다'(사용자 결정 용량·검증 용량·필독 부담) 해석은 비평가의 판단이며 정량 검증은 없다.

## 17. 레인별 확인 못 한 것

- **R1**: codebase-memory-mcp 그래프는 쓰지 않았다. 교차 SHA 비교는 git show·git ls-tree·git diff·grep 이 더 정확해서다. 그래프는 현재 작업 트리(171e3e4)만 반영한다.; v3 가 실제로 읽은 원격 상태가 main 의 7ba3c88 이후인지 codex/qh-local-delivery-20261030 브랜치인지는 UNVERIFIABLE 이다. 원격 fetch 는 하지 않았고 로컬 origin/* ref 와 커밋 시각만으로 추정했다.; GitHub 웹(PR #1·#7 본문과 리뷰 코멘트)에는 접근하지 않았다. 외부 서비스 호출도 하지 않았다.; Q27 실제 PostgreSQL 시험과 전체 제품 시험은 재실행하지 않았다. 인용한 PASS 수치(3/3, 86/86, 836)는 저장소 증거 JSON 의 자기보고이며 독립 재현이 아니다. runner(runner_sha256 6c8dc562…)는 저장소에 없어 내용을 볼 수 없다.; 어떤 단위 시험도 실행하지 않았다. 80403ab 에서 test_P2_source_invalidation… 이 정적으로 모순이라는 판독(R1-03)은 실행 결과가 아니다.; §4.2 시험은 이름과 핵심 단언만 확인했다. 시험 내용이 의미적으로 충분한지, fail_commit 대역이 실제 COMMIT 응답 유실을 모델링하는지는 평가하지 않았다.; v3 §5·§6.3(portfolio-build-request-v1 JSON)·§8.5(YAML)·§8.6(mermaid 오케스트레이션)·§12 수용 조건은 신규 제안 설계이거나 규범 서술이라 사실 판정 대상에서 제외했다. 타당성 평가는 하지 않았다.; v3 §7.3 의 '10,000 의미 구분' 은 이전 v2 §9.1 과 같은 서술이다. 외부 GitHub 사례의 사실성은 이전 라운드 W1~W3 판정(docs/v2-work-list-2026-11-14.md §GitHub)을 따르며 재검증하지 않았다.; PDF(재분석 보고서 main 5ff8e29)는 이 레인의 범위가 아니라 읽지 않았다.; docs/status.md 943줄 전체를 재독하지 않았다. 관련 줄(상단 130여 줄, :148, :157)만 읽었다.; Q25 고정24 평가 사례(ai-evaluation-spec-v1.json)의 내용과 Q23 24 결과의 실제 산출 해시는 확인하지 않았다. 구조적으로 두 24 가 서로 다른 대상이라는 점만 확인했다.; §3.1 인벤토리의 Q20/Q21 소스·테스트 행은 파일 존재와 모듈 이름 수준으로만 확인했다. 내용 깊이는 읽지 않았다.; 작업 지시문은 '§2 16행, §3.1 15행'이라고 했으나 실제는 §2 15행, §3.1 17행이다. 이 차이는 v3 파일 줄 번호로 직접 센 결과다.
- **R2**: 외부 사실 행: PDF 정정표의 '공시 접수일 시각 없음은 OpenDART 공식 가이드 근거, AlgoLab 블로그 귀속은 오류'와 'opendart-mcp 도구 수 현재 85개'는 WebFetch 로 재확인하지 않았다(저장소 follow-up §3·work-list §7 기록과의 일치만 확인).; 첫 PDF 원문 대비 '이전 지적 31개'를 항목 단위로 1:1 대조하지 않았다. PDF 자체 표만 계수했고 저장소의 64개 매핑과의 대응은 추정하지 않았다.; 836/86 PASS 재현, product_database arm64 검사 동작, PR #7 코드의 시험 결과, replace_source 수정의 실제 DB 동작은 실행하지 않았다(정적 판독과 문서 기록 인용).; PR #7 의 리뷰 코멘트·mergeable 상태(UNKNOWN)는 읽지 않았다. 메타데이터와 diff 통계만 확인했다.; Yahoo·KRX·OpenDART 약관 원문과 5/25 규칙의 원 정의는 확인하지 않았다(저장소 follow-up 조사 기록 인용).; R2-14 의 두 시험 동시 실행은 시작 기록의 RUNNING 공존으로 추정한 정적 정황이다. 실제 벽시계 시간은 UNVERIFIABLE.; N-2 의 '합성 시뮬레이션으로는 ND-03 값을 정하기 어렵다'는 의견 자체의 타당성(통계적 검정력)은 판정하지 않았다.; docs/evidence q27_complete 집계는 JSON 최상위 키 기준 90개(텍스트 키 기준 92개)로 work-list 의 93개와 차이가 있으나 true 가 0건이라는 결론에는 영향 없어 추가 조사하지 않았다.; codebase-memory-mcp 그래프 조회는 쓰지 않고 git/Grep/Read 로 줄 단위 근거를 직접 확인했다.; v3 MD(재감사서)와의 교차 검증, 첫 PDF 의 다른 주장은 이 레인 범위 밖이라 다루지 않았다.
- **R3**: 테스트·DB·Docker는 실행하지 않았다. PDF의 836/86 시험과 약 3.8시간 합산(6,800.646초+6,932.892초=13,733.5초)은 docs/status.md 기록을 인용했을 뿐이고, 두 실행이 병렬이었는지 순차였는지는 UNVERIFIABLE이다.; codebase-memory-mcp는 사용하지 않고 rg·Read로 대신했다. 호출 그래프 판단(import 방향)은 import 문 정적 판독이며 동적 호출은 보지 않았다.; v2/QuantHarbor_main_reaudit_v3_2026-11-15.md는 §1 결론과 §11 우선순위만 읽었다. 이전 v2 설계서·첫 PDF(git 이력)·v2-claim-verification-2026-11-14.md(384줄)는 직접 정독하지 않고 work-list 인용과 grep으로만 확인했다. 다른 레인의 주장은 검증 대상이 아니었다.; PR #7과 feat/p28-03-2b2a-wip는 파일 목록·diff stat만 확인했고 코드는 읽지 않았다. FUP-P28-016/017 수정 내용과 199 통합 결과는 미확인이다.; 금융위 주식시세정보(data.go.kr 15094808)의 이용허락범위와 serviceKey 필수는 WebFetch의 소형 모델 요약이고 원문 대조가 아니다. 이력 깊이·일봉 필드·재배포 조항은 미확인이다. serviceKey 발급은 계정 가입이라 시도하지 않았다. '변경금지'와 파생 계산(수정주가·정규화)의 충돌 여부, 개인 자동매매 연구가 '상업적 이용'에 해당하는지는 전문가 확인이 필요하다(NX-SECURITY-02).; 미국 일봉과 환율의 약관이 깨끗한 공급원은 찾지 못했다(UNVERIFIABLE). ECOS 약관·한도도 followup 조사에서 미확인 상태 그대로다. 외부 사실(세율·시장 규칙·약관)은 재조사하지 않았다.; AP-05가 시세 조회를 포함하지 않는다는 판독은 approval-register.md:14 문구 기준이다. 별도 ENV·SEC 문서의 승인 규정은 읽지 않았다.; SyntheticTargetRepository를 build_target 드라이런 오라클로 쓸 수 있다는 판단은 클래스 존재만 확인한 것이다. 시도 원장의 저장 후보(product DB 별도 테이블 또는 private 파일)는 구현 가능성과 마이그레이션 번호 충돌을 검증하지 않았다.; reduce-only가 막히는 동작(목표 단계 high 기준, 실행 단계 groups)은 정적 판독이고 재현 실행은 하지 않았다. 해시 영향(CostRule 필드 추가 시 canonical 변화)도 정적 추론이다.; ND-03·ND-01의 구조/값 분리가 사용자 위임 범위에 들어가는지는 사용자 확인이 없다. policy-gates.md:19를 근거로 제안만 했다.; PDF 지적 중 qh_quant_reviewer, KIS HTTP 어댑터, AI 런타임 계약, 컨테이너 arm64 고정은 이번 레인 범위 밖이라 평가하지 않았다. 일정 수치(주 단위)도 평가하지 않았다.; '즉시 착수 13개·계약 묶음 3개·트리거 대기 약 37개' 분류는 작업량 추정이 아니라 선행·소비자 관계에 따른 분류다. 각 항목의 공수(L·M·S)는 work-list 값을 그대로 썼다.; docs/status.md 945줄은 앞부분과 grep으로만 읽었다. 절대경로 134회는 rg -o 계수이며 PDF의 121회와 집계 범위 차이가 있을 수 있다.
- **R4**: scripts/check_quality.py 전체 게이트(inspect_repository)와 모든 단위시험·check_* 스크립트를 실행하지 않았다. v2/ 때문에 게이트가 fail 이라는 결론은 classify() 단독 호출과 정적 판독에서 나온 추정이다.; 실제 GitHub 상태는 확인하지 못했다: 오픈 PR #7 의 대상 브랜치, PR #5 가 병합된 merge/ 브랜치의 의미, 원격 Actions·브랜치 보호, 저장소 공개 여부. 로컬 clone 의 origin/* 참조(마지막 fetch 시점 불명)만 사용했고 gh·네트워크는 쓰지 않았다.; PDF 는 텍스트 추출본(reaudit_report.txt)만 읽었다. 표 열이 깨져 있어 N-1·N-9·위험표·권장 순서의 일부 셀을 문맥으로 재구성했다. PDF 원본의 도표·주석은 미확인이다.; v3 MD 는 문서 정합 관련 부분(§2 표, §3.1-3.3, CI 관련 줄)만 읽었다. 나머지 전체(631줄)는 다른 레인 담당이라 이 레인에서는 판정하지 않았다.; AGENTS.md 필독량은 바이트·문자 수로만 측정했다. 모델 컨텍스트 토큰 소모와 실제 읽기 시간은 측정 불가(UNVERIFIABLE)다.; 문서 간 의미 중복은 ID 재인용률과 8단어 shingle 겹침으로만 근사했다. 문장을 사람이 읽고 같은 주장인지 판별하지 않았다. 비마크다운 문서(html 와이어프레임, acceptance-matrix JSON)의 중복은 미검토다.; 링크 검사는 코드 블록 밖의 마크다운 인라인 링크만 봤다. 참조형 링크·HTML 링크·앵커 유효성·외부 URL 263개는 검사하지 않았다. 증거 JSON 역참조는 파일명 부분문자열 일치라 오탐이 있을 수 있다.; 증거 JSON 중 어떤 파일이 어떤 소스의 sha256 을 고정하는지는 전수 확인하지 않았다(check_quality.py·product-p28-01 manifest 등 일부만 확인). 따라서 '수정 불가 증거'의 정확한 범위는 모른다.; 후속 조사 §8 의 '사용자 위임 판단'이 실제 사용자 메시지로 근거가 있는지는 확인하지 못했다(문서 기록만). ND-05·06·07·08b 의 현재 결정 상태는 UNVERIFIABLE 로 남는다.; status.md 줄번호 인용 45건이 인용 시점 SHA 에서 정확한지는 검증하지 않았다(개수만 집계). hook·skill·agents 가 status.md 를 읽는 방식(전체 읽기인지 일부인지)도 확인하지 않았다.; 라벨을 붙인 '당시 기록' 구간의 정확한 경계(어디부터 과거인지)는 사람이 판정해야 한다. 이 레인은 줄 구간 비율만 제시했고 구간별 내용 정확성은 평가하지 않았다.; docs/archive 이동 시 squash merge 에서 git blame·rename 추적이 어떻게 보이는지는 시험하지 않았다. 문서 정리의 순증가·필독 예산 수치(60KB, 정리 후 45~50KB 추정)는 근거가 없는 제안값이다.; 작업 트리의 다른 프로세스 미커밋 변경은 건드리지 않았다. git status 는 시작과 probe 이후 모두 clean 이었다. 시작 때 이미 있던 src/quantharbor/adapters/__pycache__ 는 이 레인이 만든 것이 아니다(-B 사용).
- **G1**: 한국은행 ECOS Open API 이용약관 원문과 환율 시리즈(731Y001 등) 작성기관: JS 렌더링과 키 신청 화면에 가려 정적 취득 불가. 사용자 브라우저 렌더링 본문이 필요.; Stooq 약관 원문(terms.html 빈 응답, 작업증명 관문); Massive(구 Polygon) Individuals 약관 본문과 무료 등급 한도; Tiingo Terms of Service 본문(Cloudflare 403). 문서·요금 페이지 문구만 확인; Twelve Data 문서의 저장 허용 기간, 한국 시장 커버리지; EODHD 무료 등급의 KOSPI·KOSDAQ 포함 여부와 splits/dividends 포함 여부; FSC 주식시세정보 활용자가이드(docx): 요청 변수, 시작일, 시장 구분 값, 조정 여부. 주식권리일정정보의 액면분할 포함 여부; 한국수출입은행 환율 API 약관·이력 조회 방식(검색 요약만, 이용허락범위 '제한' 표기 2차); 서울외국환중개 매매기준율 약관, Finnhub·Marketstack·Nasdaq Data Link 무료 등급(조사하지 않음); Fed H.10 일별 이력의 실제 다운로드 경로(DDP 사전 구성 패키지 URL·XML)와 그 개별 약관(사이트 전체 공개 도메인 고지만 확인); ECB eurofxref-hist.csv 이상 응답의 원인(상류 문제인지 여부). SDMX 경로는 정상이라 대체 가능; OpenBB 저장소의 openbq-org 이동 경위; GitHub 비인증 호출 한도로 일부 커밋 이력·릴리스(pandas-datareader 최근 커밋, exchange_calendars 최신 릴리스 태그)는 확인하지 못함; DuckDB cp313 휠 전체 목록(PyPI 파일명에서 cp311·cp312 만 표본 확인), 모든 도구의 실제 설치·실행·성능은 하지 않았음(정적 문서·소스·메타데이터 확인만); KRX 기준가 조정 기반 조정계수 역산 가설, 규모 추정치(행 수·Parquet 용량)는 실행 검증 없는 추정; ND-03 정책 값 도출에 필요한 최소 표본 크기(이 레인에서 계산하지 않음)
- **G2**: LEAN의 결제 모델(미결제 현금, DelayedSettlementModel 등)과 OrderTargetsByMarginImpact 구현 본문, PortfolioConstructionModel.IsRebalanceDue 본문은 읽지 않았다(주석과 CreateTargets만 읽음). 매도 대금 재사용 가정 판단에서 LEAN 항목은 주석 근거이며 구현 확인이 아니다.; cvxportfolio의 SinglePeriodOptimization/MultiPeriodOptimization 내부 제약 처리, hyperparameters, 데이터 서버(Yahoo 다운로더)와 약관, 그리고 MinCashBalance 외 나머지 제약 클래스 본문은 읽지 않았다.; bt의 ffn.limit_weights 구현 본문, CapitalFlow·RebalanceOverTime·PTE_Rebalance 세부, Cython 컴파일 확장 빌드 요건, 현금 음수가 실제로 발생하는지의 실행 확인은 하지 않았다(정적 읽기만).; skfolio·Riskfolio-Lib·vectorbt 등 W1이 이미 다룬 저장소는 의도적으로 재조사하지 않았다.; 다른 구현 후보는 검색 결과에만 등장하고 열람하지 않았다: pogoetic/rebalance(노트북 튜토리얼), tradeexecutor rebalance_portfolio_old(min_trade_threshold 10.0 언급), FinWiz portfolio_rebalancing, amplpyfinance(AMPL 이산 배분), gurobi-finance 리밸런싱 노트북, zipline-reloaded·backtrader sizer·lumibot·okama(리밸런싱 밴드)·ghostfolio. 우선순위 밖이라 이름만 남긴다.; Python 3.13 설치·실행 검증은 한 건도 하지 않았다(classifier·CI 정적 신호만). Qlib·py-vallocation은 3.13 classifier가 없고 nshare-calc는 신호가 없다.; GPL-3.0 저장소(cvxportfolio, py-vallocation)의 개념 참고가 QH 배포 형태에서 허용되는지는 법률 판단이 필요하며 이번에 확인하지 못했다.; 자체 실험의 한계: 가격 분포(로그균등 3,162~316,228원), NAV(1/3/10백만 원), 종목 수(3~7), 오라클 window(floor±2, N≤5), 탐욕 휴리스틱은 내가 정한 가정이며 실제 KRX·미국 종목·ETF 가격 분포, 비용, 틱, 상하한을 반영하지 않았다. PyPortfolioOpt 탐욕은 읽은 의미를 정확 유리수로 재구현한 것이고 원본 실행이 아니다. 수치는 위험의 크기 감각이며 정책 값 근거가 아니다.; QH 쪽 판독은 모두 171e3e4의 git show 정적 읽기이며 테스트·builder를 실행하지 않았다. constructor가 쓸 snapshot에서 NAV·가격·FX를 builder와 동일하게 얻는 경로(ResearchPointInput 등)는 읽지 않았다. 작업 트리의 미커밋 변경은 건드리지 않았다.; 외부 저장소의 SHA 고정: cvxportfolio·bt·LEAN·PyPortfolioOpt·Qlib·Fynance·py-vallocation·balancer·nshare-calc는 ls-remote로 확인한 HEAD(2026-11-15)에 고정했고 PyPortfolioOpt·bt·Qlib은 고정 SHA 파일과 읽은 파일이 일치함을 cmp로 확인했다. 나머지는 읽은 branch 파일이 HEAD와 같다고 가정했다(일치 검증 안 함). GitHub REST API 한도 초과로 일부 최신 커밋 일자는 commits atom 피드와 WebFetch로 대체했다.; balancer 저장소는 README가 TLH를 로드맵이라 하나 코드에는 tlh_scanner·paper_trader·circuit_breaker·backtest 모듈이 있다. 이 모듈들과 etrade_client·auth(실주문 경로)는 읽지 않았다.; 한국 시장 특수 규칙(호가단위·상하한·거래세·ETF 틱)은 이 레인 범위 밖이라 다루지 않았다. 미국 소수점 거래·단주는 B01 확인 전이며 조사하지 않았다.
- **G3**: 제품 836개(현재 898개)의 개별 시험 시간 분포: 기록 없음, 미측정. 프로파일 1회가 ND-13 승인 사항이다. 이 조사는 시험을 실행하지 않았다.; Hypothesis·pytest·xdist·unittest-parallel·coverage·mutmut·cosmic-ray의 실제 설치와 Python 3.13.17 arm64 컨테이너에서의 동작은 설치 금지 규칙에 따라 전혀 확인하지 않았다. 호환성은 PyPI 메타데이터·파일 목록·분류자 수준의 정적 신호뿐이다.; 병렬 안전성 실검증: test_investment_ai_evaluation/review의 /tmp/quantharbor-q25 공유, setUpClass 7개 모듈의 모듈 단위 병렬 동작은 정적 판독만 했다. 그 밖의 공유 상태(포트, Docker 프로젝트 이름, 임시 디렉터리)는 전수 확인하지 않았다.; mutmut·cosmic-ray의 이 저장소에서의 실행 시간과 외부 사례 수치. 확인하지 못했다.; 전이 의존성 폐쇄 측정: mutmut(textual 등), cosmic-ray(aiohttp, sqlalchemy 등), pytest 계열은 직접 requires_dist만 확인했다. 각 휠의 aarch64 cp313 가용성은 hypothesis·coverage·libcst·setproctitle만 확인했고 나머지 전이 패키지는 확인하지 않았다.; GitHub API 비인증 한도(시간당 60) 소진으로 archived·마지막 push·최신 릴리스를 확인하지 못한 저장소: log4brains, adr/madr, nedbat/cog, mkdocs/mkdocs, squidfunk/mkdocs-material, zensical/zensical, craigahobbs/unittest-parallel, Miskler/jsonschema-diff, bufbuild/buf, oasdiff/oasdiff. 해당 항목의 활동 정보는 PyPI·npm·crates.io·raw LICENSE로만 채웠다. LICENSE 본문을 읽은 도구와 PyPI 필드만 본 도구(sphinx, zensical, mkdocs의 BSD 조항 수, pytest, hypothesis의 파일별 고지)를 license_note에 구분했다.; Hypothesis LICENSE.txt 414줄 중 앞 8줄만 읽었다. 이중 라이선스로 명시된 개별 파일 고지는 확인하지 않았다.; @given을 unittest.TestCase 메서드에 쓰는 공식 문서 확인(details 페이지가 빈 응답). 상태기계의 TestCase 통합만 확인했다.; coverage.py의 dynamic_context=test_function이 unittest 메서드에서 동작하는지: 문서 침묵, 미확인.; pip의 --group(PEP 735) 지원 최소 버전: 미확인.; 저장소 공개 여부(GitHub Actions 무료 조건의 전제): 미확인. GitHub 문서는 렌더링 전 github/docs main 소스를 읽었다.; 오프라인 해시 고정 휠 설치가 Hypothesis 네이티브 휠에서 실제로 통과하는지, manylinux2014 휠이 Debian bookworm slim 이미지에서 로드되는지: 미확인.; pytest로 전환 시 증거 manifest(test_results_sha256, source_manifest_sha256)의 산출 알고리즘이 문서에 없어 ID 형식 변경의 영향 크기를 확인하지 못했다.; HypoFuzz, pytest-gremlins(PyPI 1.14.1, 검색에서 발견), schemathesis(OpenAPI·GraphQL 대상, HTTP API 없는 QH와 무관), pytest-randomly, Pact류 소비자 주도 계약 시험, Pitest류 비Python 변이 도구, uv·tox·nox, pre-commit 훅 프레임워크는 평가하지 않았다.; Confluent 문서는 앞 100,000자만, Hypothesis 변경 기록·strategies 문서는 앞부분만 읽었다. 기존 W3 목록·oss-survey에 이미 있는 에이전트·평가·관측 저장소는 지시대로 반복하지 않았다.; v3 MD의 CI·시험 관련 서술(84·113행)은 config/ci 예제의 비활성 상태와 일치함을 확인하는 데 그쳤고 v3 MD의 다른 주장은 이 레인의 범위가 아니다.
