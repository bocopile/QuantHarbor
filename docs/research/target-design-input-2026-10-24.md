# Q24 설계 자문 반환

정적 자문. 아래 제안은 root의 target-local-v1에서 채택한 범위에 적용한다. 시험 실행 증거가 아니다.

Q24는 **기존 읽기 모델을 검증해 소비하고, 별도 합성 근거로 목표안과 불변 후보를 만드는 범위**가 적절합니다. 추가 계약 `target-local-v1`에 계획·후보·합산 계산을 정의하고, 승인 생성은 Q26, 예약·admission·dispatch는 Q27에 남기는 안을 권고합니다.

확인된 사실은 다음과 같습니다.

- [TARGET-local 카드](/Users/okestro/projects/QuantHarbor/docs/tasks/TARGET-local.md)는 합성 후보 생성과 미확인 차단을 요구합니다. [최신 상태](/Users/okestro/projects/QuantHarbor/docs/status.md:571)에 Q23 로컬 독립 판정 통과가 기록되어 있습니다. 이번 검토에서 이를 재실행하지 않았습니다.
- [Q21 PortfolioSnapshot](/Users/okestro/projects/QuantHarbor/src/quantharbor/domain/valuation.py:892)은 빈 `open_order_refs`와 `open_orders_status="unknown"`을 강제합니다. 현금 평가의 `available_cash/reserved_cash/broker_buy_capacity=None`도 기존 의미입니다.
- [Q19 bridge](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/valuation.py:213)는 정상 조회에도 매핑·수치 의미·결제/예약 포함 관계·원천 기준시각 미확인을 남깁니다. 숫자 일치나 `complete`로 실제 가용금을 확정할 수 없습니다.
- [Q23 비교 결과](/Users/okestro/projects/QuantHarbor/docs/research/strategy-comparison-synthetic-2026-10-24.md)는 합성 연구 결과입니다. 현재 [plan_orders](/Users/okestro/projects/QuantHarbor/src/quantharbor/research/strategies.py:25)는 두 종목에 각각 NAV 45%를 적용하는 고정 연구 함수이므로 일반 목표 생성기로 직접 사용하면 안 됩니다.
- [execution-v1](/Users/okestro/projects/QuantHarbor/docs/contracts/execution-v1.md:64)은 계좌 전체 위험 검사와 `A=min(L-H-F, B-U-D)`를 이미 정의합니다. [serialization-v1](/Users/okestro/projects/QuantHarbor/docs/contracts/serialization-v1.md:25)은 사용자에게 보이는 근거·위험·비용 표현까지 후보 해시에 포함하도록 요구합니다.

다음은 root가 확정할 **추가 계약 제안**입니다.

1. **입력과 결과를 닫힌 타입으로 제한합니다.**

공통 참조는 `TargetRef(kind, id, version, canonicalization_version, sha256)`로 둡니다. `kind`는 등록된 타입의 고정 enum이며, 참조만으로 검증을 통과시키지 않고 실제 주입 객체를 해소·재검증합니다. 기존 Q21 `DataRef`의 enum을 확장하지 않습니다.

| 타입 | 필수 필드와 의미 |
|---|---|
| `TargetRequest` | `schema_version, environment, account_ref, request_id, as_of, knowledge_cutoff, evaluated_at, authority_generation, expires_at, mode, scope, omission_rule, target_basis, targets, snapshot_ref, strategy_ref, policy_ref, research_refs, predecessor_plan_ref` |
| `SyntheticTargetPolicy` | 식별·계좌·유효기간·합성 결정 참조, 허용 종목/시장/통화, 통화별 자금 한도·현금 하한, 종목/업종/시장/통화 집중도, 주문당·일간 금액/수량 한도, 거래량 참여 한도, 손실/낙폭 한도와 집계창, 가격/FX/계좌근거 최대 나이, 후보 TTL·허용 가격 편차·목표 반올림 오차 |
| `SyntheticTargetFacts` | 아래의 원천·시간·계좌 의미가 완결된 합성 사실 묶음. Q21/Q19 객체를 수정하는 기능 없음 |
| `TargetPlan` | 요청·입력 참조, 정규화한 scope와 목표, 현재/목표/차이 수량, 반올림 잔차, 결정론적 주문조건 목록, 통화별 합산 부담, 계좌 전체 제약 계산, `status=eligible|blocked`, 고정 사유 코드, 이전 계획 참조 |
| `OrderCandidate` | 후보 ID/version, 정확한 plan 참조·주문조건 index, 계좌/환경/generation, 종목·매핑·venue, side·수량·단위, 주문유형·가격조건·유효조건, 비용 상한·통화별 최대 부담, 제출기간, 정책/자료/권리/capability/calendar 참조, 사용자 표시 내용 |
| `TargetBuildResult` | 요청 참조, 계획 참조, 후보 참조 목록, `outcome=eligible|blocked`, `effect=orders|no_change|none`, 구조화한 실패 사유 |

