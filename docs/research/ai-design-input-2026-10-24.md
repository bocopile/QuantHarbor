# Q25 설계 자문

정적 자문이며 아래 제안은 ai-local-v1에 채택된 범위에서 적용한다. 시험/실제 AI 성능 증거가 아니다.

Q25는 **기존 문서·숫자 원천을 재검증하는 합성 AI 소비 계층**으로 한정하는 구성이 적절합니다. 아래는 root가 추가 계약 `ai-local-v1`에 통합할 제안이며, 구현·평가 통과 판정은 아닙니다.

1. **확인된 기존 상태**

- [현재 상태](/Users/okestro/projects/QuantHarbor/docs/status.md:590)는 Q24 로컬 검토·검증 완료, Q25 설계 착수다. 기록된 시험 결과를 이번 자문에서 재실행하지 않았다.
- [execution-v1](/Users/okestro/projects/QuantHarbor/docs/contracts/execution-v1.md:5)은 요청·결과·가설, 신규 제품 API 비용0, 호출 전 예약·불명 청구 유지, 명시 재시도 정책을 이미 요구한다.
- Q18 [`select_view`](/Users/okestro/projects/QuantHarbor/src/quantharbor/domain/documents.py:615)는 실제 bundle에서 정정 계보·시점·기업 연결·현재 목적 권리를 검사한다. 기업/종목 연구는 `ai` 권리 외에 `research` 권리도 필요하다.
- Q23 [`build_bound_performance`](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/research.py:179)는 사건·snapshot·흐름 경계를 재검증한다. 다만 내부 평가는 snapshot의 `evaluated_at`을 사용하므로 **Q25 소비 시각의 권리 검사까지 대신하지 않는다**.
- Q24 [`CandidateBody`](/Users/okestro/projects/QuantHarbor/src/quantharbor/domain/target.py:520)는 금융 조건과 표시 문구를 함께 결속한다. 기존 `TargetRef.kind`에는 AI 결과가 없다.
- Q14 [`authorize`](/Users/okestro/projects/QuantHarbor/src/quantharbor/runtime/boundary.py:35)의 역할은 `research/reporting/controller`다. 아래 여섯 AI 역할의 세부 권한이나 같은 프로세스 내 악성 코드 격리를 이미 제공한다고 볼 수 없다.

2. **최소 닫힌 계약 제안**

새 최상위 형은 `ResearchRequest`, `ResearchResult`, `ResearchReview`, `Hypothesis`, `AIBudgetPolicy`, `AIBudgetAttempt` 여섯 개로 제한한다. 모두 `schema_version=1`, `environment=synthetic`; nullable 필드도 반드시 존재한다. 자유 `dict`, 임의 metadata, confidence/proof bool은 받지 않는다.

| 형 | 필수 필드와 의미 |
|---|---|
| `ResearchRequest` | `request_id, run_id, idempotency_key, role, purpose, account_ref?, scope, as_of, knowledge_cutoff, evaluated_at, deadline, locale, source_refs, required_outputs, allowed_queries, procedure_version, instruction_version, tool_schema_version, client_profile, budget_policy_ref, caps, period?, review_subject_ref?` |
| `ResearchResult` | `result_id, request_ref, input_manifest, client_identity, procedure_version, instruction_version, tool_schema_version, started_at, finished_at, finish_reason, claims, assumptions, counterevidence, unknowns, hypothesis_refs, query_receipts, budget_attempt_refs, checks, status, reasons, period_review?` |
| `ResearchReview` | `review_id, review_request_ref, exact_result_ref, reviewer_identity, reviewed_at, dependency_refs, checks, findings, verdict` |
| `Hypothesis` | `hypothesis_id, origin_result_ref, proposition, supporting_claim_refs, opposing_claim_refs, assumptions, falsification_condition, experiment_proposal?, dependencies, created_at, expires_at, assessment, supersedes_ref?, retracts_ref?` |
| `AIBudgetPolicy` | `policy_id, version, budget_scope, window_start, window_end, charge_unit, pricing_version, input_rate, output_rate, fixed_call_cost, window_caps, attempt_caps, concurrency_cap, retry_policy, escalation_policy` |
| `AIBudgetAttempt` | `attempt_id, request_ref, sequence, retry_of?, client_profile, window_ref, reserved_usage, state, reserved_at, dispatch_at?, settled_at?, actual_usage?, reasons` |

중첩형도 닫는다.

