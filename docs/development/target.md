# Q24 합성 목표안·불변 주문 후보

작업 ID Q24, 입력 계약 target-local-v1/TARGET-DEC-001 및 연결된 설계 자문. frozen data/execution/serialization/operations-v1의 의미를 유지하는 추가 구현이다. 선행 Q23 로컬 완료를 입력으로 삼았으며 root의 독립 검토·validator 판정은 별도다. 이 문서만 구현자가 소유한 인계 기록이며 status·계약·큐·evidence는 수정하지 않는다.

`build_target(request, inputs, repository)`는 `TargetArtifacts(plan, candidates, result)`를 반환한다. `eligible`은 후보 생성 적격이며 승인 상태가 아니다. 유효한 차이0만 `eligible/no_change`, 의미 미확인·제약 위반은 구조화한 `TargetFailure`와 `blocked/none`, 후보0이다. 알 수 없는 타입·필드·숫자·위조 hash·해소할 수 없는 참조는 `ContractError`다. 요청한 제안을 자동 축소하거나 일부 주문만 남기지 않는다.

입력은 `TargetRequest`, 필수값을 모두 명시한 `SyntheticTargetPolicy`, 독립 합성 사실 `SyntheticTargetFacts`, `SyntheticStrategyProposal`, 실제 Q20 사건들과 Q21 `ResearchPointInput`들, Q23 `PerformanceResult`다. 실제 채택/승인 정책값을 제공하는 기본값은 없다. paper/live는 차단하며 실제 Q19 관측을 이 사실로 변환하는 adapter는 없다. Q21의 `available_cash/reserved_cash/broker_buy_capacity=None`, `open_orders_status=unknown`은 그대로다.

현재 snapshot은 Q20 실제 사건 재생, Q21 `value_projection/reconcile`와 계좌 전체 독립 statement를 통해 다시 검증한다. 위험 근거는 `build_bound_performance`로 같은 계좌·집계창·현재 snapshot에 결속한다. Q16 `Catalog.resolve`, `ExplicitTimezone.lookup_calendar`, Q17 증빙 재생·현재 research/store 권리를 소비한다. 과거 snapshot에 저장된 권리와 현재 권리를 분리한다. 같은 rights_ref의 갱신된 grant는 현재 소비 권리를 검사하며 원래 snapshot을 바꾸지 않는다. 다른 rights_ref에 대한 대체 관계는 Q17에 정의되어 있지 않아 차단한다.

참조는 kind/id/version/canonicalization_version/sha256의 닫힌 타입이다. 등록 canonical 객체와 Q16의 별도 `context-source-facts-v1` hash를 구별한다. 계획 본문 hash에서 plan ID, 후보 본문 hash에서 candidate ID, 결과 본문 hash에서 result ID를 결정한다. 계획은 주문조건을, 후보는 plan ref/index를, 결과는 candidate refs를 갖는다. 자기 hash를 payload에 넣는 순환은 없다. 직접 생성·JSON 복원도 수치·비용·합산·표시·ID 결속을 검사한다. 각 목표 행에는 lot과 정확한 reference_base_price Metric을 보존하고, 복원 때 요청 수량/비중·생략 규칙·잔차와 다시 비교한다. 계좌 계산의 제안 수량·최악 부담, 노출 분모와 후보 유효기간도 서로 결속한다.

full은 명시 scope 안의 omitted=zero, partial은 omitted=keep를 요구한다. scope 밖 보유는 유지한다. quantity 목표·차이는 lot 배수, weight 목표는 완전 양수 NAV와 현재 FX로 계좌 절대 비중을 계산해 lot 내림한다. scope 안에서 비중을 재정규화하지 않는다. 잔차는 표시 소수와 정확한 분자/분모를 함께 보존하며 허용오차는 정확값으로 비교한다. cash 목표는 해당 통화의 현금 하한이다.

