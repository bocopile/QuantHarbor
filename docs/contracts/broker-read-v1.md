# 증권사 조회 로컬 계약 v1 — Q19

Q12 data-v1의 BrokerQueryResult 필드를 유지하는 추가 계약이다. 생산자는 고정 합성 KIS adapter, 소비자는 조회 application과 향후 Q20 원장/대사다. 원장 변경·주문·개별 체결 생성은 제공하지 않는다. 이 단계의 실행환경은 synthetic, wire_profile은 paper이며 둘은 다른 의미다. frozen 기준 7파일·canonical 버전은 변경하지 않는다.

## 등록형과 결속

serializer에 BrokerReadCapability, BrokerReadRequest, BrokerReadBatch 세 가지 고정형만 추가한다. 각각 schema_version=1, environment=synthetic을 갖고 nested형은 명시 decoder 표에만 등록한다. 기존 64KiB canonical 한도·정확 소수·UTC·고정 필드/버전·해시 prefix를 유지한다. 공통 필드의 구체 생성자 배치는 구현 문서에 기록하되 아래 의미/결속을 생략할 수 없다.

- BrokerReadBinding: binding_version, environment, broker=kis, account_ref, capability_version, wire_profile=paper, endpoint_registry_version, catalog_version. 실제 계좌번호/키/host 입력을 받지 않는다. Q14 SyntheticBinding을 변경하지 않는다.
- BrokerReadCapability: broker/account_ref/wire_profile/registry/catalog/binding 버전, 허용 operation과 정확한 scope, 지원 상태·근거, 유효 시작/만료, 호출/페이지/수신행/byte/시간 한도를 결속한다. 합성 capability를 실제 계좌 지원으로 재사용하지 않는다.
- BrokerReadRequest: query_id, binding, operation, typed scope, requested_at, deadline_at. scope에는 operation에 필요한 시장·통화·거래소·기간·기간 분류·종목·가격·주문구분을 명시하고 불필요한 필터도 조용히 무시하지 않는다.
- BrokerReadBatch: request, request_hash, 기존 필드의 nested BrokerQueryResult, page_receipts, missing_scope, reason_codes. result.items는 고정형 관측이며 request/environment/account/capability/scope와 정확히 일치한다. 결과 기간은 request와 각 receipt의 시각을 결속한다.
- receipt: request_hash, page_index, 요청/응답 cursor, received_at, body_sha256, 검증 상태/사유, account_evidence. body hash는 원천 bytes SHA256이며 canonical hash와 구별한다. 실제 계좌 echo·원문·token·msg1은 복사하지 않는다.

계약 객체는 생성 및 canonical 복원에서 enum·정확 타입·nested 결속을 다시 검사한다. capability 만료/지원 미확인·cross-account/version/environment·부적합 scope는 fetch 전에 거부한다. synthetic adapter는 임의 callback/HTTP client를 받지 않고 고정 fixture만 소비한다. port의 존재 자체를 악성 동일 프로세스 코드에 대한 보안 경계로 주장하지 않는다.

## 비전송 KIS 요청 계획

공식 근거는 [조회 명세](../research/kis-read-contracts-2026-10-24.md) 및 그 문서의 고정 커밋 20파일이다. 아래6종의 GET path/paper TR만 registry에 둔다. 실제 host·계좌·인증 헤더 없는 비전송 계획이며 CANO/ACNT_PRDT_CD는 비공개 binding용 슬롯이다. 호출자가 임의 path/TR/header/params를 덧붙일 수 없다. 모의 지원 미확인3종 및 individual_executions는 unsupported다.

| operation | paper TR | 고정 범위/입력 |
|---|---|---|
| kr_balance | VTTC8434R | AFHR_FLPR_YN=N, OFL_YN='', INQR_DVSN=02, UNPR_DVSN=01, FUND_STTL_ICLD_YN=N, FNCG_AMT_AUTO_RDPT_YN=N, PRCS_DVSN=00, FK100/NK100 |
| kr_orders | inner=VTTC0081R, before=VTSC9215R | 명시 기간분류, 시작/끝 YYYYMMDD, side/fill=00, INQR_DVSN=01, INQR_DVSN_3=01(현금), PDNO/ORD_GNO_BRNO/ODNO/INQR_DVSN_1='', EXCG_ID_DVSN_CD=KRX, FK100/NK100 |
| kr_buy_capacity | VTTC8908R | 명시 PDNO·ORD_UNPR, ORD_DVSN=01, CMA/OVRS 포함=N; 이 값은 주문 요청/주문 허용을 뜻하지 않음 |
| us_balance | VTTS3012R | 명시 NASD/NYSE/AMEX, TR_CRCY_CD=USD, FK200/NK200 |
| us_orders | VTTS3035R | 현지 시작/끝일, PDNO/OVRS_EXCG_CD/ORD_DT/ORD_GNO_BRNO/ODNO='', side/fill=00, SORT_SQN=DS, FK200/NK200 |
| us_present_balance | VTRP6504R | WCRC_FRCR_DVSN_CD=02, NATN_CD=840, TR_MKET_CD=00, INQR_DVSN_CD=01 |

정확 path·parameter key는 고정 공식 함수의 params와 결속한다. 국내 주문 EXCG_ID_DVSN_CD는 params 본문 뒤 optional 삽입도 포함한다. 기간 분류는 호출자가 명시하며 임의 90일 계산으로 선택하지 않는다. 해외 주문의 전체 조회는 `broker_overseas_all` 범위로 표시하고 US만 필터링한 성공으로 바꾸지 않는다. 국내 현금 주문 필터도 계좌 전체 주문 완전성으로 확대하지 않는다. 현재 조회 범위에 나타나는 자산을 거래 허용 목록으로 해석하지 않는다.

