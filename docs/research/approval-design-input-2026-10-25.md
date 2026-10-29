**Q26은 `approval-local-v1`을 추가하고, 승인 소비는 Q27이 사용할 순수 전이·UnitOfWork 계약으로 제한하는 설계가 적합합니다.** 합성 승인 성공 경로는 제공하되, 실제 사용자 인증·금융 승인·DB admission 원자성을 달성했다고 표현하지 않습니다.

아래 내용은 설계 제안입니다. 파일 변경·테스트·네트워크·비공개 영역 접근·Docker·Git·subagent 실행은 하지 않았습니다. 그래프 도구가 노출되지 않아 공개 문서와 관련 소스를 제한적으로 읽었습니다.

**현재 확인된 사실**

| 근거 | 확인 내용과 설계 영향 |
|---|---|
| [현재 상태](/Users/okestro/projects/QuantHarbor/docs/status.md:623), [Q26 카드](/Users/okestro/projects/QuantHarbor/docs/tasks/APPROVAL-local.md:1) | 기록상 Q25 로컬 독립 검증 완료, Q26 구현·시험 미실행. 이번 자문에서 이전 시험을 재검증하지 않았음 |
| [execution-v1](/Users/okestro/projects/QuantHarbor/docs/contracts/execution-v1.md:30) | 단일 후보 승인, 계좌 직렬화, 승인 소비·intent·예약·outbox 동일 transaction, consumed 이후 철회가 이미 필수 |
| [operations-v1](/Users/okestro/projects/QuantHarbor/docs/contracts/operations-v1.md:34) | 사용자 입력 ID나 후보 hash는 인증 근거가 아님. 세션 liveness와 복원 세대 검사가 필요 |
| [실제 후보 타입](/Users/okestro/projects/QuantHarbor/src/quantharbor/domain/target.py:442) | `OrderCandidate(candidate_id, body)`에 금융조건·표시문구·계좌·환경·세대·정책·입력 refs가 결속됨. 독립 `candidate.version` 필드는 없으므로 기존 `TargetRef.version`을 사용 |
| [Q24 저장소](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_target.py:35) | `append(TargetArtifacts)`가 plan/candidate/result 관계를 검사하고 canonical bytes를 저장. 이것만으로 현재 원천 유효성이나 사용자 권한이 입증되지는 않음 |
| [후보 표시](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:787) | 저장된 exact 후보와 현재 market report 권리를 검사. 전체 승인 원천·세션·권한 검사를 제공하는 API는 아님 |
| [Q14 합성 controller](/Users/okestro/projects/QuantHarbor/src/quantharbor/runtime/boundary.py:125) | 객체 identity와 고정 30초 합성 liveness. 실제 사용자 인증이나 같은 프로세스의 악성 코드 격리를 제공하지 않음 |
| [Q25 부속 검토](/Users/okestro/projects/QuantHarbor/docs/contracts/ai-local-v1.md:35) | exact 후보에 연결하는 검토 자료이며 후보 변경·승인·예약·주문 권한이 없음 |

**제안하는 최소 타입과 필드**

새 계약은 `schema_version=1`, `environment="synthetic"`만 허용합니다. 참조는 닫힌 `ApprovalRef(kind,id,version,canonicalization_version,sha256)`로 만들고, 기존 후보 참조에는 `TargetRef`를 그대로 사용합니다. ref의 hash뿐 아니라 실제 객체를 해소해야 합니다.

