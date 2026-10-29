# Q25 로컬 합성 AI 소비 계층

`investment_ai`는 Q18 문서, Q20 사건/Q21 snapshot, Q23 성과, Q24 불변 후보를 읽는 합성 프로토콜이다. 실제 모델 품질·투자 성과·운영 격리를 평가하지 않는다. 실제 client는 disabled이며 신규 제품 API 지출·네트워크·주문 효과는 0이다. `synthetic_microcredit`는 가상 정수 단위다.

`application.investment_ai.Sources`에 `DocumentSource`, `FinancialSource`, `CandidateSource`와 Q16 `ExplicitTimezone`를 명시 주입한다. ref는 고정 kind·identity·version·canonical hash로 해소한다. 문서의 상충 revision/observation은 내용 해시 기반 ID로 구분하고 Q18 상충 판정을 보존한다. 임의 dict 경로·URL·파일·SQL·쉘 도구는 없다.

`ReadonlyDispatcher.execute(Query)`는 여섯 역할 허용표와 요청의 query/ref 교집합을 검사한다. 계좌·시점·목적·선택된 금융 입력은 요청에서 가져온다. Q14의 research/reporting 읽기 권한도 확인한다. 같은 프로세스의 악성 코드를 격리하는 경계는 아니다.

`run_research(request, policy, sources, client, attempt_id=..., reserved=..., clock=...)`는 공유 `SyntheticAIRepository`에서 예약한 뒤 합성 client를 호출한다. 모든 역할은 같은 repository를 공유해야 한다. window·역할·요청·attempt의 token/calls/가상 비용, 동시성2, 저장할 기록과 최대 bytes를 잠금 안에서 확인한다. 예약은 input+output×2+calls다. 전송 전 취소만 해제하며 알려진 사용량은 응답이 invalid여도 정산한다. 초과 사용량은 실제 값을 기록하고 scope를 막는다. unknown 청구는 예약을 유지하고 새 window도 막는다. attempt/payload와 정산은 멱등이며 상충 입력은 거부한다. 프로세스 재시작을 넘는 영속 청구 저장소는 아니다.

응답의 성공 선언은 받지 않는다. 필수 자료 누락·상충·구조적으로 유효한 잘림·알 수 없는 수치는 partial, 스키마/정확 인용/수치/단위 불일치는 invalid, 권리/도구/예산/TTL 사용 거부는 blocked, client 실패/timeout/늦은 응답은 failed다. complete도 서술의 의미적 정답을 뜻하지 않는다. 잘못된 직접 생성자·parser 입력은 `ContractError`로 거부한다. 오류에 원시 응답·예외를 반사하지 않는다.

Q18 인용은 실제 manifest/revision/observation/original/context와 정확 UTF-8 byte 범위를 결속한다. quote는 정확 인용 본문만 허용하고 해석은 inference/hypothesis로 표시한다. 숫자는 고정 selector로 실제 원장 replay·snapshot 재구성과 bound performance를 검증한다. 문서 숫자는 authoritative 숫자 원천이 아니다. scalar benchmark만 있으면 검증된 지표로 사용하지 않는다. 현금의 타 통화 환산이 지원되지 않는 selector는 unknown으로 보존한다.

모든 평가점·흐름 경계·후보 위험/일간 입력과 benchmark에 소비 시각의 source/dataset/version/rights_ref·목적·철회/만료 및 proof 완전성을 검사한다. 과거 grant로 현재 권리를 대체하지 않는다. 실제 ref/account 범위가 필수이며 빈 position scope는 그 명시 계좌/ref의 전체 범위로 사용한다.

`review_result`는 정확 result hash와 서로 다른 invocation ID를 요구하고 현재 원천을 다시 검사한다. 합성 응답 두 개가 실제 독립 모델 평가를 의미하지 않는다. Q24 candidate/plan/inputs를 재생하지만 후보 문구·금융 조건·TargetRef는 변경하지 않는다. `current_result`는 표시 시점의 권리·원천 누락·변경을 검사한다. 현재 사용을 확인하지 못하면 본문은 `None`이며 현재 status/reasons를 함께 반환한다. 원래부터 partial인 결과의 현재 확인 가능한 부분은 유지하고 과거 기록은 변경하지 않는다.

Hypothesis는 완성 result를 먼저 저장한 뒤 origin으로 참조한다. supporting/opposing claim ID와 실제 predecessor를 검사한다. 조회마다 TTL 끝 제외·현재 의존 source/policy/strategy/rights와 supersession/retraction을 검사한다. 기록은 덮어쓰지 않으며 최대8개다. accepted review로 만료를 우회할 수 없다.

