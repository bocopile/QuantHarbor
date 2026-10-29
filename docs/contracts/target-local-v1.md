# 합성 목표안·주문 후보 계약 v1 — Q24

상태: root 구현 기준. EXEC-DEC-001의 G05~07 합성 범위이며 Q23 로컬 판정 후 적용한다. frozen execution/data/operations/serialization-v1을 보존하는 추가 계약이다. [설계 자문](../research/target-design-input-2026-10-24.md)의 1~7번 구체 필드·산식·실패 처리·golden을 아래 보완과 함께 채택한다. 자문을 실제 계좌 권한/정책으로 승격하지 않는다.

## 범위와 경계

기존 Q21의 available/reserved/broker capacity=None와 open_orders_status=unknown을 바꾸지 않는다. Q19 complete를 확인된 가용금/주문 상태로 변환하는 adapter를 만들지 않는다. 별도 명시 합성 원천 사실만 golden 후보를 지원한다. synthetic만 허용, paper/live는 후보0 차단이다. 실제 PG01·PG03·SG01/02는 미완료다.

순수 숫자 helper와 원천 결속 builder를 구별한다. 실제 builder는 Q20 projection/events, Q21 snapshot/statement와 Q17 자료를 재검증하고 전체계좌 대사·현재 research/store 권리·신선도·Q16 mapping/ExplicitTimezone/calendar를 확인한다. display 시 현재 report 권리를 검사한다. 과거 snapshot의 목적과 권리로 현재 소비를 대체하지 않는다. Q23 원천 결속 성과는 같은 계좌·집계기간·현재평가점의 손실/낙폭 근거이며 연구 전략 결과를 실제 사용자 채택으로 해석하지 않는다. 실제 객체를 받지 않은 hash/proof bool로 원천 검증을 통과시키지 않는다.

## 타입·한도·책임

TargetRef, TargetRequest, SyntheticTargetPolicy, SyntheticTargetFacts, TargetPlan, OrderCandidate, TargetBuildResult와 닫힌 중첩 타입을 추가한다. 공통 ref는 kind/id/version/canonicalization_version/sha256와 실제 객체 해소를 요구한다. 자문 필수 필드의 의미를 삭제하지 않는다. 한도·TTL·손실/낙폭·신선도·가격편차·허용반올림오차는 명시값 필수이며 미설정은 blocked다. 정책의 실제 승인 상태는 제공하지 않는다.

Collection 각각128 이하, 해소한 입력 합계8MiB 이하, 기존 canonical payload64KiB 이하. deterministic order/unique key/정확 수치·시각/환경·계좌 결속을 검사한다. 순환 참조 없이 plan 주문조건 → candidate의 plan ref/index → build result refs다. ID는 hash에서 결정하며 외부 hash 필드를 payload에 다시 포함하지 않는다. 메모리 저장128개 append/get, 동일ID/hash 멱등·상충 거부, 실제 predecessor 조회·동일계좌/환경/범위 확인, 과거 불변. 메모리 저장은 운영 내구성이 아니다.

## 합성 사실과 가용금

설계 자문의 source/semantics/mapping/scope/status/temporal/source_as_of/aligned_as_of/observation/ingestion/cutoff/cursor/projection/statement 필드를 요구한다. 현재/원천시점 사이 변동 범위가 완전해야 한다. settled ledger cash L과 개별 obligation/source event의 포함 관계에서 H/U/D를 계산하며 외부 합계만 신뢰하지 않는다. 같은 의무의 outstanding/realized 부분을 중복 차감하지 않는다. 미반영 증액/예상 매도대금/타통화를 가용금에 넣지 않는다.

A=min(L-H-F,B-U-D); 음수는 숨기지 않는다. B는 synthetic account_currency cash-only/no-auto-FX capacity만 지원한다. 종목별capacity의 일반화는 차단한다. 매도가능 수량도 독립 정산/예약/브로커사실의 최소 상한으로 계산하고 현재보유와 구별한다. 원장·보유·현금 대사 matched는 주문/가용금 matched가 아니다.

