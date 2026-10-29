**판정: Q27의 명시된 로컬 복구 계약을 충족하지 못하는 중요한 복구 결함입니다.** 과거 주문의 실행 권한과 현재 계좌의 복구 자격을 분리하는 최소 보완을 권고합니다. 원 승인 재사용이나 위험 한도 완화는 필요하지 않습니다.

**1. 실제 관측과 범위 판정**

[실제 DB 결과](/Users/okestro/projects/QuantHarbor/docs/evidence/execution-database-lifecycle-fixes-2026-10-27.json)의 `completion_approval_terminal(action='admit', expiry='approval')`는 다음을 확인했습니다.

- 만료된 admission은 `rejected/expired`, 승인 head는 `expired`.
- 종료 전후 총 필요량은 **101→91행**, **6,820,264→5,427,902bytes**로 감소했습니다.
- 이후 새 query로 대사했지만 `unresolved/recovery_readset_unresolved`; 수동 resume는 `reconciliation_required`로 차단됐습니다.
- 따라서 결과는 **13개 기능 경로 통과 + 1개 만료 차단 진단**입니다. 만료 후 성공 복구나 최신 전체73 통과 증거가 아닙니다.

정적으로 확인한 원인은 다음과 같습니다.

- [_validate_recovery](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:904)는 첫 approval head를 선택합니다. `refresh_current`와 정지 중 `replace_source`에도 같은 의존성이 있습니다.
- [validate_current](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/execution.py:22)는 원 Q24 source의 현재 유효성과 approval TTL을 함께 요구합니다.
- 시험 입력상 승인 만료는 **14:31:30**, 원 request와 실행정책 만료는 **14:31:33**입니다. 이는 시험 소스의 정적 대조이며 추가 DB 관측은 아닙니다. 따라서 이 사례의 승인 만료와 이후 발생할 source·정책 만료를 구분해야 합니다.
- source가 만료된 뒤에는 `validate_source`와 `_dependency_window`도 차단합니다. 승인 TTL 한 줄만 제외해도 정상 순환이 완성되지 않습니다.

[로컬 계약](/Users/okestro/projects/QuantHarbor/docs/contracts/execution-local-v1.md)은 현재의 완전한 대사와 명시 권한에 의한 재개를 요구합니다. 과거 승인 TTL 때문에 계좌 복구를 영구 제한한다는 예외는 없습니다. EXECUTION-DEC-002의 명시적 미지원 정정 경계와도 성격이 다릅니다. **Q27 완료 전에 보완할 범위**입니다.

**2. 최소 대안 비교와 권고**

| 대안 | 판단 |
|---|---|
| 만료 후 복구 불가를 지원 제한으로 문서화 | 현재 계약의 정상 복구·반복 수용 요구를 충족하지 못함 |
| 복구 호출에서 approval TTL만 생략 | 원 request 만료, 첫 승인 선택, source 교체 순환이 남음 |
| 승인 실행 검사와 현재 계좌 검사를 분리 | **권고.** 기존 신뢰 구성·계산·DB 경계를 재사용하며 필요한 결합만 제거 |

`validate_current`의 주문 실행 의미는 유지하고, 승인 객체를 받지 않는 내부 계좌 검증 경로를 추가합니다. 가짜 approval, 만료값 연장, `skip_expiry` 공개 플래그, caller bool/callback/hash는 사용하지 않습니다.

**3. 구체적인 계약·함수 변경안**

**검증 함수의 관계**

- `application/execution.py`에 내부 `_validate_account_current(...)`를 추출합니다. 입력은 검증된 현재 자료와 같은 transaction에서 읽은 계좌 상태이며, 반환은 계산 결과·해소된 참조·절대 유효구간입니다. 실행 허가 토큰을 반환하지 않습니다.
- 기존 `validate_current`는 원 Q24 재현, 후보/승인 terms 일치, 원 request·approval TTL, 승인 정책 결속을 유지하고 공유 현재 검사를 호출합니다.
- repository의 `_validate_recovery`는 공유 현재 검사와 기존 금융·이력 정합성 검사를 결합합니다. approval head를 선택하지 않습니다. 승인 0개인 초기 계좌도 동일한 현재 검사를 거칩니다.
- `refresh_current`, `rebind`, `reconcile`, `control('resume')`, `_final_check`의 복구 분기를 모두 연결합니다. 한 호출부만 고치면 첫 승인 의존성이 남습니다.
- `application/target.py`의 `_market_rows`·`_dependency_window`에서 필요한 순수 계산을 좁게 추출합니다. Q24 wrapper는 계속 원 request 만료를 적용합니다. 복구를 위해 더 긴 만료의 `TargetRequest`를 만들지 않습니다.

**최소 읽기 계약**