합성 의무 원천 객체와 실제 realized 사건에서 H/U/D를 계산한다. 동일 의무를 outstanding/realized에 중복 차감하지 않고 B의 reflected ID 목록과 행의 포함 관계를 대조한다. 원천 이후 settled 현금 변동은 사건 참조 전체와 비교하며 모든 차감을 설명해야 한다. `A=min(L-H-F,B-U-D)`의 음수도 숨기지 않는다. 비용은 fee/tax 각각 quantum 올림 후 합산하는 합성 whole_order_aggregate 상한이다. 매수 원금+비용 및 매도 비용만 계획 부담에 더하며 매도 최저 총대금은 별도 표시한다. 미래 매도대금·타통화·예상 매수 수량으로 여력을 만들지 않는다.

통화별 후보 누적 부담/남은 여력을 기록하고 계좌 전체의 종목·업종·시장·통화 투자 노출, funding, 주문당/일간 금액·수량, 거래량 참여, 손실·낙폭, 현금 하한을 검사한다. 노출은 현재 보유에서 매도만/매수만 체결되는 범위를 포함한다. 통화 집중도는 현금을 제외한 투자 노출이며 현금은 별도의 통화별 자금·하한 검사에 포함된다. NAV 하한은 모든 계획 비용과 불리한 체결 손실을 차감한다. Q21의 half-even 평가 반올림이 증액한 부분도 정확한 원통화 현금·현재 수량×가격×FX 합계와 대조하여 보수적으로 제거한다. 이 평가 반올림 여유도 worst_cost_and_adverse에 포함한다. FX 역수처럼 유한 소수로 표현할 수 없는 계산도 유리수를 유지하며, 기록하는 위험 금액/일간 금액은 Q21 base currency quantum으로 올림하고 최소 노출은 내림한다. 불리한 손실 올림으로 NAV 하한을 보수적으로 만든다. 가격변화 예측 보증은 없다.

지원 조건은 KR/US 현금 주식·일반 ETF, 정규장, limit/day, 명시 tick/lot/min/max/notional/volume이다. 명시 가격은 tick 배수여야 하고 자동 가격은 reference에서 매수 tick 내림/매도 tick 올림한다. 양쪽 모두 가격편차 한도를 지킨다. 제출 가능 구간은 요청·정책·TTL·capability·비용·권리·가격/FX/계좌 freshness·정규 세션의 교집합이며 끝을 제외한다.

`render_candidate(candidate, repository, market_inputs, at=...)`는 저장된 정확한 후보와 현재 report 권리를 확인한 후 후보 금융 필드에서 한국어 수치를 유도한다. 근거·위험·비용·만료·합성 문구와 render_version도 후보 hash에 들어간다. 표시 불가/해소 실패는 `ContractError`다. `candidate_json`은 기술 provenance를 포함한 canonical 객체를 JSON 자료로 제공한다. Q26은 exact candidate hash/render/generation에 결속하고 Q27은 최신 위험·권리·세션·세대 검사와 별도 원자적 승인 소비/예약을 담당해야 한다.

`SyntheticTargetRepository`는 최대128개 레코드를 canonical bytes로 저장한다. append는 plan/candidates/result 전체를 검증한 뒤 함께 반영하며 get은 새 객체로 복원한다. 같은 ID/hash는 멱등, 다른 내용·계좌/환경·plan/index·실재하지 않는 predecessor·scope/시점 역행은 거부한다. record당64KiB, 모든 collection128, 해소한 입력8MiB 한도를 적용한다. 저장소 한도에는 plan·candidate·result가 각각 포함되므로 후보 수 외에 저장 여유가 필요하다. 메모리 저장은 재시작 내구성이나 금융 예약이 아니다.

현재 버전은 원본 as_known 사건만 지원한다. 정정/restated·활성 broker 주문/로컬 의도·수량 예약 참조가 필요한 매도가능 형태는 무시하지 않고 차단한다. 실제 PG01/PG03 정책, 실제 계좌 capacity/결제/비용/capability/권리와 Q19 실제 관측은 미완료다. 네트워크·credential·password·주문 승인/제출/취소/예약·optimizer·새 package·Docker 경로는 추가하지 않았다.

