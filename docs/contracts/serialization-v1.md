# 직렬화·식별·해시 계약 v1 — Q12 통합 검토 통과

이 문서는 내부 계약용 `qh-canonical-json-v1`을 정의한다. 특정 외부 표준의 구현이라고 주장하지 않는다. 스키마 검증 전 임의 JSON을 hash해 승인하거나 실행하지 않는다. 구현과 golden/failure 테스트는 Q13이다.

## 금융 기본형·범위

금액/수량/가격/FX/비율은 문자열로 전달한다. 입력 문법은 ASCII `-?(0|[1-9][0-9]*)(\.[0-9]+)?`, 최대 입력 길이80자다. 공백·leading plus·지수표현·선행0·float·bool·NaN·Infinity를 거부한다. 정규화는 소수부 뒤0 제거·불필요한 소수점 제거·음의0을 `0`으로 변환한다. 정규화 이후 정수부 최대20자리·소수부 최대18자리인 유한 정확값만 허용한다. 따라서 PostgreSQL NUMERIC(38,18)에 넣을 때 값을 몰래 반올림하지 않는다. 금융 단위/tick/lot/최소금액·양수 조건은 별도 상품/필드 검증이다.

원통화 저장 scale과 실제 결제/주문 반올림은 다르다. 표시용 반올림 결과를 원장에 역주입하지 않는다. 곱셈·합산 중간 계산은 입력 저장 한도와 분리해 정확히 수행하고, FX division 등 반올림이 불가피한 계산은 명시한 정책의 precision/rounding/quantum 없이는 거부한다. Python 전역 Decimal context 기본값에 업무 반올림을 맡기지 않는다. 외부 공급자의 숫자 토큰은 adapter에서 원문 decimal을 정확히 파싱한 뒤 이 계약으로 변환하며 float를 거쳐 복원하지 않는다.

시각은 timezone-aware 입력만 받으며 UTC로 정규화해 `YYYY-MM-DDTHH:MM:SS.ffffffZ`로 출력한다. microsecond보다 높은 정밀도는 잘라내지 않고 거부한다. leap second와 naive 시각은 현재 미지원으로 거부한다. 날짜는 `YYYY-MM-DD`, 거래일/세션 매핑은 별도 달력 참조다. 기간 단위는 필드 스키마에 고정한다. 금융 의미의 시간 필드에 숫자 timestamp를 혼용하지 않는다.

내부 ID는 스키마별 ASCII 허용 문자·최대 길이를 검사한다. 외부 ticker/원천 ID를 내부 계좌/종목 ID로 그대로 신뢰하지 않는다. opaque ID의 `001`은 숫자 정규화하지 않는다. 필드 존재와 nullable은 스키마로 구분하며 누락을 null·0·빈목록으로 자동 채우지 않는다.

## Canonical bytes

1. payload가 등록된 `schema_name + schema_version`과 정확히 맞는지 검증한다. 알 수 없는 필드/버전/enum·중복 JSON key를 거부한다. 금액·시간은 위 정규형으로 변환한 typed payload를 사용한다.
2. 값의 종류는 객체·배열·UTF-8 문자열·bool·null·범위가 지정된 정수(예: count/version)만이다. float 및 정수 필드의 bool을 거부한다. Unicode surrogate를 거부하고 자유 문자열은 코드포인트를 그대로 보존한다(NFC 등 몰래 변환 없음). 계약 field key는 등록된 ASCII 문자열이다.
3. object key를 ASCII 사전순으로 정렬하고 UTF-8 JSON을 공백 없이 출력한다. JSON separators는 comma/colon, string escape는 quote/backslash를 각각 `\"`/`\\`, BS/FF/LF/CR/TAB을 각각 `\b`/`\f`/`\n`/`\r`/`\t`로 고정한다. 나머지 U+0000~001F는 `\u00xx`(소문자 hex 두 자리)로 출력한다. non-ASCII는 UTF-8로 그대로 인코딩하고 slash는 escape하지 않는다. 문자열 안 LF는 위 escape를 쓰며 구조/말미의 raw LF·마지막 개행·BOM을 넣지 않는다. null/true/false와 정수 표기는 표준 JSON 표현이다.
4. 배열 순서는 의미의 일부로 보존한다. 집합 의미 배열은 해당 스키마에서 명시한 stable key로 정렬·중복 거부한 후 입력한다. 임의 자동 정렬로 주문/분개/근거 순서를 바꾸지 않는다.
5. hash 입력은 ASCII 문자열 `QuantHarbor/qh-canonical-json-v1`의 bytes + 단일 LF byte(0x0A) + canonical bytes다. SHA-256 lowercase hex64를 사용하고 hash와 canonicalization_version을 함께 저장한다. 이 규칙을 변경하면 새 canonical version이다.

