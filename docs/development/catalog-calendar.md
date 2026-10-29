# Q16 합성 종목·달력 기반

Q16은 불변 합성 catalog와 명시 UTC 세션, 공급한 TZif bytes의 변환을 제공한다. 실제 종목·거래소·시간대 배포 자료·전체 시장 달력의 확보나 SG-02 권리 확인을 완료한 구현은 아니다. 새 공급자·API·계좌·주문·수집 기능은 없다.

## 카탈로그 조회

`Instrument`는 내부 ID/버전·상장 venue·명시 시장·통화·상품/ETF 분류·분류 버전/근거·효력 구간·known_at을 가진다. `SymbolMapping`은 provider/code·상장 venue·실제 체결 venue·내부 종목·매핑 ID/버전과 효력/지식 시점을 연결한다. provider code는 대문자 ASCII/숫자와 `. _ -`의 최대32자 문자열이며 case·선행0을 임의 변환하지 않는다. 이 초기 문법은 실제 공급자 형식 채택이 아니다.

```python
result = catalog.resolve(
    source_id, code, listing_venue_id, execution_venue_id,
    as_of=aware_instant, knowledge_cutoff=aware_cutoff,
)
```

조회는 `[valid_from, valid_to)`와 종목/매핑의 `known_at <= knowledge_cutoff`를 모두 만족해야 한다. 부재·미공개·효력 전/후는 `None`이다. 동일 ticker라도 시장/venue scope가 다르면 별개이며 currency나 ticker에서 시장·상품을 추정하지 않는다. 동일 상장 venue에 상충하는 market 기록은 거부한다.

초기 범위 조건은 명시 시장 `KR|US`의 equity 또는 근거가 있는 general ETF만 통과한다. unknown 시장/상품/ETF 및 leveraged/inverse ETF는 기록을 보존하면서 제외한다. 이 조건은 실제 금융 실행 권한이나 상품별 capability 확인을 대신하지 않는다.

동일 provider/code/상장·체결 scope의 매핑 구간 중첩과 동일 종목의 역방향 code 중첩을 생성 시 거부한다. 늦게 알려졌다는 이유로 중첩 중 하나를 자동 선택하지 않는다. catalog 안의 종목 identity와 mapping ID는 유일하며 매핑은 종목의 상장 효력 구간 안에 있어야 한다. alias·정정은 기존 객체를 고치거나 덮지 않고 **새 catalog version**으로 제공하고, 과거 조회자는 해당 지식 경계에 맞는 버전과 근거를 선택해야 한다. `known_at`은 구간 끝·분류를 포함한 전체 기록의 이용 가능 시각이다.

## 달력과 시간대의 주 조회 경로

`MarketCalendar`는 calendar version·venue·timezone ID·rules version/raw SHA-256·날짜 coverage `[start,end)`·known_at·source ref를 가진다. 각 `TradingDay`는 현지 trading date와 해당 날짜의 명시 UTC 시작/끝·known_at·근거를 보존한다. open day의 `TradingSession`에는 별도 session ID·정규/시간외 종류·UTC 구간·known_at·조기폐장 표시/근거가 있다. 휴장은 명시 closed day이며 누락·coverage 밖·미공개는 unknown이다. open day도 세션 밖이면 outside_session이다. 주말·UTC 날짜에서 휴장이나 현지 거래일을 추정하지 않는다.

```python
result = rules.lookup_calendar(
    calendar, aware_instant, knowledge_cutoff=aware_cutoff,
)
```

`ExplicitTimezone.lookup_calendar`가 후속 소비자의 주 진입점이다. timezone ID/version/hash와 규칙의 지식 시점을 결속하고, 각 날짜의 UTC 구간이 해당 규칙의 현지 자정 경계인지 검사한 뒤 조회한다. 불일치는 거부한다. raw `MarketCalendar.lookup`는 domain의 명시 UTC 사실 조회이며 시간대 결속 검증 완료를 뜻하지 않는다. domain에는 파일 I/O나 ZoneInfo import가 없다.

달력 metadata와 day/session의 지식 경계를 확인하고, 세션은 시작 포함·끝 제외다. 날짜/세션 구간 중첩·중복 ID·coverage 이탈·day와 session 날짜 불일치를 거부한다. day의 known_at은 포함 세션 전체가 알려진 시각이어야 한다. `regular_session_eligible`은 알려진 정규 세션 조건만 의미하며 시간외는 false다. 원장·대사·사용자 승인·실행 정책 관문을 대신하지 않는다. 달력 정정도 새 버전으로 전달하고 현재 달력을 과거에 알려진 자료로 간주하지 않는다.

`ExplicitTimezone`는 `ZoneInfo.from_file(BytesIO(explicit_bytes))`만 사용한다. host TZPATH나 설치된 tzdata fallback을 사용하지 않는다. version·raw bytes SHA-256·UTC coverage·known_at을 요구하며 실제 bytes와 hash를 대조한다. 이 hash는 원문 bytes 식별이고 기존 canonical 계약 hash와 별개다. 공통 serializer 등록 범위를 확장하지 않았다.

`to_local`은 aware instant만 받는다. `resolve_local`은 해당 zone 문맥의 offset 없는 명시 wall 문자열을 받으며 nonexistent time을 거부하고 ambiguous time은 명시 `fold=0|1` 없이는 거부한다. microsecond 초과 정밀도·bool fold·규칙 부재/미공개·coverage 밖을 조용히 보정하지 않는다.

## 합성 검증과 한계

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -v
python3.13 -I -S scripts/check_quality.py
```

테스트는 같은 ticker의 타시장 구분, 코드 변경/상장폐지 경계, 미래 매핑·분류 차단, 중첩 거부, unknown ETF/타시장 제외, 명시 휴장·조기폐장·시간외, 한국의 UTC/현지 날짜 차이, 합성 US DST 전후·23/25시간 날짜·gap/fold, 잘못된 binding/현지 날짜·naive 시각을 확인한다.

시간대 helper는 작은 TZif v1 bytes를 직접 생성한다. 이는 제한된 coverage의 합성 규칙이며 정식 IANA tzdb·실제 시장 영업일/상품 자료·공급자 권리/정확성 보증이 아니다. 이 작업의 호스트 제품 시험을 고정 Docker 재현이나 실제 시장 검증으로 확대하지 않는다. 실제 자료 채택과 권리·버전/coverage 검증은 SG-02 및 후속 작업에 남는다.