정책값 누락은 무제한이 아닙니다. 타입 내부 기본값으로 한도를 채우지 않습니다. 필수 입력이 없으면 결과는 `blocked`이며 후보 목록은 비웁니다. 유효하고 변화가 없는 목표만 `eligible/no_change`입니다.

최초 구현은 `environment="synthetic"`만 허용합니다. 실제 paper/live 요청에는 명시적 차단 결과를 반환하며, 합성 정책에 `approved`나 실제 사용자 채택을 뜻하는 상태를 만들지 않습니다.

2. **합성 사실의 출처 계약을 별도로 둡니다.**

`SyntheticTargetFacts`의 공통 필드는 다음으로 고정합니다.

```text
schema_version, environment="synthetic", account_ref,
source_id, source_revision, source_snapshot_id, semantics_version,
mapping_version, requested_scope, covered_scope, missing_scope,
status, temporal_consistency,
source_as_of, aligned_as_of, observed_at, ingested_at,
knowledge_cutoff, ledger_cursor, projection_ref, statement_ref,
cash_capacity_rows, obligations, post_source_cash_changes,
sellability_rows, broker_open_orders, local_active_intents,
classifications, daily_usage_event_refs, loss_performance_ref,
capabilities, cost_rules
```

이 묶음은 실제 증권사 사실의 인증 수단이 아니라 **독립적으로 정의한 합성 원천 사실**입니다. Q19 관측을 변환하는 생성자나 adapter는 제공하지 않습니다.

- `statement_ref`는 Q21의 독립 `SyntheticAccountStatement`를 가리킵니다. 계좌 전체 보유·경제적 현금 대사가 일치해야 하며, 주문 상태와 가용금은 별도 사실로 검증합니다.
- 현금 행은 `currency, amount, capacity_scope, capacity_basis, reflected_obligation_ids`를 갖습니다. 최초 `capacity_scope`는 `account_currency`, `capacity_basis`는 신용·자동환전을 제외한 합성 현금 기준으로 고정합니다. 종목·가격별 capacity만 있으면 계좌 공통 자금으로 합산하지 않고 `capacity_scope_unsupported`입니다.
- 의무 행은 `obligation_id, source_ref, currency, amount, kind, effective_at, outstanding_or_realized, reflected_in_L, reflected_in_B`를 갖습니다. 포함 관계는 합성 의미 버전과 원천 항목으로 대조합니다. `H/U/D` 합계만 외부에서 받지 않습니다.
- `post_source_cash_changes`는 원천 기준시각 이후 정렬 시각까지의 완전한 변동 범위·사건 참조를 제공합니다. 미반영 차감만 `D`에 반영하며 미반영 증액은 사용하지 않습니다. 같은 의무 부분을 `U`와 `D`에 중복 분류하지 않습니다.
- 매도가능 행은 종목·매핑·단위, 결제/매도가능 수량, broker 매도가능 수량, 예약·미반영 매도 의무 참조를 갖습니다. Q21의 보유 수량을 곧바로 매도가능 수량으로 사용하지 않습니다.
- broker 미체결과 로컬 활성 의도는 각각 범위·원천 snapshot·완전성을 검증합니다. 완전한 빈 목록만 “없음”입니다. 동일 종목 활성 의도와 충돌하면 차단하고, 계좌 의무에 영향을 주는 상태불명은 계좌 수준에서 차단합니다.
- 업종은 Q16 상품 분류에서 추정하지 않습니다. `position_key, sector_id, effective_from/to, known_at, source_ref`의 명시 합성 분류가 필요합니다.
- 일간 사용량은 집계창에 속하는 사건 참조에서 계산합니다. 손실·낙폭은 같은 계좌·정해진 기간·현재 평가점에 결속된 검증된 Q23 성과 입력을 사용합니다. 다른 실험의 수익률을 현재 계좌 위험으로 복사하지 않습니다.

