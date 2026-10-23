# OSS 20개 적용 결정안

기준일: 2026-10-19. 상태: **ARC-08 검토용 권고안**. 관련 작업 B04·B05, ENV-03~09, ARC-03~09. 현재 모듈·인터페이스·완료 기준은 설계 제안이며 구현 결과가 아니다.

## 조사 범위와 재현성

기존 11개 검색·530개 결과에서 선별한 후보 99개의 메타데이터를 갱신했다. 추가로 `algorithmic-trading`, `portfolio-management`, `trading-agent`, `finance`를 `sort:stars-desc`로 각각 50개씩 조회하여 새로운 122개를 확인했다. 총 221개 메타데이터를 비교했고, 범위 내 상위 20개 구성은 유지됐다. 아래 수치는 이번 재조회 스냅샷이다.

범위는 투자 AI·자동매매·백테스트·증권 보유관리·금융 데이터 구성요소다. 암호화폐 프로젝트는 운영 설계 비교 목적으로 포함했다. 가계 지출·예산 앱, 결제/블록체인 기반시설, 범용 개발 도구, 교재·링크 모음은 제외했다. 따라서 20개 모두 완성된 직접 경쟁 제품은 아니며 **정의한 후보군의 스타 순위**다. GitHub 전체의 절대 상위 20개라고 주장하지 않는다.

선정한 20개는 모두 공식 문서·라이선스 또는 핵심 소스를 읽었다. 각 프로젝트의 고정 commit과 핵심 파일을 아래 및 [메타데이터/선별 근거](github-evidence-2026-10-19.json)에 남겼다. 전체 파일 감사·실행·수익성 검증은 수행하지 않았다. 고정 commit은 조사 근거이며 운영 버전 승인이 아니다. 이전 상세 근거는 [기존 조사](oss-survey.md)에 보존한다.

## 스타 순위와 적용 방식

