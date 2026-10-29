# PRODUCT-delivery — 대시보드·사용자 운영 순차 구현

- 상태: 계획 반영 완료·Q27 로컬 판정 대기
- 단계·선행조건: Q27 로컬 독립 판정 후 P28-01 착수. 기존 실제 금융 PG/SG/AP 유지
- 요청 근거·범위: 2026-10-27 사용자 전체 목록 통합·권고 순서 실행 지시, EXEC-DEC-002
- 담당: root 계약·공통 문서 통합 → Astra/high 설계 → Sol/high 단독 구현 → Astra/high 보안·Sol/high 일반 검토 → Luna/high 검증, 한 명씩 순차
- 입력 버전: 현재 plan/implementation-backlog/operations-v1·요구/카드, product-gap-review 및 evidence. 구현 착수 시 해당 소스 SHA 고정
- 소유 파일: root는 product-delivery-plan, product-delivery-queue, 본 카드, plan/checklist/backlog/큐/OPS/INTEGRATION/status/팀 보드. 제품 코드·UI 파일은 P28-02 설계 후 착수 카드에서 배정
- Git: codex/arc-contracts, HEAD 2fa8f1d4172ddfcb43a2e2f689186833c7c4a483. 기존 변경 보존, 이번 계획 작업 commit/merge/remote 변경 없음
- 허용: 공개 문서·자체 UI·합성 데이터·사용자 요청 범위 로컬 구현/검증. 실제 키/계좌/비밀번호·외부 전송·원격 공개·웹 금융 조작 제외
- 검증 범위: 계획 연결/큐 무결성, 이후 단계별 실제 제품·화면·합성 장애 검수. 실행하지 않은 검사는 완료로 기록하지 않음
- 시간·비용: 신규 제품 API 비용0, 실제 운영값은 관문별 사용자 결정

## 산출물과 완료 기준

[실행 계획](../product-delivery-plan.md)과 [하위 큐](product-delivery-queue.json)에 각 산출물·순서·주 담당·검토·검증·범위를 기록한다. P28-01~08은 로컬 Q28, P29-01/02 및 RETURN-01은 로컬 Q29 완료 조건이다. RETURN-02는 실제 연결 복귀이며 별도 실제 관문/증거가 필요하다.

## 인계

- 실제 변경: 전체 목록에 확장 하위 작업 배치, 기존 완료와 권한 경계 보존
- 실제 확인: 검토 보고서와 사용자 채택 지시를 반영. 계획 구조 검사 결과는 status에 기록
- 미실행: P28/P29/RETURN의 설계·구현·제품 시험, 실제 연결
- 다음: Q27 완료 예약·반복 수용 보완부터 계속, 완료 판정 후 P28-01 설계
