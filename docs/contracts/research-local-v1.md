# 합성 연구·성과·기준 전략 계약 v1 — Q23

상태: root 구현 기준, PG02 합성 비교 명세 채택. EXEC-DEC-001에 따른 F07/G01~04 로컬 범위이며 전략 채택·실제 자료·LEAN 호환·실제 주문은 포함하지 않는다. 고정 data/execution/operations/serialization-v1과 Q17~22를 소비하는 추가 계약이다.

## 고정 명세와 식별

비교 입력은 comparison-spec-v1.json이다. 이 파일의 raw SHA256은 RESEARCH-DEC-001에 기록하며 Q23 canonical hash와 구분한다. 목적·12개 정확 UTC 시점·두 시장별 합성 자금/단위·종목군/경로·세 전략·두 비용 시나리오·두 fold를 사전 고정했다. 24개 실행의 합격 기준은 재현·산식·입력 경계이며 수익률 우열이 아니다. 90% 투자/10% 현금, 수수료·세금·결제 등의 값은 공학 시험 가정으로 사용자 운용 정책에 복사하지 않는다. 분석 기본15분을 이 연구의 재조정 주기로 해석하지 않는다.

ComparisonSpec, ExperimentManifest, ExperimentResult, PerformanceResult, CostBasisResult, TradeCostFact 등은 synthetic 전용 닫힌 불변 타입과 정확 수치/시각/ID·상호 결속을 검사한다. 미래 Q25 AI ResearchResult와 이름을 혼용하지 않는다. 기존 domain/serialization.py에는 고정 Q23 스키마를 additive 등록하고 기존 canonical wrapper/금액/64KiB 규칙·golden vector를 보존한다. 별도 범용 serializer를 복제하지 않는다.

manifest는 명세 hash·구현/의존성 lock hash·종목군/권리/달력/시장 버전·시점별 입력 refs·Q20 사건/cursor·Q21 snapshot refs를 결속한다. 자동 파일검색/네트워크/임의 파일경로 대신 명시 주입한 객체를 재검증하고 참조를 해소한다. raw hash만 있는 임의 NAV 배열을 검증된 스냅샷 대신 쓰지 않는다. 구현 파일/lock hash는 실제 실행 버전에서 고정 허용 파일 목록으로 산출/대조하며 사용자 임의 version 문자열만 신뢰하지 않는다. snapshot은 결과에 중복 복사하지 않는다. 실행당 참조·평가점·사건 각각128 이하, 해소한 전체 입력8MiB 이하, 각 canonical64KiB 이하. 초과를 잘라내거나 자동 분할하지 않는다.

결과 ID는 고정 input manifest에서 결정하고 완성 결과 hash는 별도다. 한도128의 메모리 append/get 저장은 동일ID/hash 멱등·상충 거부·계좌/환경 결속·실제 predecessor 확인·과거 불변을 검증한다. 동일 명세/기간/환경/범위의 입력 정정은 새 결과와 predecessor로 추적하며 정책/전략 변경은 새 명세·실험이다. 메모리 저장을 운영 내구성으로 주장하지 않는다. standalone 결과 canonical은 그 안에 포함된 산식 입력/요약·상태의 정합성을 검증하고, 원천 진위는 builder의 실제 입력 재검증과 별도 증거를 요구한다.

## 성과 산식

측정 사건은 (시작, 종료]이며 최초 NAV는 시작 경계까지 반영한다. 입금 C>0/출금 C<0만 외부흐름이고 매매·배당·수수료·세금·FX·결제는 내부다. 초기 지원은 기준통화·통화 quantum에 맞는 현금흐름이다. 외화/현물 흐름·경계 누락은 unknown이며 근사식으로 대체하지 않는다.

흐름 시각의 동일 가격/FX/지식 경계에서 완결 cursor를 이용한 직전 Vminus와 직후 Vplus를 검증하고 Vplus=Vminus+C를 요구한다. 두 cursor 사이에 해당 흐름 묶음 외 사건이 있으면 거부/unknown이다. r_j=Vminus_j/Vplus_previous-1, 마지막 흐름 뒤 종료까지도 포함하여 TWR=product(1+r_j)-1이다. 순손익=종료NAV-시작NAV-sum(C)는 별도 금액이다. 모든 평가점의 흐름 조정 부지수 W를 누적하고 MDD=max(1-W/running_max(W))로 양의 낙폭 크기를 기록한다. 지정 관측점의 낙폭이며 연율화·장중 최대·Sharpe를 추정하지 않는다.