검증은 숫자 helper와 source-bound builder를 구분한다. 독립 math golden은 L1000/H100/F100/B950/U50/D20→A800, 비용0.90+0.25=1.15, NAV1000/비중0.25/가격60/lot2→4주/잔차0.01이다. 실제 source-bound builder에서는 804>800 전체 차단/704 통과·잔여96, 미래 매도대금 미사용, KR/US quantity/weight/full/partial, scope 밖 보유 유지, 매수만 체결하면550>500 차단, 비용1.15와 NAV998.85, 현재 FX 양방향, Q23 실제 매도 사건의 D5/일간990·10주/손실15·낙폭0.0075, 현재 권리·완전성·시점·lot/tick·합산·표시·불변 저장을 검증한다. helper 성공을 원천 근거 검증으로 집계하지 않는다.

개발 중 실패도 보존한다. 최초 수동 연결에서 fixture의 KRW 대사 tolerance 누락, baseline mapping_version 불일치, RightsGrant의 독립 참조용 serializer 등록 누락을 발견·수정했다. 최초 target suite는36개 중 failure1/error1이었다. error는 ZoneInfo.from_file 객체 전체 deepcopy가 불가한 시험 fixture였고, failure는 Q17이 다른 rights_ref의 자동 대체를 허용한다고 가정한 기대값이었다. 대상 객체만 복제하고 같은 rights_ref의 갱신 grant 시험으로 수정했으며 관련3개 재검증은 통과했다. FX 추가 시험1개는 inverse FX에서 이미 quantum 반올림한 NAV333.33의 정확 잔차1333/133332를0.01로 잘못 예상해 실패했고, 독립 산식으로 기대값을 수정했다. 원래 실패 출력은 `/private/tmp/q24-target-initial.txt`, `/private/tmp/q24-target-fx-initial.txt`에 남겼다.

