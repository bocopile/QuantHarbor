# 오픈소스 20개 조사 기록

조사 기준일: 2026-10-19. 기존 대화에서 공식 저장소의 README·라이선스·핵심 코드 또는 구조 문서를 읽어 정리한 결과다. 설치·실행·수익성·실계좌 검증은 수행하지 않았다. 선정 20개의 링크는 후속 재조사에서 확인한 commit으로 고정했다. 이 commit은 조사 근거이며 채택 시 운영 release와 조건을 별도로 결정한다. 최신 적용 계약은 [OSS 적용 결정안](oss-application-plan.md), 순위 근거는 [확장 메타데이터](github-evidence-2026-10-19.json)를 따른다.

## 선정 방법

자동매매·금융 AI·백테스트·데이터·포트폴리오 관리 범위를 조사했다. 11개 검색에서 530개 결과를 수집하고, 중복 및 범위 밖 대상을 정리한 후보 99개의 GitHub 메타데이터를 조회했다. 그 후보군 안에서 스타 순 20개를 검토했다. 후속 조사에서는 99개를 갱신하고 4개 검색의 신규 122개를 더해 총 221개 메타데이터를 비교했으며 범위 내 상위 20개 구성은 유지됐다. 아래 표의 스타 수는 후속 재조회값이다. GitHub 전체에 대한 절대 순위나 모든 파일의 보안 감사는 아니다.

검색어: `algorithmic-trading`, `trading-agent`, `quantitative-finance`, `portfolio-management`, `backtesting`, `financial-data`, `trading-bot`, `trading`, `finance`, `hedge-fund`, `portfolio tracker`. 검색에는 `sort:stars-desc`를 사용했고 스타 수는 저장소 메타데이터로 확인했다. [후보 99개 메타데이터 기록](github-candidates-2026-10-19.json)을 함께 보관한다. 이 기록의 license 필드는 API 자동 분류이며 실제 LICENSE 검토 결과는 아래 설명을 우선한다.

강의·링크 모음·범용 개발 도구는 제외했다. 암호화폐 전용 프로젝트는 운영 설계 참고를 위해 포함했다. 자산관리 앱 Maybe는 보유·거래·평가 구조를 포함하므로 포함했다. 스타 수는 수익성·안전성·한국 시장 적합성을 의미하지 않는다.

## 스타 순위와 판단

