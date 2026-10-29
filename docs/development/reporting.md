# Q22 로컬 합성 보고

- 작업: REPORT-local / Q22, REPORT-DEC-001, EXEC-DEC-001. Q21 로컬 통과 후 root가 단독 구현자를 배정했다.
- 입력: reporting-local-v1, operations-v1 Report, data-v1, valuation-local-v1, serialization-v1.
- 소유: 보고 domain/application/port/합성 adapter/CLI, additive serialization·진입점, 보고 fixture·시험과 이 가이드. 공통 계약·상태·최종 증거는 root 담당이다.
- 범위: 합성 snapshot의 결정론적 로컬 조회. 실제 자료·외부 전달·예약·원가/성과·운영 저장은 후속이다.
- 이번 보완: root의 기본 text 사용성 명세에 따라 application/reporting.py, test_reporting.py, test_reporting_cli.py와 이 가이드만 수정한다. 최초 독립 정확성 검토 PASS는 이전 버전의 결과로 보존하며, 이번 보완을 reviewer 결함 수정으로 기록하지 않는다. 공통 계약·상태·증거는 root 소유다.

## 공개 호출

`application.reporting.build_report(snapshot, request, current_rights, repository)`는 Q21 `PortfolioSnapshot`, `ReportRequest`, 현재 `RightsGrant`의 정렬된 tuple, `ReportRepository`를 받는다. 임의 dict·자유 설명·원문·가격 입력은 없다. snapshot/request를 기존 canonical 검사로 재구성해 위조한 nested 객체와 hash·금액·상태·scope 불일치를 거부한다. Q21의 금융 계산을 추가하거나 변경하지 않는다.

`ReportRequest(1, 'synthetic', created_at, reporting_policy_version='synthetic-reporting-v1', supersedes_report_id=None)`에서 시각은 명시 입력이다. 보고 시각은 snapshot.created_at 이상이어야 한다. 거래일 입력 필드는 없고 `Report.trading_date=None`, `trading_date_reason='trading_date_not_resolved'`를 보존한다. UTC 날짜를 거래일로 추정하지 않는다.

`Report`는 frozen/slots인 닫힌 typed 계약이다. 검증 가능한 snapshot, 요청, `ReportInputManifest`, 상태, 거래일 미확인과 고정 대사 범위를 포함한다. account/as_of/cutoff/scope/base_currency/cursor·정책/자료 참조는 포함된 snapshot에 결속한다. manifest는 snapshot hash/request hash/순차 version/생성 시 권리를 포함한다. `report_id='report:' + hash_record(manifest)`이고 완성 보고 hash와 구별된다. 같은 입력·권리·시각은 같은 ID와 내용이다.

현재 권리는 snapshot의 모든 MarketProof에 있는 source/dataset/version의 집합과 정확히 같아야 한다. 같은 dataset의 여러 series에는 하나의 grant를 준다. 누락·중복·다른 dataset·만료·철회·목적 불허는 fail closed다. 메모리 append를 하는 생성에서는 생성 시각의 report와 store를 모두 검사한다. 과거 snapshot 권리는 현재 권리를 대신하지 않는다. 선택된 원시 항목이 없는 held proof도 동일한 현재 권리 결속 대상이다. market proof가 전혀 없으면 빈 권리 tuple을 전달한다.

`ReportPresentationRequest(1, 'synthetic', report, display_at, current_rights)`는 등록된 canonical 표시 입력이다. 표시 시각은 보고 생성 이후이며, 그 시점의 report 권리를 재검사한다. 표시는 저장하지 않으므로 store 목적을 요구하지 않는다. `application.reporting.render_report(request, output_format='text'|'json')`로 표시한다. 표시용 JSON은 canonical 입력 wrapper와 별개인 조회 결과다.

## 금융 의미와 표시

보유 identity/수량/가격/원통화·기준통화 금액·현금 component·대사 원수량/차이는 Q21 값을 그대로 표시한다. 금융값은 exact decimal string이고 표시 반올림·float 변환은 없다. JSON의 null은 미확인이며 text는 `unknown (미확인)`으로 표현한다. 원가·손익은 `costing_spec_pending_q23`, 예약금·가용금·매수가능액은 `availability_semantics_unverified`를 유지한다. 미조회 empty open_order_refs는 `orders.status='unknown'`, `orders_not_queried`이며 주문 없음으로 표현하지 않는다.