Period는 Asia/Seoul과 실제 Q16 TZif ref를 요구한다. 주간은 월요일 자정부터 다음 월요일, 월간은 1일부터 다음 달 1일이다. 표시 `[start,end)`와 Q23 성과 `(start,end]`의 차이를 결과에 기록한다. 다른 기간의 성과는 unknown이며 완전기간 수치가 있으면 그대로 보존한다. 개입 근거가 없어 0으로 만들지 않으며 현재 v1 보고는 intervention_unknown을 남긴다. 외부 전송·예약은 제공하지 않는다.

일반 한도는 canonical64KiB, 해소8MiB, refs128, claims32, citations64, checks/reasons64, 문자열 UTF-8 2KiB, repository128기록/8MiB이며 자동 eviction은 없다. Q25는 신규 의존성 없이 동작한다. in-process client를 OS 수준으로 hard kill하거나 실제 API의 timeout/usage를 측정하지 않는다. 자동 retry/escalation은 명시 차단한다.

고정 명세 `docs/contracts/ai-evaluation-spec-v1.json` SHA256은 `726411c4f367720820d7d47cc829e0baedca39254718c90c31a8bb8058004f3f`다. 평가 전 실제 fixture/source/lock/input refs를 `/tmp/quantharbor-q25/manifest-*.json`에 기록하며 case별 JSON과 evaluation JSON을 보존한다. 기대값은 실행 결과로 바꾸지 않는다. `latest.json`이 최신 구조화 결과를 가리킨다.

초기 전용9시험은 실패3/오류1이었다. 후보 중첩 필드 접근은 제품 결함, 출력 token 예약 부족·음수 배당은 fixture 오류였다. MDD fixture를 실제 Q17 가격99/119/89/107과 원장 현금1·보유1로 구성해 NAV100/120/90/108을 독립 선언했다. 중간 fixture의 발표/관측 순서와 cash0 baseline 오류도 수정했다. 첫 고정24평가는 23통과/1오류였으며 상충 revision 색인의 제품 결함을 수정했다. 별도7경계시험에서 생성자64KiB 제한 누락1실패를 재현해 수정했다. 경계시험의 최초 import 오류는 미구현 API 연결 시점의 시험 구성 오류로 별도 보존한다. 실제 명령 출력과 후속 결과는 임시 인계 파일을 따른다.

전체503시험(504.711초) 종료 뒤 추가 합성 probe에서 문서 position scope와 불완전한 원장의 cash selector가 complete가 되는 누락2건을 확인했다. 문서는 실제 catalog의 instrument/execution venue/mapping과 Q18 entity/instrument link를 대조하고, 금융 원천은 재생한 projection 완전성까지 요구하도록 수정했다. 이 수정은 전체 시험 종료 후 수행했으며 해당 전체 실행을 최종 소스 검증으로 표시하지 않는다. 최종 Q25 회귀·품질/공개 검사 결과와 전체 재실행 잔여 여부는 임시 인계 JSON을 따른다.

Q25 AS1~5 수정은 별도 `test_investment_ai_security.py`에 둔다. 수정 전 실제 공개 경로 5시험은 실패5/오류0이었다. 캐시 반환은 `current_result`로 현재 권리·원천을 재검사하며 거부 결과는 `denied:<attempt_id>`라는 저장하지 않는 `blocked` view다. response/manifest/receipt/checks/period 본문을 비우고 과거 결과와 정산 기록은 보존한다. 재호출은 client와 query를 다시 실행하지 않는다.

`SyntheticAIRepository.execute(...)`가 실제 `_run_research` 호출·정규화·원천 검증을 수행한 exact canonical 결과를 저장한다. `run_research`는 이 경계를 사용한다. `append('result', ...)`와 `finish(...)`는 저장소가 처리하지 않은 결과를 거부한다. 새 ID, caller의 status/checks/receipt/hash 변경은 처리 증거가 아니다. complete 생성자와 parser도 응답에 선언한 query에 대응하는 receipt 및 attempt ref kind를 요구하지만, standalone canonical은 실행 증명이 아니다. 실제 호출 중 query 거부는 저장소에 남으므로 client가 예외를 숨기고 응답에서 query를 지워도 blocked다.

`review_result`는 저장소의 `execute_review`를 거쳐 exact 처리 결과를 확인하고 현재 검증을 재실행한다. 원래 요청과 검토 요청 모두의 query 역할·허용표·원천 교집합을 적용한다. 검토는 query를 실행하거나 quota를 소비하지 않는다. 임의 `append('review', ...)`로 accepted를 수입할 수 없고 실제 검토로 생성된 불변 결과만 저장한다.

