# P28-03 내부2a 독립 설계 자문

**Confirmed issues: 설계 불일치 2건, 모두 P2입니다.** 계약 SHA는 검토 전후 지정값 `2e916f…6c4dd2`와 일치했습니다.

1. **[P2] target 목록 시각이 존재하지 않는 필드를 참조합니다.**  
   [계약 16행](../../docs/contracts/product-artifacts-v1.md)은 `plan.body.request.created_at`을 지정하지만, [TargetRequest](../../src/quantharbor/domain/target.py)에는 `as_of`, `knowledge_cutoff`, `evaluated_at`만 있습니다. 그대로 구현하면 정상 target의 저장·목록 생성이 실패합니다.  
   **최소 수정:** 목록 `created_at`의 원천을 `plan.body.request.evaluated_at`으로 명시하고, candidate/result도 검증된 동일 plan에서 가져오도록 확정하십시오. 기존 DTO에 시각을 추가하거나 재시작 시각으로 대체할 필요는 없습니다.

2. **[P2] 공통 branch 거부 문구가 기존 저장소 동작과 다릅니다.**  
   [계약 24행](../../docs/contracts/product-artifacts-v1.md)은 branch 거부를 기존 검사로 설명합니다. 실제 한 부모의 두 번째 자식 거부는 [experiment 140행](../../src/quantharbor/adapters/synthetic_research.py)에 있습니다. [report lineage](../../src/quantharbor/application/reporting.py), [snapshot append](../../src/quantharbor/adapters/synthetic_valuation.py), [target append](../../src/quantharbor/adapters/synthetic_target.py)는 기존 자식 존재를 검사하지 않습니다. 공통 predecessor UNIQUE를 적용하면 기존에 허용하던 정정을 제품 경로에서 거절하게 됩니다.  
   **최소 수정:** 한 부모 분기 금지와 조건부 UNIQUE는 experiment에 한정하고, 나머지는 각 기존 predecessor·scope·시각·계보 검사를 보존한다고 명시하십시오.

**권장 확정사항 — 추가 결함 판정과 구분합니다.**

- **factory·수명관리:** 네 factory의 동일 정확타입 반환과 기본 메모리 경로 보존은 유지하십시오. [계약 7·24행](../../docs/contracts/product-artifacts-v1.md)에 매 작업 시 제품모드·ready·active·소유잠금 재확인, close와 공유하는 gate, reopen 후 재초기화 규칙을 명시하면 좋겠습니다. 현재 [DB transaction](../../src/quantharbor/adapters/postgres_ledger.py)은 ready만 검사하고, [close](../../src/quantharbor/adapters/product_database.py)는 별도 gate 없이 잠금을 해제합니다.

- **canonical·복원:** [계약 18행](../../docs/contracts/product-artifacts-v1.md)에 `canonical_bytes(parse_payload(raw)) == raw`, namespace별 정확 DTO, 두 hash와 파생 metadata 비교를 구체화하십시오. [기존 parser](../../src/quantharbor/domain/serialization.py)는 유효 JSON을 복원하지만 입력 bytes의 canonical 동일성까지 검사하지는 않습니다. target 복원은 개별 DTO 검사에 더해 [기존 묶음 검사](../../src/quantharbor/adapters/synthetic_target.py)의 plan/result/candidate 순서·내용 결속을 재사용해야 합니다.

- **원자성·race·quota:** [계약 22~26행](../../docs/contracts/product-artifacts-v1.md)의 잠금 범위를 predecessor/fork 검사부터 신규 키의 행·byte 증분 계산, 묶음·index·count commit까지로 확정하십시오. `_query()`마다 별도 psql 세션이므로 여러 호출에 transaction 잠금이 이어진다고 가정하면 안 됩니다. 동일 재append는 quota 증분 0이며, 서로 다른 `capacity` facade의 정책 적용 범위도 명시하는 편이 좋습니다.

- **migration·stop/reopen:** [계약 9행](../../docs/contracts/product-artifacts-v1.md)의 별도 schema/version 방향은 기존 금융 pin과 양립합니다. 신규 DB의 미설치 상태와 기존 schema의 버전기록 결손을 구분하고, 매 reopen 후 factory 연결 전에 지원 version/checksum을 다시 검사하도록 확정하십시오. COMMIT 응답 유실은 rollback 확정과 구별해 `unknown`으로 남기고, 동일 키·bytes·묶음 전체 조회로 저장 여부를 판별하도록 명시하면 복구 의미가 분명해집니다.

**미확인·미실행**

네 저장소의 생성/get/append/canonical/lineage, target 묶음, PostgreSQL exact-type·ready·lock·migration 접점을 정적으로 읽었습니다. 내부2a 구현·SQL·실제 DB 원자성·race·stop/reopen 시험은 **NOT RUN**이며 성공 판정하지 않았습니다. 파일 수정, 하위 agent, 원격 작업, 비밀 읽기는 수행하지 않았습니다. 승인·세션·nonce·AI budget 복원과 전체 HTTP·브라우저·성능 관문은 이번 선행조건에 추가하지 않았습니다.

root반영: revision2에서target evaluated_at과experiment한정fork거부로두P2보완. 권장사항을동일gate/open-generation/canonical재인코딩/단일transaction/증분quota/schema재검증/unknown확인으로명시했다. 구현/실제DB/독립구현검토는아직NOT RUN.