| 타입 | 필수 필드 |
|---|---|
| `SyntheticApprovalPolicy` | `policy_id`, `version`, `environment`, `account_ref`, `valid_from`, `valid_to`, `approval_ttl_seconds`, `challenge_ttl_seconds`, `session_ttl_seconds`, `liveness_timeout_seconds`, `allowed_actions`, `limits`, `fixture_manifest_ref` |
| `PrincipalEvidence` | `principal_id`, `issuer_id`, `issuer_instance_id`, `authority_generation`, `environment`, `account_ref`, `role`, `allowed_actions`, `issued_at`, `expires_at`, `provenance="synthetic_fixture"`, `fixture_manifest_ref` |
| `SessionRecord` | `session_id`, `principal_ref`, `authority_generation`, `environment`, `account_ref`, `policy_ref`, `code_version`, `state`, `state_version`, `started_at`, `expires_at`, `last_control_event_ref`, `liveness_deadline`, `clock_epoch`, `previous_ref` |
| `CandidateEvidence` | `candidate_ref`, `plan_ref`, `result_ref`, `request_ref`, `input_refs`, `current_rights_refs`, `source_revision_refs`, `checked_at`, `checker_version`, `fixture_manifest_ref` |
| `PresentationRecord` | `presentation_id`, `candidate_ref`, `candidate_render_version`, `approval_render_version`, `locale`, `principal_ref`, `session_ref`, `authority_generation`, `action`, `approval_policy_ref`, `valid_from`, `expires_at`, `rendered_text`, `candidate_evidence_ref`, `rendered_at` |
| `ActionChallenge` | `challenge_id`, `command_id`, `nonce`, `action`, `principal_ref`, `session_id`, `authority_generation`, `environment`, `account_ref`, `target_ref`, `presentation_ref`, `expected_state_version`, `issued_at`, `expires_at` |
| `ApprovalRecord` | `approval_id`, `state`, `state_version`, `previous_ref`, `principal_ref`, `session_id`, `authority_generation`, `environment`, `account_ref`, `candidate_ref`, `presentation_ref`, `candidate_evidence_ref`, `target_policy_ref`, `approval_policy_ref`, `authorized_action="submit_candidate_once"`, `terms`, `created_at`, `issued_at`, `valid_from`, `expires_at`, `decision_evidence_ref`, `consumed_intent_id`, `reason_code` |
| `ActionReceipt` | `command_id`, `challenge_ref`, `command_payload_hash`, `action`, `target_ref`, `actor_evidence_ref`, `recorded_at`, `outcome`, `reason_code`, `result_ref`, `aggregate_version` |
| `WithdrawalRequest` | `request_id`, `principal_ref`, `session_id`, `authority_generation`, `approval_ref`, `intent_id`, `requested_at`, `state`, `state_version`, `previous_ref`, `runtime_evidence_ref`, `reason_code` |

`terms`에는 기존 후보의 **실제 `OrderTerms` 전체**를 넣고 후보와 정확히 일치시킵니다. 수량·단위·종목·시장·side·가격·TIF·capability·비용·최대부담·매도 최소대금·유효기간을 승인 시 다시 계산하거나 완화하지 않습니다.

`issued_at`과 `decision_evidence_ref`는 pending에서만 null, `consumed_intent_id`는 consumed에서만 필수입니다. nullable 규칙을 스키마에 고정합니다. 인증용 opaque handle은 이 canonical 타입들에 포함하지 않습니다.

**합성 권한과 승인 성공 경로**

composition root가 만든 단일 `SyntheticAuthority`가 등록된 fixture principal에 대해 **직렬화 불가능한 opaque session handle**을 발급하도록 제안합니다. application은 매 호출마다 해당 발급자의 registry에서 handle identity·계좌·환경·세대·권한·세션 상태를 확인합니다.

`PrincipalEvidence`를 직접 생성하거나 canonical JSON에서 복원한 것만으로는 권한을 얻지 못합니다. 다른 authority instance가 발급한 handle, 가짜 principal, `authenticated=True`, `proof=True`, `running=True`, AI의 “승인합니다”는 모두 거부합니다.

성공 경로는 다음과 같습니다.

1. 고정 fixture의 합성 controller가 명시적으로 세션 시작·resume를 요청합니다.
2. application이 실제 Q24 후보와 원천을 해소하고 현재 권리를 검사합니다.
3. exact 후보 금융조건과 승인 범위·만료를 표시하고 `PresentationRecord`를 저장합니다.
4. 같은 세션에 후보·표시·action·expected version으로 결속한 challenge를 발급합니다.
5. fixture의 명시적인 사용자 동작 시뮬레이션이 `approve`를 제출합니다.
6. application이 현재 권한·세션·원천·표시·nonce를 재검사하고 pending→approved와 receipt를 함께 기록합니다.

