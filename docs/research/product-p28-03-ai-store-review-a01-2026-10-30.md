**3 findings — 모두 P2.** 지정 6파일의 전후 SHA가 모두 입력값과 일치했습니다. 아래는 실행 재현 없이 코드로 확인한 조건입니다.

1. **고정 book CHECK 손상을 schema guard가 놓침** — [product_schema.py:82](../../src/quantharbor/adapters/product_schema.py#L82)
   재현 조건: 기존 v2의 `ai_state` CHECK를 `book=1`에서 `book IN (1,2)`로 바꾸고 기존 행을 `book=2`로 이동합니다. CHECK 개수·컬럼·PK는 그대로여서 registry 검사를 통과합니다. `ai_metadata()`는 `book=1`만 조회하므로 기존 checkpoint를 빈 book으로 판독하고 새 append를 허용합니다.
   영향: 손상된 DB를 거부하지 않고 공유 book을 사실상 초기화합니다.
   최소 보완: CHECK 개수에 더해 고정 book·codec·길이·hash 등 각 제약의 실제 정의를 검증하십시오.

2. **전체 deadline에 잠금 대기와 최종 codec 검증이 포함되지 않음** — [product_ai.py:650](../../src/quantharbor/adapters/product_ai.py#L650), [product_ai.py:620](../../src/quantharbor/adapters/product_ai.py#L620)
   재현 조건: 호출이 gate에서 59초 대기한 뒤 자체 I/O에 59초를 사용하면, deadline을 잠금 획득 후 생성하므로 약 118초 뒤에도 성공할 수 있습니다. 마지막 chunk 이후 decode·재검증 중 만료되는 경우도 반환 전에 확인하지 않습니다.
   영향: 설정된 60초를 전체 작업 상한으로 보장하지 못합니다.
   최소 보완: 진입 시 절대 deadline을 만들고 잠금 획득에도 적용하며, 최종 decode와 성공 반환 직전에 만료를 확인하십시오.

3. **완료 result의 receipt에 시각·해소 참조 검증이 빠짐** — [product_ai.py:311](../../src/quantharbor/adapters/product_ai.py#L311)
   재현 조건: terminal result의 receipt가 허용된 query/source를 사용하지만 `checked_at >= request.deadline`이고 `resolved_refs=()`인 canonical checkpoint를 구성합니다. 관련 hash·marker와 query count가 일치하면 현재 codec은 이를 수락합니다. 진행 중 receipt에는 있는 시각·원천 포함 검사가 완료 result에는 없습니다.
   영향: 준비된 codec이 불가능한 조회 이력을 processed 자료로 받아들이며, 후속 2b-2 복원의 잘못된 전제가 됩니다. 현재 execute proof bridge의 미구현 자체를 지적하는 것은 아닙니다.
   최소 보완: 완료 result에도 동일한 receipt 관계 검증을 적용하십시오.

검토자 실행은 **actual/full/core/closing 모두 NOT RUN**, 테스트·쓰기·네트워크·Git mutation·하위 agent 실행은 0입니다. root AI55·최종 registry3 PASS는 전달된 결과이며, worker54/23을 최종 버전 증거로 확대하지 않았습니다. 검토 중 공개된 root actual 보고서는 동일 6SHA에서 **10 PASS·17.097초·2 chunks**를 기록하지만 독립 재실행하지 않았습니다. 최대 부하·전체 제품·core·미래 closing 증명이나 완전제품 수용을 뜻하지 않습니다.