필수 NAV unknown/부분 소계, 비양수 분모이면 관련 지표는 unknown/reason이다. NAV0 도달 시 낙폭100%는 기록할 수 있으나 이후 수익률을 임의 연결하지 않는다. 중간 산술은 Fraction/정확 정수, 최종 비율만 0.000000000001 half-even quantum. 표시 결과를 다음 계산에 재사용하지 않는다.

동일 기간·시각·통화·비용 시나리오의 buy_hold 및 cash를 비교한다. 초과수익=Rstrategy-Rbenchmark(표시 pp); 상대부 변화=(1+Rstrategy)/(1+Rbenchmark)-1은 별도 이름이다. 회전율은 시간가중 평균 NAV A=sum(V_i_after_flow*delta_seconds)/sum(delta_seconds), 총매매대금(B+S)/A를 기본, (B+S)/(2A)를 보조로 명명한다. 초기 매수 포함, 비용·흐름·결제 제외. 체결대금은 해당 체결 시점의 검증된 base FX로 환산해야 하며 없으면 해당 지표 unknown이다.

## 비용·원가

수수료/세금은 side·기준대금·요율·양수 통화 quantum에 따른 half-even 비용과 별도 Q20 사건으로 결속한다. 매수 슬리피지=q*(fill-reference), 매도=q*(reference-fill)이며 불리한 tick 반올림도 포함한다. 슬리피지는 이미 실제 합성 체결대금에 들어 있으므로 NAV에서 다시 차감하지 않는다. 환율 평가 변화는 FX 거래비용이 아니다. 명시 합성 환전 사실이 있을 때만 reference 대비 spread/명시 비용을 분해한다. 엔진은 자동환전하지 않는다. zero-cost는 별도 고정 시나리오 재실행이며 net수익률에 비용률을 더해 복원하지 않는다.

원통화 이동가중평균 원가는 기초 수량0, 명시 단일 종목 체결/귀속 비용·revision 검증이 가능한 범위만 지원한다. 매수 Q'=Q+q,B'=B+notional+buy_cost. 매도 제거원가 D=half_even_quantum(B*q/Q), 전량매도 D=B; realized=sell_notional-sell_cost-D, 잔여원가 B-D. 미실현은 Q21 원통화 평가액-잔여원가다. TradeCostFact는 trade와 fee/tax 사건의 ID/hash/revision/계좌/종목/통화/금액을 묶으며 미배정/중복·초과 배분을 거부/unknown으로 둔다. costs_known bool만으로 귀속을 추정하지 않는다.

기초 보유 원가 미확인·미지원 기업행동/정정·복합 배분·가격/FX 손익 귀속은 항목별 unknown이다. 원가 unknown이 완전NAV로 계산 가능한 TWR을 반드시 막지는 않는다. Q21/Q22 v1의 원가 unknown 필드는 변경하지 않고 Q23 별도 원가/성과 결과로 제공한다. 이전 v1의 costing_spec_pending_q23는 그 읽기 모델의 미지원 사유이며 최신 Q23 지원 범위 전체의 상태 신호가 아니다. 세무 원가법·실제 세율 채택이 아니다.

## 합성 실행·전략

각 시장·비용·fold·전략은 별도 계좌/원장으로 초기화한다. fold 첫 OOS 평가점은 초기 현금이고 이 시점에 최초 신호를 만든다. cash는 이자0·거래없음. buy_hold는 동일 고정 두 종목에 각 NAV45%의 최초 목표 수량을 lot 내림하여 매수하고 유지한다. equal_weight_rebalance는 같은 최초 배분 뒤 매 OOS 평가점에90% 투자/45%씩 목표로 재조정한다. 마지막 평가점은 새 신호를 만들지 않는다. fold별 결과를 연속 운용처럼 연결하지 않는다.