이는 **합성 사용자 동작 프로토콜의 성공**입니다. 실제 사람이 화면을 보거나 로컬 사용자 인증을 완료했다는 증거가 아닙니다. 실제 인증 adapter는 미구현·차단 상태로 유지하며 비밀번호·vault·새 인증 라이브러리·자체 암호 프로토콜을 추가하지 않습니다.

**후보·현재 권리·표시 결속**

Q26의 source adapter는 후보 ref만 받는 대신 `TargetRequest`, `TargetInputs`, `TargetArtifacts`와 실제 저장 객체를 해소해야 합니다.

- 원래 입력·평가시점으로 Q24 builder를 재현해 plan/candidate/result의 exact 일치를 확인합니다. 격리된 메모리 저장소를 사용하며 기존 후보를 수정하지 않습니다.
- 재현에 사용한 과거 권리와 **현재 소비 권리**를 구분합니다. 현재·과거 위험점·일간 사용·성과 등 모든 의존 원천의 source/dataset/version/rights_ref와 정정·철회를 확인합니다.
- 표시에는 현재 report 권리, 원천 재검증에는 해당 research/store 권리를 요구합니다. Q26 자체에 AI 권리를 임의로 요구하거나 실제 권리를 발급하지 않습니다.
- Q24의 기존 후보 표시를 사용하되, Q26 표시 record에 계좌 ref·환경·세대·승인 action·정책·승인 만료를 추가로 결속합니다. 후보의 표시 문구와 금융 숫자는 그대로 보존합니다.
- `PresentationRecord` 전체 canonical hash가 실제 표시 문자열과 승인 context를 함께 묶습니다. 화면에만 다른 가격·위험문구를 덧붙이는 경로는 허용하지 않습니다.
- 표시 후 원천 정정·권리 철회·정책 변경·후보 교체가 확인되면 기존 표시를 승인에 사용할 수 없습니다.

Q25 검토를 함께 보여주려면 exact review ref와 별도 “합성 부속 검토” 표시를 사용합니다. 검토의 accepted/complete 상태는 승인 조건이나 인증 근거가 아닙니다.

**상태·시각·재전달 규칙**

| 현재 상태 / 사건 | 결과 |
|---|---|
| 신규 검증 완료 | pending v1 |
| pending + 유효한 명시 approve | approved, version +1 |
| pending + 유효한 명시 deny | denied, version +1 |
| pending/approved + 만료 | expired |
| pending/approved + 세대·정책·후보·원천 유효성 상실 | invalidated |
| approved + 권한 있는 revoke | revoked |
| approved + 동일 UoW의 admission 성공 | consumed, intent ID 필수 |
| consumed + 철회 | consumed 유지, 별도 `WithdrawalRequest` 생성 |
| denied/revoked/expired/invalidated/consumed | approved 복귀 금지 |

pending→expired/invalidated는 새 계약에서 명시할 보완 전이입니다. frozen `execution-v1`을 조용히 수정하지 않고 root가 additive 계약에 채택해야 합니다. 시스템 만료를 사용자 denied로 기록하지 않습니다.

승인 만료는 다음 교집합으로 정합니다.

```text
expires_at = min(
  candidate.valid_to,
  target_policy.valid_to,
  approval_policy.valid_to,
  issued_at + approval_ttl,
  principal.expires_at,
  session.expires_at,
  applicable_source_rights_deadlines
)
```

모든 기간은 끝 제외입니다. liveness deadline은 이 절대 만료와 별도로 매 호출 확인합니다. heartbeat로 승인 만료를 연장하지 않습니다. 시계 역행·불확실·누락은 faulted 및 신규 권한 사용 차단입니다.

**합성 fixture 제안값**은 approval TTL 20초, challenge TTL 10초, session TTL 120초, liveness 30초입니다. root가 구현 전에 실제 Q24 후보 유효기간과 맞춰 명시 고정해야 합니다. 15분 분석 주기에서 어떤 만료값도 추론하지 않습니다.