- `AIRef = kind/id/version/canonicalization_version/sha256`. `kind`는 문서 manifest/original/revision/observation/context, snapshot/event/performance/experiment, target plan/candidate, rights/policy/strategy, AI 산출물의 **고정 등록표**만 허용한다. 실제 객체 해소가 필수다.
- `Citation = manifest_ref/revision_ref/observation_ref/original_ref/context_ref/start_utf8/end_utf8/exact_quote`. 경계가 문자 중간을 자르거나 원문 bytes와 다르면 거부한다.
- `NumericClaim = claim_id/source_ref/selector/position?/period?/value/unit/currency?/as_of`. `selector`는 NAV·경제적 현금·보유수량·TWR·손익·관측 MDD·비용·회전율·후보 조건 등 구현한 필드만 enum으로 등록한다. 임의 JSONPath·수식·SQL은 금지한다.
- `Check = code/subject_ref/expected?/observed?/outcome`, `outcome=pass|fail|unknown`. 검사 근거와 비교값을 보존하고 성공 bool 하나로 축약하지 않는다.
- `purpose=ai_research|ai_report`; 실제 필요한 기존 권리는 각각 `ai+research`, `ai+report`, 연구 성과를 보고에 쓰면 `research`도 추가한다. 저장에는 `store`가 필요하다.

`input_manifest`에는 실제 해소한 객체 참조, 원천 발표/관측/수집 시각, 현재 권리 참조와 검사 시각, 정책·전략·자료 버전을 남긴다. 요청자가 보낸 권리 승인 문자열을 신뢰하지 않는다.

3. **역할·도구와 원천 연결**

도구는 문자열 실행기가 아니라 다음 고정 query union과 역할별 허용표로 구현한다. 모든 query는 요청에 이미 포함된 ref만 사용할 수 있다.

| 역할 | 허용 query | 산출물 |
|---|---|---|
| `collector` | `document_view` | 기존 합성 문서 분류·누락·계보 설명 |
| `study` | `document_view`, `hypothesis_view` | 근거별 공부 기록·가설 |
| `strategy` | 위 두 개, `research_view` | 기존 실험 해석·미실행 실험 제안 |
| `portfolio` | `snapshot_view`, `research_view`, `candidate_view` | 자산·기존 후보 설명 |
| `risk` | 위 모든 읽기 query | 반례·제약·독립 검토 |
| `report` | `document_view`, `snapshot_view`, `research_view`, `candidate_view`, `hypothesis_view` | 주간/월간 검토 |

`document_view` 인자는 정확한 bundle ref·entity/position·`as_known|restated`·cutoff다. 나머지도 snapshot/experiment/candidate/hypothesis ref와 고정 selector만 받는다. 계좌·목적·시각은 요청에서 상속하며 도구 인자로 확대할 수 없다.

원천 소비는 다음처럼 연결한다.

- **문서:** 실제 `DocumentBundle`·catalog·현재 grant로 Q18 `select_view`를 호출한다. 인용 일치가 의미적 주장의 참임을 증명하지는 않는다. 인용 외 해석은 명시적 추론/가설로 분리한다.
- **숫자:** Q20 사건과 Q21 입력으로 snapshot을 재구성하고, 기간 성과는 Q23 bound API로 계산한다. 모든 과거 평가점·흐름 경계·시장 입력에 대해 현재 소비 권리를 추가 검사한다.
- **벤치마크:** `benchmark_return` scalar만 주입하지 않는다. 동일 기간·통화·시나리오의 실제 benchmark 입력을 검증해 계산하거나 `unknown`으로 둔다.
- **문서 숫자:** Q18은 재무 숫자 추출기가 아니다. 최소 Q25에서는 문서 숫자를 인용 문자열로만 취급하고, 숫자 claim의 권위는 기존 typed 수치 API로 제한한다.

실제 AI client는 항상 disabled, 실제 신규 지출0이다. `DeterministicSyntheticClient`와 fault stub은 `evaluation_kind=synthetic`, `model_id=null`로 표시한다. 역할명 변경·문서 지시·도구 결과로 허용표를 늘리지 않는다. URL·경로·명령·네트워크·주문·정책·승인 쓰기 query는 존재하지 않는다.

4. **예약·사용량·실패 의미**

예약은 **하나의 공유 budget repository 잠금 안에서** 전역 window·역할 cap·request cap·동시성·저장 여유를 모두 검사한 뒤 저장한다. 역할별 repository를 만들어 공통 한도를 우회하면 안 된다. client 호출은 예약 성공 후 잠금 밖에서 수행한다.