수량은 신호 당시 완료/발표/관측/수집된 가격과 NAV로 결정하고 다음 적격 봉 종가에서 체결한다. fill 시 미래가격을 신호 계산에 역주입하지 않는다. 매도 우선→종목ID 순으로 처리한다. 실제 수량은 신호의 고정 수량; lot/minimum_notional/volume참여/비용포함 현금 제약 미충족은 해당 주문 전체 미체결이며 미래가격에 맞춰 조용히 수량을 줄이지 않는다. 매수 fill은 reference*(1+slippage) tick 올림, 매도는 reference*(1-slippage) tick 내림. 조건을 갖춘 합성 T+0 settlement 사건을 생성한다. 연구 예산 검사 결과를 Q20의 unknown available_cash에 역주입하지 않는다. 차입·공매도·자동FX·강제종료청산·실제 BrokerPort 호출 없음.

고정 close 경로는 실제 시장 자료가 아니며 동일 bar의 open/high/low/close, volume을 명시한다. 두 synthetic 종목의 equity/generalETF 분류·유효/알려진시각·시장/통화/매핑은 첫 시점 전 알려진 버전이다. 실제 거래소 달력/상품 권리의 보증으로 쓰지 않는다. Q16 달력/시간대·Q17 수집/select_view·Q20 append/replay·Q21 value/snapshot을 실제로 연결하며 자체 숫자 배열만으로 이를 우회하지 않는다. 범위 완전성·권리·시점 검증과 사건 반영을 실행 증거로 남긴다.

## 시점·분할·재현

두 fold의 train/validation/OOS는 JSON에 정확히 고정되어 있으며 fit=none이다. 기준 전략에는 학습 파라미터가 없다. 미래 revision, unknown publication, 종목군 지식/상장폐지 근거 누락, 입력 dependency 누락은 불완전/거부다. 부분 종목을 삭제하거나 최신값으로 보완하지 않는다. 기업행동 없음도 시나리오의 명시 사실이고 누락을 없음으로 추정하지 않는다. 각 snapshot cutoff마다 당시 descriptor/receipt/evidence를 사용하며 마지막 전체기간 bundle을 과거에 공급하지 않는다. 권리는 각 소비 시각/목적에서 기존 검사를 재사용한다.

OOS를 보고 명세·비용·종목군·주기를 고치면 새 spec/version/탐색 기록이다. fold별 reset·관측점·비용·오류를 보존하고 성공한 일부 결과만 전체 비교로 발표하지 않는다. 학습형 전략은 label 의존기간/purge/gap 계약이 없으므로 미지원이다. LEAN 설치/실행·실제 데이터 백테스트·실제 수익성·운용전략 선택은 미실행으로 남긴다.

## 독립 기대값과 검증

- 100→입금직전110→입금50→종료176: TWR0.21·순손익26. 100→출금80→20 가격변화없음: 수익률0·낙폭0.
- 부지수1,1.2,0.9,1.08의 MDD0.25; 전략0.21/벤치0.10의 초과0.11·상대0.10. B60/S40/A100의 총회전율1·절반0.5.
- NAV2000,10주 reference100→매도fill99,fee2,tax3: 종료1985·수익률-0.0075, slippage10/fee2/tax3 중복차감없음.
- buy10*100+10,buy10*200+10,sell5*180-cost3,가격180: 매도전원가3020·제거755·실현142·잔여2265·미실현435.
- 100USD FX1300→1320 거래없음: KRW증가2000·FX거래비용0. quantum0.05의1.025/1.075/-1.025→1/1.1/-1.
- 흐름 경계 누락·unknownNAV·비양수분모·원가귀속 누락, 미래정보/위조hash/부분자료·행동누락·권리철회·상충manifest·128초과·한도·정정/중복·전략별현금/lot/tick/volume·다음봉체결을 거부/unknown으로 확인한다.

기본 golden은 독립 예상값이며 구현 전 통과 기록이 아니다. 최종24개 고정 실행은 결과/manifest hash와 비용/지표/미확인을 남기고 동일 입력 재실행 일치를 확인한다. 원시 모델 결과나 수익률 순위만으로 완료하지 않는다.

## R1 연구 소비 목적 보완

build_bound_performance를 포함한 실제 snapshot 결속 연구 API는 모든 평가점과 외부흐름 직전/직후 입력을 research 목적으로 재검증한다. report 목적으로 유효한 snapshot이나 store 권리만으로 연구 소비 권리를 대체하지 않는다. 목적 불일치·권리 미확인/철회는 계산 전 거부한다. 순수 수학 함수의 무원천 숫자 산식과 원천 검증 API를 구별한다.
