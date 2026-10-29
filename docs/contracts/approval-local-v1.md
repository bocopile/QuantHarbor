# 합성 승인·철회 계약 v1 — Q26

상태: root 구현 기준, EXEC-DEC-001 J05 로컬 범위. Q25 독립 판정 후 적용하며 frozen execution/operations/data/serialization-v1은 보존한다. [설계 자문](../research/approval-design-input-2026-10-25.md)의 타입·권한·원천·전이·경합·복원·한도를 아래 명시 보완과 함께 채택한다. 실제 인증·계좌 승인·주문은 활성화하지 않는다.

## 타입과 권한

자문 표의 SyntheticApprovalPolicy, PrincipalEvidence, SessionRecord, CandidateEvidence, PresentationRecord, ActionChallenge, ApprovalRecord, ActionReceipt, WithdrawalRequest의 필드를 구현 기준으로 한다. 작은 중첩형으로 합칠 수 있지만 필수 바인딩·전이·검증은 생략하지 않는다. closed ApprovalRef를 추가하고 기존 TargetRef와 OrderTerms를 그대로 사용한다. candidate.version을 새로 만들지 않고 TargetRef.version으로 참조한다. 기존 금융 모듈·TargetRef enum·frozen 의미는 변경하지 않는다.

실제 사용자 인증 adapter는 미구현/비활성이다. 합성 composition root가 등록된 fixture principal에 직렬화할 수 없는 issuer-instance-bound opaque handle을 발급한다. 매 동작에서 실제 registry의 handle identity·principal·account·environment·generation·현재 session/권한을 해소한다. 증거 JSON/hash·AI 문구·caller bool·임의 principal ID는 권한이 아니다. 다른 authority instance의 handle과 복원 JSON은 인증으로 사용할 수 없다. 이 경계는 선의의 프로그램 합성 프로토콜이며 같은 Python 프로세스의 악성 코드 격리나 실제 OS 사용자 인증을 주장하지 않는다.

approver/controller/reporting/research의 권한을 명시 분리한다. approver는 지정 계좌의 approve/deny/revoke/withdraw, controller는 별도 stop/resume/session 제어다. 같은 principal이 두 권한을 가지려면 fixture가 명시해야 한다. reporting/research는 쓰기 port·handle·nonce를 받지 않는다. 조회는 계좌/목적·개수/cursor를 검사하고 금융 상세에는 현재 report 권리를 요구한다. 실제 cancel/liquidate/외부 전송 API는 없다.

## 원천·표시·유효기간

Q24의 실제 request/inputs/artifacts/repository를 해소하고 원본 입력으로 candidate/plan/result를 재현·대조한다. 과거 생성 권리와 현재 소비 권리를 구분하며 history/flow/daily/시장/문서/정책 등 실제 의존 원천의 정확한 ref·revision·권리·기간·누락/정정을 확인한다. 현재 권리 실패를 historical grant로 숨기지 않는다. 신규 승인 원천 재검사에는 해당 research/store, 표시에는 report 권리를 요구한다. Q26에 실제 AI 권리를 새로 발급하거나 불필요하게 요구하지 않는다.

변하지 않는 입력의 재현 검증을 캐시한다면 모든 실제 immutable source/code/contract hash로 결속하고 바뀔 때 무효화한다. 현재 권리·시각·liveness·세대·정책·승인 상태 판정은 캐시하지 않는다. 캐시가 없는 직접 재현도 허용한다.

표시는 Q24 원본 금융조건·문구를 그대로 사용하고 승인 account/environment/generation/action/policy/expiry를 추가해 PresentationRecord의 canonical hash로 결속한다. ApprovalRecord.terms는 실제 후보 OrderTerms 전체와 같아야 한다. Q25 검토는 exact ref의 합성 부속 자료이며 인증·승인 권한이 없다.

합성 fixture의 t0는 2024-03-08T14:31:08Z, 승인 TTL20초·challenge10초·session120초·liveness30초다. 실제 운영 PG01 값이 아니다. 기본 후보의 종료14:31:33Z와 맞춰, t0에 표시한 승인 종료는14:31:28Z로 고정한다. 14:31:10Z에 클릭해도 종료는 늘어나지 않는다. **자문의 issued_at+TTL 제안 대신 presentation.rendered_at+TTL을 상한으로 고정**하고 candidate/target policy/approval policy/principal/session/current rights의 더 짧은 종료와 교집합한다. approved.issued_at은 실제 결정시각이며 최종 expiry를 연장하지 않는다. 표현된 validity와 의미가 달라지면 기존 challenge를 사용할 수 없다. 기한은 끝 제외, heartbeat로 승인 만료를 연장하지 않는다. 15분 분석 주기와 무관하다.