가설 생성자는 `repository.hypothesis_dependencies(origin_result_ref)`가 반환한 결정론적 필수 집합을 dependencies에 포함한다. 원래 요청·검증된 manifest·수치 claim·문서 citation의 원천/권리/자료, 금융 event·snapshot·benchmark, 후보 plan/policy/strategy를 결속한다. 추가 의존성은 허용하되 모두 실제 해소한다. `append('hypothesis', ..., sources=current_sources)`로 현재 원천을 명시할 수 있다. 생략하면 동일 저장소에 마지막으로 완성·주입한 `Sources`를 사용하며 과거 origin 원천으로 되돌아가지 않는다. 조회는 원래 요청의 원천/claim 검증과 필수 집합·현재 소비권리·TTL·정정/철회를 다시 검사한다. 호스트는 현재 원천을 주입할 책임이 있고 외부 원천의 최신성을 자동 수집하지 않는다.

`execute_query`는 실제 해소 전에 공유 저장소 잠금에서 요청 전체의 query16 한도를 소비한다. 실패한 해소는 한도를 환급하지 않으며 권한 거부는 해소하지 않는다. dispatcher·attempt·동시 호출을 새로 만들어도 초기화되지 않는다. `query_count(request_ref)`로 누적값을 읽는다. 같은 attempt의 진행 중 중복 호출은 결과를 저장하거나 client를 재호출하지 않는다.

전송 후 잘못된 calls/가격/usage의 `settle`은 원자적으로 `unknown_charge`와 scope 차단을 저장하고 예약을 유지한다. 다음 window도 차단한다. 이미 settled인 정상 usage는 잘못된 후속 정산으로 바뀌지 않는다. 상태 enum과 schema/spec 버전은 그대로다. 로컬 처리 증거는 in-process 저장소의 기록이며 악성 Python 코드·호스트·프로세스 재시작에 대한 격리나 외부 서명이 아니다.

고정24 평가 manifest는 매 실행의 고유 run_id, 실제 전체 제품 소스·합성 fixture·전용 시험·안내·lock·baseline SHA와 입력 refs를 첫 사례 전에 기록한다. 과거 평가/실패 파일을 덮어쓰지 않으며 latest 포인터만 갱신한다. AS1~5 및 inline 거부 은닉의 실제 red, 수정 중 생성자 거부로 발생한 시험 입력 오류, 최종 green·전체 시험의 source freeze와 실행 시간은 `/tmp/quantharbor-q25-security/`의 인계 산출물에서 구분한다. 이전 전체503 통과를 이번 수정 후 전체 검증으로 재사용하지 않는다. 이 안내 작성 후의 최종 검증 결과는 해당 산출물을 따른다.

2026-10-25 AS1b/AS3b/AS4b/AS5b/AS6의 회귀는 `test_investment_ai_security_second.py`에 별도로 둔다. 최초 5시험에서 원천 누락·변경을 포함한 실패6/오류0을 재현했다. 예약과 소유권을 결속하면 먼저 진입한 호출과 실제 예약자가 다를 수 있으므로, AS5b는 실제 예약자의 완료 기록 보존을 확인하도록 구체화했고 수정 전 실패1/오류0을 다시 보존했다. 시험 구성 오류는 없었다.

실행 소유권은 공유 저장소의 원자적 `reserve`가 새 예약을 반환한 실제 호출에서 결정한다. 예약을 얻지 못한 호출은 dispatch나 결과 확정을 수행하지 않는다. 정산 직후 아직 결과가 저장되지 않은 구간의 중복 호출도 원래 호출의 완료를 덮어쓰지 않는다. `_run_research`의 내부 반환은 결과와 실제 새 예약 여부이며, 공개 `run_research` 반환형은 `ResearchResult`로 유지한다. 이 내부 값은 caller의 처리 증명 필드가 아니다.

검토는 응답의 queries와 실제 모든 inline query_receipts를 합쳐 원래 요청·검토 요청 각각의 역할/허용 query/source를 검사하고, 검토 요청의 현재 원천·계좌·시점 범위도 재검증한다. query를 다시 실행하지 않는다. 검토 request와 review의 중복·총 records/bytes·예약 여유를 한 잠금에서 확인한 뒤 함께 저장하며 실패 시 둘 다 추가되지 않는다.

