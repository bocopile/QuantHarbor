# 증권사 선택 결정안

기준일: 2026-10-19. 관련 작업 A01~06, B01·03, ARC-06~09, I01~08. 상태: **첫 구현 대상에 대한 권고, 실계좌·운영 승인 전**. 한국 거주 개인의 국내·미국 현금 주식 투자를 가정한다. 거주지·계좌 종류가 다르면 자격부터 다시 확인한다.

## 권고

**첫 BrokerPort 구현 대상은 한국투자증권 KIS, 동등한 대체 후보는 키움 REST로 둔다.** 초기에는 승인된 원화·달러 가용 현금 범위에서 운용하는 안을 전제로 한다. 2026-10-23 사용자는 수동 환전·시스템 현금 조회를 선택했다([A-DEC-001](../decisions/A-DEC-001-initial-product-input.md)). 따라서 아래 자동 환전 필수 조건은 현재 발동하지 않는다. 공급자 기능의 조사 기준일은 2026-10-19이며 이번 요구 반영이 최신 API 재검증이나 증권사 최종 선정을 뜻하지 않는다.

**한국·미국 간 자산배분을 위해 자동 환전까지 초기 필수 기능으로 정하면 키움을 우선 재평가한다.** 키움은 공식 환전 실행 API 예제가 확인됐고, KIS의 환전 실행 API는 이번 공개자료 조사에서 확인하지 못했다. 이를 KIS가 영구적으로 미지원한다는 결론으로 확대하지 않는다. 직접 근거는 [키움 환전 신청 ust31302 예제](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/953e5dbff123f437ab4d11a78a95191a685eb51f/examples/%EB%AF%B8%EA%B5%AD%EC%A3%BC%EC%8B%9D/%ED%99%98%EC%A0%84/request_overseas_currency_exchange.py)다. 실제 계좌 환전 권한·거래시간·모의 지원은 미검증이며, 실전 API 존재와 모의 기능 동등성은 별도 확인한다.

KIS의 우선순위는 공식 국내·미국 모의/실전 예제, 주문·체결·잔고 경로, 전략 정의와 LEAN 백테스터를 연결하는 자료가 현재 단계적 개발의 조사 비용을 줄인다는 설계 판단이다. 두 증권사 모두 기본 시장 범위를 지원하므로 KIS가 체결 품질·장애 복구·비용·철학 적합성에서 절대 우위라는 실측 결론은 아니다. 백테스터 자료는 참고 근거이며 KIS 샘플 전체를 복사할 전제가 아니다.

**AI 도구의 역할·권한 분리 설계는 키움의 Spec/Exec MCP를 적극 참고한다.** 브로커 선택과 공식 MCP 채택은 별도 결정이다. 어느 증권사를 택하든 연구 AI가 공식 주문 MCP를 직접 호출하는 구조는 채택하지 않는다.

## 철학을 선택 기준으로 바꾸기

증권사 회사의 경영 철학이 우리와 같다고 판정하는 문서가 아니다. “설명하고, 검증하고, 통제할 수 있는 투자”를 구현하는 데 필요한 API 기능을 비교한다.

| 기준 | 필요한 기능/증거 | 현재 판단 |
|---|---|---|
| 범위 | 사용자 자격으로 KR·US 실전 거래 | KIS·키움 우선, 나머지는 아래 제약 |
| 단계적 검증 | KR·US 모의 주문·취소·조회와 실전 차이 명세 | KIS·키움 확인, 세부 API 동등성은 미완료 |
| 자산 파악 | 보유·체결·미체결·가용/미결제 현금·외화 조회 | 양사 명세 존재, 원장 대사 완료를 뜻하지 않음 |
| 통제 | 정정/취소·상태조회·인증/권한 경계 | 제공 API 위에 자체 승인·단일 실행자·위험 검사 필요 |
| 실패 복구 | 응답 유실·WS 단절 후 완전한 주문/체결 재조회 | 양사 실제 계좌 검증 필요; 샘플 오류처리 그대로 사용 금지 |
| 학습·설명 | 데이터 출처·재현 연구·주문과 결정 연결 | KIS 연구 예제 참고; 공통 기록 체계는 자체 구축 |
| 양 시장 자금 이동 | 외화 주문 가능액·환전·결제 시점 | 자동 환전 요구가 확정되면 키움의 상대적 강점 |
| 데이터 사용권 | 저장·AI 입력·개인 보고·제3자 공유 허용 범위 | 모든 후보별 추가 계약 확인 필요 |