시간은 최소 `source_as_of ≤ aligned_as_of=as_of`, `source_as_of ≤ observed_at ≤ ingested_at ≤ knowledge_cutoff ≤ evaluated_at`을 만족해야 합니다. 원천 이후 변동, snapshot 간 일관성, scope 중 하나라도 불완전하면 가용금은 unknown이며 후보는 차단합니다.

Q21의 `None/unknown`은 그대로 남깁니다. 합성 계산 결과는 `TargetPlan.cash_calculation`에만 저장하고, 출처도 “합성 가용자금”으로 표시합니다.

3. **기존 API를 소비하되 현재 소비 시점에 다시 검증합니다.**

- Q16 `Catalog.resolve(...)`로 종목·매핑·효력·지식시각을 확인합니다. 초기 상품은 KR/US 주식·일반 ETF, 현금계좌·정규장으로 제한합니다.
- 달력은 `ExplicitTimezone.lookup_calendar(...)`를 사용합니다. raw `MarketCalendar.lookup`만으로 시간대 결속 검증을 대체하지 않습니다.
- Q21 `value_projection(...)`와 `reconcile(...)`를 이용해 snapshot의 평가·원장·statement 결속을 확인합니다.
- Q17 `select_view(...)`와 기존 저장 증빙 검증을 사용해 **현재 `evaluated_at`의** research 권리를 재검사합니다. 저장·표시에는 각각 store/report 권리도 확인합니다. 과거 snapshot 생성 당시 허용됐다는 사실만으로 현재 소비를 허용하지 않습니다.
- Q23 결과는 설명·전략 근거 참조로 소비합니다. 원천 검증이 필요한 성과는 `build_bound_performance(...)` 등 검증 API를 사용하며 순수 산식 함수 결과만으로 증명하지 않습니다.

지원하지 않는 정정·restated 입력은 최초 버전에서 명시적으로 차단해도 됩니다. 기존 읽기 모델의 의미를 변경할 필요는 없습니다.

4. **목표 생성은 한 번의 결정론적 제안과 제약 검사로 충분합니다.**

`scope`는 시장·현금 통화와 정확한 종목 키 목록을 포함합니다. 시장 이름만으로 청산 대상을 확장하지 않습니다.

- `full`: 명시 scope 안에서 생략을 허용하려면 `omission_rule="zero"`가 필요합니다. 그렇지 않으면 누락 오류입니다. scope 밖 보유는 유지합니다.
- `partial`: `omission_rule="keep"`만 허용합니다. 명시하지 않은 보유를 유지합니다.
- 두 경우 모두 계좌 전체 현금·노출·손실·일간 사용량을 검사합니다. 범위를 좁혀 기존 위반을 숨길 수 없습니다.
- 수량 목표는 정확한 단위·lot 배수를 요구합니다. 비중 목표는 완전한 양수 NAV와 검증된 FX로 절대 계좌 비중을 수량으로 변환하고 lot 내림합니다. scope 안의 비중만 다시 100%로 정규화하지 않습니다.
- 비중 목표의 lot 내림 잔차를 보존하고 정책의 허용 오차를 검사합니다. 현재 보유와 목표의 차이가 거래 lot에 맞지 않으면 차단합니다.
- cash 목표는 현금 제약입니다. 환전이나 자금 이동 후보를 만들지 않습니다.
- 중복·상충 목표를 거부합니다. 기존 의도를 취소하거나 반대 방향 주문으로 상쇄하지 않습니다.

제안 수량을 줄이거나 종목 일부를 버려 조용히 성공시키지 않습니다. 선택한 제안이 제약을 만족하지 못하면 `proposal_infeasible`을 반환합니다. 이는 모든 가능한 포트폴리오의 불가능성을 증명했다는 뜻은 아닙니다.

5. **후보 집합 전체의 현금과 최악 노출을 계산합니다.**

기존 산식을 그대로 사용합니다.

\[
A_c=\min(L_c-H_c-F_c,\ B_c-U_c-D_c)
\]

