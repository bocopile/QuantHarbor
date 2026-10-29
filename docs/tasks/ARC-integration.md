# ARC-integration — Q12 설계 통합과 구현 계약 고정

- 상태: 완료
- 단계·선행조건: Q07~11 독립 설계 판정, ARC-10·11
- 요청 근거·실행 범위: 사용자 전체 순차 작업, 확정 요구 및 후속 운용 관문 유지
- 담당·독립 검토 여부: root 통합, qh_reviewer 독립 검토 예정
- 입력 계약·설정 버전: 요구 v1·data/execution/operations v1, PG01~05·SG01~04
- 소유 파일: root architecture·contracts/serialization-v1·implementation-backlog·ARC-DEC004·본 카드·status·보드·큐
- Git 기준: head2fa8f1d, codex/arc-contracts 기존 checkout. 미커밋·PR/merge 없음
- 허용 도구·외부 변경 범위: 공개 로컬 문서/코드 구조 읽기·설계 통합. 제품 실행/연결 없음
- 검증 요청 범위: 계약 충돌·선행조건·소유권·완료 증거·문서 정합성. 금융 코드 검증 미실행
- 시간·비용 제약: 기존 구독·신규 지출0

## 산출물과 완료 기준

canonical 직렬화/hash 규칙, 전체 설계 관계, 요구/시나리오와 구현 단계 매핑, 단계별 소유 파일·검증·관문을 고정한다. 실제값 미정과 기술 결정을 구분하고 독립 검토 후 Q13 착수한다.

## 인계

- 실제 변경: serialization-v1·implementation-backlog·ARC-DEC004 및 아키텍처 통합본을 작성했다. execution-v1 후보에도 authority_generation을 명시했다.
- 실제 확인: Q11 보안/일반 통과. 코드 그래프에 QuantHarbor 인덱스 ready, src 파일 검색 결과 없음.
- 미실행: 제품 코드·DB·종속성 설치·계좌/API·금융 검증.
- 독립 판정: 제어문자 canonical escape 보완 후 통합 범위 통과. [증거](../evidence/arc-integration-review-2026-10-23.json).
- 다음: Q13 기반 구현.