재전달은 `(issuer_instance, generation, session_id, nonce)`와 `command_id`를 함께 검사합니다.

- 동일 command·동일 payload는 기존 receipt만 반환하며 전이·소비를 반복하지 않습니다.
- 같은 nonce 또는 command ID의 다른 payload는 conflict입니다.
- 재전달에도 현재 인증·조회 권리를 확인합니다. 접근이 상실되면 과거 금융 상세를 반환하지 않습니다.
- 유효하게 인증된 challenge 처리의 nonce 사용·판정 receipt·상태 변경은 함께 기록합니다. 실패 후 다른 payload로 nonce를 재사용하지 못합니다.
- 승인과 거절이 경합하면 expected version을 먼저 확정한 한 건만 성공합니다.
- 세션 단절은 해당 세션의 challenge와 미소비 승인 사용을 차단합니다. 연결 회복이나 renew만으로 재승인·재개하지 않습니다.

**Q27 통합 경계**

공개 `consume_approval()` 또는 별도 commit을 수행하는 approval repository API는 만들지 않습니다. 내부 순수 함수는 변경 계획만 반환합니다.

```text
plan_admission_transition(
    aggregate_snapshot,
    approval_ref,
    intent_draft,
    resolved_runtime_facts,
    expected_versions
) -> TransitionPlan | Rejection
```

이 함수의 반환값은 실행 권한이나 commit 증거가 아닙니다. Q27의 UoW가 같은 계좌 직렬화 경계에서 실제 객체와 현재 상태를 해소하고 다음 항목을 **동일 transaction**으로 commit해야 합니다.

```text
approval → consumed
+ candidate submission uniqueness claim
+ intent → prepared
+ cash / quantity / risk reservations
+ outbox → pending
+ immutable history / command receipt
```

승인 서비스가 먼저 consumed를 저장하고 실행 서비스가 나중에 intent를 저장하는 구성은 금지합니다.

Q26 메모리 adapter는 공유 aggregate와 하나의 lock 아래 이 묶음을 모사할 수 있습니다. 승인·명령·후보 소비 인덱스·합성 intent·예약·outbox·history를 staging한 뒤 한 번에 교체하고, 실패하면 전체를 유지합니다. 이 모사는 프로세스 내 동시성만 검증합니다.

필수 제약은 다음과 같습니다.

- 같은 계좌/환경/세대의 exact 후보에는 submission claim이 최대 하나입니다. 병렬 approval ID를 만들어도 우회하지 못합니다.
- 동일 candidate ID에 다른 hash가 들어오면 저장 충돌입니다. 변경 후보는 새 identity/hash와 새 승인 절차가 필요합니다.
- consumed는 `aborted_unsent` 이후에도 재사용하지 않습니다. 같은 후보의 다른 승인으로도 소비 claim을 우회하지 않습니다.
- 승인·철회·중단·정책 변경·admission·dispatch 전이는 동일한 계좌 lock/version 경계를 공유합니다.
- 다른 서비스 instance나 worker도 동일 저장소와 lock을 공유해야 합니다. instance별 lock은 충분하지 않습니다.
- Q27의 risk/session/intent/egress 사실은 저장된 객체·사건·현재 버전에서 해소합니다. caller가 넘긴 `risk_allowed`, `is_prepared`, `unsent_confirmed` bool은 받지 않습니다.

Q26 합성 runtime evidence에는 `provenance="synthetic_aggregate"`, aggregate ID/version, event ref, fixture manifest ref를 넣습니다. Q27의 영속 transaction·dispatch fencing·외부 egress 원자성 검증은 **미완료**로 남깁니다.

**철회와 dispatch 경합**

철회는 승인 상태와 별도 요청 상태를 갖습니다.

