# Q26 합성 승인 개발 안내

작업 ID는 Q26-local/J05다. 입력은 [approval-local-v1](../contracts/approval-local-v1.md), [APPROVAL-DEC-001](../decisions/APPROVAL-DEC-001-synthetic-authority.md), 구현 전 고정된 [21사례 fixture](../contracts/approval-fixture-v1.json)다. 실제 Q24 `TargetRequest`, `TargetInputs`, `TargetArtifacts`, `TargetRepository`를 사용한다. `docs/examples/target-synthetic.json`은 권한이나 원천으로 읽지 않는다.

이 모듈은 합성 사용자 동작과 프로세스 내 원자적 저장을 검증한다. 실제 사용자 인증·비밀번호·실계좌 승인·PG-01 운영 정책·Q27 DB transaction·dispatch fencing·외부 egress·복원 후 실제 대사는 미완료다. 같은 Python 프로세스에서 내부 속성을 임의 조작하는 코드를 격리하지 않는다. Q14의 `authorize(synthetic_binding(...))`를 사용하되 Q14의 범용 합성 account binding을 실제 계좌 권한으로 해석하지 않는다.

## 정상 합성 흐름

개발용 실행 예제는 저장소 루트에서 다음과 같다. 테스트 helper는 실제 시장 ingest·원장 replay·평가·Q24 builder로 원천을 생성한다. 기본 후보의 수량·가격·비용·최대부담은 각각 **3주·100 USD·2 USD·302 USD**다. 승인 모듈은 후보의 `OrderTerms` 전체와 원래 표시 문구를 그대로 결속한다.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests/product python3.13 -B - <<'PY'
from synthetic_approval import Harness
from quantharbor.domain.approval import ref

h = Harness()  # 등록된 합성 principal, 명시 resume, 저장된 합성 risk 사건
presentation, pending = h.present()
print(presentation.rendered_text)
challenge = h.app.challenge(
    h.approver, ref('approval', pending.approval_id, pending),
    action='approve', command_id='example-explicit-approve')