해시용 객체는 고정 wrapper `{schema_name, schema_version, environment, payload}`다. payload에는 해당 immutable 계약 전체를 넣되 hash 자체는 별도 저장하고 제외한다. schema_name은 엔티티를 분리하며 environment는 payload에도 존재할 경우 반드시 일치한다. 사용자가 제외할 필드 목록을 공급하는 API는 없다. 별도 mutable 상태·delivery receipt는 불변 후보 payload 바깥에 두고 자신만의 버전/hash를 갖는다.

OrderCandidate의 payload에는 candidate/plan ID·version·계좌·authority_generation·종목/venue·side·수량·가격/주문 조건·통화별 상한·정책/입력/권리/capability/calendar refs·기한·승인 화면의 근거/위험/비용 표현을 포함한다. 사용자 화면의 주문 의미가 바뀌면 새 후보/hash로 승인한다. approval에는 exact candidate hash와 사용자가 확인한 render version을 묶는다. 현재 quote/대사 입력의 갱신은 별도 RiskDecision으로 기록하며 기존 후보를 고쳐 쓰지 않는다.

원시 파일/HTTP 증빙의 `source_content_sha256`은 원문 bytes에 대한 별도 SHA-256이다. canonical 계약 hash와 원문 hash를 같은 종류로 혼용하지 않는다. 입력이 같으면 같은 해시지만 해시만으로 출처·사실·권한·위변조 방지를 증명하지 않는다.

## DB·처리 제약

- account/environment/authority generation·candidate identity·approval 소비 intent·dispatch attempt·source revision·consumer inbox 등에 업무별 고유키/foreign key를 둔다. hash만을 외부 사실 ID로 사용하지 않는다.
- 상태 전이는 expected version을 요구하고 전이/예약/감사/outbox를 원자적으로 처리한다. 충돌 시 기존 상태를 읽어 같은 요청이면 기존 결과 반환, 다른 요청이면 conflict다. 금융 입력을 last-write-wins로 덮지 않는다.
- DB lock 획득·transaction deadline 실패는 unknown 금융 결과나 실행 허가로 변환하지 않는다. broker 호출은 transaction 밖이며 execution-v1의 dispatch/최종성 규칙을 따른다.
- schema migration마다 checksum·순서·호환 코드 범위를 기록한다. 이미 적용한 migration checksum이 달라지면 중단한다. 데이터 손실 down migration 대신 새 migration/검증된 복구를 계획한다. 원장 사건 원본의 의미를 migration으로 조용히 바꾸지 않는다.

## 구현 검증 기준

동일 payload의 key 순서 변경·정상 decimal 표현 차이·UTC offset 차이는 정규화 후 같은 결과여야 한다. 후보의 계좌·환경·가격·수량·상한·기한·정책·generation 변화는 다른 hash다. 배열 순서 변경은 해당 의미에 맞게 다른 hash 또는 명시 집합정규화 결과다. duplicate key·unknown field·float·bool-as-int·과대 decimal·precision 손실·surrogate·잘못된 날짜·missing/null 오용은 거부한다. 고정 bytes/hash golden vector는 독립 실행 가능한 명령으로 대조한다. 현재 테스트는 미실행이다.