가중치·점수로 미확인을 메우지 않았다. 초기 운용정책에서 필수로 정한 기능을 확인하지 못하면 운영 채택은 보류한다.

## 6개 증권사 비교

| 후보 | 국내 / 미국 | 모의→실전 | 강점과 제한 | 결정 |
|---|---|---|---|---|
| 한국투자증권 KIS | 둘 다 공식 경로 | 둘 다 확인, 세부 API 차이 존재 | Python·REST/WS·주문/잔고·공식 LEAN 연구 예제. 환전 실행·최신 계정별 유량·결제잔고 모의 범위 미확인 | **첫 어댑터 권고** |
| 키움 REST | 둘 다 공식 지원 | 둘 다 확인 | REST 멀티OS·환전 API·Spec/Exec MCP. 세션/유량 제약과 모의 제한, 소스 이용조건 확인 필요 | **동등 비교·대체 후보**, 자동 환전 필수 시 우선 재평가 |
| LS증권 | 국내·미국 API 확인 | 별도 실전/모의 키; 미국 모의 상세 미확인 | 미국 주문·체결·잔고·이벤트 카탈로그. 모의 범위/복구 계약 확인 필요 | 조건부 후속 후보 |
| 토스증권 | 둘 다 REST/WS | 실전 확인; 공개 모의 환경 미확인 | clientOrderId·허용 IP. 체결 단위 REST 없음, WS 재전달 없음, 일부 앱 주문 조회 제외 | 모의·대사 공백 해결 전 주력 보류 |
| IBKR | 미국 가능; 한국 거주자의 KRX 접근 제한 | API paper/live 있음 | 글로벌 확장성. 사용자 거주지 제한·세션/재인증 운영 부담 | 한국 거주자 전제에서 단일 주력 제외; 미국 확장 후보 |
| Alpaca | 미국 중심; 국내 지원 근거 없음 | 미국 paper 가능; 한국 개인 실전 자격 미확인 | 별도 paper 키/host·주문 client ID. 데이터/체결 시뮬레이션 제약 | 미국 연구/보조 후보 |

## KIS와 키움 상세 비교

| 항목 | KIS 확인 사실 | 키움 확인 사실 | QuantHarbor 적용 |
|---|---|---|---|
| 환경 | 국내/해외 예제의 real/demo 및 별도 키·TR | 실전/모의 도메인·별도 키 | 키·계좌·host·DB·큐를 함께 환경에 결속 |
| 주문 | 해외 주문 및 원주문번호 기반 정정/취소 | 국내/미국 주문·정정·취소 예제 | 접수·체결·취소 요청·취소 완료 분리 |
| 복구 조회 | 해외 주문체결내역·미체결·실시간 통보; 주문번호 직접 검색 제한 | 국내 미체결/체결, 미국 일별/기간별 주문체결/미체결 및 WS | 페이지 완전성과 오류를 상태 데이터로 보존 |
| 현금·잔고 | 체결기준잔고 real/demo; 읽은 결제기준잔고 예제는 실전 TR만 | 미국 원장잔고 확인 등 | 잔고·평가·결제·매수가능금액을 같은 숫자로 취급하지 않음 |
| 환전 | 실행 API 공개 근거 미확인 | 환율·환전예상·환전실행 예제 | 자동 환전은 자금 행위로 별도 정책·승인·원장 필요 |
| 모의 차이 | 미국 모의 지정가 제한; 일부 조회 필터 제한 | 국내 모의 거래/계좌 KRX만; 미국 NYSE/NASDAQ/AMEX; Exec MCP 문서상 모의 환율/주문가능금액 조회 거절 | API·시장·세션별 capability 명세 |
| API 유량 | 신규 고객 제한 공지 존재; 적용 수치 미확인 | 국내 주문/조회 각 5회/초; 미국 일반 10/5/환전1, KST09~10은 3/3/1; 모의 TR당1회/초 | 코드 상수 대신 환경/계좌별 설정과 중앙 호출 할당 |
| 세션 | 계정별 현재 조건 확인 필요 | 토큰당 세션1, 실시간 시세200종목 | AI마다 연결하지 않고 수집 서비스가 배포 |
| 연구 | Strategy Builder·.kis.yaml·LEAN Docker 백테스터 | 공식 스펙·Python·CLI·MCP; 같은 형태 백테스터는 미확인 | 연구 결과는 공통 TargetPlan으로 내보냄 |
| AI 도구 | 코딩/트레이딩 MCP | 무자격증명 Spec MCP, 주문 기본off Exec MCP | 문서검색·연구·실전 실행 권한 분리 |

