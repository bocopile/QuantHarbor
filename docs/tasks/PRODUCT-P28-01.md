# P28-01 — 화면·사용 흐름·제품 완료표

- 상태: 진행 — 정적 설계 artifact_ready·브라우저/통합 검수 대기
- 단계·선행조건: 요구9개/시나리오16개·기존 공개/합성 계약, EXEC-DEC-003의 독립 착수 정책
- 요청 근거·실행 범위: 사용자 전체 계획 우선 진행·실패 후속 큐 지시. 로컬 제품 화면·조회/CLI 흐름·합성 와이어프레임·수용 매핑
- 담당: qh_architect의 읽기 전용 자문 → root 작성/통합 → 독립 일반/보안 검토. 역할 반환 자체는 완료가 아님
- 입력: docs/requirements-scenarios.md, requirements-input.md, vision.md, product-delivery-plan.md, architecture.md 및 기존 application/domain/ports 계약. Q27 미완료 상태와 source 버전 명시
- 소유: root의 docs/product/screen-spec-v1.md, synthetic-wireframes.html, acceptance-matrix-v1.json 및 본 카드/큐/상태. 자문자는 파일 수정 없음
- Git: main80403ab와 기존 미커밋 변경 보존. Q27 고정 검증 worktree 입력에는 쓰지 않음. HTML/품질검사단위commit0f9e149·originSHA확인·PR없음
- 허용 도구·외부 변경: 제한 qh_review 부모·Astra/high, 공개 파일 읽기와 결과 반환. root가 정적 산출물 작성. 실제 연결·주문·키·자금·새 의존성/외부 게시 없음
- 검증 요청: REQ9/SC16 누락·상태/화면/CLI/서비스/시험 매핑, 합성 표시/접근성·문서/JSON 정합성, 정적 와이어프레임 표시 확인. 실제 제품 동작/통합 검증과 구분
- 시간·비용: 초기 자문600초, 자동재시도0·기존 구독 사용

## 산출물과 완료 기준

- 자산/현금/위험, 분석/근거/반론, 후보/승인, 주문/체결/대사, 투자 AI 작업, 운영/연결 화면과 전환 흐름.
- 환경·표시용 계좌·통화·기준시점·원천/버전·잠정/확정·빈값/누락/실패/만료/차단을 구분.
- 브라우저가 금액을 재계산하거나 새로고침으로 제어 세션·승인을 연장하지 않음. 금융 제어는 기존 보호 CLI/IPC로 연결.
- 정적 합성 와이어프레임과 실제 모듈/미구현 seam을 명확히 표시. 설계 수용/통합 준비와 Q27 관문 충족 후 최종 완료를 구분.

## 인계

- 현재: 설계 자문 배정 준비. 실제 배정/반환·작성·검토·표시 확인은 관측 뒤 기록한다.
- 미실행: 제품 대시보드 구현·실제 API·사용자 인증·주문·외부 전송.

## 설계 자문 배정 — P28-01-architecture-a01

- 03패널·Astra/high·qh_review 별도 읽기 부모, 실제 thread/turn 기동을 확인한다. 자문 출력은 JSON의6화면·공통표시·REQ9/SC16 매핑·완료표·구현 인계다.
- root가 그래프로 확인한 application/reporting의 build_report/presentation_data/render_report와 기존 valuation/research/target/AI/approval/execution 경로를 입력으로 전달했다. 기존 서비스와 새 제품 seam, 기존 시험과 예정 시험을 구분한다.
- 보호 입력82개: 기존src73과 요구/비전/계약/실행결정 등. 변동 상태/큐는 원래 checkout의 최신 지시를 따르고 Q27 검증 worktree는 수정하지 않는다.
- 배정 준비/기동을 설계 수용이나 제품 동작 PASS로 기록하지 않는다. 반환 후 root 정합성·화면 표시·독립 검토를 진행한다.

## 재개·root 초안 작성

- 설계 자문은600.036초 제한·exit-15·최종파일 없음으로 종료했다. 안정 입력82개는 불변이다. [실제 기록](../evidence/product-p28-01-architecture-timeout-2026-10-30.json). FUP-P28-001에 등록했으며 반복 기동하지 않고 root가 기존 요구에서 초안을 작성했다.
- root 작성: [6화면 명세](../product/screen-spec-v1.md)와 [수용 매핑 JSON](../product/acceptance-matrix-v1.json). 요구 원문9개/시나리오 원문16개를 추출해6화면·실제 존재하는 서비스/컴포넌트 시험·새 제품 통합 대기에 연결했다. 제품 동작 PASS나 독립 설계 검토로 기록하지 않는다.
- 04 구현자는 synthetic-wireframes.html과 그 공개 정적HTML을 읽기 검사할 최소 check_quality.py 확장/품질 회귀만 소유한다. 기존 금액/승인/실행 계약과 Q27 검증 입력은 수정하지 않는다. HTML 검사는 실행·외부 fetch 없이 기존 공개후보/비밀탐지/용량/경로 경계를 유지한다.
- 다음: 실제 정적HTML 구현·동작 없는 합성 표시 확인·독립 일반/보안 검토, 산출물 artifact_ready 판정. Q27 통합/완료 관문과 실패 큐는 유지한다.

## 구현 실제 반환 — revision1

- Sol/high 단독 구현453.660초·exit0, 소유3파일만 변경·보호626개 전후 SHA 불변(root 재대조). [증거](../evidence/product-p28-01-wireframe-build-2026-10-30.json).
- 품질21/21 PASS·공개629파일 지적0·git diff --check PASS. 정적6영역/19fragment/8details/태그·CSP·외부자원 없음 확인. 정적 검사는 브라우저 표시나 실제 제품 동작을 대신하지 않는다.
- 브라우저 표시: NOT RUN. IAB 부재, Chrome HTTP 연결 시간초과, file URL 정책거절. 로컬 HTTP 서버는 종료했고 정책을 우회하지 않았다.
- 다음: 05 독립 일반 검토 → 06 독립 보안 검토 → 정적 설계 산출물 준비 판정. 제품 UX/실제 표시·인증/API·Q27 통합 관문은 남는다.

## 정적 설계 산출물 준비 판정

- 독립 일반95.852초·보안81.327초 정상 반환, 각 지적0·읽기 입력6개 SHA 불변. [일반](../evidence/product-p28-01-review-2026-10-30.json)·[보안](../evidence/product-p28-01-security-2026-10-30.json).
- artifact_ready=true는 명세/매핑/정적 source 와이어프레임의 후속 계약 착수 준비에 한정한다. P28-01 status는 in_progress이고 completed가 아니다. 실제 브라우저 검수 FUP-P28-002와 Q27 통합/완료 관문은 면제하지 않는다.
- FUP-P28-001은 root 초안·구현·독립 검토 확보로 해결. P28-02 계약 설계를 이어간다.