- `settled_usage + outstanding_reservations + proposed_reservation ≤ cap`을 호출·입출력 token·비용 각각 검사한다.
- `attempt_id=(request identity, sequence)`를 멱등키로 사용한다. 같은 payload는 기존 상태 반환, 다른 payload는 conflict다.
- 상태는 `reserved → dispatched → settled|unknown_charge`; 전송 전 취소만 `cancelled_before_dispatch`로 해제한다.
- 알려진 실제 사용량은 결과가 invalid/failed여도 정산한다. 불명 청구는 예약을 유지하고 해당 budget scope의 추가 호출을 차단한다. window 교체로 outstanding을 없애지 않는다.
- 확정 사용량이 예약보다 크면 실제 초과량을 기록하고 scope를 차단한다. 예약치로 잘라 저장하지 않는다.
- 정산도 멱등·직렬화한다. 상충하는 정산은 기존 기록을 덮어쓰지 않는다.
- `retry_policy={max_retries, retryable_reasons, backoff_ms}`, `escalation_policy={max_escalations, transitions}`를 필수로 둔다. 기본 합성 프로필은 각각 `0`, 빈 transition이다. timeout·unknown charge에 자동 재호출하거나 fallback 모델을 선택하지 않는다.

합성 비용 시험은 `synthetic_microcredit` 같은 명시 가상 단위를 사용한다. 가상 사용량을 실제 token 계측·청구 증거로 표시하지 않는다. 비용은 정수 단위, 금융값은 기존 정확 decimal 규칙을 사용하며 bool-as-int·음수·overflow·통화/단위 혼용을 거부한다.

| 결과 상태 | 판정 |
|---|---|
| `complete` | 요구 산출물·원천·인용·숫자·사용량 검사가 모두 충족 |
| `partial` | 구조적으로 유효한 일부 결과만 존재; 필수 자료 누락·상충·잘림 또는 사용량 미확정 명시 |
| `invalid` | schema·인용·숫자·단위·identity 불일치. 잘려 파싱할 수 없는 응답도 포함 |
| `blocked` | 권리·허용 도구·예산·기한·의존성 문제로 작업 또는 사용 거부 |
| `failed` | client/내부 실패·timeout으로 유효한 결과를 얻지 못함 |

`finish_reason`과 검사 사유는 상태와 별도로 보존한다. 원시 예외·응답을 실패 로그에 붙이지 않는다. AI의 자기 선언으로 `complete`를 정하지 않는다.

5. **검토·가설·Q24 연결**

`ResearchReview.verdict=accepted|changes_required|blocked`는 exact result hash에만 적용한다. 작성·검토 invocation identity를 구분하고 검토 시 원천·현재 권리·숫자를 다시 검사한다. stub 두 개의 일치는 합성 검토 흐름 평가이며 실제 두 모델의 독립 검증이 아니다.

가설의 저장된 assessment는 `proposed|supported|refuted|inconclusive`로 두고, **현재 사용 가능성은 조회 시 계산**한다. TTL, 원천 revision, 자료·정책·전략 버전, 권리 철회, supersession/retraction을 모두 검사한다. 원천 변경은 기존 가설의 자동 재검증 성공이 아니다. 대체·철회는 새 불변 기록으로 남기며 이전 기록을 삭제했다고 표현하지 않는다.

Q24 연결은 `ResearchRequest.review_subject_ref`에 기존 `TargetRef(kind=candidate)`를 넣는 것으로 충분하다. 정확한 후보·plan·입력 객체를 해소하고 기존 표시 API를 사용한다. AI 검토는 별도 부속 결과다.

**Q25에서는 `TargetRef.kind` 확장, 새 TargetPlan 생성, 후보 문구 변경, 전략 채택, 승인·예약·주문 동작을 연결하지 않는다.** 향후 연결은 별도 계약 변경이다.

6. **J03 주간·월간 보고**

`period_review`는 닫힌 중첩형으로 둔다:

`cadence=weekly|monthly, period_start, period_end, timezone_ref, reporting_policy_version, account_scope, base_currency, snapshot_refs, performance_refs, benchmark_refs, metrics, research_changes, strategy_changes, intervention_unknowns, unknowns, supersedes_result_ref?`.

보고 기간은 `[start,end)`로 고정하고, Q23의 평가점·흐름 포함 규칙과 대응하는 경계 입력을 명세한다. 다른 기간의 실험 결과를 현재 월 실적으로 재명명하지 않는다.

현재 `report` 권리를 생성·표시 시 재검사한다. 완전한 원천이 없으면 지표별 unknown을 출력한다. 특히 기존 Q22의 미확인 주문·체결·손익 범위를 그대로 유지하고, 개입 기록 부재를 “개입0”으로 바꾸지 않는다. AI 설명 실패에도 결정론적 수치는 보존한다. 외부 전달·스케줄 생성은 없다.