`known_subtotal`은 확인된 부분 소계로만 이름 붙인다. 불완전 평가에서 nav는 null이다. 전체 평가가 complete이고 `full_account_balances_matched`인 경우만 보고 status가 reconciled다. 평가 complete/대사 mismatch와 평가 incomplete/대사 matched는 별개 축으로 보존한다. subset의 detail matched는 전 계좌 일치가 아니다. 출력은 보유·세 경제적 현금 component에 한정된 대사이며 주문/체결 전체 운영 대사·손익 확정을 뜻하지 않는 고정 문구를 포함한다.

기본 text는 한국어 자산 요약 → 보유 자산 → 통화별 현금 → 통화별 평가·환산 → 잔고 대사 → 주문 미확인 → 보고 근거·정정 순서다. synthetic 표시, 계좌·scope·as_of/cutoff/보고 생성·표시·snapshot 생성 시각, 조회 모드·최초 cutoff와 거래일 미확인 사유를 표시한다. 완전 NAV와 확인된 부분 소계를 구분하고, 모든 보유 identity/수량/가격/원통화 평가액/원가·손익 미확인, 모든 통화의 현금 component·가용성 미확인, 원통화 소계·FX 방향/환율/시각/출처·기준통화 금액과 각 사유를 빠짐없이 표시한다. 대사는 요청/확인/누락 범위·전 계좌 일치 여부·원천 참조와 모든 비교 행의 원장/원천 수량·차이·허용차·단위·상태·사유를 보존한다. 일치 행도 생략하지 않는다.

빈 보유·현금·통화 집계는 평가 complete 여부에 따라 확인된 빈 결과와 불완전 평가의 미확인을 구분한다. 미조회 주문의 빈 참조는 주문 없음의 근거로 쓰지 않는다. text의 추적 근거는 전체 report/snapshot ID, 정정 전 ID, 정책 버전과 원장 cursor/schema/reducer다. 전체 nested schema를 path별로 펼치지 않으며, hash·data refs·생성/표시 권리의 전체 진단 구조는 기존 JSON에서 확인한다. 문자열은 기존 JSON quoting과 제어문자·HTML/Markdown 구분자 escaping을 그대로 사용하며 JSON decode 후 원래 ID·문자열을 정확히 복원한다. text/JSON 모두 숫자를 재계산·반올림하거나 금융 행을 자르지 않는다. 원시 시장 payload·증빙 전문·외부 AI 설명은 표시하지 않는다.

## 저장과 정정

`adapters.synthetic_reporting.SyntheticReportRepository(capacity=128)`는 최대128개 canonical bytes의 메모리 append/get만 제공한다. 작은 capacity도1~128 범위다. 동일 ID/hash/bytes는 멱등이고 상충·용량 초과는 거부한다. evict/delete/overwrite는 없다. 반환 객체를 내부 Python 기능으로 변조해도 저장된 bytes는 바뀌지 않는다. 조회는 environment/account/ID/hash를 확인한다. 재시작 후 내구성·실제 운영 저장을 제공하지 않는다.

최초 보고는 이전 report ID가 null이고 version1이다. 정정은 실제 저장된 이전 report를 조회하며 version을1 증가시킨다. 같은 environment/account/as_of/scope/base_currency, 생성·cutoff·ledger cursor 순서를 검사한다. 새 snapshot의 supersedes_snapshot_id는 바로 이전 report의 snapshot ID여야 한다. Q21 restated의 original_cutoff와 더 늦은 cutoff도 기존 검증 함수를 재사용한다. 전체 report predecessor chain을 최대128회 실제 조회하여 누락·순환·역순을 거부한다. 같은 snapshot에 대한 단순 재표시는 정정 보고를 만들지 않는다.

정정 계보의 실제 저장 조회는 build/append 경계에서 확인한다. canonical 형식과 hash는 생성 주체의 서명이나 권한 증명이 아니다. CLI는 전달받은 보고의 구조·snapshot·권리·시각을 재검증하는 표시 경로이며 외부 저장소의 존재나 운영 권리를 증명하지 않는다.

## CLI

```sh
PYTHONPATH=src python3.13 -B -m quantharbor report
PYTHONPATH=src python3.13 -B -m quantharbor report --format json
```

API로 만든 `ReportPresentationRequest`를 `CanonicalPayload('ReportPresentationRequest', 1, 'synthetic', request)`와 `canonical_bytes`로 직렬화해 stdin에 전달한다. 기본은 text이며 `--format text`도 허용한다. 입력은 기존 canonical64KiB 한도이고 stdin read는65537 bytes까지만 요청한다. 전체 nested 보고와 표시 요청이 한도를 넘으면 거부하며 snapshot이 단독으로64KiB 안이라는 이유로 더 큰 wrapper를 허용하지 않는다. 표시 출력도 UTF-8 1MiB를 넘으면 거부하며 절삭하지 않는다.