공식 근거: [KIS 저장소](https://github.com/koreainvestment/open-trading-api/blob/2077773a69a428daf63e148182511f068cc45de3/README.md), [KIS 해외 주문](https://github.com/koreainvestment/open-trading-api/blob/2077773a69a428daf63e148182511f068cc45de3/examples_llm/overseas_stock/order/order.py), [정정취소](https://github.com/koreainvestment/open-trading-api/blob/2077773a69a428daf63e148182511f068cc45de3/examples_llm/overseas_stock/order_rvsecncl/order_rvsecncl.py), [체결기준잔고](https://github.com/koreainvestment/open-trading-api/blob/2077773a69a428daf63e148182511f068cc45de3/examples_llm/overseas_stock/inquire_present_balance/inquire_present_balance.py), [결제기준잔고](https://github.com/koreainvestment/open-trading-api/blob/2077773a69a428daf63e148182511f068cc45de3/examples_llm/overseas_stock/inquire_paymt_stdr_balance/inquire_paymt_stdr_balance.py), [키움 공식 저장소](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/953e5dbff123f437ab4d11a78a95191a685eb51f/README.md), [키움 API 가이드](https://openapi.kiwoom.com/guide/apiguide?dummyVal=0), [키움 호출/세션 한도](https://openapi.kiwoom.com/intro?dummyVal=0), [키움 모의 안내](https://openapi.kiwoom.com/intro/mockInvestInfo). 동적 포털 수치는 연결 전 재확인한다.

## 공식 예제도 그대로 사용할 수 없는 부분

### KIS: 빈 조회·부분 조회와 주문 없음을 구분

[해외 주문체결내역 예제](https://github.com/koreainvestment/open-trading-api/blob/2077773a69a428daf63e148182511f068cc45de3/examples_llm/overseas_stock/inquire_ccnl/inquire_ccnl.py)는 ODNO 직접 검색 제한, 재귀 깊이 상한에서 부분 결과 반환, API 오류에서 빈 DataFrame 반환 동작을 포함한다. 이러한 반환값을 “기존 주문이 없음”으로 해석하여 재전송하면 중복 주문을 만들 수 있다.

자체 조회 계약은 다음을 반환해야 한다.

```text
BrokerQueryResult:
  items, complete, continuation, pages_fetched,
  queried_scope, as_of, source_error, raw_reference
```

조회 실패/불완전 결과는 성공한 빈 결과와 다른 상태다. 타임아웃 주문은 UNKNOWN으로 유지하고 전체 범위 조회와 식별 절차를 거친다. 증권사 측 exactly-once 보장은 확인하지 못했으며, 식별 불가능한 경우 자동 재전송하지 않고 사람 검토로 남긴다.

### MCP: 도구의 확인 플래그와 실제 승인 구분

[KIS Trading MCP 코드](https://github.com/koreainvestment/open-trading-api/blob/2077773a69a428daf63e148182511f068cc45de3/MCP/Kis%20Trading%20MCP/tools/base.py)는 GitHub main의 인증/API 코드를 동적으로 가져와 subprocess로 실행한다. 프로세스 종료코드와 timeout은 주문 접수·체결의 확정 결과가 아니다. 실전은 검토·고정된 자체 어댑터로 운용한다.

[키움 Exec MCP](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/953e5dbff123f437ab4d11a78a95191a685eb51f/mcp_exec/README.md)는 주문 기본 비활성화와 preview/submit 분리가 장점이다. 하지만 confirm은 AI도 설정할 수 있으므로 사람의 승인 증명이 아니다. 실제 승인은 계좌·제안 hash·금액/수량 상한·만료·승인자와 결속된 기록으로 확인한다. README와 [server.py](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/953e5dbff123f437ab4d11a78a95191a685eb51f/mcp_exec/src/kiwoom_exec_mcp/server.py)의 해외 주문 설명 차이는 배포 CLI/MCP 버전 확인 과제로 남긴다. REST 지원과 특정 도구 지원을 혼용하지 않는다.

### 라이선스: API 이용과 소스 복사는 다른 결정

[키움 LICENSE](https://github.com/Kiwoom-Securities/Kiwoom-REST-API/blob/953e5dbff123f437ab4d11a78a95191a685eb51f/LICENSE.md)는 복제·수정·배포·상업이용 등에 사전 동의 조건을 둔다. KIS에서 확인한 MIT는 [Trading MCP 하위 LICENSE](https://github.com/koreainvestment/open-trading-api/blob/2077773a69a428daf63e148182511f068cc45de3/MCP/Kis%20Trading%20MCP/LICENSE) 등 해당 범위이며 루트·백테스터 전체 MIT라는 근거는 확보하지 못했다. API 명세를 바탕으로 자체 어댑터를 설계하고, 코드 재사용은 파일별 조건 확인 후 결정한다. 조건의 법적 효력을 판정한 것은 아니다.

## 나머지 후보의 보류 근거

### LS증권

[공식 서비스 목록](https://openapi.ls-sec.co.kr/apiservice)에 미국 주문 COSAT00301, 정정 COSAT00311, 주문체결 COSAQ00102, 잔고 COSOQ00201, 예수금 COSOQ02701 및 AS0~AS4 이벤트가 있다. [이용안내](https://openapi.ls-sec.co.kr/about-openapi)는 실전/모의 별도 키를 설명한다. 미국 주문·취소·부분체결·잔고까지 모의 지원한다는 세부 근거는 확보하지 못했다. 미국 모의와 체결 복구 범위를 확인하면 같은 기준으로 재평가한다.

### 토스증권

[FAQ](https://openapi.tossinvest.com/openapi-docs/faq.md), [연동 가이드](https://openapi.tossinvest.com/openapi-docs/overview.md), [OpenAPI 1.2.24 조회본](https://openapi.tossinvest.com/openapi-docs/latest/openapi.json)을 확인했다. clientOrderId는 10분 이내 동일 주문의 재요청 결과를 돌려주지만, 기간 밖에는 같은 키가 새 주문이 될 수 있으므로 자체 중복 방지가 필요하다.

체결 단위 REST 조회 대신 주문별 누적수량·평균가격을 제공하며 WS 단절 구간 이벤트를 재전달하지 않는다. 따라서 단절 동안 발생한 개별 체결 시각·가격을 누적치만으로 완전히 복원할 수 없다는 판단이다. API 미지원 호가 유형의 일부 앱 주문도 조회에서 제외된다. 모의 endpoint는 미확인이다. 정확한 원장 복구를 위해 추가 거래명세 경로와 전용 계좌 정책이 필요하다.

유효 토큰은 클라이언트당 하나이므로 업무별 독립 발급은 서로를 끊을 수 있다. 미국 시세는 NBBO가 아니고 상장폐지 시세 조회가 제한된다. 데이터의 제3자 제공 제한도 있어 연구 데이터·AI 입력·Slack 공유 범위를 계약으로 확인해야 한다.

### IBKR

[계좌 신청 국가](https://ndcdyn.interactivebrokers.com/en/accounts/open-account-country-list.php)에 한국이 포함되더라도 실제 계좌 승인을 뜻하지 않는다. [공식 한국시장 안내](https://www.interactivebrokers.com/en/trading/nextrade.php)는 한국 거주자의 KRX 이용 제한을 명시한다. [API paper 계좌](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/)가 있으나 단일 국내·미국 주력 요건과 충돌한다.

[Client Portal Gateway](https://www.interactivebrokers.com/docs/web-api/authentication/cpgw/client-portal-gateway-faq)의 재인증과 [IB Gateway](https://www.interactivebrokers.com/docs/tws-api/doc/architecture/the-trader-workstation/the-ib-gateway)의 운영 세션 조건은 향후 미국 어댑터 도입 시 별도 검토한다. 다른 인증 상품까지 모두 동일하다고 일반화하지 않는다.

### Alpaca

[paper 문서](https://docs.alpaca.markets/us/docs/paper-trading)는 전 세계 paper-only 가입, 별도 키/host를 설명하지만 시뮬레이션이 배당·시장충격·일부 수수료 등을 반영하지 않는다. [주문 가이드](https://docs.alpaca.markets/us/docs/working-with-orders)의 client_order_id는 어댑터 설계 참고에 유용하다. [실전 지원 국가 안내](https://alpaca.markets/support/countries-alpaca-is-available)는 고객지원 확인을 요구하며 한국 개인 실전 자격은 확정하지 못했다. Broker API의 지원국 목록을 개인 Trading API 자격으로 대신하지 않는다.

## QuantHarbor의 구현 계약

### 권한과 자금 경계

- 연구·일일 공부·포트폴리오 AI: 버전 데이터/가명화 스냅샷 읽기와 제안 생성만 허용.
- 검토 AI: 근거·정책 위반·반론 기록. 승인·주문 권한 없음.
- 실행 서비스: 계좌별 단일 작성자, 주문 의도 선저장, 코드 기반 위험 검사, 승인 정책 확인.
- 대사 서비스: 주문·체결·현금·외화·배당·비용을 증빙과 맞추고 결과 제공.
- 보고 서비스: 원장 read model → 버전 있는 보고서 → outbox. 사용자 승인 이벤트는 별도 검증 서비스로 전달.
- 자동 환전: 추가 자금 행위로 정의하고 승인 정책·한도·원장·실패 처리 후 도입. 자료 수집 AI에게 권한 부여 금지.

### 기능표와 후속 검증 증거

모든 항목은 **향후 구현/검증 계획**이며 이번에 실행하지 않았다.

| 관문 | 완료 근거 | 미충족 시 |
|---|---|---|
| 계좌·약관 | 사용자 계좌 자격, API 신청, 시장/시세 권한, 데이터 저장/AI 제공 조건 | 운영 선택 보류 |
| KR/US × paper/live | 시세·잔고·주문·정정취소·미체결·체결·환전별 지원표 | 미지원 기능을 capability로 차단 |
| 접수 불명 | 응답 유실 주문을 식별하고 중복 제출 없이 종결 | 신규 위험 주문 중단·사람 검토 |
| 체결 복구 | WS 단절·부분체결·역순·페이지 누락을 조회/명세로 대사 | 보고 잠정·실전 승격 보류 |
| 원장 | 수량·수수료·세금·배당·환전·미결제금·가용금의 증빙 일치 | 차이 원인 조사, 임의 잔고 조정 금지 |
| 격리·중단 | 실전/모의 키·host·DB·큐 구분, 오래된 실행자 차단, 정지/취소/청산 분리 | 실전 기동 차단 |
| 비용·유량 | 실제 계좌 수수료·환전비용·시세비용·현재 호출 한도 | 예산/전략 재평가 |
| 제한 실전 | 승인된 자금·시장·전략·기간·손실 대응 및 관찰 기록 | 자동운영 확대 보류 |

## 선택을 뒤집는 조건

1. 자동 환전이 처음부터 필수이고 KIS에서 필요한 API를 확인할 수 없으면 **키움 우선**.
2. KIS의 주문 식별·조회 완전성·원장 대사·계좌 권한·유량 조건이 필수 관문을 충족하지 못하고 키움이 충족하면 **키움으로 전환**.
3. 양사가 모두 실패하면 **실전 채택 보류** 후 LS 등 재평가. 확인하지 못한 기능을 구현 가능으로 가정하지 않는다.
4. 거주지·시장 범위가 달라지면 IBKR·Alpaca를 포함해 다시 비교한다.

## 현재 완료와 다음 단계

완료: 6개 후보의 공개 자료 비교, KIS/키움 핵심 소스와 기능 차이 확인, 선택/전환 조건 및 구현 계약 권고. 계좌 연결·키 설정·주문·설치·테스트·Slack 전송은 수행하지 않았다. 실제 비용·체결 품질·장애 이력 우열은 미평가다.

순서: ENV 완료 → ARC에서 운용정책(특히 자동 환전·세션·계좌·자금)과 위 계약 확정 → 데이터·원장·어댑터 구현 → 요청된 검증 → 모의 관찰 → 별도 승인된 소액 실전. 이번 권고는 구현 선행조건을 생략하는 승인이 아니다.