7. **상한·직렬화·소유권**

합성 프로필의 구체 상한 제안은 다음과 같다. root가 실행 전 고정하고 요청에는 실제 값을 명시한다.

- canonical 객체당 **65,536 bytes**; 해소 원천 합계 **8MiB**.
- refs 128, claims 32, citations 64, hypotheses 8, checks/reasons 각각64; 기존 원천별 더 작은 상한 유지.
- 자유 문자열당 UTF-8 2KiB; 인용은 Q18 원문 상한과 전체 canonical 한도 동시 적용.
- 호출당 input/output token 8,192/2,048; 요청 총합 32,768/8,192; client 호출4·도구 조회16.
- 호출 deadline 10초, 요청 deadline 60초, 동시 실행2, 대기 queue0. 누락은 무제한이 아니라 거부다.
- 메모리 저장 전체128 records·8MiB, 자동 eviction 없음. 결과·감사·정산 저장 여유도 호출 전에 확보한다.

직접 생성자, parser, application 진입점, repository append/get에서 동일 검사를 적용한다. 객체 내부를 변조한 입력도 canonical 재구성으로 거부한다. 중복 key·알 수 없는 enum/field·환경 불일치·과대 collection·깊이·수치 범위를 검사하고 자동 잘라내기는 하지 않는다.

저장소는 canonical bytes를 보존하고 재파싱하여 반환한다. `RLock`은 단일 프로세스의 동시성만 보장한다. 재시작 후 예약·멱등성·철회 이력의 내구성이나 OS 메모리/CPU 격리를 주장하지 않는다. 실제 client 활성화에는 별도 영속 저장·격리 계약이 필요하다.

소유 파일은 다음으로 제한한다.

- `src/quantharbor/{domain,ports,application}/investment_ai.py`
- `src/quantharbor/adapters/synthetic_investment_ai.py`
- 기존 `domain/serialization.py`의 **추가 등록만**
- `tests/product/test_investment_ai*.py`, 합성 fixture
- `docs/development/investment-ai.md`

root가 `docs/contracts/ai-local-v1.md`, 작업 카드·상태·큐를 통합한다. 기존 금융 모듈 의미 변경, 새 dependency, 범용 agent framework는 필요 없다.

8. **실행 전 고정할 golden·완료 경계**

root가 평가 manifest에 사례·입력 버전·기대 상태/사유·기대 수치·예산 잔액·허용 query를 먼저 고정해야 한다.

| 사례 | 기대값/거부점 |
|---|---|
| KR/EN 동명이름·유사 ticker | entity/venue/version이 다르면 자동 병합 금지 |
| KRW/USD, 원/천원, `%`/ratio | 명시 단위 없이 변환 금지; `0.21=21%` |
| cutoff 이후 정정·DST·naive time | 미래 근거 배제; 모호한 시각 거부 |
| 문서 누락·상충·철회 | partial/blocked 및 정확한 원인; 빈 성공 금지 |
| 원문 prompt injection·미허용 도구 | 권한 변화0, query 실행0 |
| Q23 원천 golden | 100→110→입금50→176: TWR `0.21`, 손익 `26` |
| 독립 수치 golden | 부지수 1/1.2/0.9/1.08: MDD `0.25`; 잘못된 숫자는 invalid |
| 예산 경합 | cap100에서 예약70 후 예약40 거부; 실제50 정산 시20 해제 |
| 불명 청구·중복 요청 | 예약70 유지; 재호출·window reset 우회 금지 |
| 가설 만료·정책 변경·권리 철회 | 과거 accepted review가 있어도 재사용 차단 |
| schema/인용 변조·잘림·timeout | 상태·사유 구분, 발생 사용량은 별도 정산 |
| Q24 후보·보고 | 후보 hash 불변, 주문 효과0; 정확 기간·unknown 유지 |

동일 거부 사례를 직접 생성·JSON parser·repository 경계에 각각 적용하고, 숫자 기대값은 구현 함수로 역산하지 않는다. H01~08/J03 완료는 **이 고정 합성 계약·접근 거부·원천 대조·예산 경합·보고 범위의 검증**까지다. 실제 모델 품질·실제 청구·운영 내구성·전략 수익성은 포함하지 않는다.

남은 결정은 root의 상한 프로필 확정, 고정 selector/reason enum, 주간·월간 시간대와 평가 manifest다. 이번 자문은 공개 파일 읽기만 수행했으며 수정·테스트·네트워크·private 접근·Docker·Git·subagent 실행은 없었다.