# 모델과 증권사 조사 기록

기준일: 2026-10-19. 대화에서 확인한 공식 자료의 기록이다. 운영 구성 시 문서와 실제 계정 가용성·계약을 다시 확인한다. 가격·한도·모델 이름·API 지원 범위를 영구 상수로 취급하지 않는다.

## 모델

| 공식 API 모델 ID | 확인한 reasoning.effort | 입력/출력 100만 토큰 기본 가격 |
|---|---|---|
| gpt-6-luna | none, low, medium, high, xhigh, max | $0.10 / $0.50 |
| gpt-6.1-sol | low, medium, high, xhigh, max | $2 / $10 |
| gpt-6-astra | low, medium, high, xhigh, max | $10 / $50 |

근거: [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra), [요금표](https://developers.openai.com/api/docs/pricing).

캐시·서비스 등급·긴 컨텍스트·도구 호출 등은 별도 조건이다. 추론 토큰도 비용과 출력 한도에 반영한다. 미완료 응답을 정상 결과로 처리하지 않는다. Codex 개발 구독과 운영 API의 접근권한·청구를 동일시하지 않는다. API에서 확인되지 않은 ultra 옵션을 Codex UI 이름만 보고 넣지 않는다.

Luna low 자료 분류, Luna medium 학습, Sol high 연구·포트폴리오, Astra high 별도 검토, Luna 보고, Sol 개발·장애 분석을 초기안으로 제시했다. 주문·회계·한도 검사에는 LLM을 쓰지 않는다. 상세 배치는 [AI 환경 초안](../ai-environment.md)을 따른다.

역할별 정답셋에서 정확도·수치 보존·종목/통화/시점 오류·비용·지연을 비교한 후 확정한다. 모델 둘의 동의가 객관적 검증이나 오류 독립성을 보장하지 않는다. Claude/Gemini 등 다른 공급자와의 금융 업무 비교 평가는 완료하지 않았다.

근거: [모델 선정 가이드](https://developers.openai.com/api/docs/guides/model-selection), [추론·토큰·미완료 응답](https://developers.openai.com/api/docs/guides/reasoning).

## 비용 예시

실제 평균 예측이나 승인된 예산이 아닌, Standard·캐시 미사용 가정의 산술 예시다.

| 그룹 | 하루 호출 수 | 호출당 입력/출력 토큰 상한 | 하루 토큰 비용 |
|---|---:|---:|---:|
| Luna | 100 | 8000 / 4000 | $0.28 |
| Sol | 10 | 20000 / 16000 | $2.00 |
| Astra | 2 | 30000 / 25000 | $3.10 |
| 합계 | 112 | — | $5.38 |

출력에 추론 토큰을 포함하고, 재시도·도구 후속 호출도 위 호출 수에 포함해야 한다. 30일이면 토큰 비용 $161.40이며 도구·데이터·서버·Codex 비용은 별도다. 낮은 출력 상한으로 미완료가 발생할 수 있어 실제 역할 평가 후 한도를 조정한다. 월 예산은 미정이며 설정하지 않았다.

## 증권사 우선 후보

| 후보 | 확인 범위 | 남은 확인 |
|---|---|---|
| 한국투자증권 KIS | 국내/해외 주식, 실전/모의 환경, Python 예제, 인증·주문·잔고·실시간 통보 경로 | 계좌별 권한·호출 제한·데이터 조건·정정/취소/복구 검증 |
| 키움 REST | 국내/미국 주식, 실전/모의, 다양한 OS | 실제 계좌·세션·조회/주문 제한·모의와 실전 차이 |

KIS [공식 저장소](https://github.com/koreainvestment/open-trading-api)는 상품별 시세·주문·잔고와 모의/실전 설정을 제공한다. [미국 주문 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/order/order.py)는 모의 주문의 지정가 제한을 명시한다. [공식 백테스터](https://github.com/koreainvestment/open-trading-api/blob/main/backtester/README.md)는 Python·Docker·LEAN과 전략 파일 연계를 설명한다. 샘플 존재를 운영 안전성 검증이나 모든 실전 기능 지원으로 확대하지 않는다.

키움 [REST 소개](https://openapi.kiwoom.com/intro?dummyVal=0)는 국내/미국 거래와 호출·세션 조건을 설명한다. 조사 당시 모의 계좌는 TR당 국내·미국 각각 초당 1회, 계좌 토큰당 세션 1개, 세션당 실시간 시세 200종목으로 안내됐다. 3개월 미접속 해지 기준은 실서버 접속이며 모의만 사용하면 해지될 수 있다. [모의 안내](https://openapi.kiwoom.com/intro/mockInvestInfo)는 국내 KRX 거래와 NXT 미지원, 미국 NYSE/NASDAQ/AMEX 범위를 구분한다. 수치는 변경 가능하므로 연결 전 최신 공지를 확인한다.

후속 조사에서 LS·토스증권·IBKR·Alpaca를 포함한 6개 비교를 완료했다. [증권사 선택 결정안](broker-selection.md)은 KIS 첫 어댑터 권고, 키움 대체 후보 및 자동 환전 필수 시 재평가 조건을 정의한다. 키움도 국내·미국 API와 공식 Spec/Exec MCP를 제공한다. 공식 MCP의 승인 플래그·샘플 오류 처리·소스 라이선스를 실전 안전성이나 자유 재사용의 근거로 확대하지 않는다. 계좌 이용조건·기능별 모의/실전 차이·원장 대사 등 운영 관문은 미완료이며 계좌 연결·키 입력·주문 호출은 하지 않았다.

## Slack와 AI 도구

보고·승인·경보는 별도 메시지 유형으로 설계한다. 승인에는 사용자·계좌·제안 버전·만료·중복 방지를 적용하고 주문 직전 정책을 재검사한다. [Slack 서명 검증](https://docs.slack.dev/authentication/verifying-requests-from-slack/), [상호작용 처리](https://docs.slack.dev/interactivity/handling-user-interaction/)를 구현 근거로 사용한다.

[OpenAI Skills 문서](https://developers.openai.com/plugins/build/skills)는 재사용 절차 구성의 참고 자료다. [Hooks 문서](https://learn.chatgpt.com/docs/hooks)는 일부 도구 경로 예외와 완전한 통제 경계가 아니라는 제한을 설명한다. 따라서 실전 위험 통제를 Hook 하나에 위임하지 않는다.

GitHub에는 공개 가능한 코드·문서·설정 템플릿을 두고 실제 키·원장·거래내역·개인 보고서를 분리한다. [민감정보 정책](../security.md)을 따른다.