`settle_unknown(attempt_id)`는 dispatch 이후 clock 예외·잘못된 시각·역행·정산 전제 실패를 예약 유지·scope 차단으로 확정한다. 기록 시각은 dispatch 시각보다 이르지 않으며 이미 settled인 실제 사용량을 보존한다. 최종 clock 실패/역행도 이미 확정된 정산과 결과 시각을 되돌리지 않는다. 실제 client는 계속 disabled다. 이번 최신 소스의 전체 제품 시험은 실행하지 않으며, 과거521 통과는 이전 버전 증거다. 최종 집중 시험·고정24·품질·hash와 미실행 범위는 `/tmp/quantharbor-q25-security-second-20261025/handoff.json`을 따른다. 최종 독립 검토 후 전체 실행은 별도 validator가 담당한다.

2026-10-25 일반 검토 AR1~6의 추가 회귀는 `test_investment_ai_review.py`에 둔다. 초기 fixture 오류 2건(이미 응답 한도 초과, 현재 grant 변경 후 snapshot 미재구성)을 제품 실패와 분리하고, fixture 수정 후 8시험의 실패14/오류0을 보존했다. 실패14는 subTest를 포함한 수이며 독립 결함 수는 AR1~6이다. 최종 실행 결과와 파일 해시는 임시 `handoff.json`에서 인계하며 root가 공통 상태·증거를 통합한다.

결과 포장 크기는 생성자 검증 전에 계산한다. 64KiB 초과 시 응답·중복 checks를 제거한 invalid 결과로 축약하며 기존 blocked/failed 판정은 유지한다. exact request/attempt와 실제 query receipt·청구는 보존하고 PeriodReview도 들어갈 공간이 있으면 유지한다. 추가 축약이 필요하면 manifest를 권리 ref로 줄이고, 이후 중복 manifest, 마지막으로 period를 생략한다. 원래 source_refs는 저장된 request에 결속되며 축약 후에도 `current_result`는 현재 권리를 다시 검사한다. 실제 실행 receipt는 잘라내지 않는다. 기록 가능한 작은 결과 공간을 남기도록 누적 receipt의 UTF-8 JSON은 32KiB 안에서 수락하고 초과 query는 capacity 거부로 남긴다. 요청 query16은 계속 누적 상한이다.

전송 전 clock 예외·잘못된 값·역행은 새 예약을 가진 실행만 취소하고 failed 결과로 저장한다. 취소 시각은 마지막 확정 예약 시각을 사용하며 결과 저장 여유는 `finish`까지 유지한다. `cancel(..., retain_result=True)`는 이 내부 실행 경로의 추가 선택 인자다. 직접 cancel의 기본 해제 동작은 그대로다. 취소 attempt의 actual_usage는 기존 스키마대로 None이며 호출·비용 합산에서 제외한다. 전송 후 usage 불명·시각 실패의 unknown_charge 및 비소유 실행의 예약 보호는 별도 경로다.

주간·월간 추가 fixture는 해당 Asia/Seoul 경계의 실제 USD 전체 현금계좌 원장·snapshot을 사용한다. NAV100→110→121, 외부흐름·거래0에 대해 TWR0.21·PnL21·관측MDD0·회전율0을 독립 상수로 확인한다. benchmark0.21은 동일 합성 현금 경로를 명시 counterpart로 결속한 시험이며 실제 시장 benchmark나 시장자료 권리 검증을 주장하지 않는다. 정상 AI에서도 개입 자료는 unknown이므로 전체 상태는 partial이다. malformed known-usage 응답은 invalid, client 예외는 failed를 유지하면서 계산 가능한 기간 지표를 보존한다. 고정 E20의 다른 기간 fold는 계속 period_mismatch/unknown이다.

고정24 manifest의 과거 공통 refs 기록은 실제 사례별 변형을 모두 담지 못했다. 과거 기록은 삭제하거나 완전한 입력 기록으로 재해석하지 않는다. 새 `PreparedCase`/`PreparedVariant`는 평가 전에 모든 정정·누락·권리 변형, 요청·응답 bytes·usage·예약·정책·constant clock·부가 parser 입력을 구성한다. manifest는 각 변형의 실제 refs와 원천 내용 hash·현재 grants·의도한 누락을 기록한다. 각 시험은 준비 객체를 소비하고 시작/종료 시 결속을 검사하며 모든 준비 variant의 소비 여부를 평가 JSON에 남긴다. 검토의 exact result ref와 가설 origin/dependencies는 평가 실행에서 생성되는 출력이므로 사전 manifest에 output binding 규칙을 명시하고 실행에서 그 출력으로만 결속한다. 이 출력들을 평가 전 이미 해소한 원천 ref로 가장하지 않는다. 실제 모델 평가·독립 최종 검증 완료를 뜻하지 않는다.
