# ARC-data-contracts — Q09 구성요소·공통 데이터 계약

- 상태: 완료
- 단계·선행조건: Q08 설계 선택 독립 판정 통과. ARC-03·04
- 요청 근거·실행 범위: 전체 작업 순차 진행 및 확정 요구 v1. 금융 구현 전 계약 설계
- 담당·독립 검토 여부: qh_architect 읽기 설계 자문, root 계약 통합, qh_reviewer 독립 검토
- 입력 버전: 요구 v1·A-DEC001~003·B-DEC001·PG01~05·SG01~04
- 소유 파일: root만 docs/contracts/data-v1.md·decisions/ARC-DEC-001-data-boundaries.md·architecture·본 카드·status·보드·큐 수정. 제안 소스 경로는 아직 생성하지 않음
- Git 기준: head2fa8f1d, codex/arc-contracts 기존 checkout. Q09 진행 중 승인된 Git 전략에 따라 로컬 작업 브랜치를 만들었고 기존 변경을 보존했다. 추가 commit·PR·merge 없음
- 허용 도구·외부 변경 범위: 공개 문서 읽기/로컬 계약 문서 작성, 실제 계좌·키·API·주문·외부변경 없음
- 검증 요청 범위: 계약 일관성·실패경로·추적·로컬 링크·문법. 구현 테스트 미실행
- 시간·비용 제약: 기존 개발 구독, 신규 지출0

## 산출물과 완료 기준

- 구성요소 책임·호출/이벤트 경계·소유 데이터·생산자/소비자.
- 금융 기본형·시점·DataEnvelope·BrokerQueryResult·원장 이벤트·Snapshot·버전/정정/이행 계약.
- 결측/불완전·중복/역순·미체결 예약·수량과 평가 분리·미확인 공급자 필드 처리.
- 후속 Q10 승인/목표/주문 계약과 Q11 권한/운영 설계의 연결. 독립 검토 후 완료.

## 인계

- 실제 변경: [data-v1](../contracts/data-v1.md)과 [ARC-DEC-001](../decisions/ARC-DEC-001-data-boundaries.md) 작성. qh_architect 읽기 자문을 통합했다.
- 실제 확인: Q08 선행조건 충족. 모든 PG/SG의 실제 운용 관문은 미완료 유지.
- 미실행: 금융 소스·DB migration·실제 API·실계좌·성능/금융 테스트.
- 독립 판정: qh_reviewer가 정정·FX·시점·nullable 보완을 확인하고 Q09 명시 범위 통과. [검토 버전 증거](../evidence/arc-data-review-2026-10-23.json).
- 다음: Q10 AI·목표·승인·위험·주문 계약.
