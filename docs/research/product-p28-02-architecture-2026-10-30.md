**독립 설계 자문 결과: 보완 7건입니다.** additive 방향과 조회 HTTP/금융 IPC 분리는 타당합니다. 다만 아래 연결 규약을 확정해야 구현자가 서로 다른 해석으로 P28-03과 P28-06을 만들지 않습니다. 미구현 코드의 실행 결함을 판정한 것은 아닙니다.

[`qh-contract-change`](../../.agents/skills/qh-contract-change/SKILL.md)를 적용해 지정 계약과 제한된 생산자 소스를 대조했습니다.

1. **화면별 `data`와 생산자 연결이 계약으로 고정되지 않았습니다.**  
   [계약 32행](../contracts/product-read-v1.md)은 화면 목록과 공통 envelope만 정의합니다. 각 화면의 필수 필드·nullable·목록/상세 구조·원본 참조·조회 포트가 빠져 있습니다. 기존 `ReportRepository`도 `append/get`만 제공하므로 화면 목록을 바로 만들 수 없습니다.  
   **최소 보완:** 6행 매핑표로 화면별 생산자/조회 포트/최소 필드/미제공 상태를 고정하십시오. 후보 화면에는 기존 `full|partial`, 대상 scope, 생략 의미와 대체 관계를 보존해야 합니다. 이는 조회 결과의 `partial`과 별개입니다. 상세를 목록에 포함할지 별도 선택자로 조회할지도 정해야 합니다.

2. **복합 화면의 시점·완전성·상태 판정이 모호합니다.**  
   [34~38행의 시작점](../contracts/product-read-v1.md)에 단일 `as_of`, `knowledge_cutoff`, `state`가 있지만, 서로 다른 시점의 현금·주문·연구 결과를 함께 표시할 때 이 값들의 의미가 없습니다. `ZERO`인 현금과 `MISSING`인 평가액이 공존할 때 envelope 상태도 결정되지 않습니다. “오래되면 STALE”의 판정 근거도 미정입니다.  
   **최소 보완:** 구성요소별 시점·완전성·상태를 두고, 공통 cutoff가 없으면 envelope의 해당 값은 명시적으로 미확정 처리하십시오. `created_at`이 원본 생성인지 조회 snapshot 생성인지 구분하고, 신선도 정책 참조 또는 표시 유효기한을 반환하십시오. Decimal은 기존 serialization-v1을 그대로 적용하면 되며 FX·비율과 표시 반올림에도 같은 규칙이 적용됨을 명시하면 충분합니다.

3. **페이지 간 동일 snapshot을 유지할 수단과 수명이 없습니다.**  
   [38~40행의 시작점](../contracts/product-read-v1.md)의 repeatable snapshot transaction은 개별 요청 안의 일관성을 보장할 수 있지만, 다음 HTTP 요청까지 자동 유지되지는 않습니다. 서명 cursor와 revision vector만으로 과거 데이터를 다시 읽을 수 있는 것도 아닙니다.  
   **최소 보완:** 제한된 불변 조회 결과를 서버에 보관하거나, 정확한 revision으로 재구성하는 방식 중 하나를 선택하십시오. snapshot TTL·총 보관 상한·회수/퇴거·재시작 후 410 처리와 화면별 정렬키를 정해야 합니다. 여러 목록이 있는 화면에서 100행 한도와 cursor가 어느 목록에 적용되는지도 필요합니다. 권리 검사는 고정 snapshot과 별도로 매번 현재값을 사용해야 합니다.

4. **‘현재 권리’의 정본과 회수 전달 경로가 빠져 있습니다.**  
   [15행](../contracts/product-read-v1.md)과 [28행](../contracts/product-read-v1.md)은 권리 version과 응답 commit 직전 검사를 요구하지만, 누가 최신 권리를 제공하고 변경하는지는 정하지 않습니다. 실제 [`ReportPresentationRequest`](../../src/quantharbor/domain/reporting.py)는 호출자가 전달한 `current_rights`를 검증할 뿐 최신 권리를 조회하지 않습니다. 같은 오래된 grant를 두 번 검증해도 회수는 발견되지 않습니다.  
   **최소 보완:** 사용자 조회 scope와 자료별 이용권리를 각각 제공하는 정본 포트, revision 변경 주체, 실패 시 차단 규칙을 지정하십시오. 사용자별 lock만으로는 여러 사용자가 소비하는 자료 권리 변경을 직렬화할 수 없으므로, 관련 권리 revision의 변경과 응답 commit이 공유하는 검증 경계도 필요합니다.

