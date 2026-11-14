독립 일반 검토 결과: **P2 지적 1건**입니다. 기존 설계 7건·보안 2건은 revision3에서 계약 수준으로 해소됐습니다.

1. **P2 — 세대별 cookie의 브라우저 잔존 수명이 제한되지 않습니다.**  
   근거: [product-read-v1.md:26](../contracts/product-read-v1.md), [28행](../contracts/product-read-v1.md).

   **조건·영향:** 로그인마다 새 cookie 이름을 만들지만 발급 cookie의 `Max-Age`/`Expires`는 규정하지 않습니다. 종료 요청 없이 서버 세션이 만료되거나, 늦은 로그인 응답의 proof를 클라이언트가 폐기하면 cookie만 브라우저에 남습니다. 서버의 300초 만료와 활성 세션 8개 제한은 이 cookie를 삭제하지 않습니다. 같은 브라우저 세션에서 재인증을 반복하면 과거 세대 cookie가 누적되어 Cookie 헤더 크기 제한에 걸리거나 유효 cookie가 브라우저에서 축출될 수 있습니다. 따라서 “잔여cookie/고아발급을 제한한다”는 보장이 현재 규약만으로 성립하지 않습니다.

   **최소 수정:** 발급 cookie의 브라우저 수명을 서버 세션 만료에 맞춰 명시하고, proof 미채택·상실 세대를 포함한 잔존 cookie의 발급/정리 상한을 정하십시오. 지연 응답의 처리도 포함하되, 다른 활성 세대 cookie를 삭제하지 않는 기존 격리는 유지해야 합니다.

기존 9건의 확인 결과는 다음과 같습니다.

- **설계 1~3:** 6화면 생산자·조회 포트·목록/상세·nullable/state, Decimal·구성요소 시점·coherence, 불변 snapshot·TTL·페이지 결속이 36~59행에 반영됐습니다.
- **설계 4~5:** 현재 권리 정본·coordinator·회수와 응답 commit 경계, 요청 ID·epoch/generation·성공/오류 처리 순서가 63~71행에 반영됐습니다.
- **설계 6~7:** 정확타입을 유지하는 제품 DB 수명관리 제안, disposable 동작 보존, canonical DTO·목록 색인의 동일 transaction·lineage, 금융사실과 authority 복원 분리, 정책별 CAS·중간실패 차단이 79~105행에 반영됐습니다.
- **보안 1~2:** cookie와 독립적인 origin-memory proof, 세대별 cookie 이름·정확한 선택·해당 세대만 종료하는 규칙이 26~28·71행에 반영됐습니다. 위 추가 지적은 그와 별개인 잔존 수명 문제입니다.

검토 범위는 지정 계약 revision3, 기존 검토 보고서, data/execution/operations/serialization-v1 및 관련 reporting·approval·execution·PostgresLedger/UoW 소스입니다. 새 파일·포트·수명관리 진입점은 제안으로 평가했습니다. 그 밖의 실질적 상충은 확인하지 못했습니다.

파일 수정·재귀 위임·웹·테스트·실제 금융 행위는 수행하지 않았습니다. **HTTP/브라우저/IPC/재시작 검증은 NOT RUN**이며, 미실행 자체를 계약 결함으로 판정하지 않았습니다. **Q27·FUP-P28-002 통합/완료 관문은 유지**합니다.