| 직렬화 시 확인한 사실 | 저장·표시 결과 |
|---|---|
| approved, 소비 전 | approval revoked |
| consumed + prepared, 미전송 근거 확정 | withdrawal `unsent_confirmed`, intent `aborted_unsent`; consumed 보존 |
| dispatching이 먼저 확정 | withdrawal `requested`; “철회 요청” 표시 |
| dispatching 이후 egress가 미전송을 확정 | 증거를 연결해 `unsent_confirmed` |
| 전송 중·전송 후·unknown | `requested` 유지, 조회·대사 필요; 자동 재전송·예약 해제 없음 |

Q26에서는 위 상태를 합성 aggregate의 저장된 사건으로만 모사하고 화면에도 “합성”을 표시합니다. 실제 미전송 확인이라고 주장하지 않습니다.

철회/중단에는 적절한 현재 사용자 권한이 필요하지만, 신규 주문용 risk allow나 시장자료 report 권리까지 요구해 보호 동작을 막으면 안 됩니다. 만료·복원 전 세션에 묶인 consumed intent도 새로 권한을 확인한 같은 계좌의 제어 세션에서 철회를 요청할 수 있어야 합니다.

`stop_new_orders`, `resume`, `cancel_order`, `liquidate`는 서로 다른 command와 권한입니다. approval/revoke/withdraw에서 취소·청산을 발생시키지 않습니다. Q26은 cancel/liquidate 실행 경로를 제공하지 않습니다.

**복원·조회·저장 경계**

복원 시 새 authority generation은 복원 snapshot 밖의 합성 authority에서 발급합니다. snapshot에 들어 있는 generation으로 현재 authority를 덮어쓰지 않습니다.

이전 세션·handle·nonce·pending/approved는 실행 불가로 만들고 immutable invalidation 기록을 남깁니다. consumed·intent·unknown·예약·철회 요청·submission claim은 보존합니다. 복원 누락이 의심되는 이력은 새 제출을 차단하며 자동 재생하지 않습니다. 실제 rollback 방지·이전 egress 종료 확인은 후속 운영 경계입니다.

조회 API는 mutation API와 분리합니다.

| 역할 | 허용 범위 |
|---|---|
| 합성 approver | 지정 계좌의 표시·approve/deny/revoke/withdraw |
| 합성 controller | 별도 권한의 세션·stop/resume; approver 권한 자동 상속 없음 |
| reporting | 지정 계좌·목적의 제한된 상태 조회, 금융 상세는 현재 report 권리 검사 |
| research/AI | 명시 허용된 비권한 요약만; session handle·challenge·nonce·쓰기 port 없음 |

조회에는 개수 제한·cursor·계좌 필터를 강제합니다. report 결과에 opaque handle이나 nonce를 노출하지 않습니다.

제안 한도는 canonical 객체 64KiB, 해소 입력 8MiB/128 refs, 문자열 2KiB, rendered text 16KiB, 공유 메모리 전체 128 records/8MiB입니다. session·nonce·receipt·history·소비 인덱스도 합계에 포함합니다. 자동 eviction으로 replay 방지 증거를 제거하지 않습니다. 열려 있는 절차의 종료·철회 기록 공간을 발급 전에 예약하고, 공간이 없으면 신규 발급을 차단합니다.

history는 `previous_ref`를 실제 조회해 동일 entity/account/environment, 연속 version, 허용 전이를 검사합니다. canonical 재파싱·constructor·repository·application 모두 닫힌 필드와 불변식을 검사합니다. hash chain은 인증이나 관리자 변조 방지 증명이 아닙니다. 직접 repository에 approved/consumed JSON을 넣어 권한을 얻는 경로는 제공하지 않습니다.

오류는 다음과 같은 고정 code만 반환합니다.

```text
invalid_contract / unsupported_environment / authority_denied
session_inactive / session_expired / generation_mismatch / clock_invalid
nonce_unknown / replay_conflict / version_conflict
candidate_mismatch / presentation_mismatch / source_unresolved
rights_denied / policy_changed / expired / terminal_state
candidate_already_consumed / capacity_exceeded / commit_failed
```