| 구분 | 필요한 근거 |
|---|---|
| 권한·제어 | 실제 issuer registry의 opaque handle, 현재 principal/session/permissions, 승인 정책, account version·mode·generation·fence |
| 원장·실행 | 잠긴 Q20 전체 사건·projection·cursor, 모든 intent/claim/consumed approval/attempt/outbox/reservation, 취소·철회·격리·비용 미확정 상태 |
| broker | 같은 실제 합성 issuer journal의 query·statement·manifest, 전체 scope, receipts/events/request-attempts, journal sequence와 inclusion/cutoff |
| 현재 자료 | Q21 평가·대사, Q23 정정 이력·성과·비용, 현재 실행/target 정책, 가격·FX·분류·매핑·달력·capability·비용 규칙 |
| 권리·시간 | 실제 소비하는 현재 및 과거 자료 전체의 현재 권리, dataset/version/purpose scope, 관측·수집·effective·knowledge 시각과 신선도 |

복구 scope는 **계좌 전체 보유·통화·실행 의무**를 포함해야 합니다. 오래된 부분 후보의 scope로 축소하면 안 됩니다. 사용되는 risk/boundary/daily-history 자료의 `research/store/report` 권리 검사도 유지합니다.

복구 유효구간은 현재 정책, 권리 철회시점, 실제 자료 시점에 기초한 freshness, 가격·FX·매핑 등의 교집합으로 계산합니다. `checked_at + 새 TTL`로 오래된 자료를 신선하게 만들지 않습니다. 과거 주문의 request/approval TTL은 이 구간에 넣지 않습니다.

**새 source 수용과 순환 차단**

권고 순서는 다음과 같습니다.

`stopped → 현재 자료 결속 → rebind·새 matched 대사 → 명시 resume → 새 Q24 candidate → 새 approval → admit/dispatch`

- **approval만 만료:** 현재 자료가 유효하면 새 승인 없이 계좌 복구가 가능해야 합니다.
- **원 Q24 request만 만료:** 원본은 보존하고 현재 계좌 검증에서 그 주문 요청의 TTL을 사용하지 않습니다. 다음 주문에는 새 Q24 원본이 필요합니다.
- **현재 자료·실행정책도 만료:** 새로 검증된 현재 자료·정책이 필요합니다. 기존 시험의 실행정책은 원 request와 같은 시각에 만료하므로 이 경우도 별도 검증해야 합니다.

구체적으로 `rebind`가 기존 `refresh_current(..., market_inputs=...)` 경로를 사용할 수 있게 하고, 필요한 현재 이력·정책 입력을 좁은 typed 결속 경로로 받도록 보완합니다. 공급된 projection/events/performance를 그대로 권위로 채택하지 않고 잠긴 DB와 기존 Q20/Q21/Q23 계산으로 재구성합니다. 정책 참조 변경은 기존 `policy` 권한과 승인된 합성 구성에 결속하며 `runtime` 권한만으로 임의 정책을 채택하지 않습니다.

`replace_source`의 “새 source에서 첫 과거 candidate를 해소” 검사는 제거하고, **새 source 자체의 실제 Q24 재현·repository 해소·현재 권리·계좌/정책 결속**으로 대체합니다. 이 변경은 대사를 무효화하고 재대사 비용을 확보해야 하며, 기존 matched 결과를 요구하는 순환 조건을 두지 않습니다.

원 candidate/terms·presentation·consumed·claim·challenge/receipt·원본 이력은 보존합니다. 이전 source에 결속된 pending/approved는 신규 실행에 사용할 수 없게 처리하고 consumed는 되돌리지 않습니다. 과거 참조의 조회에 필요한 원본 repository 연결도 보존하며, 보존 자료 전체를 기존 source 한도에 계상합니다.

**DB·결속·쓰기 경계**

기존 [실제 신뢰 구성](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/execution_uow.py:158)을 유지합니다.

- 같은 계좌의 모든 facade가 같은 registry와 broker gate를 사용합니다.
- 잠금 순서는 `ledger_stream → execution_account → execution_head`를 유지합니다.
- 현재 자료 변경은 동일 transaction의 version·generation·fence·기존 source identity CAS와 결속합니다.
- 새 reconciliation에는 기존 account/session/query/cursor 결속에 **현재 자료 identity, 검증 버전, 절대 유효구간**을 추가합니다. identity는 검증 후 계산한 변경 탐지값이며 인증 수단이 아닙니다.
- SQL의 closed shape/context/read-set 검사와 `common_plan`의 matched 판정도 같은 필드를 검사합니다. 오래된 형식의 matched 결과는 새 검증 없이 resume 근거로 승격하지 않습니다.
- registry의 새 입력은 commit 확인 뒤 공유합니다. 실패는 DB와 staged 입력을 함께 되돌립니다. COMMIT 응답 유실은 DB 결속을 조회해 정확히 준비했던 자료와 대조하며, 불확실하면 모든 facade를 차단합니다. 자동 금융 write 재시도는 없습니다.

복구가 쓸 수 있는 것은 현재 자료 결속, 검증된 inclusion/source-cutoff, 대사·감사 결과와 명시 제어 상태입니다. 새로운 intent·승인 소비·주문 전송을 만들지 않습니다. 새 자료만으로 금융 hold를 해제하지 않습니다.

