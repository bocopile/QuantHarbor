# Q23 합성 연구 API

작업 ID: RESEARCH-local / Q23. 입력은 [고정 계약](../contracts/research-local-v1.md), [PG02 사전 명세](../contracts/comparison-spec-v1.json), RESEARCH-DEC-001이다. 소유 범위는 신규 research domain/application/ports/adapter와 연구 산식·전략·시험 및 이 문서, 기존 serializer의 고정 registry 추가다. 원장·시장·평가·보고 v1, 계약·정책·상태는 변경하지 않는다.

## 호출

Python 3.13, 표준 라이브러리만 사용한다. 네트워크, 설치, LEAN, 실제 계좌, 모델 API, BrokerPort가 필요하지 않다.

```python
from quantharbor.adapters.synthetic_research import run_fixed_comparison

results, summaries = run_fixed_comparison()
assert len(results) == len(summaries) == 24
# results: tuple[ExperimentResult, ...]
# summaries: tuple[RunSummary, ...]
# summary.result_id / manifest_hash / result_hash는 별개다.
```

`run_fixed_comparison()`은 명세의 두 시장×두 비용×두 독립 fold×세 전략을 순서대로 모두 반환한다. 수익률 순위나 승자를 고르지 않는다. 첫 OOS 관측점에서 선언 현금으로 새 계좌를 시작하고 신호를 만든다. 마지막 점에서는 신호를 만들거나 강제 청산하지 않는다. 전략은 fit=none이며 train/validation/OOS와 탐색 기록은 사전에 고정한다. 분석 기본15분은 이 재조정 일정의 근거가 아니다.

명시 객체를 보관·검토하려면 아래 API를 사용한다.

```python
from quantharbor.adapters.synthetic_research import (
    fixed_experiment_inputs, SyntheticExperimentRepository,
)
from quantharbor.application.research import build_comparison, build_experiment, summarize

inputs = fixed_experiment_inputs()  # tuple[ExperimentInputs, ...], 24개
repo = SyntheticExperimentRepository(capacity=128)
results = build_comparison(inputs, repo)

one = inputs[0]
peers = {x.strategy: x for x in inputs
         if (x.market_id, x.scenario_id, x.fold_id)
         == (one.market_id, one.scenario_id, one.fold_id)}
result = build_experiment(one, repo,
                          benchmark=peers['buy_hold'],
                          cash_benchmark=peers['cash'])
summary = summarize(result)
```

`build_experiment`는 실제 비교 입력 세 군을 모두 검증한다. `build_comparison`은 24개 조합의 누락·중복을 거부하며, 한 호출 안에서 검증된 입력만 재사용한다. 전역 검증 cache는 없다. 데이터·권리·행동 선언 등의 경계가 잘못되면 `ContractError`로 전체 호출을 중단하며 성공한 일부를 전체 비교처럼 반환하지 않는다. 원천 오류를 지우거나 다른 가정으로 보완하지 않는다.

`ExperimentInputs`는 spec/registry/fingerprint, 시점별 `ResearchPointInput(snapshot, market_inputs)`, 실제 `LedgerEvent` tuple, `TradeCostFact` tuple, `ExecutionTrace`를 명시적으로 받는다. production은 tests를 import하지 않는다. 결과에는 snapshot 본문을 복사하지 않고 ID/hash와 성과에 필요한 작은 산식 입력만 보관한다. 원가 결과는 Q23 별도 객체이며 Q21/Q22의 기존 unknown 필드를 소급 변경하지 않는다.

## 검증 경로와 수치

fixture는 Q16의 명시 합성 TZif·달력·상품 catalog, Q17 `ingest`와 `select_view`, Q20 `append`/`replay`, Q21 `build_snapshot`을 실제 호출한다. builder는 모든 사건을 다시 append하여 accepted 결과·사건 ID/hash를 비교하고, 각 cursor에서 replay한 projection과 Q21 재계산 snapshot을 원본과 대조한다. 각 시점 bundle은 그 시점에 알려진 두 봉만 담는다. 최종 bundle로 과거 평가를 대체하지 않는다. 현재 권리는 각 평가 시각 및 명세의 최종 소비 시각에서 research/store/report 목적을 검사한다.

신호는 완료·발표·관측·수집된 가격과 NAV로 수량을 정하고 lot 내림한다. 체결은 다음 지정 적격 봉의 종가에 불리한 tick을 적용한다. 매도 우선·종목 ID 순, 고정 신호 수량을 유지한다. volume 10%, 최소 대금, 비용 포함 현금, 보유 수량에 걸리면 주문 전체가 미체결이다. 매매·수수료·세금·명시 T+0 결제는 각각 Q20 사건으로 남는다. 자동 환전·차입·공매도·실제 주문은 지원하지 않는다. Q20의 available_cash unknown에 연구 예산을 역주입하지 않는다.

중간 연산은 `Fraction`과 정확 정수다. `Metric`은 표시값과 정확한 분자/분모를 함께 보존해 반올림한 수익률·평균 NAV를 다음 산식에 재투입하지 않는다. 비율 표시는 0.000000000001 half-even, 금액 산식 입력은 정확값을 보존하고 필요한 경우 표시만 최대 소수18자리다. 매매 비용과 이동평균 매도 제거원가는 지정 통화 quantum half-even을 적용한다. 전량 매도는 반올림 잔액을 포함한 원가 전부를 제거한다.