h.clock.at = '2024-03-08T14:31:10Z'
receipt = h.app.execute(h.approver, challenge)  # fixture의 명시 클릭 시뮬레이션
assert receipt.outcome == 'applied'
approved = h.head(pending)
admission = h.command(approved, 'admit', 'example-synthetic-admission')
assert admission.outcome == 'applied'
print(h.head(pending).state)  # consumed; broker 호출 없음
PY
```

실제 composition에서는 `FixturePrincipal`의 계좌·역할·명시 action을 먼저 등록하고 `SyntheticAuthority(clock=...)`, `SyntheticApprovalRepository(authority, source, policy)`, `ApprovalApplication(repository)`를 조립한다. `issue_session()`은 등록된 fixture ID에 대해서만 issuer-instance-bound opaque 객체를 발급한다. 이 합성 발급 메서드는 실제 인증 엔드포인트가 아니다. `PrincipalEvidence`, hash, JSON, 임의 principal ID, AI 문구, `proof=True`는 application의 handle 자리에 사용할 수 없다. handle은 pickle/canonical 직렬화할 수 없다.

## API와 권한

| API | 의미 |
|---|---|
| `present(handle, candidate_ref)` | Q24 원천을 재현하고 pending과 exact presentation을 함께 저장 |
| `challenge(handle, approval_ref, action=..., command_id=...)` | action·principal·session·세대·계좌·표시·expected version에 결속된 nonce 발급 |
| `execute(handle, challenge)` | registry·현재 권한·시각·상태를 다시 검사하고 전이와 receipt를 함께 저장 |
| `withdraw(handle, approval_ref, command_id=...)` | 합성 보호 철회의 발급·실행을 같은 잠금에서 완료; 아래 AS2 계약 채택 항목 참고 |
| `control(handle, action)` | 명시 `resume`, `stop`, `heartbeat`, `disconnect` |
| `query(read_permit, account_ref=..., purpose=..., limit=10, cursor=0)` | `status`, `financial`, `research_summary`; limit 1~20, cursor 0~128 |
| `plan_admission_transition(...)` | 순수 계획 생성. 저장·실행 권한이 없으며 repository에 주입하는 API 없음 |

approver는 present/approve/deny/revoke/withdraw 및 합성 admission만 가진다. controller는 별도 session/stop/resume/runtime/policy/dispatch와 명시적으로 부여된 보호 withdraw를 가진다. approver에게 controller 권한이 자동 추가되지 않는다. reporting/research에는 쓰기 session handle 대신 registry에 결속한 read permit만 발급한다. research는 금융 상세 없는 summary만 조회한다. 조회 결과에 handle·nonce·challenge·원시 예외를 넣지 않는다.

같은 `SyntheticApprovalRepository`를 여러 application instance가 공유해야 한다. 다른 authority instance의 handle은 사용할 수 없다. 계좌별 repository의 단일 `RLock`이 승인·철회·admission·dispatch·권리/정책/위험 사건·중단·복원을 직렬화한다. 서로 다른 저장소를 만들어 같은 계좌를 운영하는 구성은 지원하지 않는다.

`record_risk(controller, 'clear'/'blocked')`, `record_unknown(controller, intent_id)`, `replace_source`, `replace_policy`, `change_permissions`는 trusted composition의 합성 사건 주입용이다. 저장된 event의 aggregate ID/version·event ref·fixture ref를 해소한다. admission/withdraw API에 `risk_allowed`, `prepared`, `unsent_confirmed` bool을 넘기는 경로는 없다. 합성 risk 사건은 Q27의 실제 위험 계산을 대체하지 않는다.

## 시각과 원천

고정 합성 값은 approval TTL 20초, challenge 10초, session 120초, liveness 30초다. t0=2024-03-08T14:31:08Z의 표시 종료는 **14:31:28Z**, challenge 종료는 **14:31:18Z**다. 14:31:10Z에 approve해도 승인 종료는 28Z다. 후보 종료 33Z와 정책·principal·session·모든 의존 권리 종료의 교집합으로 더 짧아질 수 있다. 전부 끝 제외다. heartbeat는 liveness만 갱신하며 승인·session의 절대 종료를 연장하지 않는다. 15분 분석 주기나 실제 운영값에서 추론한 수치가 아니다.

UTC clock은 composition에서 주입한다. 누락·불확실·역행은 fault를 latch하고 신규 권한 사용을 차단한다. 조회에서 관찰한 시각도 역행 판정에 포함한다. disconnect/만료 후 heartbeat·자동 재연결로 재개하지 않는다. clock fault를 임의 bool로 해제하는 API는 없다.

매 원천 검사에서 원래 평가시점의 Q24 builder를 격리 저장소에 재실행하고 plan/candidate/result 전체를 비교한다. 실제 Q24 저장소의 exact ref도 다시 조회한다. 현재·위험 이력·flow boundary·일간 사용의 모든 시장 의존 source/dataset/version/rights_ref와 research/store/report 권리를 현재 시각에 검사한다. Q24 snapshot의 과거 grant는 원래 생성 결과 재현에만 사용한다. 현재 권리 철회를 과거 grant로 덮지 않는다. Q24가 받지 않는 문서나 AI 권한을 임의로 추가하지 않는다. 현재 구현에는 재현 캐시가 없다.

동일 command와 exact payload의 execute 재전달은 기존 receipt만 반환한다. 현재 principal 권한과 금융 자료 권리는 매번 다시 검사한다. 이미 처리한 receipt 조회는 후보 만료 후에도 신규 소비 없이 가능하지만 세션·권리는 유효해야 한다. action/nonce/계좌/표시/세션/대상 치환은 conflict 또는 denial이다. 유효한 인증 후 거부된 명령도 receipt 하나로 고정한다. challenge만 만료된 경우 approval을 조기에 expired로 바꾸지 않는다.

## 상태와 원자성

pending→approved/denied, pending/approved→expired/invalidated, approved→revoked/consumed를 허용한다. terminal에서 approved로 돌아가지 않는다. pending만 issued_at과 decision evidence가 null이다. pending의 시스템 종료에는 종료시각과 합성 종료 event를 기록한다. consumed에는 intent ID가 필수다. 각 history의 previous_ref는 실제 canonical bytes를 해소하고 동일 entity·계좌·환경·연속 version·허용 전이를 검사한다.

합성 admission은 consumed+candidate 고유 claim+prepared intent+cash/quantity/risk 예약+pending outbox+history/receipt를 staging한 뒤 **한 번의 aggregate 교체**로 저장한다. 어떤 단계든 실패하면 nonce 처리·상태·예약·outbox가 그대로다. 독립 `consume_approval()`나 arbitrary TransitionPlan 저장 API는 없다. consumed나 candidate claim은 aborted_unsent 이후에도 재사용하지 않는다.

approved 보호 철회는 revoked다. consumed 보호 철회는 consumed를 보존하며 별도 WithdrawalRequest를 만든다. 저장된 prepared/미전송 사건이 먼저면 unsent_confirmed와 aborted_unsent가 되고 합성 예약을 released로 표시한다. dispatching이 먼저거나 unknown이면 requested만 기록하고 예약을 유지한다. 자동 취소·청산·재전송은 없다. 보호 철회에는 시장 report 권리나 신규 risk allow를 요구하지 않는다. 같은 계좌의 유효한 새 controller session으로 옛 consumed intent를 철회할 수 있고, 금융 상세는 계속 별도 권리 검사를 받는다.

AS1 보완(2026-10-25): dispatch는 같은 aggregate 잠금 안에서 호출한 controller와 **원 승인 principal의 현재 approve 권한**을 각각 검사한다. 원 세션의 registry handle을 다시 해소해 발급자 instance·현재 권한·정책·세대·시각·liveness와 approval의 principal/session/account/environment/generation 결속을 확인한다. controller에게 approve 권한을 요구하지 않는다. 권한 회수나 세션 단절은 dispatch 거부 receipt를 남기며 prepared intent·outbox·예약·claim을 자동 취소하거나 해제하지 않는다.

`snapshot()`은 trusted composition의 상태 복사이며 사용자 조회 API가 아니다. `restore(snapshot)`은 **현재 aggregate와 exact 일치하는 snapshot만** 수락한다. 오래되거나 수정한 snapshot의 rollback은 거부한다. 외부 authority가 새 generation을 발급하고 옛 handle/read permit/session/pending/approved를 무효화한다. consumed·unknown·예약·claim·withdrawal·nonce/receipt 이력은 보존하고 stopped로 시작한다. 이 in-process simulation에는 복원 후 resume를 해제하는 경로가 없다. Q27의 실제 대사·영속 복원·rollback 방지·이전 egress 종료 확인은 후속 작업이다.

## 저장 한도와 실패

canonical 객체 64KiB, rendered text 16KiB, 일반 text 2KiB UTF-8, 해소 입력 8MiB/128 refs, 전체 저장소 128 records/8MiB를 상한으로 둔다. canonical bytes로 저장·재파싱한다. source 객체·session·registry·nonce/command/receipt/head index·예약·outbox·claim·hold까지 계산한다. source는 해소된 입력 표현 크기, index/registry 등은 항목당 보수적으로 4096bytes를 계산한다. 이는 Python allocator의 실제 heap 계측이 아닌 저장 계약의 보수적 크기 계산이다.

session 발급 전 종료용 **8 records×64KiB**, presentation 발급 전 결정·소비·철회용 **40 records×64KiB**를 예약한다. 예약 엔트리 자체도 record 하나다. 각 commit에서 실제로 증가한 record/계산 bytes만 그 절차의 hold에서 차감한다. 일반 제어/runtime 사건은 **stop용1개+disconnect용2개**와 대응 bytes를 보존한다. heartbeat는 자기 비용2개를 포함해 session에5개 이상, resume/runtime의 단일 사건은4개 이상 남아야 한다. stop은3개, disconnect는2개 이상을 요구한다.

AR1 보완(2026-10-25): 이미 stopped인 aggregate의 반복 stop은 **현재 handle·principal·권한·세대·절대 만료·liveness·시각을 먼저 검사**하고 같은 세대의 기존 stop 사건 ref를 반환한다. 같은 시각이나 바뀐 시각 모두 추가 사건·version·공간 사용 없이 멱등이며 마지막 저장 시각도 바꾸지 않는다. 기존 canonical 사건을 해소해 새 인덱스를 추가하지 않는다. 명시 resume 이후 stop은 새 사건을 저장한다. 일반 사건의 용량 거부 뒤에도 보호된 stop과 disconnect를 순서대로 완료할 수 있다. 이 동작은 risk 사건·intent·outbox·금융 예약·claim을 변경하거나 자동 재개·취소하지 않는다.

AR2 보완(2026-10-25): disconnect는 paused session history와 사건을 저장하는 **동일 commit에서 자기 session hold의 잔여 records/bytes를 전부 해제**한다. session·registry·이력·receipt·command/nonce는 삭제하지 않는다. restore는 running 세션의 무효화에 더해 paused/faulted/invalidated 및 시각상 만료된 모든 옛 세대 session의 hold도 동일 staging에서 해제한다. 이미 종료된 session head/history를 다시 쓰지는 않는다. 다른 approval의 미완료 명령 완료 예약·consumed 보호 철회 hold·unknown 금융 예약/claim은 보존한다. operation/commit 실패는 hold 해제를 포함해 롤백하며 clock 오류는 기존 fault latch만 남긴다. 일반 eviction은 없고 이력이 누적되므로 유한 저장 한도에서 신규 session 발급이 정당하게 소진될 수 있다.

AS2 보완(2026-10-25): 발급된 challenge마다 아래 최대 완료 비용을 **해당 approval hold 안에** 예약한다. 별도 저장 컬렉션을 추가하지 않고 기존 command 중 receipt가 없는 항목을 해소한다. 따라서 `_usage()`의 실제 records/bytes와 hold를 더한 전체 한도에 이미 포함되며 완료 비용을 두 번 더하지 않는다.

| action | 최대 완료 records | 근거 |
|---|---:|---|
| approve / deny / revoke | 4 | event·approval history·receipt·receipt index |
| admit | 10 | event·consumed history·claim·intent·예약3·outbox·receipt·receipt index |
| dispatch | 4 | 정상 event+receipt/index는3, pending/approved 시스템 무효화 경로까지 보수적으로4 |
| withdraw | 5 | event·withdrawal·head·receipt·receipt index; approved 철회는4 |

각 완료 예약의 bytes는 records×64KiB다. 일반 신규 challenge는 **기존 미완료 명령의 완료 비용 + 신규 발급3 + 신규 최대 완료 비용 + 보호8**을 동시에 확보한다. hold가 부족하면 아직 배정하지 않은 전체 용량에서 필요한 records/bytes만 보충하며, 보충 후에도 **128 records/8MiB**를 넘으면 발급 전체를 거부한다. 잘못된 현재 상태의 신규 action은 command/nonce를 만들기 전에 거부한다. 이미 발급한 명령이 나중에 version conflict·만료·권한 회수 등으로 거부되면 해당 완료 예약 안에서 receipt/index를 한 번 저장한다. exact replay는 기존 challenge/receipt만 반환하고 추가 비용을 차감하지 않는다.

denied/revoked/expired/invalidated가 확정돼도 미완료 명령이 남으면 그 완료 비용만 hold에 남긴다. 마지막 완료 후 잔여 hold를 해제한다. 복원으로 generation이 바뀌어 영구적으로 인증 불가능한 옛 challenge는 완료 예약 계산에서 제외한다. consumed의 보호 공간은 명시 철회를 위해 보존한다. 자동 eviction이나 신규 양성 경로의 일괄 차단은 없다.

### AS2 root 계약 채택 항목 — 원자적 합성 보호 철회

독립 발급한 철회 challenge 자체도 만료·거부될 수 있다. 유한 저장소에서 그 기록이 마지막 보호8을 쓰도록 허용하면 같은 결함을 철회 action으로 다시 만들 수 있다. 따라서 일반 2단계 발급은 철회에도 보호8을 남기며, 마지막 공간의 적법한 사용에는 additive `withdraw(handle, approval_ref, command_id=...)`를 제공한다. **root가 approval-local-v1의 API/원자성 설명에 채택해야 할 구현 제안**이며, worker는 고정 계약·fixture·decision을 수정하지 않았다.

이 API는 현재 withdraw 권한을 가진 approver 또는 같은 계좌 controller가 명시 호출한다. 기존 challenge의 모든 nonce/session/command 결속과 기존 execute 검사를 그대로 사용하며, 하나의 공유 잠금에서 발급과 실행을 끝낸다. 내부 발급과 완료는 각각 version을 올리지만 다른 application에서 중간 상태를 관찰할 수 없다. 발급·완료·receipt·최종 commit 실패나 거부는 내부 발급까지 되돌려 보호 공간을 차감하지 않는다. clock fault latch는 유지한다. 승인된 철회만 보호8을 사용하며 다른 미완료 명령의 완료 예약은 보존한다. 실제 사용자 인증·비밀번호나 외부 취소 API를 추가하지 않는다.

예: `app.withdraw(controller, ref('approval', consumed.approval_id, consumed), command_id='explicit-protective-withdraw')`. 같은 command·대상·세션 재전달은 같은 receipt를 반환한다. 다른 payload/세션은 conflict다. report/risk/원 승인자의 현재 권한 상실 후에도 새 유효 controller로 호출할 수 있다. 원자적 호출이 실패하면 미발급 상태로 되돌아가므로 해당 호출의 거부 receipt는 남기지 않는다. 이미 독립 발급된 미완료 command는 이 API로 인수하지 않고 replay_conflict로 거부한다. 해당 2단계 challenge는 기존 execute로 완료하며 거부 receipt 규칙을 유지한다. Q27은 이 명시 요청도 실제 DB transaction 한 번으로 구현해야 한다.

오류는 `ApprovalDenied.reason`의 고정 code다. 입력·경로·객체 repr·원시 예외를 반사하지 않는다. `_safe` 경계는 임의 소스 adapter 예외도 고정 code로 바꾼다. 합성 시험의 `inject_failure(label)`은 staging 각 단계와 최종 commit을 실패시키며 외부 시스템을 호출하지 않는다.

## 검증

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3.13 -B -m unittest discover \
  -s tests/product -p 'test_approval*.py' -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3.13 -B -m unittest discover \
  -s tests/product -p 'test_serialization.py' -v
python3.13 -I -S -B scripts/check_quality.py
python3.13 -I -S -B scripts/check_ai_team.py
git diff --check
```