원시 예외·경로·입력 문자열·객체 repr은 반환하지 않습니다. `denied`는 사용자 거절, 시스템 오류는 rejection code로 구별합니다. 비소유 중복 호출의 오류가 기존 소유자의 승인·intent 상태를 변경해서도 안 됩니다.

**구현 전 고정할 golden과 안내서 검증 항목**

root가 fixture 입력·기대값·버전·source hash를 먼저 고정하고 다음 사례를 순차 및 thread 경합으로 검증하도록 제안합니다. 이번에는 실행하지 않았습니다.

| 사례 | 필수 기대 결과 |
|---|---|
| 정상 표시→명시 approve→합성 admission | approved 후 consumed; intent/예약/outbox 각 한 묶음 |
| 실제 Q24 기본 후보 A | 3주 × 100 USD + 비용 상한 2 USD = 최대부담 302 USD 그대로 표시·결속 |
| 동일 command 재전달 | receipt 재사용, version·소비 건수 증가 없음 |
| nonce의 action/candidate/display/session 변경 | conflict 또는 authority denial |
| application 직접 호출 + 가짜 principal/proof bool | 승인 생성·상태 변경 없음 |
| quantity/price/문구/hash/계좌/세대 변경 | 기존 승인 사용 불가 |
| 표시 후 현재 권리 철회·정책 변경 | 승인/admission 차단, 과거 상세의 무권한 재노출 없음 |
| 기한 바로 전·정확한 만료시각·시계 역행 | 경계별 허용/차단이 고정 기대값과 일치 |
| 단절·liveness 만료·worker renew·자동 재연결 | 신규 권한 사용 차단, 자동 resume 없음 |
| 동일 후보의 두 승인 동시 admission | consumed 최대 1, intent/예약/outbox 최대 1 |
| revoke↔admission 경합 | 먼저 확정한 상태와 일치, 부분 저장 없음 |
| prepared withdrawal↔dispatching 경합 | withdrawal 선행이면 dispatch 불가; 반대면 requested |
| commit 단계별 주입 실패 | 소비·예약·outbox·nonce에 부분 성공 없음 |
| consumed→aborted_unsent→재사용 시도 | 기존 승인과 같은 후보 병렬 승인 모두 재소비 불가 |
| restore | 옛 handle/approved 차단, consumed/unknown/예약 보존 |
| canonical/repository reseal·잘못된 predecessor·용량 초과 | 우회 거부, 기존 history 보존 |
| 역할별 조회·예외 주입 | 권한 분리, 금융 상세·nonce·원시 예외 유출 없음 |

thread 시험은 sleep 순서에 의존하지 않고 barrier로 두 순서를 각각 강제해야 합니다. 여러 application instance가 하나의 aggregate를 공유하는 경우도 포함합니다.

소유 범위는 다음으로 제한합니다.

```text
src/quantharbor/domain/approval.py
src/quantharbor/application/approval.py
src/quantharbor/ports/approval.py
src/quantharbor/adapters/synthetic_approval.py
src/quantharbor/domain/serialization.py  # 신규 타입 등록만
tests/product/synthetic_approval.py
tests/product/test_approval*.py
docs/development/approval.md
```

root는 새 계약·결정·fixture manifest·작업 카드·상태·증거를 통합합니다. 기존 금융 모듈·TargetRef·frozen 계약·DB migration·dependency는 변경하지 않습니다.

개발 안내서에는 정상 합성 사용자 동작 예제, TTL·한도, state/receipt 의미, thread 시험 범위, 실제 인증 미구현, Q27 동일 transaction 요구를 명시합니다. 후속 실행용 전용 시험 명령은 다음처럼 제공할 수 있습니다.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3.13 -m unittest discover \
  -s tests/product -p 'test_approval*.py' -v
```

**미결정 사항은 root의 fixture 값·pending 종료 전이 채택·표시 버전 고정입니다.** 실제 인증/비밀번호, PG-01 운영 정책, 실제 계좌 권한, 영속 admission·dispatch/egress 검증은 계속 차단 또는 후속 미완료로 남습니다. 이번 자문은 Q26 구현 완료나 실제 금융 승인으로 집계하지 않습니다.