## 원천 관측

고정 nested 관측은 보유/현금/주문누적/매수가능의 종류, 원천 section·row key, symbol/venue/currency와 관측시각, 숫자 필드와 unknown 사유를 갖는다. 공급자 symbol은 내부 instrument ID가 아니다. Q16의 정확 매핑이 없는 경우 source symbol만 보존하고 mapping_unknown을 명시한다. 금액·수량의 의미/단위가 미확정이면 내부 Money/Quantity로 만들지 않는다. 이 단계에서 source 사실만 출력하는 최소 구현도 허용한다.

- 숫자 필드는 source_field, 정확 decimal-string 또는 null, missing_reason, currency/unit 또는 null, semantic_status를 가진다. null/빈 문자열/0을 구별한다. float/bool/NaN/exponent/비정상 길이를 거부하며 조용한 trim/반올림/합산을 하지 않는다.
- 현금은 settlement_inclusion=unknown, reservation_inclusion=unknown, usable_for_internal_available_cash=false다. 동일 의미로 보이는 서로 다른 필드를 더하거나 max_buy_amt를 현금계좌 가용금으로 사용하지 않는다.
- 주문 키는 ord_dt+ord_gno_brno+odno 및 orgn_odno를 분리한다. execution_granularity=order_cumulative, individual_execution_id=null. 누적3→5의 차이2를 새 체결로 만들지 않는다. 날짜/수량/식별 필드가 불명확하면 complete로 승격하지 않는다.
- 반복 동일 행도 receipt와 수신 상한에 포함한다. 같은 주문 키의 다른 수량은 복수 관측+conflicting_observation으로 보존하고 합산/최신 덮어쓰기하지 않는다. 결과 complete는 false다. 같은 값의 중복도 이상 사유와 false를 유지한다.
- 신뢰된 합성 계좌 echo와 응답 값 비교는 decoder 내부에서만 수행한다. 불일치 페이지는 거부한다. 부재는 request_bound_only이며 계좌 검증 성공이 아니다. 숫자 계좌 echo·원시 오류·인증값은 repr/예외/반환 canonical에 포함하지 않는다.

## 응답·페이지·한도

고정 source 함수/chk에서 출력 section shape·필수 식별/숫자 필드·허용 미사용 필드 목록을 추출해 adapter 상수로 기록한다. 샘플/명세가 모순되거나 shape를 확정할 수 없으면 지원 미확인으로 남긴다. 임의 dict fallback·unknown field 무시·행을 조용히 버리는 동작은 금지한다. 성공 rt_cd='0' 및 필요한 section/타입을 검사하며 오류 msg1을 public 결과에 복사하지 않는다. 중복 JSON key/unknown field/과대 깊이·길이/계약 변화는 schema_mismatch로 닫는다.

현재 합성 기술 상한은 요청당4페이지·32개 원천행(중복 포함), 페이지64KiB, 실행관측 구간30초, canonical 결과64KiB다. capability는 이를 줄일 수 있으나 늘릴 수 없다. 금융 운용값이나 실제 API 유량으로 재사용하지 않는다. 상한 도달·시각 역전·미래 수신·만료·응답 부재는 정상 완료가 아니다. 재시도/sleep/refresh는 없다. 크기 초과 출력은 잘라서 성공시키지 않고 명시 실패로 반환한다.

M/F는 후속 페이지가 있다는 공개 근거이며 다음 요청 N과 cursor 쌍을 결속한다. 반복/누락 cursor·다음 페이지 오류·미확인 marker는 incomplete다. present_balance의 계속 표시에는 검증된 다음 token이 없으므로 중단한다. 성공 종료 marker의 실제 계정 의미는 미확인이다. **합성 fixture에서만 명시 `synthetic_terminal_v1` 근거와 빈 tr_cont를 함께 사용해 끝을 증명한다.** 순수 wire decoder가 빈/알 수 없는 marker만 보고 실제 완료를 판단하지 않는다. 이 합성 근거는 paper/live에 쓸 수 없다.

BrokerQueryResult status는 success/partial/error/unsupported/unknown이다. 앞선 검증 페이지 후 오류는 partial, 정상 종료 증거가 없는 첫 응답은 unknown 또는 error다. success+complete 및 정확 scope의 명시 종료 근거가 있어야 빈 성공이다. source_as_of=null을 관측시각으로 채우지 않는다. temporal_consistency는 최대 bounded_observation이며 source_snapshot이 아니다. raw_reference는 합성 증빙 참조이고 원시 bytes/계좌/키가 아니다.

## 연결 준비와 검증

ConnectionReadiness는 serializer 밖 고정 보고형으로 target_environment=paper, dummy account_ref, checked_at, missing_requirements/evidence_refs, real_transport_available=false, connectable=false를 반환한다. PG01/SG01/필요SG02/AP05·private 주입·암호화/키관리·보존/복원 항목을 고정 코드로 보고하며, 단순 true flag 목록으로 실제 권한을 열지 않는다. 키 loader·실제 transport·파일/환경변수 읽기는 이 구현에 없다.

필수 회귀는 binding/scope/version/만료·허용 요청 계획·6종 정상/미지원·정확소수/누락/0·오류/빈/부분·cursor/상한/시간·누적 중복/충돌·mapping unknown·계좌 echo/canary 미노출·JSON 구조 변경·canonical 왕복/기존 golden·실제 연결 불가다. 단독 구현 후 보안→일반→독립 실행 검증한다. 현재 로컬 준비의 통과와 실제 Q19 완료는 [카드](../tasks/BROKER-read-adapter.md) 기준대로 분리한다.
