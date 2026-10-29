# APPROVAL-local — Q26 합성 승인·철회·만료

- 상태: 로컬 합성 범위 완료·전체 실제 연결 관문 유지
- 선행: EXEC-DEC-001, Q25 로컬 판정, Q24 불변 후보, execution/operations-v1
- 범위: J05 합성 로컬 사용자·세션·승인·중복/철회/만료·복원세대 시험
- 담당: root 계약 → 제한 설계 자문 → 단독 구현 → 보안/일반/독립 실행 검증
- 소유: approval-local-v1의 approval 모듈·additive serializer·합성 시험·안내. root 공통 문서 통합
- 허용: 실제 비밀번호 없이 명시 합성 principal/session/nonce/generation과 후보 검증
- 제외: 실제 인증/승인 수단·실계좌 권한·주문/취소·비공개 정책값·외부 전송
- 완료 기준: 후보/표시/계좌/세대/정책/시각 결속·단일 소비·동시성·만료/철회/단절·복원 후 옛 승인 무효
- Q27 경계: 실제 admission의 승인소비/intent/예약/outbox 원자성은 Q27에서 같은 transaction으로 검증해야 한다
- 현재 산출물: 소유11파일, 독립 일반/보안 PASS, 제품630·품질87·공개478findings0·고정21/승인70 통과
- Git: codex/arc-contracts HEAD2fa8f1d, 기존 변경 보존, 새commit/remote없음

- 2026-10-25 Q25 로컬 독립 판정 이후 Astra/high 설계 자문을 배정한다. 실제 사용자 인증·비밀번호·금융 승인으로 취급하지 않는다.

- Astra/high 자문을 root가 approval-local-v1/APPROVAL-DEC-001/21사례 fixture에 통합했다. 합성 만료값과 표시 시점 고정 상한을 채택했고 단독 Sol/high 구현을 배정한다. 구현/시험은 아직 미실행이다.

- 구현자 전용40(290.526초)·호환27·공개466 findings0·팀/diff·소유9/고정7/fixture 불변 확인. 전체 제품·품질 unittest는 미실행이다. 현재 스냅샷 복원만 허용하며 과거 백업 복원/Q27 DB/실제 인증은 미검증. [구현 증거](../evidence/approval-implementation-2026-10-25.json).

- AS1·AS2 red2실패 후 전용57 통과, 소유10 hash 일치. root가 원자적 합성 보호 withdraw 계약을 채택했다. 전체 제품/품질 unittest는 미실행이며 독립 재검토를 진행한다.

- 최종 독립 제품630(1085.401초)·품질87·공개478findings0·팀/diff·소유11/고정7/fixture 불변. AS1·AS2/AR1·AR2는 실제 red→수정→독립 재검토를 완료했다. [검증](../evidence/approval-validation-final-2026-10-25.json), [실제 합성 예시](../examples/approval-synthetic.txt). 현재 스냅샷 복원만 지원하며 과거 백업/DB/실제 인증은 후속이다.