입력 경로·출력 경로·shell·환경변수 옵션은 없다. 파일 자동 탐색/private·env 읽기/네트워크/파일 저장을 수행하지 않는다. `--version`, `status`, `validate-config PATH`는 기존 동작을 유지한다. 잘못된 보고·형식·초과 입력은 exit2와 고정 `QuantHarbor: invalid synthetic report input.`이고 금융 payload·입력 canary·예외 본문·stacktrace를 출력하지 않는다. 알 수 없는 명령은 기존 고정 오류다.

## 검증과 인계

전용 시험은 `tests/product/test_reporting.py`, `test_reporting_canonical.py`, `test_reporting_cli.py`와 `synthetic_reporting.py`를 사용한다. fixture는 기존 Q17/Q20/Q21 공개 API를 이용하며 제품 소스에서 tests를 import하지 않는다. 독립 금액 기대1022/1328600, 18자리 현금, unknown/0/부분 소계, mismatch/subset/empty-source, 현재 권리·시간·위조·정정·메모리 한도를 확인한다. 이번 text 보완은 독립 한국어 기대 행, 두 통화와 비영 수취25/지급-17·경제적 현금1008·기준통화 NAV1340300, 역방향 FX, 보유12행, 대사7행의 원수량/허용차/사유를 추가 확인한다. 실제 subprocess로 완전/부분/다중통화/mismatch/정정의 text와 기존 JSON을 확인하고, 기존 --version/status/--help/validate-config도 실행한다. canonical 전용 시험·공유 fixture는 수정하지 않았다.

이번 보완의 실행 명령:

```sh
PYTHONPATH=src python3.13 -B -m unittest discover -s tests/product -p 'test_reporting*.py' -v
python3.13 -I -S scripts/check_quality.py
git diff --check
```

2026-10-24 기본 text 보완의 단독 구현자 실제 로컬 검증:

- Q22 전용 최종 실행:47개 통과, 실패/오류0, 52.199초. 이전37개에 text/API8개·CLI2개를 추가했고 기존 text 기대값도 갱신했다.
- 공개 후보 정적 검사:352개 파일, findings0, 통과. ignored private 파일·Git 이력·원격 CI·전체 비밀정보/취약점 감사는 검사 범위가 아니다.
- 보완 첫 실행:47개 중 실패3·오류1, 50.994초. 새 시험에서 canonical 시각의 microsecond 표기와 권리 ID를 잘못 기대했고, 미결제 현금 fixture에 중복 counterparty leg를 넣었다. 두 번째 실행:47개 중 실패1·오류0, 50.321초. 중복을 없앤 fixture도 초기 baseline에 미결제 현금을 넣어 `baseline_shape`로 격리됐다. 기존 원장 계약에 맞는 초기 잔고와 합성 매도/매수로 수정한 해당 시험1개가 1.883초에 통과했고, 위 최종47개를 재실행했다. 이 과정에서 제품 금융 계산·계약은 수정하지 않았다.
- 전체 제품·품질 suite는 이번 보완에서 실행하지 않았다. 최신 버전의 독립 검토·전체 회귀는 후속 담당자에게 남긴다. 공개 후보 정적 검사·diff 결과와 원본 증거12파일의 최종 SHA256은 최종 인계에 반환한다.

이전 구현 버전의 실제 결과(이번 보완 버전의 회귀 결과로 사용하지 않음):

- Q22 전용 최종 실행:37개 통과, 실패/오류0, 37.169초. 정상 API 생성→canonical→실제 subprocess text/JSON 및 정정 표시를 포함한다.
- 전체 제품 suite:338개 통과, 실패/오류0, 45.547초. 기존301개와 Q22 37개다.
- 품질 suite:지정된 `-I -S -B`로87개 통과, 실패/오류0, 3.433초.
- 최초 Q22 실행:36개 중 실패1, 오류0, 37.503초. 0 현금을 zero-leg baseline으로 만든 fixture가 Q20에서 `baseline_missing`/`quarantined_observation`이 된 것이 원인이다. 정상적인 빈 baseline(cash_legs=())으로 fixture를 수정했다. Q22는 격리 사실을 그대로 보존했으며 unknown을0으로 바꾸는 제품 수정은 하지 않았다. 이후 두 원통화 현금 시험을 추가해 최종37개가 됐다.
- 이전 버전의 공개 후보 정적 검사:348개 파일, findings0, `git diff --check` 통과. 당시 소유12파일 hash와 결과는 원본 구현 증거에 보존한다.

독립 검토·최종 판정과 공통 status/evidence는 root 소유다. 합성 권리 검증을 실제 자료 권리 확보·실계좌 보고·외부 Delivery·영속 저장 완료로 표현하지 않는다.