5. **요청 식별·세대 전환·오류 응답의 순서 규칙이 미완성입니다.**  
   [46행](../contracts/product-read-v1.md)은 요청마다 식별자와 generation을 붙이도록 하지만, endpoint에는 이를 전달할 위치와 첫 generation 획득 방식이 없습니다. 또한 이전 요청의 늦은 403/410이 새 로그인 이후 도착할 때, 즉시 정리 규칙과 이전 응답 폐기 규칙 중 무엇이 우선인지 불명확합니다.  
   **최소 보완:** 요청 ID·예상 generation의 전달 위치, 최초 조회 절차, sequence의 할당 시점과 범위를 정하십시오. 성공·오류 모두 요청 당시의 클라이언트 세대에 결속하고, 종료/재로그인 시 로컬 세대를 먼저 변경하여 이전 응답이 새 화면을 지우거나 복원하지 못하게 하십시오.

6. **영속성 차이는 정확히 식별했지만 실제 조립 연결부가 빠져 있습니다.**  
   [60행](../contracts/product-read-v1.md)의 `PostgresLedger` 설명은 실제 코드와 일치합니다. [`close()`](../../src/quantharbor/adapters/postgres_ledger.py)는 자기 project에 `down --volumes`를 수행합니다. 추가로 [`ApprovalApplication`](../../src/quantharbor/application/approval.py)은 repository의 정확한 타입을 제한합니다. 따라서 새 영속 repository를 만든다는 설명만으로 기존 application에 연결되지는 않습니다.  
   **최소 보완:** 제품 소유 DB 연결/수명관리와 기존 실행 repository 사이의 지원 연결부를 지정하십시오. 비금융 저장은 기존 canonical DTO·hash·lineage를 보존하고, 승인 capability·세션 handle은 복원하지 않는 범위를 정해야 합니다. 기존 migration1~3과 baseline을 수정할 필요는 없습니다.

7. **정책 교체 대상과 CAS 경계가 하나의 ‘정책’으로 뭉쳐 있습니다.**  
   [54행](../contracts/product-read-v1.md)은 정책 ref/version/hash CAS를 요구하지만 기존 승인에는 `target_policy_ref`와 `approval_policy_ref`가 구분됩니다. 실제 [`replace_policy()`](../../src/quantharbor/adapters/synthetic_approval.py)는 `SyntheticApprovalPolicy` 교체이고, source 교체는 별도 연산입니다.  
   **최소 보완:** 교체 가능한 정책 종류별로 정본·기대 참조·직렬화 경계·기존 후보/승인/세션 영향을 매핑하십시오. 여러 저장소 변경이 필요하면 중간 실패 동안 신규 실행을 차단하는 절차를 명시해야 합니다. 기존 주문·unknown·예약 보존과 금융 자동 재전송 금지는 현재 문구를 유지하면 됩니다.

**P28-03 최소 실행 분해 권고 — 최대 6작업**

아래 경로와 연결부는 제안이며 아직 구현됐다고 간주하지 않습니다. 계약 보완은 root가 P28-02에서 먼저 통합하고, 작성자 한 명으로 순차 진행하는 편이 적합합니다.

| 작업 | 최소 산출물 | 후속 완료 증거 |
|---|---|---|
| 1. 제품 DB 수명관리 | 영속 DB 연결 어댑터, 기존 migration checksum 확인, 안전 종료 연결부 | 재기동 전후 금융 사실 보존·종료 시 자료 삭제 없음 |
| 2. 비금융 영속 저장 | 보고·평가·연구·AI·목표 저장 어댑터와 목록 색인 | canonical 값·hash·lineage 보존, 부분 저장을 완성 결과로 노출하지 않음 |
| 3. 화면 read model | 제안된 `domain/ports/application/product_view.py`와 `adapters/product_read.py` | 6화면 최소 필드·원본 참조·부분/누락·Decimal 변환 대조 |
| 4. 조회 snapshot·권리 경계 | 현재 권리 포트, snapshot 보관/재구성, cursor·순서 규약 | 변경 중 페이지 일관성·회수 후 응답 차단·만료 처리 |
| 5. 제품 실행 조립 | 제안된 `runtime/product_composition.py`, 재시작 상태 전이 | 테스트 fixture 의존 없음, 새 권한 세대·대사 전 차단·자동 재전송 없음 |
| 6. 분석 slot 연결 | 기존 operations-v1에 따른 15분 slot과 작업 상태 저장 | 중복기동·긴 작업·절전·시계변화 처리, 기존 주문 추적 우선 |

실제 사용자 인증·정책 교체 명령은 P28-04, HTTP·브라우저 연결은 P28-06에 유지하십시오.

파일 수정·재귀 위임·웹·테스트·실제 금융 행위는 수행하지 않았습니다. 구현 검증은 **NOT RUN**이며, P28-01의 FUP-P28-002와 Q27 통합 관문도 그대로 남습니다.