AP01~21은 manifest의 사전 기대값을 실제 aggregate에 대조한다. 별도 회귀는 canonical/실제 원천 변경/예외/role/time/복원/동시성을 다룬다. AS1·AS2는 수정 전 실제 assertion 실패를 재현한 뒤 현재 권한 회수·복구/세션 결속·다중 challenge 완료/만료/거부·동시 발급·철회 선후·보호 철회 원자 실패를 검사한다. thread 시험은 barrier와 event로 두 순서를 강제하고 실제 동시 barrier 경합도 확인한다. DB·다중 프로세스·네트워크 exactly-once 검증은 포함하지 않는다. 전체 product 및 quality unittest87과 독립 판정은 root의 후속 validator 담당이다. serializer는 이 보완에서 변경하지 않아 호환 suite를 재실행하지 않는다. 실제 실행 수·시간·개발 중 실패 이력·최종 소유 hash는 worker의 임시 handoff.json에 남긴다.

AR1·AR2 수정은 adapter·이 안내·`tests/product/test_approval_review.py`만 소유한다. 제품 수정 전 red2는 assertion 실패2·오류0으로 재현했다. 제어 회귀는 원천 재현 호출이 없음을 검사하며 같은/다른 timestamp 반복 stop, 명시 resume, 현재 권한/세션 상실, records/bytes 포화 후 보호 종료를 다룬다. 세션 정리는 live 완료/철회 hold 보존, legacy paused·만료·기타 종료 세대 복원, clock/operation/commit 실패 롤백, unknown 금융 예약과 새 controller의 복원 후 보호 철회, 유한 이력 소진을 다룬다. 최종 검증은 새 모듈과 영향받는 기존 메서드만 선택한다. 정확한 선택·이유·실제 결과·명령·로그·소유11 hash는 임시 handoff에 남기고 종전57 통과는 당시 이력으로 보존한다. 전체57·전체 product·품질 unittest87은 이 수정자가 재실행하지 않는다.