미체결·로컬의도 범위/시점 완전성을 요구한다. 동일종목 활성 충돌은 차단, 계좌 의무 상태불명도 신규 후보를 차단한다. 초기 버전에서 기존 활성의도의 최악 영향을 확정할 수 없으면 전체를 보수적으로 차단해도 되며 무시/상계는 금지한다. 업종·일간 사용·손실/낙폭 근거도 명시 사건/분류/성과에서 결속한다.

## 목표와 합산 제약

full은 명시 종목scope와 omitted=zero를 요구해 생략0을 적용하며 scope 밖은 유지한다. partial은 omitted=keep, 생략보유 유지다. 전체계좌 제약은 두 경우 모두 적용한다. duplicate/상충/음수/미지원상품은 거부. quantity는 lot 배수, weight는 완전 양수NAV·현재FX 기반 절대계좌비중으로 lot 내림, 잔차/허용오차를 기록한다. scope 내 재정규화 없음. cash목표는 현금제약이며 환전/이동을 만들지 않는다.

가용금·현금하한·자금한도·종목/업종/시장/통화 집중도·주문당/일간 금액과 수량·거래량참여·손실/낙폭을 모두 검사한다. P=sum(후보별 최대부담), P<=A를 통화별 검사하며 정렬된 누적부담/남은계획여력 기록. 이것은 계획상 부담이며 예약이 아니다. 불가 제안의 자동축소·일부삭제·반대주문상계·자동취소 금지. 후보 한개라도 필수제약 불충족이면 전체 결과blocked/candidates빈목록. 유효한 차이0만 eligible/no_change다.

노출은 현재보유와 기존/제안매수만 채워진 경우, 매도만 채워진 경우의 범위를 포함한다. 미래매도를 전제한 현재한도위반 해소 금지. 고정가격 평가축에서 최악비용과 불리한체결 손실을 차감한 보수적NAV하한을 분모로 사용한다. 하한<=0/미확인은 차단. 가격변화 예측을 보증하지 않으며 Q27의 최신 위험재검사를 대체하지 않는다.

## 거래조건·표시·후속 계약

합성 KR/US 현금 정규장 주식/일반ETF, 지정가·명시TIF·capability/tick/lot/min/max/notional/volume, 가격편차·자료권리/정규세션을 검사한다. 신용/공매도/레버리지/인버스/자동FX 없음. 고정비+주당비용을 whole_order_aggregate 상한으로 정의하고 fee/tax 각각 quantum ceiling 후합계, 부분체결 횟수와 무관한 합성조건을 명시한다. Q23 비율비용을 실제규칙으로 복사하지 않는다.

유효기간은 request/policy/capability/cost/data freshness/권리/calendar의 교집합, 끝 제외다. 비중 계산 reference와 주문한계의 관계·편차를 검증하며 가격계산시 매수상한 tick내림/매도하한 tick올림은 한계를 완화하지 않는다. 비용과 매수최악원금·매도최저대금/비용을 구별한다. 미래 매도대금으로 새 매수 여력을 만들지 않는다.

candidate 금융조건·계좌/환경/generation·plan/index·policy/inputs·rationale/risks/cost/expiry/synthetic 안내와 render_version은 exact hash에 결속한다. 표시의 숫자는 후보 필드에서 유도하고 의미문구 변경도 새hash다. 기본 text는 간결한 한국어 금융조건, 기술출처는 JSON. 실제 보이는 금융조건/위험문구를 hash 밖에서 추가하지 않는다.

Q24 eligible은 후보생성 적격이며 승인/실행권한이 아니다. Q26은 단일candidatehash에 승인, Q27은 최신 입력·위험·세대·세션 재검사 후 원자적 승인소비/예약을 담당한다. Q24에는 승인상태·submit/cancel/credential/network path를 추가하지 않는다.

## 검증과 소유

설계 자문 golden11건을 독립 기대값으로 사용한다. 합산804>800 차단/704통과, 미래매도대금 불사용, full/partial 차이, NAV1000/0.25/60/lot2→4주/잔차0.01, 한쪽체결노출550>500, 비용0.90+0.25=1.15 등을 실제 builder 또는 해당 산식의 독립시험에서 검증한다. raw 숫자helper 통과만으로 source-bound builder를 완료하지 않는다. 시점/권리/범위/unknown/변조/정정/한도/저장/사용자표시 binding 실패도 시험한다.

