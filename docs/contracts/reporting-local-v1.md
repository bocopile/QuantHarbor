# 로컬 합성 보고 계약 v1 — Q22

상태: Q21 로컬 완료 후 채택한 root 추가 구현 명세. operations-v1·data-v1·valuation-local-v1을 소비한다. EXEC-DEC-001에 따른 synthetic 전용 조회이며 실제 금융보고·외부 전송·예약 작업은 아니다.

## 보고 입력·내용

닫힌 불변 Report는 schema/version, synthetic 환경·account/scope, snapshot ID/hash와 검증 가능한 snapshot, ledger cursor, as_of/knowledge_cutoff/projection_mode, 생성시각, 계산·보고 정책 버전, 자료권리 참조, provisional|reconciled, 미평가/미확정 사유·대사 차이, 정정 이전 report ID를 갖는다. 실제 snapshot을 canonical로 재검증한다. report ID는 고정 manifest hash이며 결과 hash와 분리한다. 필드/형식/schema/숫자·크기 검사에 기존 canonical 계약을 재사용한다.

보유 수량·가격·원통화/기준통화 평가·현금 component·대사 차이를 snapshot에서 그대로 취한다. Q22는 원가/성과/원장 계산을 추가하지 않는다. 원가·손익과 가용금/예약금/매수가능액이 unknown이면 미확인 사유를 표시한다. open_order_refs empty를 주문 없음으로 바꾸지 않는다. 부분 평가 known_subtotal은 확인된 부분 소계로만 표시하고 NAV/전체 자산/비중 분모로 부르지 않는다. 완전 NAV와 불완전 소계를 분리한다. 표시용 float·정밀도 손실·누락/잘라내기가 없어야 한다.

보고의 reconciled는 평가 complete와 전 계좌 보유·세 현금 component full_account_balances_matched가 모두 참일 때만 가능하다. 이 상태도 주문/체결 전체 운영 대사 또는 손익 확정을 뜻하지 않는 범위 문구를 표시한다. subset match·미평가·불완전·미조회는 provisional이며 미확인 이유를 보존한다. 근거가 없는 거래일은 UTC 날짜에서 추정하지 않는다. 초기 on-demand 보고의 거래일은 null 및 trading_date_not_resolved 사유를 명시할 수 있다. 검증되지 않은 사용자 날짜를 시장 거래일로 확정하는 입력은 두지 않는다. 일/주/월말 집계·달력 기반 job은 Q28 이후다.

## 소비 권리·시점

생성/표시 시각은 명시 입력이며 snapshot.created_at 이전이면 거부한다. report 목적(및 보고를 저장한다면 store) 권리를 해당 시각에 다시 확인한다. snapshot에 과거 유효한 권리가 들어 있었다는 이유로 현재 소비를 허용하지 않는다. 현재 RightsGrant를 명시 전달하고 snapshot market proof의 source/dataset/version과 정확히 결속한다. 누락·중복·무관한 grant·만료·철회·report 불허는 fail closed다. 자유 원문이나 외부 AI 설명은 입력/출력에 추가하지 않는다. 합성 권리 계약 검증은 실제 자료 권리 확보의 증거가 아니다.

## 저장·정정·표시

기본 repository는 최대128의 불변 메모리 append/get이며 동일 ID/hash 멱등·상충 거부·계좌/환경 결속·반환 객체 변조 방지를 검사한다. 운영 내구성으로 표현하지 않는다. 정정 보고는 실제 저장된 이전 report를 조회해 같은 계좌/환경/as_of/scope/base_currency, 생성·cutoff 순서와 snapshot 정정 계보를 확인한다. 최초는 이전ID null; 동일 snapshot의 단순 재표시는 정정 새 버전을 만들지 않는다. 기존 보고를 덮어쓰지 않으며 predecessor 누락/다른 계좌/역순/순환은 거부한다. 계보 검증에 SnapshotRepository 등 필요한 읽기 port를 사용할 수 있으나 원장/실행 쓰기 경로는 없다.

plain text와 JSON 표시를 제공한다. 숫자는 exact decimal string, null은 명시 unknown으로 보존한다. ID/참조도 escape하여 제어문자·터미널 escape·Markdown/HTML 삽입을 실행하지 않는다. 자유 입력을 오류에 반사하지 않는다. 출력에는 synthetic 표시, 평가/대사 범위, as_of/cutoff/생성시각, 원본 snapshot/보고ID 및 정정 전ID가 있어야 한다.

CLI는 기존 --version/status/validate-config 동작을 보존하며 로컬 보고 조회 명령을 추가한다. 표준 입력의 크기가 제한된 등록 canonical 합성 입력만 읽어 text/JSON을 stdout에 출력한다. 자동 파일검색·private/env 읽기·네트워크·파일 저장·shell 실행은 하지 않는다. stdin read 한도를 두며 잘못된 입력/초과/모르는 형식은 고정 오류와 nonzero, 금융 payload/stacktrace를 stderr에 내보내지 않는다. API 생성→canonical→CLI 표시의 실제 subprocess 시험을 포함한다. CLI가 무인 운영/외부 전달 경로를 만들면 안 된다.

## 검증·후속

독립 기대 텍스트/금액으로 완전/부분/unknown/0, 여러 통화, mismatch/subset/empty-source, 미확인 손익·주문 상태, 시점·권리철회/만료·목적/결속, canonical 위조, 실제 정정/누락 predecessor/멱등/충돌, CLI 초과/오류 비노출을 검증한다. Q21 입력 계약은 그대로 소비하며 수정이 필요하면 root에 보고한다. 외부 Delivery는 Q28과 AP10, 실제 운영 데이터·암호화 저장은 Q19 관문에 남긴다.

## 기본 text 표시 보완

기본 text는 사용자가 읽는 자산 보고다. account/scope·평가/지식/생성/표시 시각, NAV/확인된 부분소계와 평가 상태, 모든 보유·통화별 현금·원통화/기준통화·미확인 사유, 대사 범위와 모든 차이, 정정 관계를 한국어 구분과 행으로 보여준다. 모든 금융 항목은 보존하지만 전체 nested schema를 path=value로 펼치는 개발 진단 덤프를 기본 화면으로 삼지 않는다. 보고/snapshot ID와 정책 버전 등 추적에 필요한 근거는 간결하게 남기고, 모든 hash/data refs/current rights 전체 구조는 JSON에서 확인한다. JSON 구조·정확값·권리 검사·CLI 한도는 변경하지 않는다.