실행 명령과 최종 결과는 아래 실행 완료 기록에 덧붙인다.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3.13 -m unittest discover -s tests/product -p 'test_target*.py' -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3.13 -m unittest discover -s tests/product -v
python3.13 -I -S -B -m unittest discover -s tests/quality -v
python3.13 -I -S scripts/check_quality.py
python3.13 -I -S -B scripts/check_ai_team.py
git diff --check
```

실행 완료 기록(2026-10-24): target 전용38개/146.823초 통과 후 복원 결속·유효기간·보수적 NAV 검사를 보강했다. 추가 canonical10개/11.128초, FX/요청 결속 집중2개/16.534초, 원천 시점/유효기간 집중1개/3.039초, NAV 반올림 집중1개/2.897초를 통과했다. 보강 전 전체 제품418개/304.778초도 통과했으나 최종 버전 검증으로 대체하지 않고 별도 보존한다. 최종 source freeze 뒤의 전체 제품 실행 결과는 아래에 추가한다. 제품 전체를 처음 한 번 실행하던 중 위 직접 복원 검증을 강화하여 최종 버전 전체 실행을 추가로 수행한 사실을 숨기지 않는다.

품질 전용 명령은 `python3.13 -I -S -B -m unittest discover -s tests/quality -v`로87개 통과했다. 공개 품질 CLI는396개 파일/finding0, 팀 검사는6명·큐36개·작업110개 정합성 통과, `git diff --check`는 exit0이었다. frozen baseline-v1의7개 파일 모두 manifest SHA-256과 일치했다. 이 검증은 독립 reviewer/security reviewer의 판정이 아니라 단독 구현자의 실행 기록이다.

최종 source freeze 검증: 제품 전체421개(그중 Q24 target41개)가308.858초에 모두 통과했다. 명령은 위 전체 제품 명령 그대로이며 출력은 `/private/tmp/q24-product-final.txt`에 보존했다. 제품 실행 후 품질 전용87개도3.263초에 모두 통과했다(`/private/tmp/q24-quality-after-product.txt`). 최종 공개 품질·팀 정합성·공백·baseline hash 검사는 아래 최종 인계 시점에 다시 확인한다. 독립 검토/보안 검토/validator 완료나 실제 정책 승인으로 기록하지 않는다. 다음 담당은 root의 독립 검토와 validator다.

최종 인계 검사도 공개396개/finding0, 팀6명·큐36개·작업110개 정합성, `git diff --check` exit0, baseline-v1 SHA-256 7/7 일치를 확인했다. status·queue·evidence·상위 금융 모듈·설정·migration은 수정하지 않았다. serializer만 신규 target 타입과 독립 RightsGrant 참조의 추가 등록을 수행했다.

Q24 T1~T6 수정 착수(2026-10-24): 단독 구현자, subagent 없음. 입력은 AGENTS/status/TARGET-local/target-local-v1의 T1~T6 보완/target-review-initial 및 target-review-input 전문이다. 원래 소유10파일과 신규 `tests/product/test_target_review.py`만 소유하며 루트 계약·상태·큐·증거는 수정하지 않는다. 시작 시 소유10/10 SHA가 원구현 증거와 일치했다. graph 도구는 제공되지 않아 허용된 공개 파일만 읽었다.

내부 실패 기록: 최초 공개 파일 hash 목록을 넓게 만들던 도중 보호 설정의 stat이 거부되어 중단됐다. 보호 설정 내용은 읽지 않았으며 이후 명시 공개 디렉터리만 snapshot했다. 초기 red 준비 실행에서 T1 baseline fixture는 중복 현금계정/지원하지 않는 baseline 채무 형태, T6 fixture는 과거 snapshot 대사를 현재와 동일하게 가정한 오류였다. T1을 실제 매수·매도 원장 사건/TradeCostFact로 만들고 현금행 정렬을 교정했다. T6는 Q20이 수량0 tombstone을 보존한다는 사실을 반영하고 새 종목의 mapping version을 기존 계좌에 맞춰 다시 ingest했다. 이 fixture 실패는 결함 red로 집계하지 않는다. T6는 실제 `_source` 재검증 후 현재 경제적 보유/요청 종목만 전달한 `_constraints`에서 `daily_usage_fx` 누락을 재현했다(1건/5.148초). scalar 환산값이나 mock으로 통과시키지 않는다. 결함 재현 출력은 `/private/tmp/q24-fix-red-*.txt`에 있다.

원본 소스의 확정 red는 `q24-fix-red-clean.txt`: 9시험/39.960초, 실제 실패10건·오류0건이다. T2 직접생성의 가격/현금 두 subtest를 각각 실패로 집계한다. T1 양수채권1000/지급채무500/settled1000/기존보유500에서600 추가매수 허용, T2 직접생성/parse/완전 reseal repository 우회, T3 과거 봉 포함 정상 이력 거부, T4 무capability 유지보유/현재 장종료 유지보유 두 경로, T5 별도 FX 권리5초/후보30초, T6 source-bound 일간 계산의 과거 종목 환산 누락을 확인했다.

수정 결속:

- T1: 원본 매수 사건 ID/revision/hash·통화·잔여채무를 원장 정산 dependency와 projection의 음수 payable에 대조한다. 모든 잔여채무에 정확히 하나의 outstanding obligation이 필요하다. 양수 receivable은 H를 줄이지 않는다. 정산된 의무는 H에서 제외하며 기존 realized 차감은 L/B 반영 관계로 한 번만 처리한다. 미지원 정정/부분정산 형태는 차단한다. 명시 식별 채무500과400 매수, B 기반영 시 U0, 완전정산 뒤 H0 정상 경로를 보존한다.
- T2: 계획에 canonical synthetic policy 실제 객체를 추가 결속했다. 직접 생성·parse·repository 복원도 요청 매수상한/매도하한, 정책 floor와 cash target의 최대값, 가용금/잔여를 검사한다. 해시만 다시 붙인 모순된 계획은 거부한다. 실제 정책 채택을 추가한 것은 아니다.
- T3: Q21의 명시 dataset/series selection, 최신 적격 원본, 실제 보유 price_ref를 해소한다. 과거/미래 다른 봉을 현재가격으로 선택하지 않는다.
- T4: 계좌전체 보유에는 평가·권리·시점·분류를 요구한다. capability와 현재 정규장은 실제 수량차이가 있는 주문에 요구한다. 수량0 원장 tombstone을 현재 노출에서 제외하며 이 사건의 일간 사용은 T6로 보존한다.
- T5: 모든 현재 계좌 가격/FX, Q17/Q21/target 신선도, 원천 계좌/statement 시각, 전체 위험·일간 과거 입력의 현재 권리, 정책/요청과 실제 주문 capability/비용/세션의 유효기간을 교차한다. 과거 시장가격의 freshness는 검증된 과거 평가시점 기준이며, 현재 소비권리는 현재시점 기준이다. 과거 snapshot·현재 권리·TradeCostFact 참조도 후보 hash에 결속한다.
- T6: 기존 TradeCostFact와 실제 trade/fee/tax 사건을 먼저 재검증하고 과거 catalog mapping의 종목/통화, 명시 FX selection과 사건시점까지 알려진 원본 FX를 현재 보유 목록과 독립 해소한다. `base_notional` scalar를 환산 증명으로 신뢰하지 않는다. 추가 `daily_usage_inputs`도 실제 snapshot/source 재검증·계좌/기준통화/시점/권리/크기 한도를 적용한다. 과거 FX 여러 시각은 최신 적격 시각을 선택하며 같은 시각의 환산 상충은 차단한다.

추가 내부 실패: 첫 수정9시험/39.148초 중3오류는 `FXSelection.native_currency` 필드명을 `currency`로 쓴 구현 오류였고 바로 교정했다. 다음 target50시험/198.471초 중1실패는 세션 종료가 stale 사유로 먼저 차단된 것이어서 실제 주문의 session 검사를 먼저 수행하도록 고쳤다. 신규 golden14시험/74.696초 중1오류는 미래 봉 observation이 published_at보다 빨랐던 fixture 오류였으며 관측시각을 cutoff로 교정해 해당 시험1개/6.957초를 통과했다. 이후 집중24시험/103.668초와 추가3시험/14.792초가 통과했다. 마지막 과거 FX 이력 정상사례1시험/9.513초에서 서로 다른 시각의 유효 FX를 모두 상충으로 처리하던 추가 결함을 실제 재현해 최신 적격 시각 선택으로 보완했다. 전체 제품 실행 전의 실패와 보완이며, 전체 실행 중 소스 변경으로 숨기지 않는다.

과거 FX 이력 보완 뒤 관련3시험/18.033초도 통과했다. 확정 원본 red10실패와 추가 이력 red1실패를 구분한다. 이제 제품 소스·시험을 동결하며 전체 제품 명령을 한 번 실행한다. 최종 결과와 실행 후 hash·품질 확인은 완료 후 아래에 기록한다.

최종 실행 결과(2026-10-24): 동결 뒤 전체 제품을 **한 번** 실행해448시험(그중 target68시험)이421.639초에 모두 통과했다(`/private/tmp/q24-fix-product-final.txt`). 전체 실행 중 소스·시험·가이드 변경0, 실행 전후 소유12/12 SHA 일치다. 품질은 지정 명령 `python3.13 -I -S -B -m unittest discover -s tests/quality -v`로87시험/3.246초 통과했다(`/private/tmp/q24-fix-quality-final.txt`). 공개 품질402파일/finding0, 팀6/큐36/작업110 정합성, diff 공백 검사 exit0, baseline7/7 SHA 일치를 확인했다. 시작 시 명시 공개 파일285개의 hash와 비교해 비소유 변경0이었다. 결과 기록을 위한 이 가이드의 최종 갱신 후 공개 품질·diff·baseline·소유 hash를 다시 확인하며 제품 코드는 재변경하지 않는다.

실제 변경6경로: `src/quantharbor/domain/target.py`, `src/quantharbor/application/target.py`, `src/quantharbor/ports/target.py`, `tests/product/test_target_review.py`(신규), `tests/product/test_target_review_cases.py`(신규), `docs/development/target.md`. 원래 소유10개와 신규 시험2개, 총12개의 최종 SHA는 `/private/tmp/q24-fix-final-hashes.json`에 반환한다. 루트 계약/상태/큐/증거, 상위 금융 모듈, frozen/spec/config/policy 파일은 수정하지 않았다.

이 결과는 단독 구현자의 합성 자체 검증이며 독립 재검토·validator 판정은 root가 수행한다. 실제 정책 채택·비밀번호·비공개 자료·실계좌/API·네트워크·Docker·설치·저장소 Git 변경·외부 전송은 수행하지 않았다. 품질/팀/diff의 승인된 읽기 검사와 품질 시험의 임시 합성 저장소는 운영 Git 변경과 구분한다. 부분정산/정정 등 미지원 원장 형태, 실제 PG/SG·승인/예약/주문 경로는 범위 밖이다.

Q24 두 번째 수정 T5b/T6b(2026-10-24): 단독 구현자, 제한 qh_development 범위이며 subagent 없음. AGENTS/status/TARGET-local, target-local-v1의 T5b/T6b 보완, target-review-second 증거와 second-input 전문을 입력으로 삼았다. 시작 시 이전 소유12/12 SHA와 baseline7/7이 일치했다. 소유 파일은 `application/target.py`, `test_target_review_cases.py`, 이 안내의 세 경로뿐이다. 코드 그래프 도구는 현재 제공되지 않아 허용된 파일을 제한해서 읽었다. 공통 상태·계약·큐·evidence는 root가 기록한다.

수정 전 실제 red는4시험/14.438초, 실패4·오류0이다(`/private/tmp/q24-second/red-initial.txt`). risk_points와 daily_usage_inputs의 `current_rights.rights_ref`만 다른 정상 참조로 바꿔도 허용되는 두 경로를 재현했다. 실제 Q17 ingest·receipt/evidence replay·Q21 snapshot으로 만든 추가 daily 입력은 `partial`, nonempty missing_scope, `MarketProof.usable=False`, held_reasons 빈값이다. 기존 완전 FX3에 더 최신 FX1을 더하면 USD990 매도의 일간사용이2970 대신990으로 낮아지고 일간한도3200에서 신규 후보가 허용됐다. 더 오래된 불완전 FX4를 조용히 건너뛰고 완전 FX3으로 돌아가는 경로도 별도 red다. 이 red 실행에는 fixture 오류가 없었다.

T5b는 과거 grant로 치환하기 **전** 원본 proof의 rights_ref와 현재 grant의 참조를 비교한다. 서로 다른 참조는 ContractError이며 기존 현재 research/store 목적·source/dataset/version·유효기간·철회 검사와 원본 과거 grant 검증을 모두 유지한다. 같은 참조의 갱신은 과거 snapshot을 바꾸지 않고 허용하며 현재 만료를 후보 유효기간에 반영한다.

T6b는 `_source`에서 실제 Q17 재생/Q21 재구축으로 검증한 snapshot의 **해당 FX series** proof에 `usable`을 요구한다. 이 속성은 complete quality·rights_allowed·빈 reasons/missing_scope/held_reasons를 모두 요구한다. 불완전 proof는 `source_incomplete/complete_historical_daily_fx_proof`로 후보0 차단하며 더 낮은 다른 환율로 fallback하지 않는다. 이후 사건시점의 원본 FX 선택·publication/observation/ingestion cutoff·현재 권리·환율 방향·나이·동시각 상충 검사는 유지한다. 완전 FX3의2970 및 한도차단, 완전한 더 최신 FX1의990 정상 경로를 구분해 시험한다. 상위 금융 계산·frozen/spec·정책값을 변경하지 않았다.

추가 시험7개는 참조 불일치2경로, 같은 참조 갱신2경로, 현재 권리의 source/dataset/version·목적2개·만료/미래시작/철회 각2경로, 실제 불완전 최신FX1/과거FX4 차단, 완전 과거FX 정상 경로를 포함한다. 집중 green 확인 뒤 source/test를 동결하고 전체 제품을 한 번 실행한다. 품질은 `python3.13 -I -S -B -m unittest discover -s tests/quality -v`, 공개/팀은 같은 `-I -S -B`의 기존 CLI를 사용한다. Git 직접 호출은 하지 않으며 시작 사본과의 텍스트 diff·공백 및 공개 파일 SHA 대조를 수행한다. 기존 품질 CLI 내부의 읽기 전용 Git 조회와 quality 시험의 임시 합성 저장소는 요청된 품질 검증에 포함된다. 최종 실제 결과·한계·12개 SHA 경로는 실행 완료 후 덧붙인다.

집중 첫 실행은25시험/111.048초, 실패0·오류1이다(`/private/tmp/q24-second/green-cases.txt`). 제품이 불완전 FX를 차단한 뒤 비어 있는 account_calculation을 시험의 red 진단문이 읽어 발생한 AttributeError다. 제품 결함 red4건과 별도 시험 오류1건으로 보존하고 진단문에 None 처리를 추가했다. 나머지24개는 T1~T4 및 기존 정상 과거FX/신규 권리·완전FX 경로를 포함해 통과했다. 제품 수정은 이 오류와 무관하다.

진단문 수정 뒤 신규7시험/29.536초가 실패0·오류0으로 통과했다(`/private/tmp/q24-second/green-new.txt`). 이제 source/test를 동결하며 전체 제품 시험을 한 번 실행한다. 동결 SHA는 `/private/tmp/q24-second/freeze-owned-hashes.json`의 이전 소유12개 전체에 기록하고 실행 직후 다시 대조한다.

두 번째 수정 최종 결과: 동결 뒤 전체 제품을 **한 번** 실행해455시험(그중 target75시험)이448.487초에 모두 통과했다(`/private/tmp/q24-second/product-final.txt`). 실행 중 변경0, 실행 직후 소유12/12 SHA가 동결값과 같았다. 품질87시험/3.121초 통과(`/private/tmp/q24-second/quality-final.txt`), 공개405파일/findings0, 팀6명·큐36개·작업110개 정합성 통과다. Git 직접 호출 없이 시작 사본의 diff/추가행 공백 검사와 공개391파일 SHA를 대조해 지정 세 파일 외 변경0 및 baseline7/7 불변을 확인했다. 검사 결과는 `/private/tmp/q24-second/verification-after-product.json`에 있다.

최종 결과를 기록한 이 안내 외 소스·시험은 재변경하지 않았다. 최종 SHA 목록은 이전12개 전체를 포함한 `/private/tmp/q24-second/final-owned-hashes.json`이며 새 시험 파일은 없다. 최종 안내 갱신 후 공개 품질·diff/공백·비소유 SHA·baseline을 다시 대조한다. root는 이 출력과 실제 red/green 원문을 근거로 공통 evidence/status/큐를 갱신하고 후속 판정을 수행한다. 이 기록은 단독 구현자의 합성 자체 검증이다. 실제 권리/정책 채택·실계좌/주문·비공개 자료·네트워크·Docker·설치·상위 금융/frozen/spec 변경을 포함하지 않는다.