각 후보의 최대 현금 부담은 매수 원금과 검증된 비용 상한입니다. 매도 비용도 결제 전 현금 의무가 되는 합성 규칙이라면 별도로 포함합니다.

\[
P_c=\sum_i R_{i,c},\qquad P_c\le A_c
\]

정렬키는 `(instrument_id, venue_id, side)`로 고정하고 후보별 누적 부담·잔여 계획 여력을 남깁니다. 각 후보가 동일한 `A`를 독립적으로 재사용하지 않습니다. `P`는 계획상 부담이며 실제 예약이 아닙니다.

매도대금은 이 계산에 더하지 않습니다. 종목별 매도 합계는 execution-v1의 결제/예약 포함 매도가능 상한을 만족해야 합니다. 매수 예상 수량으로 매도 여력을 만들지 않습니다.

노출 검사는 매수만 체결되고 매도가 체결되지 않는 경우도 포함합니다. 각 보유의 가능한 수량 범위를 `현재−매도합계`부터 `현재+매수합계`로 두고, 기존 활성 주문의 최악 영향까지 합산합니다. 비중 분모도 비용과 불리한 체결 영향을 반영한 보수적 NAV 하한을 사용해야 합니다. 이 하한이나 노출 평가 기준을 확정할 수 없으면 차단합니다. 기존 초과 상태를 미래 매도 완료 가정으로 정상화하지 않습니다.

6. **거래조건·비용·기한을 닫힌 규칙으로 결속합니다.**

`SyntheticOrderCapability`는 계좌/종목/venue/통화, 효력·지식시각, catalog/calendar 참조, `order_kind`, `time_in_force`, `tick`, `lot`, 최소/최대 수량·금액, 정규장 조건, 부분체결 의미를 포함합니다.

최초 주문유형은 상한을 검증할 수 있는 합성 지정가로 제한하는 것이 적절합니다. 명시 가격 한계는 tick에 정확히 맞아야 합니다. 제안 가격을 reference와 허용 편차에서 계산한다면 매수는 상한을 넓히지 않는 tick 내림, 매도는 하한을 낮추지 않는 tick 올림을 사용하고 조정 내역을 표시합니다.

최소 비용 계약은 합성 전용 `fixed_plus_per_share`로 충분합니다.

```text
rule_id/version, account/market/currency/side, valid_from/to,
fee_fixed, fee_per_share, tax_fixed, tax_per_share,
money_quantum, rounding="ceiling",
charging_basis="whole_order_aggregate"
```

수수료·세금 각각을 quantum 올림한 뒤 합산합니다. 부분체결 횟수와 무관하게 전체 주문 상한이라는 합성 의미를 고정합니다. 실제 broker 비용이나 Q23 연구 비용률을 이 규칙으로 자동 채택하지 않습니다. 유한 상한을 계산할 수 없는 비용 체계는 차단합니다.

제출 가능 기간은 요청 만료, 정책·capability·비용 규칙·권리 유효기간, 자료 freshness, 정규 세션의 교집합이며 끝은 제외합니다. 기간이 비면 차단합니다. 분석 주기 15분을 승인 TTL로 사용하지 않습니다.

7. **해시와 후속 단계의 연결은 순환 없이 유지합니다.**

`TargetPlan`에는 후보 해시를 넣지 않고 주문조건 목록을 넣습니다. 각 후보는 완성된 plan의 정확한 참조와 항목 index를 가리킵니다. 마지막 `TargetBuildResult`가 후보 참조를 나열합니다.

후보의 `display_terms`는 다음을 포함합니다.

```text
render_version, locale="ko-KR", account_label, instrument_label,
rationale, risks, cost_explanation, expiry_explanation,
synthetic_notice
```

수량·지정가·최대 부담 등은 후보의 금융 필드에서 표시합니다. 사용자에게 새로 보이는 의미 있는 문구는 모두 exact candidate hash에 포함합니다. 기술 provenance는 별도 JSON 표현으로 제공합니다.

기본 문장은 다음 정도면 충분합니다.

> 합성 주문 후보 · A 주식 3주 매수 · 지정가 100원 · 비용 최대 2원 · 최대 필요자금 302원 · 정규장 내 ○시까지 유효. 승인 전이며 주문은 전송되지 않았습니다.