| 순위 | 프로젝트 | Stars | 적용 방식 | QuantHarbor 책임 영역 |
|---:|---|---:|---|---|
| 1 | [TradingAgents](https://github.com/TauricResearch/TradingAgents) | 111,977 | 패턴 참조 | research_orchestrator · evidence_store |
| 2 | [OpenBB](https://github.com/openbq-org/OpenBB) | 74,428 | 패턴 + 선택 공급자 패키지 후보 | market_data/providers · normalizer |
| 3 | [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) | 66,719 | 보고·전송 패턴 참조 | reporting · notification_outbox |
| 4 | [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 64,081 | 목표·리밸런싱 패턴 참조 | portfolio/target_validator · rebalance/planner |
| 5 | [freqtrade](https://github.com/freqtrade/freqtrade) | 55,592 | 운영 패턴 참조 | execution/order_monitor · research/validation |
| 6 | [maybe](https://github.com/maybe-finance/maybe) | 54,217 | 보유·평가 패턴 참조; 운영 포크 제외 | ledger/projector · portfolio/valuation |
| 7 | [qlib](https://github.com/microsoft/qlib) | 49,498 | 후속 ML 연구 패키지 후보 | research/experiment_runner · model_registry |
| 8 | [vnpy](https://github.com/vnpy/vnpy) | 45,942 | Gateway 계약 패턴 참조 | brokers/base · brokers/kis · execution/reconciler |
| 9 | [ccxt](https://github.com/ccxt/ccxt) | 44,461 | MCP 권한 패턴 참조; 거래 라이브러리 제외 | tool_gateway · approval_service · audit_log |
| 10 | [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 35,864 | 연구 근거·환경 capability 패턴 참조 | broker_capabilities · environment_guard · evidence_store |
| 11 | [FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal) | 32,727 | 일반 개념 참고; 코드·UI 채택 보류 | market_data/subscriptions · reporting/read_models |
| 12 | [TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) | 32,344 | 모델 역할 분리 패턴 참조; 전체 포크 보류 | investment_ai/model_policy · review |
| 13 | [nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | 30,322 | 주문 복구 패턴 참조; 초기 엔진 도입 보류 | execution/order_state · recovery · ledger/reconciliation |
| 14 | [yfinance](https://github.com/ranaroussi/yfinance) | 25,551 | 연구 전용 선택 패키지 후보 | research_data/providers/yahoo |
| 15 | [backtrader](https://github.com/mementum/backtrader) | 23,513 | Broker 계약 참고; 초기 엔진 제외 | brokers/contracts · simulation/contracts |
| 16 | [akshare](https://github.com/akfamily/akshare) | 22,985 | 데이터·도구 카탈로그 패턴 참조 | data/catalog · mcp/tool_registry |
| 17 | [AI-Trader](https://github.com/HKUDS/AI-Trader) | 22,850 | 신호/체결/검토 분리 개념 참고; 코드 보류 | research/proposals · execution/events · review/notes |
| 18 | [Lean](https://github.com/QuantConnect/Lean) | 22,093 | 별도 백테스트 worker 1순위 후보 | research/backtest_worker · portfolio/targets · risk/policies |
| 19 | [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 21,421 | AI 업무별 평가 패턴 참조; 초기 파인튜닝 보류 | investment_ai/evaluation · evidence_extraction |
| 20 | [hummingbot](https://github.com/hummingbot/hummingbot) | 20,574 | 운영·격리 패턴 참조; 거래 엔진 제외 | runtime/supervisor · ops/cli · ops/health |

## 프로젝트별 계약과 완료 기준

직접 코드 복사 범위는 이번 조사에서 승인하지 않았다. 패턴 참고는 QuantHarbor 계약에 맞춘 자체 구현을 뜻한다. 패키지 후보도 라이선스·데이터 권리·버전·운영 부담을 확인한 뒤 도입한다.

### 1. TauricResearch/TradingAgents

- **방식:** 패턴 참조.
- **적용 위치:** `research_orchestrator · evidence_store`. 작업 ENV-03·08, H01·02·07·08.
- **입출력 계약:** ResearchTask(종목·as_of·데이터버전·질문·예산) → ResearchReport(주장·근거ID·반대근거·불확실성·만료).
- **변경·제한:** 보고서의 각 수치에 출처를 연결한다. 대화 상태 분리 외에 컨테이너·파일·네트워크·키 격리가 필요하다. AI 합의만으로 사실 검증을 완료하지 않는다.
- **향후 완료 기준:** 분석가 하나의 실패가 다른 결과를 손상시키지 않고, 근거 없는 수치는 보류되며 연구 worker에 주문 권한이 없다.
- **고정 근거:** [tradingagents/graph/setup.py](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/graph/setup.py) · commit `e8f5503e9b86`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 2. openbq-org/OpenBB

- **방식:** 패턴 + 선택 공급자 패키지 후보.
- **적용 위치:** `market_data/providers · normalizer`. 작업 B02·03, E01·03·04·06·07.
- **입출력 계약:** DataQuery → DataEnvelope(출처·발표/수집/효력시점·통화·조정정책·품질·버전).
- **변경·제한:** 타입 정규화에 시점 정합성·단위·데이터 이용권리를 더한다. 대체 공급자의 값도 조정 방식과 단위가 같을 때만 교환한다.
- **향후 완료 기준:** 공급자 코드가 내부 종목ID로 매핑되고, 지연·결측·미래 정정자료 유입을 식별한다. 필요한 공급자만 연구 환경에 설치한다.
- **고정 근거:** [openbb_platform/core/openbb_core/provider/abstract/fetcher.py](https://github.com/openbq-org/OpenBB/blob/78020ee4b864ab50b8c1f56373877c2b4e7fb623/openbb_platform/core/openbb_core/provider/abstract/fetcher.py) · commit `78020ee4b864`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 3. ZhuLinsen/daily_stock_analysis

- **방식:** 보고·전송 패턴 참조.
- **적용 위치:** `reporting · notification_outbox`. 작업 E01·02·06, J01~04.
- **입출력 계약:** ReportRequest(원장스냅샷·시장세션·대사상태) → ReportArtifact → DeliveryReceipt(보고버전·청크·메시지ID).
- **변경·제한:** 국내 종목을 6자리 숫자만으로 중국 종목으로 추정하지 않는다. 한국 원화 회계를 자체 원장에서 공급한다. 원본의 순차 전송 결과만으로 부분 전송 복구가 충분하지 않으므로 청크별 영수증을 저장한다.
- **향후 완료 기준:** 미대사 보고는 잠정 표시, 수치는 원장 버전과 일치, 실패한 청크만 재시도하며 보고 worker는 읽기 전용이다.
- **고정 근거:** [docs/market-support.md](https://github.com/ZhuLinsen/daily_stock_analysis/blob/7a21cd76952c7fe44a7fc5a6113a5b2b8a16bb32/docs/market-support.md) · commit `7a21cd76952c`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 4. virattt/ai-hedge-fund

- **방식:** 목표·리밸런싱 패턴 참조.
- **적용 위치:** `portfolio/target_validator · rebalance/planner`. 작업 F01~03·08, G05·06, I04·05.
- **입출력 계약:** TargetPlan(mode=full|patch) + Snapshot + OpenOrders + Quotes → RebalancePlan(의도·잔여현금·제약·보류이유).
- **변경·제한:** 원본은 누락 목표를 0으로 간주한다. patch 누락은 보유 유지로 정의한다. Decimal·통화별 가용금·미체결 예약금·비용·호가/수량단위를 반영한다. 매도 제출과 사용 가능한 현금을 구분한다.
- **향후 완료 기준:** patch 누락으로 임의 청산이 생기지 않고 동일 입력 계획이 재현된다. 실전 원장은 rewind 대신 증빙 있는 정정 이벤트를 남긴다.
- **고정 근거:** [hedge_fund/pipeline/execution.py](https://github.com/virattt/ai-hedge-fund/blob/78b779c1389e2d1452dc29606d2c4126d859b964/hedge_fund/pipeline/execution.py) · commit `78b779c1389e`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 5. freqtrade/freqtrade

- **방식:** 운영 패턴 참조.
- **적용 위치:** `execution/order_monitor · research/validation`. 작업 G03·04, I03·06~08, M01·02.
- **입출력 계약:** TrackedOrder + BrokerObservation + MarketSession → OrderTransition / 조회·취소·중단 요청.
- **변경·제한:** 24시간 암호화폐 규칙을 휴장·세션·거래정지 규칙으로 바꾼다. timeout은 즉시 실패·재전송이 아닌 UNKNOWN이다. GPL 코드 직접 이식을 초기안에 넣지 않는다.
- **향후 완료 기준:** 통보 누락·부분체결 후 취소·수수료 변경을 조회로 맞추고, 미래정보 검사 한계와 백테스트/실전 callback 차이를 기록한다.
- **고정 근거:** [docs/bot-basics.md](https://github.com/freqtrade/freqtrade/blob/3ce38b587d6c7a1ea479fb3e59d724dee5195561/docs/bot-basics.md) · commit `3ce38b587d6c`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 6. maybe-finance/maybe

- **방식:** 보유·평가 패턴 참조; 운영 포크 제외.
- **적용 위치:** `ledger/projector · portfolio/valuation`. 작업 F02·04~06·08.
- **입출력 계약:** LedgerEvents + PriceSnapshot + FXSnapshot → PortfolioSnapshot(수량·현금·평가상태·이벤트커서).
- **변경·제한:** 원본은 가격 없는 보유 생성을 건너뛴다. 보유 수량은 남기고 평가를 unknown으로 둔다. 총액에 맞추기 위해 현금을 역산하여 대사 차이를 숨기지 않는다. archived 상태다.
- **향후 완료 기준:** 가격 누락 자산도 보유 목록에 남고 같은 이벤트 재생 시 수량이 같다. 불일치의 원인·증거·정정 이력이 추적된다.
- **고정 근거:** [app/models/holding/forward_calculator.rb](https://github.com/maybe-finance/maybe/blob/77b5469832758d1cbee1a940f3012a1ae1c74cd3/app/models/holding/forward_calculator.rb) · commit `77b546983275`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 7. microsoft/qlib

- **방식:** 후속 ML 연구 패키지 후보.
- **적용 위치:** `research/experiment_runner · model_registry`. 작업 D02·07, E07, G02~04·07.
- **입출력 계약:** ExperimentSpec(데이터·종목군·기간·feature/label·비용·seed) → Run(예측·성과·편향검사·계보).
- **변경·제한:** 국장·미장 달력/비용을 추가하고 feature 발표시각과 label horizon 겹침을 통제한다. ML은 초기 필수 요소가 아니다.
- **향후 완료 기준:** 동일 입력의 실험을 재현하고 기준 전략과 비용 반영 비교가 가능하다. 연구 컨테이너에 실전 키가 없다.
- **고정 근거:** [docs/component/workflow.rst](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/docs/component/workflow.rst) · commit `543552324638`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 8. vnpy/vnpy

- **방식:** Gateway 계약 패턴 참조.
- **적용 위치:** `brokers/base · brokers/kis · execution/reconciler`. 작업 I01~03·05·06·08, F05.
- **입출력 계약:** BrokerCommand(계좌·환경·intent) → BrokerEvent(주문/체결ID·상태·수량·가격·통화·시각·원문참조).
- **변경·제한:** ID를 계좌·환경·거래일과 묶는다. 원본의 connect 오류 로그만으로는 READY 판정이 불충분하다. 응답 유실은 REJECTED가 아니라 UNKNOWN으로 분리한다.
- **향후 완료 기준:** 계좌·보유·주문·체결의 완전한 조회와 대사 이후에만 READY. 중복·역순 이벤트를 처리하며 KIS/키움 어댑터는 별도 구현한다.
- **고정 근거:** [vnpy/trader/gateway.py](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/vnpy/trader/gateway.py) · commit `c6e231caf32b`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 9. ccxt/ccxt

- **방식:** MCP 권한 패턴 참조; 거래 라이브러리 제외.
- **적용 위치:** `tool_gateway · approval_service · audit_log`. 작업 ENV-06~08, D01·05·06, H05·06, J05.
- **입출력 계약:** ToolRequest(역할·계좌·행위·제안·정책) → PolicyDecision / AuditEvent.
- **변경·제한:** 연구 AI에 주문·환전·이체 도구를 노출하지 않는다. 승인 기록을 사용자·계좌·환경·계획hash·만료에 결속한다. 도구 목록만 숨기는 것으로 파일 접근 권한을 대체하지 않는다.
- **향후 완료 기준:** 만료·변조·중복 승인을 거절하고 실행 직전 잔고·가격·위험을 다시 검사한다. CCXT를 국내 주식 어댑터로 사용하지 않는다.
- **고정 근거:** [mcp/README.md](https://github.com/ccxt/ccxt/blob/dd23ee988b8ada0fa397801dc36f81e45583b046/mcp/README.md) · commit `dd23ee988b8a`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 10. HKUDS/Vibe-Trading

- **방식:** 연구 근거·환경 capability 패턴 참조.
- **적용 위치:** `broker_capabilities · environment_guard · evidence_store`. 작업 D03·05, H07·08, I01·02·06·08.
- **입출력 계약:** BrokerProfile(계좌·환경·기능·허용host) + OrderIntent → CapabilityCheck.
- **변경·제한:** 확인한 KIS connector의 live 주문은 거부된다. 공개 모의 코드도 실계좌 검증 증거가 아니다. 페이지 상한을 완전한 조회로 간주하지 않는다.
- **향후 완료 기준:** KR/US×paper/live 기능표를 만들고 host/키 혼합을 기동 시 거부한다. complete=false 조회에서 위험 증가 주문을 보류한다.
- **고정 근거:** [agent/src/trading/connectors/kis/sdk.py](https://github.com/HKUDS/Vibe-Trading/blob/c546e877274e7d36056c042808e1a875d9081eb9/agent/src/trading/connectors/kis/sdk.py) · commit `c546e877274e`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 11. Fincept-Corporation/FinceptTerminal

- **방식:** 일반 개념 참고; 코드·UI 채택 보류.
- **적용 위치:** `market_data/subscriptions · reporting/read_models`. 작업 E03·06, J06, ARC-03·04.
- **입출력 계약:** Subscription → DataSnapshot(원천시각·수신시각·만료·품질).
- **변경·제한:** 구독 공유·캐시 원리는 참고하되 단일 프로세스 모듈화는 격리가 아니다. LICENSE에 상업·사내사용 추가 조건이 있어 코드·UI 복제는 보류한다.
- **향후 완료 기준:** 중복 수집을 줄이고 캐시 만료를 소비자에 전달한다. 화면에 마지막 값을 표시하더라도 만료 가격으로 신규 주문을 허용하지 않는다.
- **고정 근거:** [LICENSE](https://github.com/Fincept-Corporation/FinceptTerminal/blob/3d8617cae3f13c93874d4bee4fb0f2846e9c83bc/LICENSE) · commit `3d8617cae3f1`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 12. hsliuping/TradingAgents-CN

- **방식:** 모델 역할 분리 패턴 참조; 전체 포크 보류.
- **적용 위치:** `investment_ai/model_policy · review`. 작업 ENV-04, H01~03·08.
- **입출력 계약:** TaskRequest(역할·근거·기한·예산) → Assessment(주장·불확실성·보류·사용량).
- **변경·제한:** quick/deep 역할과 reasoning.effort를 구분한다. 모델 이름은 현재 가용성으로 관리한다. Apache/독점 구성과 core 의존을 분리 검토한다.
- **향후 완료 기준:** 역할별 스키마·출처·예산 상향 이유를 기록하고 분석가에게 주문 권한을 주지 않는다. 원본 TradingAgents 패턴을 우선한다.
- **고정 근거:** [LICENSE](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/LICENSE) · commit `51060a7682cf`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 13. nautechsystems/nautilus_trader

- **방식:** 주문 복구 패턴 참조; 초기 엔진 도입 보류.
- **적용 위치:** `execution/order_state · recovery · ledger/reconciliation`. 작업 I03·05·06, F05·08, D04.
- **입출력 계약:** OrderIntent + BrokerReport → OrderEvent / ReconciliationResult / TradingPermission.
- **변경·제한:** 비동기 캐시 저장은 주문 전송 전 내구성을 보장하지 않는다. 전송 전에 주문 의도의 영속 저장 완료를 확인하고 계좌별 단일 실행자를 강제한다. 늦은 스냅샷·합성조정·실제체결을 구분한다.
- **향후 완료 기준:** 응답 유실·재시작·역순·부분체결에서 중복 주문/원장 반영을 막는다. 불완전 대사 동안 신규 위험 증가 주문을 차단한다.
- **고정 근거:** [docs/concepts/live.md](https://github.com/nautechsystems/nautilus_trader/blob/8705495b380f9b1569cf048d1c0f664707a67a72/docs/concepts/live.md) · commit `8705495b380f`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 14. ranaroussi/yfinance

- **방식:** 연구 전용 선택 패키지 후보.
- **적용 위치:** `research_data/providers/yahoo`. 작업 B02·03, E03·05~07.
- **입출력 계약:** HistoryQuery(조정정책) → PriceSeries(공급자·버전·품질).
- **변경·제한:** auto_adjust=False도 완전한 원시 체결가가 아니다. 분할·배당 조정을 기록하고 배당 이중 계산을 피한다. 데이터 사용조건을 별도 확인한다.
- **향후 완료 기준:** 국장 suffix·통화·거래일과 기업행동 계산이 일관된다. 실전 주문 가격은 별도 증권사 시세로 검사한다.
- **고정 근거:** [doc/source/advanced/price_adjustment.rst](https://github.com/ranaroussi/yfinance/blob/2081dca0b224512ff768f9c5e6bd9c658a3b8339/doc/source/advanced/price_adjustment.rst) · commit `2081dca0b224`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 15. mementum/backtrader

- **방식:** Broker 계약 참고; 초기 엔진 제외.
- **적용 위치:** `brokers/contracts · simulation/contracts`. 작업 I02·08, G03.
- **입출력 계약:** BrokerCommand → Ack/Event; Account/Position/OpenOrders 조회.
- **변경·제한:** 현금을 원통화별 가용금·예약금·미결제금으로 분리한다. 접수·체결과 환경 capability를 구분한다. 두 번째 백테스트 엔진 도입과 GPL 직접 이식은 초기 제외한다.
- **향후 완료 기준:** 모의/실전이 같은 계약을 쓰면서 미지원 기능은 명시 거부한다. 오래된 연결 예제의 현재 호환성을 추정하지 않는다.
- **고정 근거:** [backtrader/broker.py](https://github.com/mementum/backtrader/blob/b853d7c90b6721476eb5a5ea3135224e33db1f14/backtrader/broker.py) · commit `b853d7c90b67`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 16. akfamily/akshare

- **방식:** 데이터·도구 카탈로그 패턴 참조.
- **적용 위치:** `data/catalog · mcp/tool_registry`. 작업 B03, E04·07, H05.
- **입출력 계약:** ToolSearch(질의·역할·시장) → 허용 ToolDescriptor(스키마·출처·권리·신선도·버전).
- **변경·제한:** 검색 점수는 데이터 신뢰도가 아니다. 발견 가능성과 실행 권한을 분리한다. 국내·미국용 공급자와 데이터 저장/AI 제공 조건을 등록한다.
- **향후 완료 기준:** 미등록·권한 없는·스키마가 바뀐 도구는 거부하고 호출 버전을 재현한다. 중국 중심 전체 패키지를 주 데이터원으로 채택하지 않는다.
- **고정 근거:** [docs/registry.md](https://github.com/akfamily/akshare/blob/fe10d1decb705e5f43cc8ca3339ca39e580fb8f4/docs/registry.md) · commit `fe10d1decb70`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 17. HKUDS/AI-Trader

- **방식:** 신호/체결/검토 분리 개념 참고; 코드 보류.
- **적용 위치:** `research/proposals · execution/events · review/notes`. 작업 H01·07, F02, J01.
- **입출력 계약:** ResearchProposal / ExecutionRecord / ReviewNote를 ID·근거로 연결.
- **변경·제한:** AI 서술을 실제 체결로 인정하지 않는다. 공개 server README의 proprietary 문구와 LICENSE 부재 때문에 MIT 배지만으로 재사용하지 않는다.
- **향후 완료 기준:** 제안·승인·접수·체결 상태가 보고에서 구분되고 증권사 증빙과 연결된다. 외부 신호가 자동으로 주문 권한을 얻지 않는다.
- **고정 근거:** [service/README.md](https://github.com/HKUDS/AI-Trader/blob/d03ff6c056b32ced735adf7c19ed8175adb1c8df/service/README.md) · commit `d03ff6c056b3`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 18. QuantConnect/Lean

- **방식:** 별도 백테스트 worker 1순위 후보.
- **적용 위치:** `research/backtest_worker · portfolio/targets · risk/policies`. 작업 B04, G01·03~06, D02.
- **입출력 계약:** BacktestJob(전략·데이터·달력·비용·FX·seed) → Manifest / TargetTimeline / SimulatedFills / Metrics.
- **변경·제한:** 동일가중 예제 기본값 LONG_SHORT를 정책에 맞게 명시 설정한다. 국장 달력·호가단위·통화·현금 하한을 추가한다. 예제 낙폭 모델을 계좌 전체 손실 보장으로 취급하지 않는다.
- **향후 완료 기준:** 국장·미장 비용·배당·환율과 결과가 재현되고 공통 목표안으로 변환된다. 연구 worker에는 실전 키가 없으며 KIS live 지원을 가정하지 않는다.
- **고정 근거:** [Algorithm.Framework/Portfolio/EqualWeightingPortfolioConstructionModel.py](https://github.com/QuantConnect/Lean/blob/d4cac37514427c84d40064cecbf3f0e6be4b0137/Algorithm.Framework/Portfolio/EqualWeightingPortfolioConstructionModel.py) · commit `d4cac3751442`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 19. AI4Finance-Foundation/FinGPT

- **방식:** AI 업무별 평가 패턴 참조; 초기 파인튜닝 보류.
- **적용 위치:** `investment_ai/evaluation · evidence_extraction`. 작업 H03·08, E04.
- **입출력 계약:** EvaluationCase(문서·as_of·정답사실·근거) → TaskScore / 오류유형 / 비용·지연.
- **변경·제한:** 한국 공시·SEC 문서·종목·단위·통화·시점 오류 정답셋을 추가한다. 구조 완전성 점수와 사실 정확도·투자성과는 별도다.
- **향후 완료 기준:** 모델 변경의 근거 일치·보류 성능·비용·회귀를 비교할 수 있다. 코드·가중치·데이터 이용조건은 각각 검토한다.
- **고정 근거:** [fingpt/FinGPT_Benchmark/readme.md](https://github.com/AI4Finance-Foundation/FinGPT/blob/fdb04c9a273d1ccc3764b09b8e3ed1e708e57566/fingpt/FinGPT_Benchmark/readme.md) · commit `fdb04c9a273d`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

### 20. hummingbot/hummingbot

- **방식:** 운영·격리 패턴 참조; 거래 엔진 제외.
- **적용 위치:** `runtime/supervisor · ops/cli · ops/health`. 작업 ENV-08, D02~04, C05, M01·02.
- **입출력 계약:** RunSpec(환경·계좌·전략·설정·자원한도) → RunStatus(heartbeat·health·대사시각·오류).
- **변경·제한:** 컨테이너에 DB·키·큐·네트워크 권한을 결합한다. stop의 원본 의미를 그대로 복사하지 않고 신규주문중지·취소·청산을 분리한다. CLI의 향후 계획을 현재 기능으로 표시하지 않는다.
- **향후 완료 기준:** 중복 실행자를 거절하고 오래된 heartbeat를 정상으로 표시하지 않는다. 버전·중단·복구 상태가 남으며 실행 중 자동 업데이트를 막는다.
- **고정 근거:** [hummingbot/cli/README.md](https://github.com/hummingbot/hummingbot/blob/9af100d6822da7d2d0291a906c730ef172284ee2/hummingbot/cli/README.md) · commit `9af100d6822d`. 추가 근거는 [기존 프로젝트별 조사](oss-survey.md)를 따른다.

## 통합 적용 결정

### 1. 초기 직접 의존성은 작게 유지

- **LEAN:** 연구/백테스트 worker의 1순위 검토 후보. 국장·미장 데이터와 시장 규칙 적합성 확인 후 버전 고정.
- **OpenBB:** 실제로 필요한 공급자가 있을 때만 해당 구성 도입 검토.
- **yfinance:** 이용조건을 충족하는 연구 데이터 보조원으로만 검토.
- **Qlib:** 단순 기준 전략과 실험 기록이 갖춰진 뒤 ML 연구가 필요할 때 도입 검토.
- **Nautilus·vn.py·Backtrader·Freqtrade·Hummingbot:** 초기에는 계약·복구·운영 패턴만 참고. 여러 실행 엔진이 동시에 계좌 상태를 소유하는 구조를 만들지 않는다.
- **FinceptTerminal·TradingAgents-CN·AI-Trader:** 소스 이용조건 불명확/혼합 구성에 해당하는 코드 채택 보류. 일반 원리를 독립적으로 설계한다.

### 2. 원장·실행 책임을 한곳으로 모으기

```mermaid
flowchart LR
    D[버전 데이터와 근거] --> R[격리된 연구 AI·백테스트]
    R --> P[목표 포트폴리오 제안]
    P --> V[독립 검토·코드 검사]
    V --> A[승인 또는 승인된 정책]
    A --> E[계좌별 단일 실행자]
    E --> I[주문 의도 영속 저장 완료]
    I --> B[증권사 어댑터]
    B --> L[주문·체결·현금 원장과 대사]
    L --> S[조회 스냅샷·보고 outbox]
    S --> N[Slack·검토·학습]
```

원장은 PostgreSQL의 주문 의도·체결/현금 이벤트·정정 이력과 대사 결과를 기준으로 설계한다. Parquet/객체 저장소는 시세·문서·연구 산출물에 사용한다. 보고 숫자는 원장 스냅샷에서 계산하고 AI는 근거를 설명한다. 정기 리밸런싱도 현재 보유·미체결·가용금·통화·비용을 다시 확인한다. DB 선택 자체가 중복 없는 실행을 보장하지는 않는다.

### 3. 제품 철학을 검증 가능한 요구로 연결

| 철학 | 설계 결과 | 주요 참고 |
|---|---|---|
| 근거 있는 판단 | 출처·발표/수집시각·데이터/모델/전략 버전·반대근거 | TradingAgents, OpenBB, Qlib, FinGPT |
| 사용자의 통제 | 승인 범위·만료·위험 검사·중지/취소/청산 분리 | CCXT, Hummingbot 및 자체 정책 |
| 자산·위험 가시화 | 가격 누락 자산 보존·통화별 현금·대사 차이 표시 | Maybe, ai-hedge-fund |
| 검증 후 확대 | 재현 가능한 연구→모의→제한된 실전과 승격 기록 | LEAN, Qlib, Freqtrade |
| 역할 분리 | 연구는 제안, 실행은 코드; 보고는 읽기 전용 | TradingAgents, vn.py 계약 |
| 실패 격리·복구 | UNKNOWN·완전한 조회·단일 실행자·기동 대사 | Nautilus, vn.py, Freqtrade |
| 기록·학습 | 제안/체결/검토 구분·보고 정정·업무별 평가 | AI-Trader 개념, daily, FinGPT |

### 4. 적용 순서

1. **ENV 먼저:** 역할 출력·도구 권한·격리·근거 기록·모델/비용 상한을 명세한다. ENV 완료 조건을 충족한다.
2. **ARC:** BrokerPort, DataEnvelope, LedgerEvent, TargetPlan, ReportArtifact 계약과 데이터 소유권을 확정한다. 증권사 선택은 [별도 결정안](broker-selection.md)을 따른다.
3. **데이터·원장:** 종목·달력·통화·시점·이벤트·조회 스냅샷과 잔고·주문·체결 조회 전용 증권사 어댑터를 구현하고 대사에 연결한다. 보고는 이 단계부터 붙인다.
4. **연구·목표안:** 기준 전략, LEAN 검토, full/patch·비용·미체결을 반영한 리밸런싱을 구현한다.
5. **주문·운영:** 모의/실전 capability, 주문 제출·정정·취소와 실행 상태기를 구현한 뒤 요청된 검증을 수행한다. 모의 관찰과 별도 승인된 소액 실전을 거쳐 범위를 확대한다.

## 높은 스타지만 제외한 항목

추가 검색에서 20위 기준 이상인 아래 9개는 범위 기준에 따라 제외했다. 낮은 스타 후보를 임의로 올리기 위한 제외가 아니라 비교 대상의 정의를 공개한 것이다. 범위를 가계부·결제·범용 AI 도구까지 넓히면 순위도 달라진다.

| 프로젝트 | Stars | 제외 이유 |
|---|---:|---|
| [unionlabs/union](https://github.com/unionlabs/union) | 73,737 | 블록체인 브리지 인프라; 투자 연구·포트폴리오·매매 엔진 범위 밖 |
| [juspay/hyperswitch](https://github.com/juspay/hyperswitch) | 45,359 | 결제 오케스트레이션; 증권 매매·투자 원장 대상 아님 |
| [ashishpatel26/500-AI-Agents-Projects](https://github.com/ashishpatel26/500-AI-Agents-Projects) | 38,796 | 프로젝트 링크 모음 |
| [wilsonfreitas/awesome-quant](https://github.com/wilsonfreitas/awesome-quant) | 30,198 | 프로젝트 링크 모음 |
| [actualbudget/actual](https://github.com/actualbudget/actual) | 29,605 | 지출·예산 관리 중심; 이번 증권 보유·거래·연구 비교 범위 밖 |
| [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) | 28,383 | 여러 산업의 범용 skill 모음 |
| [firefly-iii/firefly-iii](https://github.com/firefly-iii/firefly-iii) | 24,938 | 지출·수입·예산 관리 중심; 이번 증권 투자 비교 범위 밖 |
| [plotly/dash](https://github.com/plotly/dash) | 24,458 | 범용 대시보드 프레임워크 |
| [stefan-jansen/machine-learning-for-trading](https://github.com/stefan-jansen/machine-learning-for-trading) | 21,455 | 교재 부속 코드; 운영 프로젝트 비교에서 제외 |

Maybe는 실제 증권 보유·거래·평가 소스를 확인했기 때문에 포함했다. Actual/Firefly는 이번 조사에서 확인한 예산·지출 중심 제품 범위 때문에 제외했다. 제외된 프로젝트 전체 기능을 감사한 것은 아니다.