TWR은 외부흐름 경계별 기하 연결, 금액손익은 종료−시작−순입출금이다. MDD는 관측된 흐름 조정 부지수의 최대 낙폭이다. NAV0 도달의 낙폭100%는 기록할 수 있지만 이후 비양수 분모의 수익률은 unknown이다. 총회전율과 절반회전율은 시간가중 평균 NAV를 분모로 구분한다. benchmark excess와 relative wealth도 별도다. 연율화는 없다. fee/tax는 사건별 귀속과 요율/대금/양자 반올림을 대조한다. 슬리피지는 이미 fill 대금에 포함되므로 다시 차감하지 않는다. FX 평가 이익을 FX 거래비용으로 취급하지 않는다.

`research.metrics.calculate_performance`와 `research.costing.calculate_basis`는 원천 진위 검증을 하지 않는 순수 산식 API다. 실제 스냅샷의 외부흐름 검증은 `application.research.build_bound_performance(points, events, boundaries=..., boundary_inputs=..., costs=...)`를 사용한다. 이 API는 기준통화·정확 quantum 현금흐름만 지원한다. 경계의 두 스냅샷은 동일 가격/FX/시각/범위/정책을 사용하고, cursor 사이에는 지정 입출금 사건만 있어야 한다. 누락 경계·다른 사건 개입·외화/현물 흐름은 거부한다. 이 API에 선택적으로 제공하는 benchmark scalar는 산식 시험용이며, 완전한 비교 결속은 `build_experiment`가 실제 benchmark 입력을 재검증해 제공한다.

R1 보완: 실제 snapshot 결속 API의 공통 재검증은 모든 평가점과 외부흐름 직전·직후 snapshot의 요청 목적을 `research`로 제한한다. Q21 재계산으로 검증한 모든 시장 증빙에 대해 요청의 `evaluated_at`에서 해당 source/dataset/version의 `research`·`store` 권리를 검사한다. `report` 목적 snapshot은 연구 권리가 있어도 거부하며, 현금 NAV가 완전하더라도 제공한 시장 증빙의 연구 권리 누락·철회·만료는 거부한다. 보고용 snapshot의 정상 생성과 순수 산식 API는 기존 계약을 따른다.

기초 원가, 행동, 정정 지원이 없거나 평가액이 누락된 원가 항목은 unknown이다. 가격/FX 손익 귀속은 항상 미지원으로 남긴다. 수량0·완결 귀속이 검증된 원가와 명시 무거래/무환전 시나리오만 0으로 기록한다. 필수 NAV 누락·비양수 분모는 관련 지표마다 null과 reason을 남긴다. fixed primary의 행동 unknown은 차단한다.

## 해시·한도·저장

명세 raw SHA256은 `b24ec83a0cbbe1646fee64c2d433cf8d2c57831f58c8e2e746c0e9c371dc4bb4`이며 Q23 canonical hash와 다르다. loader는 이 raw 해시가 일치하는 고정 파일만 읽는다. 구현 fingerprint는 adapter의 `FINGERPRINT_PATHS`에 나열한 실제 파일과 lock을 읽어 계산하고 Python 3.13 패치 버전을 함께 기록한다. 호출자는 파일 경로나 임의 version을 지정할 수 없다. 경로 구성요소의 symlink와 비정규/다중 hardlink 파일을 거부하며 파일당1MiB로 읽기를 제한한다. 이 fingerprint는 소스·lock의 재현 식별이며, host가 lock의 Linux 이미지와 같다는 증명이나 stdlib/하드웨어 전체 attestation은 아니다.

기존 `qh-canonical-json-v1`의 고정 registry와 nested table에 Q23 타입만 추가했다. 별도 범용 codec·fallback·사용자 등록은 없다. 객체당 canonical64KiB, 실행당 참조·평가점·사건128, 실제 해소 입력 전체8MiB를 넘으면 거부한다. 비교 기준 입력도 총량에 포함한다. 결과 ID는 입력 manifest에서, 결과 hash는 완성 결과에서 계산한다. 결과 canonical 복원은 포함된 성과/원가/비용 요약의 산식 정합성을 재검사한다. 해시만으로 원천 데이터의 진위를 증명했다고 주장하지 않는다.

메모리 저장소는 capacity≤128이며 append/get만 제공한다. 동일 ID/hash는 멱등, 상충 내용·계좌/환경 불일치·없는 predecessor·다른 비교 범위 predecessor는 거부한다. 기존 결과는 보존한다. 같은 predecessor의 상충 정정 분기도 거부한다. primary builder는 사전 고정 original/no-actions 경로만 실행하며, 저장소의 predecessor 기능이 미지원 원가 정정이나 OOS 파라미터 변경을 허용하는 것은 아니다. 운영 내구성·DB 이관은 범위 밖이다.

## 완료 증거와 한계

독립 golden은 입금 TWR21%/손익26, 출금 낙폭0, 관측 MDD25%, benchmark 초과11pp/상대10%, 회전율1/0.5, 이동평균 원가·전량 청산·quantum 반올림을 사용한다. 실제 검증 결과·검사 수·미확인과 소유 파일 SHA256은 구현자 인계에서 root에게 반환한다. root가 contracts/evidence/status를 통합한다. 이 문서는 실행하지 않은 검사를 통과했다고 기록하지 않는다.

합성 로컬 엔지니어링 범위다. 실제 역사적 성과, 공급자 권리, 실제 결제/세무 원가법, LEAN 호환, 모델 평가, 전략 채택, 실제 계좌 연결·주문은 검증하지 않는다.