기존 canonical wrapper·hash prefix·64KiB 제한을 유지하고 등록형과 중첩형만 추가합니다. 직접 생성·복원에서도 수치·합계·참조·표시 결속을 검사합니다. hash 자체는 payload 밖에 둡니다.

Q26은 `CandidateRef + render_version + environment/account/authority_generation`에 합성 승인을 결속합니다. Q27은 최신 근거로 별도 `RiskDecision`을 만들고 admission에서 승인 소비·예약을 처리합니다. Q24의 `eligible`을 제출 허가나 최신 위험 판정으로 재사용하지 않습니다.

실패는 `TargetFailure(code, subject_ref, required_input, observed_status)`로 반환합니다. 코드는 최소 다음 범위를 닫힌 enum으로 정의하면 됩니다.

```text
environment_blocked, policy_missing, source_incomplete,
source_semantics_unknown, temporal_mismatch, reconciliation_incomplete,
nav_unknown, mapping_unknown, rights_denied, stale_input,
calendar_ineligible, capability_unknown, cost_bound_unknown,
active_intent_conflict, open_orders_unknown,
ambiguous_omission, lot_violation, tick_violation,
cash_shortfall, sellability_unknown, exposure_limit,
daily_limit, loss_limit, proposal_infeasible, expired
```

알 수 없는 schema·필드·위조 hash·숫자 문법 오류는 `ContractError`로 거부합니다. 의미상 미확인·실현 불가능은 명시 `blocked`로 반환합니다. 일반 `proof=true`, 자유형 실행 action, `allow_unknown`은 두지 않습니다.

독립 계산 golden은 구현과 별개로 다음을 고정할 수 있습니다. **이번 검토에서는 실행하지 않았습니다.**

| 사례 | 독립 기대값 |
|---|---|
| `L=1000,H=100,F=100,B=950,U=50,D=20` | `A=min(800,880)=800` |
| 위 계좌에서 매수 부담 `3×100+2=302`, `5×100+2=502` | 합계 `804`; 각각 통과하더라도 전체 `cash_shortfall` |
| 두 번째 매수를 4주로 명시한 새 제안 | 합계 `704`, 계획 잔여 `96`; 원래 제안을 자동 축소하지 않음 |
| `A=200`, 예상 매도대금 `1000`, 매수 부담 `300` | `cash_shortfall`; 예상 매도대금 미사용 |
| 보유 A10/B7, 목표 A6 | partial은 B7 유지; full의 명시 scope `{A,B}`와 omitted zero는 B 목표0; 생략 규칙 없으면 차단 |
| NAV1000, 비중0.25, 가격60, lot2 | 목표4주, 평가금액240, 비중 잔차0.01 |
| 종목 노출450, 한도500, 매수100·매도100 제안 | 매수만 체결하면550이므로 차단 |
| 수량3, 수수료 `0.5+0.125×3`, 세금 `0+0.075×3`, quantum0.05 | 수수료 상한0.90, 세금 상한0.25, 합계1.15 |
| Q21의 unknown, Q19 complete 빈 조회만 제공 | 후보0, 가용금/미체결 미확인 차단 |
| 수량·비용 상한·만료·generation·표시 위험 문구 변경 | 새 candidate hash; 기존 승인 재사용 불가 |
| 세션 종료시각과 evaluated_at이 동일 | 끝 제외 규칙으로 차단 |

소유권은 root가 `docs/contracts/target-local-v1.md`, 결정 문서, TARGET 카드·상태·증거를 통합하고, 단독 구현자가 신규 `domain/target.py`, `application/target.py`, `ports/target.py`, `adapters/synthetic_target.py`와 serializer의 additive 등록을 맡는 구성이 적절합니다. 필요 저장소는 한도 있는 append/get 메모리 구현으로 충분합니다. 기존 원장·평가·연구 의미와 frozen 계약·migration을 유지하며 새 패키지·optimizer·DB 상태기계는 추가하지 않습니다.

미결정 사항은 실제 PG01 자금·위험값, PG03 전략 채택, broker의 실제 capacity·미체결·결제·비용·주문 capability, 실제 자료 권리입니다. 이들은 합성 fixture 성공으로 해소되지 않습니다. 이번 반환은 공개 파일의 정적 설계 자문이며, 파일 수정·테스트·네트워크·비공개 접근·Docker·Git·하위 위임은 수행하지 않았습니다.