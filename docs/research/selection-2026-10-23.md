# Q08 요구 기반 외부 선택 기록

확인일: 2026-10-23. 상태: 조사·통합 중. A-DEC-001~003 및 요구 계약 v1을 입력으로 한다. 실제 계좌·데이터 권리·도입 버전·실행 검증과 공개 설계 선택을 구분한다. 기존 2026-10-19 조사 수치와 commit을 오늘의 수치로 바꾸지 않는다.

## B04·05 기술·OSS 적용 선택

아래는 설계 선택이며 설치·호환성 검증 결과가 아니다. 배포 버전·해시·전이 의존성은 C01~03에서 고정하고, 해당 구성요소를 활성화하기 전에 필요한 실행 검증을 수행한다.

| 영역 | 초기 선택 | 이유·조건 | 대안·보류 |
|---|---|---|---|
| 금융 도메인 | Python, Decimal 기반 순수 계산·명시 계약 | 기존 Python 개발 기반을 활용. 금액/수량·통화·반올림을 명시하고 float 유입 거부. 공식 Decimal 문서는 정확한 10진 표현·반올림 제어를 설명 | Python 구체 버전은 C01 의존성 호환 후 고정. 최신이라는 이유만으로 업그레이드하지 않음 |
| 영속 업무 상태 | PostgreSQL, numeric·명시 transaction·제약 | 원장·승인·주문 의도·outbox의 저장 경계와 동시성 통제를 같은 DB에서 설계 | 로컬 fixture/in-memory는 합성 테스트 전용. DB를 썼다는 이유만으로 exactly-once 주장 금지 |
| 연구 데이터 | Parquet 파일·manifest·출처/권리/시점/해시 | 컬럼 형식과 데이터 버전 분리. 초기에는 로컬 저장, 원장 정본과 분리 | 객체 저장 서비스·유료 데이터는 초기 필수에서 제외 |
| 백테스트 | LEAN 엔진을 별도 연구 실행 경로의 1순위로 유지 | 자체 도메인·BrokerPort·원장과 분리. 직접 소스 빌드·Launcher 경로와 데이터 주입을 고정 버전으로 검증 후 사용 | 유료 LEAN CLI/Cloud는 도입 보류. 자체 합성 체결기는 장애/계약 검사 용도이며 투자 성과 백테스터의 대체 검증 결과가 아님 |
| 실행/원장 | 자체 계약·자체 구현 | 승인·재시도·계좌 환경·부분체결/불완전 조회를 제품 요구에 맞춰 통제 | 프레임워크 전체 포크, 직접 주문 MCP, 여러 실행 엔진 동시 도입 제외 |
| 초기 사용자 조작 | 로컬 수동 세션·승인 인터페이스 | 시작/종료는 사용자, 가동 중 분석15분. 후보별 승인·중단·재가동 상태 표시 | 원격 서비스·상시 스케줄러·외부 투자 보고 전송은 관문 확정 후 |

공식 확인 근거:

- [Python 3.12 Decimal](https://docs.python.org/3.12/library/decimal.html): 정확한 10진 표현·정밀도·반올림·신호 처리. 금액의 통화/업무 반올림 규칙은 자체 계약 책임이다.
- [PostgreSQL numeric](https://www.postgresql.org/docs/18/datatype-numeric.html)와 [transaction isolation](https://www.postgresql.org/docs/18/transaction-iso.html): 정확한 수치형과 격리 수준의 동작. [공식 라이선스](https://www.postgresql.org/about/licence/)는 PostgreSQL License다. 각 클라이언트·확장 라이선스까지 확인한 것은 아니다.
- [Apache Parquet 개요](https://parquet.apache.org/docs/overview/): 컬럼 지향 저장 형식. 형식 채택은 데이터 제공자의 저장/재배포 권리를 제공하지 않는다.
- [LEAN LICENSE](https://github.com/QuantConnect/Lean/blob/master/LICENSE): 확인한 엔진 루트 Apache-2.0. [공식 README](https://github.com/QuantConnect/Lean#readme)는 직접 .NET 빌드/Launcher 실행을 설명한다. 이 mutable URL은 확인일 근거이며 도입할 commit/digest는 별도로 고정한다.
- [LEAN CLI 설치](https://www.quantconnect.com/docs/v2/lean-cli/installation/installing-lean-cli)와 [로컬 백테스트](https://www.quantconnect.com/docs/v2/lean-cli/backtesting/deployment)는 CLI 사용에 유료 조직 요금제와 로컬 실행의 Docker 의존을 명시한다. 엔진 라이선스와 CLI 서비스 조건을 혼용하지 않는다. 신규 비용0이므로 CLI를 필수 경로로 선택하지 않는다.

## 기존 상위20개 적용표의 처리

[20개 적용 계약](oss-application-plan.md)과 [고정 조사 근거](github-evidence-2026-10-19.json)를 유지한다. 이번에는 새로운 스타 순위를 발표하지 않는다. 스타 수는 2026-10-19 스냅샷이며 구현 성능·안전성의 근거가 아니다. 코드 복사·전체 프레임워크 설치 없이 아래 범위로 설계에 반영한다.

| 기존 순위·프로젝트 | 초기 적용 결정 | 후속 확인 |
|---|---|---|
| 1 TradingAgents | 근거·반론·연구 역할 분리 패턴 참고 | H의 출처·실패·권한 평가 |
| 2 OpenBB | 공급자 정규화 패턴 참고; 패키지 도입 보류 | 권리가 확인된 공급자별 필요 시 재평가 |
| 3 daily_stock_analysis | 보고 outbox·전달 상태 패턴 참고 | 한국 통화/시장 구분·보고 권한 |
| 4 ai-hedge-fund | 목표/부분 변경·리밸런싱 패턴 참고 | 누락 종목 임의 청산 금지 |
| 5 Freqtrade | 기동 대사·미체결 감시·연구 검증 패턴 참고 | 주식 세션/휴장과 상태불명 계약 자체 구현 |
| 6 Maybe | 원장 projection·미평가 자산 표시 패턴 참고 | 전체 포크 제외·수량과 평가 구분 |
| 7 Qlib | 초기 도입 보류 | 기준 전략/버전 데이터 확보 후 ML 비교 |
| 8 vn.py | BrokerPort·이벤트 계약 패턴 참고 | 국내 증권사 어댑터 자체 구현 |
| 9 CCXT | 도구 권한 분리만 참고, 거래 라이브러리 제외 | 주식 브로커 기능으로 오인하지 않음 |
| 10 Vibe-Trading | 환경 capability·연구 근거 패턴 참고 | 공식 broker API 지원 검증 별도 |
| 11 FinceptTerminal | 코드/UI 채택 보류 | 파일별 이용조건 확인 전 복사 금지 |
| 12 TradingAgents-CN | 모델 역할 분리 패턴 참고, 전체 포크 보류 | 모델·언어 평가 및 구성별 조건 |
| 13 NautilusTrader | 주문 상태·복구 패턴 참고, 엔진 도입 보류 | 자체 단일 실행자·중복/역순 처리 |
| 14 yfinance | 초기 필수 의존성 제외 | 개인 연구 접근과 저장/AI 이용권 별도 확인 |
| 15 Backtrader | 계약 참고, 초기 엔진 제외 | LEAN과 중복 엔진 도입하지 않음 |
| 16 AKShare | 데이터 카탈로그 패턴 참고 | 데이터별 권리·시장 적합성 |
| 17 AI-Trader | 개념 참고, 코드 채택 보류 | 고정 조사에서 남은 소스 이용조건 |
| 18 LEAN | 별도 연구 엔진 1순위, 유료 CLI 제외 | 소스/의존성 고정·직접 실행·데이터·국내 비용/달력 검증 |
| 19 FinGPT | 업무별 평가 체계 참고, 초기 파인튜닝 보류 | 데이터/기반모델 권리·한국어 평가 |
| 20 Hummingbot | 프로세스/작업 책임 분리 패턴 참고, 거래 엔진 제외 | 개발 폴더 분리와 실제 운영 격리 구분 |

표의 패턴 참고는 알려진 동작을 자체 요구·코드로 구현하는 결정이다. 라이선스 표기를 생략한 코드 이식 권한으로 확대하지 않는다. 실제 패키지 도입 시 해당 버전 LICENSE·NOTICE·전이 의존성을 별도 확인한다.

## B06 투자 운영 AI

개발 팀 모델 설정과 제품의 운영 AI를 구분한다. 초기 신규 유료 비용0 요구에 따라 외부 유료 모델 호출은 비활성으로 설계하고, 제안/검토/설명 인터페이스 및 합성 응답으로 계약을 검증한다. 결정론적 원장·위험 검사·승인·주문은 AI 가용성과 별도로 동작해야 한다. 이것이 AI 연구 기능의 성능 평가 완료라는 뜻은 아니다.

기존 후보 역할표는 평가 후보로 유지한다. 모델 ID·추론·도구·데이터 제공 범위·예산·재시도·사용량 기록은 Q25/H의 운영 활성화 전에 최신 공식 지원과 계정 가용성, 고정 평가셋을 확인한 뒤 채택한다. 기존 개발 구독이 제품 API 호출 권한/과금을 포함한다고 추정하지 않는다. 로컬 모델도 설치·성능·라이선스 근거 없이 대체 가능하다고 선언하지 않는다. 해당 확인 전 제품 AI 경로는 명시적으로 비활성/미검증 상태다.

## 확인 범위

이번 기록은 공식 공개 문서와 기존 고정 조사 결과에 대한 설계 판단이다. 패키지 설치·벤치마크·데이터 다운로드·계좌 로그인·주문·유료 API 호출을 수행하지 않았다. 증권사·데이터의 B01~03 결과는 조사 반환 후 아래에 통합한다.

## B01 증권사: 설계 대상과 운영 채택 분리

**첫 자체 BrokerPort 설계 대상은 KIS, 대안은 키움 REST로 정한다. 운영 연결은 보류한다.** 수동 환전 선택으로 환전 실행 API가 초기 필수에서 빠졌고, KIS의 양 시장 주문·잔고·체결 경로와 real/demo 예제를 활용해 공통 어댑터 계약을 구체화할 수 있다. 이는 설계 비용에 대한 판단이며 회사 철학·체결 품질·수익성의 우열 판정이 아니다. 사용자 거주지·계좌 자격은 확인하지 않았다.

| 공급자·시장/환경 | 공개 확인 범위 | 미확인·차단 조건 |
|---|---|---|
| KIS 국내 주식 실전/모의 | 공식 카탈로그의 현금 주문·정정취소·체결·잔고·매수가능 조회, 샘플의 환경 분리 | endpoint·계정별 모의 동등성, 종목별 상품 허용, 현재 유량/비용·정규장 매핑은 연결 전 확인 |
| KIS 미국 주식 실전/모의 | 해외 주문·취소·미체결·체결·현금/잔고 경로, 주문/체결기준잔고 예제의 real/demo TR 분기 | 결제기준·체결기준·매수가능금액을 혼동하지 않음. 페이지 완전성·상태불명 식별·미국 정규장/주문 유형은 검증 필요 |
| KIS 국내/미국 ETF × 실전/모의 | 국내 ETF 시세/NAV 예제와 주식 API 카탈로그 | 시세 API를 ETF 주문 지원으로 승격하지 않음. 종목별 조회·주문·취소·체결·분류 근거 확보 전 capability unknown |
| 키움 국내 모의 | 모의 서비스와 KRX 거래/계좌조회 범위 공개. NXT 거래는 모의 미지원 | 시세에 NXT가 있어도 해당 거래 허용으로 해석하지 않음. ETF 주문은 별도 확인 |
| 키움 미국 모의 | NYSE/NASDAQ/AMEX 모의 범위·무료 실시간 시세 안내 | 모든 ETF 주문/체결·현금 필드의 동등성을 보장한 근거 아님 |
| 키움 국내/미국 실전 | 주식 REST·신청/계좌 요건·호출 제한 공개 | 실제 자격·상품·시장시세 비용·정규장·주문 유형·데이터 권리 확인 전 연결 보류 |

직접 출처(2026-10-23 열람): [KIS API 카탈로그](https://apiportal.koreainvestment.com/apiservice-category), [KIS README](https://github.com/koreainvestment/open-trading-api/blob/main/README.md), [해외 주문 환경 분기](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/order/order.py), [체결기준잔고 환경 분기](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_present_balance/inquire_present_balance.py), [국내 ETF 조회 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/etfetn/etfetn_examples.py), [키움 서비스 안내](https://openapi.kiwoom.com/intro?dummyVal=0), [키움 모의 안내](https://openapi.kiwoom.com/intro/mockInvestInfo?dummyVal=0), [키움 API 가이드](https://openapi.kiwoom.com/m/guide/apiguide?dummyVal=0).

독립 검토에서 [KIS 해외 주문 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/order/order.py)의 미국 모의 매도 TR 주석과 실행 분기 생성값이 다른 점을 확인했다. 현재 API의 정답이나 실제 실패를 판정하지 않았으며 SG-01에서 공식 명세와 승인된 모의 검증으로 확정한다.

목록과 예제는 동작 보장이 아니다. 상태불명 주문의 재전송 방지와 조회 완전성·부분체결 복구는 자체 계약/실행 검증 책임이다. 호출량은 15분 회차 평균이 아닌 종목/endpoint별 burst를 포함해 제한한다. KIS 계정별 최신 유량은 미확인이고 키움의 공개 수치를 다른 환경에 복사하지 않는다. 최신 main과 기존 고정 commit의 완전 diff는 수행하지 않았다.

## B02·03 데이터 선택과 이용권

- 개발/계약 검증에는 합성 자료를 채택한다. 실제 시장성능·실제 계좌 대사 통과로 표시하지 않는다.
- 계좌·미체결·체결·매수가능 현금은 선택된 브로커가 원천이다. 실제 연결 전 필드 의미·완전성·환경 지원과 계정 권한을 확인한다.
- 운영 시세의 1차 어댑터 대상은 브로커 시세다. 장기 연구 데이터·공시/뉴스의 실제 공급자는 이용조건·coverage를 확인할 때까지 보류한다. yfinance·OpenBB 설치나 공개 웹 열람 자체를 재사용 권리로 취급하지 않는다.
- API 호출·화면 표시·로컬 보존·파생 지표 저장·백테스트·외부 AI 제공·개인 외부 보고·제3자 배포를 각각 구분한다. 확인되지 않은 용도는 허용하지 않는다. 데이터별 출처·확인일·권리 참조·허용 용도·보존·만료를 manifest에 연결한다.
- [KIS Provider 안내](https://apiportal.koreainvestment.com/provider)는 개인 자기자산 이용과 제3자 서비스 제공을 구분한다. 이 페이지에서 개인의 장기 시세 저장·외부 LLM 제공 권리를 확인하지 못했다. 이 미확인을 허용이나 영구 미지원으로 바꾸지 않는다.
- 키움의 모의 무료 조건은 [모의 안내](https://openapi.kiwoom.com/intro/mockInvestInfo?dummyVal=0)의 범위에 한정한다. [서비스 안내](https://openapi.kiwoom.com/intro?dummyVal=0)는 거래 수수료·요건을 따로 설명한다. 신규 지출0 조건에서 비용이 필요한 경로는 보류한다.

## 후속 확인 관문 SG-01~04

PG 관문은 사용자 정책이며, SG는 공급자/기술 근거 확인이다. 둘 중 하나만 통과해서 연결·운용할 수 없다. 현재 아래 SG는 모두 미완료다. root가 증거를 취합하고 필요할 때만 사용자 자격·비용·권한 결정을 요청한다.

| ID | 시작 전 충족할 항목 | 적용 작업·차단 동작 |
|---|---|---|
| SG-01 | 사용자 자격·계좌/API 신청·환경별 host/TR·정규장·종목 분류·주식/ETF 조회/주문/취소/체결 capability, 최신 유량·수수료·시세비용·현금 의미 | Q19 실제 연결 전·Q27 제출 전 및 Q31 실전 환경 준비 시 재확인. 미확인 공급자 운영 연결 보류. 특히 ETF 지원을 기존 주식 근거로 채우지 않음 |
| SG-02 | 데이터별 coverage·가격조정·기업행동·시점·완전성, 목적별 저장/연구/AI/보고 권리 및 비용 | Q16 종목/달력 및 Q17·18 실제 수집/보존, Q23 실제 자료 평가, Q25 외부 AI 제공, Q28 외부 보고 전. 확인되지 않은 용도의 수집·보존·전송 금지 |
| SG-03 | 도입할 의존성/엔진의 고정 버전·해시·LICENSE/NOTICE·전이 의존성·호환성·로컬 실행·KR/US 비용/달력·데이터 주입 검증 | C01~03 실제 의존성 도입, Q23 엔진 사용 전. 유료 CLI 우회나 mutable main 실행 금지 |
| SG-04 | 운영 모델/공급자·계정 API 권한·데이터 제공권·운영 예산·시간/재시도·고정 평가셋 통과 | Q25 운영 AI 활성화 전. 그전에는 합성 응답/명시 비활성, 제품 AI 평가 전체 완료 아님 |

## B 항목별 판정 범위

| 항목 | Q08의 설계 결정 | 남는 실제 완료 증거 |
|---|---|---|
| B01 | KIS 첫 어댑터 설계 대상, 키움 대안, 운영 연결 보류 | SG-01·PG-01·AP-05 및 후속 API 검증 |
| B02·03 | 합성 입력 우선, 브로커 조회/시세 어댑터 대상, 권리 미확인 용도 차단 | 실제 공급자 coverage/조건 확정·SG-02 |
| B04·05 | Python·PostgreSQL·Parquet, 별도 LEAN 직접 실행 검증 경로, 기존20개 참고/보류 표 | SG-03 버전·라이선스·실행 검증 |
| B06 | 개발 팀과 운영 AI 분리, 제품 호출 비활성 기본·평가 후 활성화 | SG-04·PG 예산·모델/데이터 권리·평가 |

Q08 완료 판정은 채택/대안/보류와 적용 조건의 명확화다. 보류 항목의 실제 제품 기능을 완료로 표시하지 않는다. 다음 Q09~12에서는 공급자와 모델이 비활성인 상태에서도 합성 검증 가능한 공통 계약을 확정한다. B의 미확인이 구현 계약을 결정할 수 없게 만드는 경우 해당 설계는 확정하지 않는다.