시계 누락·역행·불확실은 신규 승인/admission/dispatch 사용을 차단한다. 확정 이력 시각을 뒤로 돌리지 않고 같은 계좌의 정상 소유 상태를 다른 중복 요청의 오류로 변경하지 않는다.

## 상태·명령·경합

pending→approved/denied, approved→revoked/expired/invalidated/consumed를 적용한다. pending의 expired/invalidated는 이 additive 계약에서 명시 채택한다. 최종 상태에서 approved로 복귀하지 않는다. pending만 issued_at/decision evidence가 없으며 consumed는 intent ID가 필수다. 전체 이력은 실제 previous_ref를 해소해 entity/account/environment·연속 version·허용 전이를 확인한다.

challenge는 command/nonce/action/principal/session/generation/account/candidate/presentation/expected version과 정확히 결속한다. 유효하게 인증된 동작의 nonce 사용·receipt·상태 변경은 하나로 저장한다. 동일 command+payload 재전달은 기존 receipt만 반환하며, 변경 payload는 conflict다. 재전달도 현재 권한·상세 조회 권리를 확인한다. 인증 실패를 사용자 denied로 기록하지 않는다. 세션 단절/만료 후 자동 reconnect/renew로 resume·재승인하지 않는다.

승인·거절·철회·admission·정책 변경·중단·dispatch는 같은 계좌 aggregate lock/version을 사용한다. 서로 다른 application instance도 같은 저장소 경계를 공유한다. barrier로 두 실행 순서를 각각 검증하며 sleep 순서에 의존하지 않는다.

## Q27 연결과 합성 runtime

공개 standalone consume_approval commit API는 만들지 않는다. 순수 plan_admission_transition은 변경 계획만 반환하며 저장·실행 권한이 아니다. Q27이 승인 소비+후보 submission 고유키+prepared intent+현금/수량/위험 예약+outbox+history/receipt를 **같은 DB transaction**에서 저장해야 한다. 현재 Q26에서는 이 영속 원자성·실제 egress·fencing을 미완료로 남긴다.

Q26 SyntheticApprovalRepository는 이 묶음을 하나의 공유 메모리 aggregate에서 staging 후 한 번에 교체하는 명시 simulation adapter를 제공한다. 합성 runtime 사건은 실제 aggregate가 발급한 객체·version·event ref·fixture manifest에 결속하며 caller의 risk_allowed/prepared/unsent bool로 만들지 않는다. 임의 순수 TransitionPlan을 repository에 넣어 권한을 얻을 수 없다. 실제 broker 호출은 없다.

동일 계좌/환경/세대의 exact candidate submission은 최대1개이며 다른 approval ID로 우회하지 못한다. consumed→aborted_unsent여도 같은 승인·후보 소비 claim을 재사용하지 않는다. 실제 Q27 위험 계산·준비 상태는 이 합성 simulation으로 대체 완료하지 않는다.

approved 철회는 revoked, consumed 철회는 consumed를 유지한 별도 WithdrawalRequest다. 저장된 prepared+미전송 근거가 확정되면 unsent_confirmed/aborted_unsent, dispatching이 먼저면 requested다. 전송중/후/unknown은 조회·대사 전 불명/예약을 유지한다. 취소·청산은 자동 발생하지 않는다. 시장자료 권리나 신규 risk allow가 없다는 이유로 적법한 보호 철회/중단을 막지 않는다. 새로 권한을 확인한 같은 계좌 제어 세션으로 과거 consumed intent의 철회를 요청할 수 있으나 금융 상세 조회는 계속 제한한다.