| 순위 | 프로젝트 | Stars | 참고할 설계 | 제약·라이선스 |
|---:|---|---:|---|---|
| 1 | [TradingAgents](https://github.com/TauricResearch/TradingAgents) | 111977 | 독립 분석가 상태·찬반 연구·위험 검토 | 연구·모의 중심, 국내 주문 별도. Apache-2.0 |
| 2 | [OpenBB](https://github.com/openbq-org/OpenBB) | 74428 | 공급자 정규화·Python/REST/MCP | 데이터 조건과 국내 범위 별도. LICENSE Apache-2.0 |
| 3 | [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) | 66719 | 정기 분석·품질 표시·Slack | 한국 기능은 제한적이며 KRW 회계 미완성. MIT |
| 4 | [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | 64081 | 목표 검증·주문 차이·모의 원장 | README가 실거래 제외 명시. MIT |
| 5 | [Freqtrade](https://github.com/freqtrade/freqtrade) | 55592 | dry-run/live·상태 재조회·미체결 | 암호화폐 중심. GPL-3.0 |
| 6 | [Maybe](https://github.com/maybe-finance/maybe) | 54217 | 거래→보유/평가·스냅샷·조정 | 유지보수 중단·archived. AGPL-3.0 |
| 7 | [Qlib](https://github.com/microsoft/qlib) | 49498 | 학습·시계열 평가·실험·최적화 | 한국 데이터/달력 필요, 예측과 주문 구분. MIT |
| 8 | [vn.py](https://github.com/vnpy/vnpy) | 45942 | Gateway·계좌/주문/체결 이벤트 | 확인한 공식 목록에 KIS·키움 없음. MIT |
| 9 | [CCXT](https://github.com/ccxt/ccxt) | 44461 | 공통 API·MCP 권한·감사 | 주식 증권사 연결용 아님. MIT |
| 10 | [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 35864 | 연구 근거·스냅샷·예산·예약 보고 | KIS 모의 주문 지원, KIS 실전 주문 미구현. MIT |
| 11 | [FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal) | 32727 | 데이터 구독 공유·통합 투자 단말 | 라이선스 추가 제한·문서 충돌, 코드 채택 보류 |
| 12 | [TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) | 32344 | 학습·토론·quick/deep 역할 | 중국 A주 중심, Apache/독점 구성 혼합 |
| 13 | [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | 30322 | 이벤트 실행·unknown·기동 대사 | develop v2 RC 전환기, 국내 어댑터 별도. LGPL-3.0 |
| 14 | [yfinance](https://github.com/ranaroussi/yfinance) | 25551 | 연구 가격·재무·뉴스 | 비공식 Yahoo 접근·데이터 약관 별도. Apache-2.0 |
| 15 | [Backtrader](https://github.com/mementum/backtrader) | 23513 | 시뮬레이션/실전 Broker 계약 | 메타데이터 마지막 push 2024-08-19, 호환성 확인 필요. GPL-3.0 |
| 16 | [AKShare](https://github.com/akfamily/akshare) | 22985 | API 카탈로그·스키마·출처 | 중국 중심, 데이터 조건 별도. MIT |
| 17 | [AI-Trader](https://github.com/HKUDS/AI-Trader) | 22850 | 신호/체결/토론 분리·동기화 | MIT 배지와 LICENSE 부재·독점 서버 문구, 채택 보류 |
| 18 | [LEAN](https://github.com/QuantConnect/Lean) | 22093 | 유니버스·목표·위험·실행 분리 | C#/Python 운영 부담·국내 live 어댑터 확인. Apache-2.0 |
| 19 | [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | 21421 | 금융 NLP 업무별 평가셋 | 국문 성능·기반 모델/데이터 조건 별도. MIT |
| 20 | [Hummingbot](https://github.com/hummingbot/hummingbot) | 20574 | controller/executor·컨테이너·CLI | 암호화폐 중심, 일부 기능은 향후 계획. Apache-2.0 |

`pushed_at`은 기본 브랜치 최종 commit 시각과 다를 수 있다. 해당 값만으로 유지보수 품질을 판정하지 않는다. GitHub API의 `NOASSERTION`은 라이선스가 없다는 뜻으로 단정하지 않았다.

## 프로젝트별 핵심 근거와 적용

### 1 TradingAgents

[graph/setup.py](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/graph/setup.py)는 분석가별 private message history와 보고서 단위 병합, 도구 호출 상한을 구현한다. 연구팀 구성에 참고한다. 대화 상태 분리는 OS·권한 격리가 아니므로 별도 환경 통제가 필요하다. 국내 공시·주문 연결은 별도다.

### 2 OpenBB

[Fetcher](https://github.com/openbq-org/OpenBB/blob/78020ee4b864ab50b8c1f56373877c2b4e7fb623/openbb_platform/core/openbb_core/provider/abstract/fetcher.py)의 query 변환→수집→데이터 변환 계약을 참고한다. 공개 데이터 라이브러리와 별도 UI·공급자 서비스를 구분한다. API 메타데이터는 NOASSERTION이었지만 [LICENSE](https://github.com/openbq-org/OpenBB/blob/78020ee4b864ab50b8c1f56373877c2b4e7fb623/LICENSE) 본문은 Apache-2.0으로 확인했다.

### 3 daily_stock_analysis

[시장 지원 범위](https://github.com/ZhuLinsen/daily_stock_analysis/blob/7a21cd76952c7fe44a7fc5a6113a5b2b8a16bb32/docs/market-support.md)는 한국의 Yahoo suffix 기반 MVP와 KRW 포트폴리오 처리 한계를 명시한다. 종목 6자리 코드만으로 국가를 판단하지 않아야 한다. [Slack sender](https://github.com/ZhuLinsen/daily_stock_analysis/blob/7a21cd76952c7fe44a7fc5a6113a5b2b8a16bb32/src/notification_sender/slack_sender.py)의 알림 구현을 참고한다.

### 4 ai-hedge-fund

[execution.py](https://github.com/virattt/ai-hedge-fund/blob/78b779c1389e2d1452dc29606d2c4126d859b964/hedge_fund/pipeline/execution.py)는 목표 비중에서 주문 차이를 만든다. 목표에서 빠진 보유종목은 0으로 간주되므로 전체/부분 변경 계약이 필요하다. [validation.py](https://github.com/virattt/ai-hedge-fund/blob/78b779c1389e2d1452dc29606d2c4126d859b964/hedge_fund/portfolio/validation.py)와 [ledger.py](https://github.com/virattt/ai-hedge-fund/blob/78b779c1389e2d1452dc29606d2c4126d859b964/hedge_fund/paper/ledger.py)를 참고하되 파일·해시 원장을 다중 실행자의 DB 트랜잭션과 동일시하지 않는다. 매도 우선 제출도 체결 현금 확보를 보장하지 않는다.

### 5 Freqtrade

[bot-basics](https://github.com/freqtrade/freqtrade/blob/3ce38b587d6c7a1ea479fb3e59d724dee5195561/docs/bot-basics.md)의 주문 상태·수수료·타임아웃 처리, [lookahead-analysis](https://github.com/freqtrade/freqtrade/blob/3ce38b587d6c7a1ea479fb3e59d724dee5195561/docs/lookahead-analysis.md)의 미래정보 검사와 한계를 참고한다. 암호화폐의 거래시간·수수료·주문 규칙을 주식에 복제하지 않는다.

### 6 Maybe

[ForwardCalculator](https://github.com/maybe-finance/maybe/blob/77b5469832758d1cbee1a940f3012a1ae1c74cd3/app/models/holding/forward_calculator.rb), [PortfolioSnapshot](https://github.com/maybe-finance/maybe/blob/77b5469832758d1cbee1a940f3012a1ae1c74cd3/app/models/holding/portfolio_snapshot.rb), [ReconciliationManager](https://github.com/maybe-finance/maybe/blob/77b5469832758d1cbee1a940f3012a1ae1c74cd3/app/models/account/reconciliation_manager.rb)에서 거래→보유 이력·평가와 조정 기록을 참고한다. 공식 README의 유지보수 종료에 따라 운영 기반 채택은 제외하는 안이다. 복식부기·한국 세무 원장 완성으로 해석하지 않는다.

### 7 Qlib

[workflow](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/docs/component/workflow.rst)와 [portfolio 예제](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/examples/portfolio/README.md)의 시계열 분리·실험 추적·위험모형을 참고한다. [online serving](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/docs/component/online.rst)은 최신 예측과 다음 거래일 주문 생성 지원을 구분한다. 중국 예제 파라미터를 국장·미장에 그대로 적용하지 않는다.

### 8 vn.py

[BaseGateway](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/vnpy/trader/gateway.py)는 이벤트 정규화·재연결·계좌/잔고/주문/체결 조회 계약의 참고점이다. [공식 설명](https://github.com/vnpy/vnpy/blob/c6e231caf32b7fc97e6459817fff66458cf7e7c4/README_ENG.md)의 IB 경로가 한국 거주자의 계좌 이용 가능성을 보장하지는 않는다.

### 9 CCXT

[공식 MCP 문서](https://github.com/ccxt/ccxt/blob/dd23ee988b8ada0fa397801dc36f81e45583b046/mcp/README.md)의 조회·거래·이체 권한, 명시적 실전 설정, 미리보기·확인·감사 구조를 참고한다. 호스트 파일 접근이 허용되면 도구 설정에서 숨긴 credential도 노출될 수 있다는 경계를 함께 고려한다.

### 10 Vibe-Trading

[KIS profiles](https://github.com/HKUDS/Vibe-Trading/blob/c546e877274e7d36056c042808e1a875d9081eb9/agent/src/trading/connectors/kis/profiles.py)와 [sdk.py](https://github.com/HKUDS/Vibe-Trading/blob/c546e877274e7d36056c042808e1a875d9081eb9/agent/src/trading/connectors/kis/sdk.py)는 paper/live host 분리와 KIS live 주문 거부를 확인할 근거다. KIS 증권사가 실전 API를 제공하지 않는다는 의미가 아니다. [Toss profiles](https://github.com/HKUDS/Vibe-Trading/blob/c546e877274e7d36056c042808e1a875d9081eb9/agent/src/trading/connectors/toss/profiles.py)는 조회 전용이다. README의 수치 근거·예산·예약 보고를 참고하며, 실험적 broker 기능을 실계좌 검증 완료로 소개하지 않는다.

### 11 FinceptTerminal

[ARCHITECTURE](https://github.com/Fincept-Corporation/FinceptTerminal/blob/3d8617cae3f13c93874d4bee4fb0f2846e9c83bc/docs/ARCHITECTURE.md)와 [BrokerRegistry](https://github.com/Fincept-Corporation/FinceptTerminal/blob/3d8617cae3f13c93874d4bee4fb0f2846e9c83bc/fincept-qt/src/trading/BrokerRegistry.cpp)를 읽었다. 단일 프로세스 모듈화는 사용자가 요구한 실행환경 격리와 다르다. [LICENSE](https://github.com/Fincept-Corporation/FinceptTerminal/blob/3d8617cae3f13c93874d4bee4fb0f2846e9c83bc/LICENSE)에 AGPL 표기 외 상업·사내 사용 제한이 있으며 README와도 불일치가 있어 코드 채택을 보류한다. 조건의 법적 효력을 판정한 것은 아니다.

### 12 TradingAgents-CN

[LICENSE](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/LICENSE)는 tradingagents/·cli/·docs/·tests/·web/ 등 Apache 구성과 app/·frontend/·core/ 독점 구성을 구분한다. [graph](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/tradingagents/graph/setup.py)는 일부 core import도 포함하므로 디렉터리별 허용만으로 독립 실행 가능성을 추정하지 않는다. [모델 설정](https://github.com/hsliuping/TradingAgents-CN/blob/51060a7682cf51810b4bc3a704829438d18cd8dc/tradingagents/default_config.py)의 quick/deep 구분은 API reasoning.effort와 별개다.

### 13 NautilusTrader

[live 문서](https://github.com/nautechsystems/nautilus_trader/blob/8705495b380f9b1569cf048d1c0f664707a67a72/docs/concepts/live.md)의 unknown 처리·기동 대사·프로세스 제한을 참고한다. 같은 venue의 여러 execution client가 계좌 전체 격리를 보장하지 않는다는 제한을 반영한다. [ADAPTERS](https://github.com/nautechsystems/nautilus_trader/blob/8705495b380f9b1569cf048d1c0f664707a67a72/ADAPTERS.md)와 [README](https://github.com/nautechsystems/nautilus_trader/blob/8705495b380f9b1569cf048d1c0f664707a67a72/README.md)의 v2 RC 전환 상태를 확인했다. 국내 어댑터와 안정된 버전은 별도 검토한다.

### 14 yfinance

[가격 조정 문서](https://github.com/ranaroussi/yfinance/blob/2081dca0b224512ff768f9c5e6bd9c658a3b8339/doc/source/advanced/price_adjustment.rst)를 기준으로 조정 정책을 기록한다. auto_adjust=False도 완전한 원시 체결가격을 뜻한다고 가정하지 않는다. [README](https://github.com/ranaroussi/yfinance/blob/2081dca0b224512ff768f9c5e6bd9c658a3b8339/README.md)의 데이터 이용조건을 확인하며 실전 가격의 유일한 기준으로 사용하지 않는 안이다.

### 15 Backtrader

[BrokerBase](https://github.com/mementum/backtrader/blob/b853d7c90b6721476eb5a5ea3135224e33db1f14/backtrader/broker.py)의 현금·평가·포지션·주문·취소 계약을 참고한다. [README](https://github.com/mementum/backtrader/blob/b853d7c90b6721476eb5a5ea3135224e33db1f14/README.rst)의 오래된 연결 설명과 현재 호환성을 구분한다. 신규 실거래 주력 엔진의 우선순위는 낮게 둔다.

### 16 AKShare

[API registry](https://github.com/akfamily/akshare/blob/fe10d1decb705e5f43cc8ca3339ca39e580fb8f4/docs/registry.md)의 함수 검색·입출력 스키마·원천 URL을 참고한다. 모든 도구를 모델에 노출하기보다 업무 관련 도구를 검색해 제한한다. 소프트웨어 MIT와 원천 데이터의 학술·개인 사용 조건은 구분한다.

### 17 AI-Trader

현재 main에서 [agent API](https://github.com/HKUDS/AI-Trader/blob/d03ff6c056b32ced735adf7c19ed8175adb1c8df/docs/README_AGENT.md), [tradesync](https://github.com/HKUDS/AI-Trader/blob/d03ff6c056b32ced735adf7c19ed8175adb1c8df/skills/tradesync/SKILL.md), [trading routes](https://github.com/HKUDS/AI-Trader/blob/d03ff6c056b32ced735adf7c19ed8175adb1c8df/service/server/routes_trading.py)를 확인했다. README의 MIT 배지와 달리 조사한 전체 tree에 LICENSE가 없고 [service README](https://github.com/HKUDS/AI-Trader/blob/d03ff6c056b32ced735adf7c19ed8175adb1c8df/service/README.md)는 proprietary implementation이라고 명시한다. 실제 증권사 주문 어댑터를 입증하지 못했으므로 코드 채택을 보류한다. a-stock은 중국 A주다.

### 18 LEAN

[동일가중 모델](https://github.com/QuantConnect/Lean/blob/d4cac37514427c84d40064cecbf3f0e6be4b0137/Algorithm.Framework/Portfolio/EqualWeightingPortfolioConstructionModel.py)과 [낙폭 리스크 모델](https://github.com/QuantConnect/Lean/blob/d4cac37514427c84d40064cecbf3f0e6be4b0137/Algorithm.Framework/Risk/MaximumDrawdownPercentPortfolio.py)의 목표·위험·실행 분리를 참고한다. 예제 리스크 모델은 계좌 전체 손실 상한 보장이 아니다. [KIS 공식 백테스터](https://github.com/koreainvestment/open-trading-api/blob/main/backtester/README.md)에서 LEAN 활용을 확인했지만 KIS live 어댑터·복구 완료의 근거로 확대하지 않는다.

### 19 FinGPT

[태스크별 벤치마크](https://github.com/AI4Finance-Foundation/FinGPT/blob/fdb04c9a273d1ccc3764b09b8e3ed1e708e57566/fingpt/FinGPT_Benchmark/readme.md)의 감성·NER·관계추출 등 평가 분리를 참고한다. 영문·중문 결과를 한국 공시 성능으로 일반화하지 않는다. 코드 MIT와 기반 모델·학습 데이터 조건은 별도 확인한다.

### 20 Hummingbot

[CLI 문서](https://github.com/hummingbot/hummingbot/blob/9af100d6822da7d2d0291a906c730ef172284ee2/hummingbot/cli/README.md)의 1설치=1봇, 다중봇 컨테이너, JSON·종료코드·doctor·운영 중 업데이트 제한을 참고한다. 일부 명령은 계획 단계이므로 현재 기능으로 소개하지 않는다. 정지·취소·청산은 우리 운용정책에 맞게 별도 정의한다.

## 채택 방향

연구팀은 TradingAgents, 데이터 계약은 OpenBB, 실험은 Qlib, 목표·위험·실행은 LEAN, 목표 검증은 ai-hedge-fund, 주문·대사는 Nautilus/vn.py, 보고는 daily_stock_analysis, 격리·운영은 Hummingbot/Freqtrade를 우선 참고한다. 구현 채택 범위와 버전은 B05/ARC-08에서 확정한다.