`prepared/dispatching/unknown`, armed/unknown cancel, 미해결 reservation, unknown cost, unsupported correction, 잘못된 broker manifest는 계속 차단합니다. 기존 승인으로 새로운 admission을 만들 수 없으며, 복구가 과거 intent의 dispatch 권한을 되살리지 않습니다. 정상 신규 admission 직후 consumed가 되는 기존 최초 dispatch 계약은 그대로 유지합니다.

현재 시각·권한은 저장/재개 직전에 다시 확인합니다. 이후 주문 제출에는 기존 `current_risk`와 **SEC2의 모든 DB I/O 이후 최종 handoff 시각 검사**가 계속 적용됩니다.

**4. 필수 실제 DB 검증 행렬 — 아래는 미실행 계획**

| 검증군 | 필수 결과 |
|---|---|
| approval 만료만 발생 | 현재 자료 유효 상태에서 새 대사 matched → 명시 resume 성공. 기존 expired-target 음성 증거는 보존 |
| consumed/revoked/expired 이력 | 과거 TTL과 무관하게 계좌 복구 가능. 원 terms·consumed·claim·이력 불변 |
| 과거 실행 차단 | 과거 승인 admit, 과거 intent 재dispatch, 옛 challenge/nonce 재사용 모두 신규 경제효과·broker 수신 0 |
| 정상 신규 실행 | 복구 후 실제 새 Q24 candidate·새 approval로 admission/dispatch 성공. 신규 위험 검사까지 도달 |
| oldest ordering | expired/consumed/revoked/live head의 순서·ID를 바꿔도 같은 현재 계좌의 복구 판정 동일. 승인 0개도 포함 |
| source 만료 구분 | approval만 만료 / request만 만료 / 현재 정책도 만료 / 시장자료도 만료를 각각 분리. fresh 자료 전 차단, 적법한 갱신 뒤 성공 |
| fresh source 순환 | stopped에서 새 자료 결속·rebind 가능. 새 Q24 source가 과거 candidate를 포함하지 않아도 순환 차단 없음. 원본 보존 |
| 권한·시간·권리 | 권한 철회, session/liveness/generation/fence 불일치, 역행·미래 시각, 경계시각 `at == valid_to`, 잘못된 dataset/purpose·정책 모두 차단 |
| 금융·broker 음성 | active unknown, 불일치 예약, 미지원 정정, incomplete cost, foreign issuer, 누락/추가 사건·receipt·attempt, 잘못된 inclusion/cutoff가 fresh 자료로 해제되지 않음 |
| SQL·경합·rollback | source/head/권한/원장 변경 경합, stale CAS, 가짜 context/hash, 직접 product-role mutation 거절. 단계별 실패·EOF·timeout에서 DB/registry 원자성 확인 |
| COMMIT 유실·restore | 결속 결과 관측으로만 해소. 새 generation과 정확한 schema/code/source 재결속 요구, 옛 facade/handle/session/egress 차단, unknown·claim 보존 |
| 용량·기존 회귀 | 기존 한도 그대로 rows/index bytes/복사본 독립 계상. 필수 전이 `Δactual+Δremaining≤0`, 선택 갱신 사전 확보, 타 owner 예약 불사용. active3·terminal-third·포화·SEC1·SEC2 재검증 |

특히 새 결속 필드·원본 보존 비용이 기존 **repair 2행/393216bytes** 등에 들어간다고 추정만으로 처리하면 안 됩니다. 실제 최대 크기를 계상하고, 기존 조건부 noncontroller repair·승인 별도 종료 예약·복구 명령6행·immutable lookup을 유지해야 합니다.

**5. 파일 소유·미확인·완료 기준**

단독 구현자에게 필요한 최소 소유 범위는 다음과 같습니다.

- 검증·제어: `application/execution.py`, `adapters/postgres_execution.py`.
- 순수 계산 추출: `application/target.py`의 좁은 호환 seam.
- typed 결속·SQL: `domain/execution.py`, 필요한 `ports/execution.py`·serialization 등록, `adapters/execution_uow.py`, `0003_synthetic_execution.sql`.
- 검증·안내: 기존 execution control/SQL/storage 시험, 합성 입력 helper, `scripts/check_execution.py`, `docs/development/execution.md`.
- root: 추가 결정, execution-local 계약, task/status/evidence 통합. 원 승인 검증 변경은 기본 범위에서 제외합니다.

이번 읽기 전후 **owned28·baseline7·fixture2 SHA 모두 입력과 일치**했습니다. owned28은 구현 인계 및 실제 DB before/after와도 동일합니다. 실제 DB의 fixture·0003 SHA도 현재와 일치합니다.

미확인은 새 결속의 최악 저장비용, 실제 성공 복구, SQL 경합/응답 유실, 독립 보안·일반 검토, 최신 전체 DB/제품/품질 검증입니다. 위 행렬과 기존 고정 계약 회귀를 같은 최종 소스에서 확인한 뒤 Q27 완료를 판단해야 합니다.

이번 작업은 **읽기전용 설계 자문**입니다. 파일·status 수정, 시험·Docker·network 실행, 모델·권한 변경을 수행하지 않았습니다. Q27과 제품 완료를 주장하지 않으며 P28은 Q27 판정 이후입니다.