복원은 snapshot 밖 authority가 새 generation을 발급하고 stopped/reconciling으로 시작한다. 옛 handle/nonce/pending/approved는 사용 불가, consumed/intent/unknown/reservations/submission claims/withdrawals는 보존한다. 새 generation을 snapshot 값으로 되돌릴 수 없다. 합성 초기 empty aggregate의 명시 controller 시작/resume는 허용하되, 복원 후 unresolved intent가 있는 경우 Q27의 실제 합성 대사 결과 없이 재개하지 않는다. 임의 complete bool이나 시간 경과로 불확실성을 지우지 않는다.

## 저장·상한·검증

fixture JSON의 canonical64KiB·source8MiB/128refs·문자열2KiB·표시16KiB·전체128records/8MiB를 적용한다. nonce/receipt/history/session/소비 인덱스·예약 공간까지 합산하고 자동 eviction은 없다. 유효한 절차 시작 전 후속 결정·종료·철회 기록 공간을 예약한다. exact reserve 수량과 해제 규칙을 개발 안내에 기록하고 capacity/fault 주입 시 부분 저장·권한 소비가 남지 않음을 검증한다. constructor/parser/application/repository 경계의 closed fields·identity·state/version·capacity를 일치시킨다. canonical bytes 저장/재파싱, 제한된 고정 오류 code만 반환, 원시 예외·입력/경로/repr 반사 없음.

approval-fixture-v1.json의21개 기대 사례를 구현 전 고정한다. 실제 Q24 원천으로 후보3주×100+비용2=302를 확인하고, 정상 승인부터 합성 admission까지 양성 경로를 제공한다. 단순히 모든 입력을 차단하는 구현은 통과가 아니다. 실제 인증·API·PG01 정책 채택·Q27 DB 원자성은 미실행으로 남긴다.

단독 구현자 소유: domain/application/ports approval.py, adapters/synthetic_approval.py, additive domain/serialization.py, tests/product/synthetic_approval.py 및 test_approval*.py, docs/development/approval.md. 모듈 내부 분할은 인계 목록에 명시한다. root는 contract/spec/decision/task/status/evidence/queue를 통합한다. 기존 금융 모듈/TargetRef/frozen/migration/config/dependency는 변경하지 않는다.

## AS1·AS2 보완 채택 — 2026-10-25

AS1 실제 재현에 따라 합성 dispatch는 호출 controller 외에 원 승인자의 registry 권한을 같은 잠금 안에서 재검사한다. 원 session·principal·account·environment·generation 결속과 현재 approve 권한이 모두 유효해야 한다. controller에 approve 권한을 추가하지 않는다. 권한 회수는 전송 차단이며 자동 취소·청산이 아니다.

AS2 실제 재현에 따라 미완료 challenge 각각의 최대 완료 비용을 기존 approval hold 안에 예약하고, 일반 신규 발급은 그 합계 외에 보호 종료8 records/대응 bytes를 남긴다. 완료 비용과 hold를 중복 합산하지 않으며 전체128 records/8MiB를 지킨다. 다른 command가 terminal 전이를 확정해도 기존 미완료 command의 완료 예약은 보존한다. 정확한 비용·해제 규칙은 개발 안내의 AS2 표를 채택한다.

합성 `ApprovalApplication.withdraw(handle, approval_ref, command_id=...)`를 additive 보호 API로 채택한다. 유효한 현재 withdraw 권한과 기존 nonce/session/command 결속 검사를 적용하며 같은 aggregate lock에서 발급·완료를 수행한다. 미처리 command를 외부에 남기지 않고 성공한 철회만 마지막 보호 공간을 사용한다. 실패·거부 시 내부 발급·nonce·receipt·공간 사용을 모두 되돌리되 clock fault 차단은 보존한다. 따라서 이 원자적 호출의 거부 receipt는 남기지 않는다. 기존 2단계 command의 거부 receipt 규칙은 그대로이며, 이미 독립 발급된 미완료 command를 이 API로 인수하지 않는다. 성공한 exact replay는 같은 receipt만 반환한다. Q27 영속 구현은 내부 두 번의 메모리 교체가 아니라 실제 DB transaction 한 번으로 구현해야 한다.

개발 안내의 ‘root 계약 채택 항목’은 구현자가 남긴 제안 이력이며 이 절에서 채택을 확정한다. 고정21사례 fixture와 frozen baseline7은 변경하지 않았다. 추가17개 보안 회귀를 포함한 전용57 통과는 구현자 증거이고 독립 재검토·전체 검증은 별도다.
