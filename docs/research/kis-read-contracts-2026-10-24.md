# KIS 조회 명세 재확인 — Q19

확인일 2026-10-24. root가 공식 공개 자료를 내려받고 `requirements_scout`가 읽기 분석했다. 코드 실행·토큰 발급·계좌/API 호출은 하지 않았다. [20개 파일 URL·해시](kis-read-sources-2026-10-24.json), 고정 커밋 [cd63cae](https://github.com/koreainvestment/open-trading-api/tree/cd63caee6aeb90553d506b15ab6866cfad23beda), [공식 포털](https://apiportal.koreainvestment.com/apiservice-category)을 근거로 한다. 예제 코드 전체를 복사하거나 해당 저장소 전체의 재사용 라이선스를 확정하지 않는다.

## 조회 후보

| 내부 후보 | GET 경로 (/uapi 아래) | 실전 / 모의 TR | 출력·범위와 주의 |
|---|---|---|---|
| kr_balance | domestic-stock/v1/trading/inquire-balance | TTTC8434R / VTTC8434R | output1 보유·output2 현금 요약. hldg_qty/ord_psbl_qty와 dnca_tot_amt/nxdy_excc_amt/prvs_rcdl_excc_amt는 별도 원천 사실. 현금 포함 관계 미확인 |
| kr_orders | domestic-stock/v1/trading/inquire-daily-ccld | 최근 TTTC0081R / VTTC0081R; 이전 CTSC9215R / VTSC9215R | output1 주문별 누적 체결·output2 요약. 요청 기간/필터 밖으로 완전성을 확대하지 않음 |
| kr_buy_capacity | domestic-stock/v1/trading/inquire-psbl-order | TTTC8908R / VTTC8908R | 종목·가격·주문구분에 따른 단건 output. ord_psbl_cash·nrcvb_buy_amt와 max_buy_amt는 같은 의미가 아님 |
| us_balance | overseas-stock/v1/trading/inquire-balance | TTTS3012R / VTTS3012R | output1/2, ovrs_pdno/ovrs_cblc_qty/ord_psbl_qty/tr_crcy_cd. 모의 거래소 NASD/NYSE/AMEX. 일부 행에 cano/acnt_prdt_cd echo |
| us_orders | overseas-stock/v1/trading/inquire-ccnl | TTTS3035R / VTTS3035R | output 주문별 ft_ord_qty/ft_ccld_qty/nccs_qty. 모의는 전체 조회 중심: 종목/거래소 공란, 매도매수·체결구분00 |
| us_present_balance | overseas-stock/v1/trading/inquire-present-balance | CTRP6504R / VTRP6504R | output1/2/3. 국가840 미국·원화/외화·시장·일반/미니스탁 구분. frcr_dncl_amt_2/frcr_use_psbl_amt 등은 포함 관계 확인 전 별도 관측 |
| kr_amendable_orders | domestic-stock/v1/trading/inquire-psbl-rvsecncl | 샘플 TTTC0084R, 모의 실제 지원 미확인 | helper의 V 접두어 치환만으로 지원을 확정하지 않음 |
| us_open_orders | overseas-stock/v1/trading/inquire-nccs | 샘플 TTTS3018R, 모의 실제 지원 미확인 | env_dv가 함수 TR 선택에 쓰이지 않음. NASD는 이 조회에서 미국 전체라는 설명; 다른 endpoint와 거래소 의미를 혼용하지 않음 |
| us_settlement_balance | overseas-stock/v1/trading/inquire-paymt-stdr-balance | 샘플 CTRP6010R, 모의 TR/지원 미확인 | 결제 기준·기준일 조회. 일반 체결 기준 잔고를 대체하지 않음 |

정확한 필수 params와 output 필드는 고정 source의 각 함수 및 `chk_` 파일을 함께 확인한다. 실전 TR 표는 비교 정보이고 현재 실행 대상이 아니다. 함수의 실전/모의 분기 존재는 사용자 계좌의 실제 지원·권한 확인이 아니다.

## 페이지·시점·식별

- 국내 FK100/NK100, 해외 FK200/NK200의 응답 값을 다음 요청에 전달한다. 응답 `tr_cont=M|F`이면 다음 요청 헤더 `N`. 종료가 확인되지 않거나 cursor 반복/누락·상한·오류이면 partial/unknown이다. 샘플의 재귀 상한 후 부분 rows 반환을 complete로 번역하지 않는다.
- 국내 매수가능조회는 단건이다. 해외 현재/결제 잔고는 FK/NK 없이 tr_cont만 다뤄, 검증 가능한 후속 토큰이 없으면 임의 반복하지 않고 미완료로 남긴다.
- 확인한 자료에 source snapshot/as-of ID나 전체 페이지 동일 시점 보장은 없다. 여러 페이지의 완료와 동일 시점 일관성은 별개다.
- 주문 키는 날짜·주문지점·주문번호와 원주문 참조다. 주문별 누적 체결수량/금액을 개별 체결 이벤트로 만들지 않는다. 개별 execution ID는 이 자료에서 확인되지 않았다.
- 계좌 echo는 일부 해외 잔고 행에서 보이지만 모든 응답에 존재한다는 근거는 없다. 요청 binding과 echo 검증 유무를 구분하고 누락을 임의 계좌 확정으로 승격하지 않는다.
- 현금·주문가능금액의 결제/미결제·예약금 포함 관계는 미확인이다. 원천 수치를 별도 typed 관측으로 보존하되 내부 가용금이나 위험 검사 통과로 사용하지 않는다. 해외 현재잔고 `chk_`에는 같은 frcr_evlu_amt2에 중복 설명이 있어 해당 의미를 추정하지 않는다.

## 인증·지원 관문

[공식 개요](https://apiportal.koreainvestment.com/apiservice?keyword=ci%EC%BD%94%EB%93%9C)는 모의 REST를 `https://openapivts.koreainvestment.com:29443`, 실전 REST를 `https://openapi.koreainvestment.com:9443`로 나눈다. 계좌 조회는 GET, 주문은 POST이며 TLS1.2/1.3을 지원한다. 토큰은 별도 POST `/oauth2/tokenP`다.

인증-001 공개 안내는 개인 토큰 24시간·1일 발급 원칙·6시간 이내 재호출 동일 토큰과 응답 만료시각 관리를 설명한다. README의 1분 재발급 제한 주석과 helper 구현을 계정별 최신 유량 정책으로 확대하지 않는다. 고정 최소 재발급 간격을 실제 권리로 확정하지 않고 기존 유효 토큰을 재사용하며 인증 실패의 무한 재시도·자동 갱신 폭주를 금지한다.

PG-01 모의 정책, SG-01 계좌별 지원·권한, SG-02 필요한 자료 권리, AP-05 대상·행동 승인과 비공개 주입 전 실제 연결은 차단한다. 모의 미지원 조회를 실전으로 우회하지 않는다. 실제 ETF 지원·요금·유량·현금 포함 관계·개별 체결 식별은 계정/공식 명세 확인이 남아 있다.

## 2026-10-24 운영 공지·약관 보충 확인

공식 [호출 유량 공지](https://apiportal.koreainvestment.com/community/10000000-0000-0011-0000-000000000001/post/d0d1a83f-6f8d-4437-9700-6d26702fd989)를 브라우저에서 실제 렌더링해 확인했다. 본문은2026-04-20 기준 모의 REST 초당1건·계좌 단위 제한, tokenP 초당1건을 안내한다. 원 게시일2023-01-11과 본문 갱신 기준일을 구분한다. 검색/단순 HTML 읽기에 본문이 누락되어 UI로 보완했다.

같은 페이지 하단 고객 이용약관(2022-10-01 시행)을 읽었다. 제3조는 계좌/잔고/거래내역 조회도 대상으로 삼는다. 제5조는 키 비공개 관리와 시세의 개인 프로그램 이용·제3자 제공 제한, 제11조는 별도 게시 수수료 기준, 제13조는 점검 중 조회 반영 지연을 규정한다. 제14조의10년 기록 보존은 증권사의 의무이며 제품의 보존기간으로 복사하지 않는다. 로그인·약관 동의·계좌 설정은 하지 않았다.

적용 제안: 단일 in-flight·최소1.1초 요청 시작 간격을 두고 세션/페이지 상한을 별도로 결속한다. 실제 제한을 충족하는지 계좌별 확인은 여전히 필요하며, 공지의 즉시 재호출 문구를 자동 재시도 권한으로 채택하지 않는다. 키·원시 금융자료·시세를 외부 AI나 공개 로그로 전달하지 않는다. 이 확인만으로 사용자 계좌의 지원·요금·자료 보존/AI 제공 권리를 모두 확인했다고 판정하지 않는다.