단독 구현자 소유: domain/target.py, application/target.py, ports/target.py, adapters/synthetic_target.py, additive domain/serialization.py, tests/product/synthetic_target.py·test_target.py·test_target_constraints.py·test_target_canonical.py, docs/development/target.md. 필요시 동일 target 이름의 테스트 분할은 허용하되 최종 소유목록을 반환한다. 기존 원장/시장/평가/보고/연구 의미·frozen 계약·migration·외부설정은 보존한다. root는 계약·결정·카드·상태·증거·큐를 통합한다.

## 독립 검토 T1~T6 보완

- T1: 현존 원장 미결제 지급채무·미완료 매수 결제/확정 비용 의무와 합성 obligation의 원천 ID/revision/잔여금액/정산상태를 대조한다. H가 빈 목록/적은 금액으로 줄어들면 eligible 금지. 원장의 양수매도채권으로 음수매수채무를 상계해 숨기지 않는다. 부분이행·중복·정산 후 의무는 L/H/U/D의 중복차감/누락 없이 결속하고 미지원 의미는 blocked다.
- T2: direct constructor/canonical parse/repository에서도 request의 명시 가격한계·cash targets와 plan의 주문가격/현금하한/잔여를 다시 결속한다. 새hash를 붙인다고 모순된 계산이 유효해지지 않는다. 기준정책 하한과 cash목표 중 큰값을 적용하며 매수상한/매도하한을 완화하지 않는다.
- T3: 시계열은 종목 중복이 아니다. Q21의 실제 선정된 가격 ref와 최신 적격 원본 봉을 해소하고 과거/미래의 다른 봉을 해당 가격으로 오인하지 않는다. 단순 종목당1봉 제약으로 정상 이력을 거부하지 않는다.
- T4: 계좌전체의 미변경 타시장 보유는 평가/권리/시점/분류 근거로 검사하되 현재 거래세션·주문 capability는 실제 해당 주문에만 요구한다. KR/US 정규장 동시 개장을 요구하지 않는다. 별도 snapshot/가격 freshness 정책을 만족해야 하며 장외 자료가 자동으로 신선한 것은 아니다.
- T5: 후보 집합 유효기간에는 계좌 전체 NAV·노출·위험·가용금 계산이 의존한 모든 가격/FX/원천 사실/정책/권리의 신선도와 만료를 반영한다. 후보 자신의 종목 자료만으로 끝을 정하지 않는다. 원천시각 등 freshness 기준을 Q17/Q21과 동일하게 계산한다.
- T6: 현재 보유·목표scope에서 빠진 당일 완전매도 종목의 일간 사용량도 삭제하지 않는다. 해당 사건시점의 검증된 종목/통화/환산 근거를 독립 해소한다. 현재 가격/다른 종목 FX/불명확 hash로 과거 사용량을 대체하지 않는다. 근거 완결 정상사례는 후속 후보를 허용할 수 있고 미완결은 차단한다.

이 보완은 원래 요구한 완전성·계좌전체 제약·가격/현금/유효기간 결속의 구현 기준이다. 고정 비교 spec이나 실제 운영 정책값은 바꾸지 않는다.

## T5b/T6b 과거 증거 경계 보완

과거 risk_points/daily_usage_inputs의 현재 grant는 원본 source/dataset/version뿐 아니라 원본 rights_ref에도 일치해야 한다. 원본 historical grant로 재검증한다고 현재 참조 불일치를 지우지 않는다. 같은 rights_ref 갱신과 정상 research/store권리는 유지한다. 과거 일간사용 환산에 채택되는 각 FX proof는 Q17 quality·missing scope·usable·권리·시점이 모두 유효해야 한다. 부분 자료의 더 최신 FX로 완전한 근거를 대체하거나 일간 사용량을 줄이지 않는다. 필수 proof 미완결은 명시 차단이며 숫자존재/held_reasons 빈값만 신뢰하지 않는다.
