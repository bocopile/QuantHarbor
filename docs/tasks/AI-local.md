# AI-local — Q25 합성 AI 계약·검토·예산

- 상태: 로컬 합성 범위 완료 — 실제 모델/API 운영 관문 별도
- 작업: EXEC-DEC-001 H01~08/J03 로컬 합성 범위
- 선행: Q24 로컬 판정·Q18 문서 근거·Q21/Q23 숫자·Q14 역할 권한
- 담당: root 계약 통합 → 제한 설계 자문 → 단독 구현 → 독립 검토/검증
- 입력: frozen execution/operations/data/serialization-v1, 실제 코드 계약
- 소유: ai-local-v1 명시 investment_ai 도메인/앱/port/adapter·additive serializer·합성 시험·개발 안내
- 허용: 합성 응답·로컬 읽기 도구·근거/숫자/예산·TTL·실패 시험
- 제외: 실제 외부 모델/API 활성화·비밀값·실제 정책 채택·주문/승인·지출
- 완료: 구조·출처·숫자·목적 권리·호출권한·상한예약/불명청구·만료/정정 거부를 합성 검증하고 실제 모델평가와 구분
- 현재 변경: 설계·고정24 평가·구현·보안 보완 완료. 독립 검토/최종 검증 진행
- Git: codex/arc-contracts HEAD2fa8f1d, 기존 변경 보존, remote/새commit 없음

- Q24 독립 검토/검증 완료. 제한 Astra/high 설계 자문을 배정한다. 구현/평가셋 실행은 아직 없다.

- Astra/high 자문을 root가 ai-local-v1/AI-DEC-001/24개고정평가spec에통합. 단독Sol/high구현자배정, 실제평가/구현검증은미실행. root동시저장소쓰기를중단한다.

- Q25 구현11파일hash/spec일치. 최종전용50·고정24평가·품질87·공개426findings0·팀/diff통과. 전체503통과뒤문서scope/불완전원장현금2건수정했으므로최종전체재검증은미완료다. 보안→일반→독립실행검증을순차배정한다. [구현](../evidence/ai-implementation-2026-10-24.json).

- Q25 독립 보안 AS1~5(P1 3/P2 2) 지적: 재호출권리·가설의존성·결과승격·usage불명·요청query누적한도. 단독구현자에게 실제red/수정/회귀를 배정한다. [보안지적](../evidence/ai-security-initial-2026-10-24.json).

- Q25 AS1~5 실제 red 5실패·추가 inline 거부 은닉 1실패 후 보완. 최종 제품521·전용66·고정24·품질87·공개431findings0·12hash/고정spec/7파일 불변. 독립 보안 재검토를 배정한다. [수정](../evidence/ai-security-fixes-2026-10-24.json).

## 2026-10-25 Q25 재개·보안 2차 보완

- 중단된 읽기 전용 검토는 종료됐으며 AS1b/AS3b/AS4b/AS5b/AS6(P1 2/P2 3) 정적 지적을 반환했다. 실제 재현·수정·회귀를 단독 구현자에게 배정한다. [2차 지적](../evidence/ai-security-second-2026-10-25.json). 이전 제품521 통과는 당시 버전 증거로 보존한다. 비밀번호·실제 연결은 계속 대기다.

- Q25 2차 지적 실제 red 5시험/6실패/오류0와 예약 소유권 추가1실패를 보완했다. 최종 전용89·고정24·품질87·공개435findings0·13hash/고정7/spec 불변. 최신 전체 시험은 최종 독립 검증에서 수행하며 현재 미실행. [수정](../evidence/ai-security-fixes2-2026-10-25.json). 보안 재검토를 배정한다.

- Q25 2차 수정 재검토에서 AS45c P2 1건이 남았다. 비소유 중복 호출의 마지막 clock 실패가 소유자의 attempt를 unknown으로 바꾸는 경로를 재현·수정한다. 나머지 재검토 범위는 추가 지적 없음. [지적](../evidence/ai-security-third-2026-10-25.json). Q27~29는 준비 카드만 작성했고 미착수다.

- AS45c 실제 red 4시험/2실패/오류0 후 소유권 조건1줄과 회귀를 보완했다. 관련51·품질87·공개441findings0·13hash/고정7/spec 불변. [수정](../evidence/ai-security-fixes3-2026-10-25.json). 마지막 보안 재검토 후 일반 검토·독립 전체 검증을 진행한다.

- Q25 보안 최종 재검토 PASS, 13hash/고정7/spec 불변. [최종 보안](../evidence/ai-security-final-2026-10-25.json). 정적 독립 판정이며 일반 정확성 검토와 최종 전체 실행은 남아 있다.

- Q25 일반 독립 검토 AR1~6 P2 지적을 반환했다. 결과 크기·전송 전 clock/예약·slippage 타입·계좌 selector 종목 identity·AI 실패 시 기간 지표·사례별 사전 manifest 결속을 실제 재현/수정한다. [지적](../evidence/ai-review-initial-2026-10-25.json). 기존24평가 통과는 유지하되 사례별 실제 입력 manifest 완전성은 미충족으로 정정한다.

- AR1~6 실제 red 8시험/14실패/오류0(초기 fixture 오류2건 별도) 후6파일 보완. 최종 전용105·고정24·품질87·공개446findings0·14hash/고정7/spec 불변. 24사례42변형 사전 입력/실제 소비를 결속하고 이전236산출물을 보존했다. [수정](../evidence/ai-review-fixes-2026-10-25.json). 일반 재검토→보안 영향 확인→독립 전체 시험 순서다.

- Q25 AR1~6 일반 재검토 PASS, 소유14/고정7/spec·manifest source/lock88 일치. 24사례42변형 사전 입력·실제 소비를 독립 대조했다. [일반 최종](../evidence/ai-review-final-2026-10-25.json). 변경된 예약/저장/기간 경계 보안 확인 후 최종 전체 실행을 진행한다.

- AR1~6 후 보안 영향 검토 PASS, 14hash/고정7/spec 불변. [보안 영향](../evidence/ai-security-post-review-2026-10-25.json). 최신 소스의 별도 Luna/high 독립 전체 시험·고정평가를 배정한다. Q25 완료 판정은 그 결과 이후다.

## 2026-10-25 Q25 로컬 완료·Q26 설계 착수

- 일반·보안 최종 검토와 독립 전체 검증 PASS: 제품560(587.882초)·품질87·고정24/42변형·공개449findings0·팀/diff·14hash/고정7/spec 불변. [검증](../evidence/ai-validation-final-2026-10-25.json), [평가 요약](../research/ai-evaluation-synthetic-2026-10-25.md). validator 마지막 서술의 hash 오기를 실제 JSON/파일 대조로 정정했으며 테스트 결과에는 영향이 없다.
- 로컬6/10 완료·Q26 승인/철회 설계. 전체 통합18/36과 Q19 실제 연결 대기는 유지한다. 비밀번호·실제 계좌/API 호출0. Q26은 실제 인증 없이 합성 principal/session/nonce/세대 경계와 Q27 원자성 연결을 설계한다.
