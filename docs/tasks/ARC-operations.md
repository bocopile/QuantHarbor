# ARC-operations — Q11 권한·배포·운영·보고 설계

- 상태: 완료
- 단계·선행조건: Q10 범위 독립 통과, ARC-07·09
- 요청 근거·실행 범위: 전체 순차 작업·A-DEC-003 로컬 수동 운영
- 담당·독립 검토 여부: root 설계 통합, 보안/일반 읽기 검토 순차 예정
- 입력 계약·설정 버전: data-v1·execution-v1·요구 v1·PG/SG·security
- 소유 파일: root만 operations-v1·ARC-DEC-003·본 카드·status·큐·보드
- Git 기준: head2fa8f1d, codex/arc-contracts 기존 checkout; 미커밋·PR/merge 없음
- 허용 도구·외부 변경 범위: 로컬 공개 문서 작성·읽기, 운영 자원/키/계좌/전송 생성 없음
- 검증 요청 범위: 설계상 권한 우회·복구·세션·보고 일관성, 실제 권한 거부 검증은 후속
- 시간·비용 제약: 기존 구독, 신규 지출0

## 산출물과 완료 기준

권한표·배포 경계·계좌/환경 바인딩·자격증명 주입·로컬 인증·단일 egress·세션/큐·감사·보고·백업복구와 미정 운영값 관문을 명시하고 독립 검토한다.

## 인계

- 실제 변경: operations-v1·ARC-DEC-003 작성. 실제 권한·배포는 미구현.
- 실제 확인: Q10 독립 검토 통과. Q11 보안 검토의 복원 시 승인/nonce rollback 및 취소 egress 권한 구분 지적을 수정했다. execution-v1에도 authority_generation을 결합했다. 보안 판정 통과 후 일반 검토의 제어 세션 liveness 지적을 보완했다. 연결상실/기한 만료 시 admission/dispatch/egress 차단을 execution-v1에도 결합했다. 최종 일반 독립 검토에서 Q11 범위 통과.
- 미실행: 컨테이너/DB/계좌 생성·키 변경·보고 전송·운영 테스트.
- 완료 증거: [일반 검토](../evidence/arc-operations-review-2026-10-23.json), [보안 검토](../evidence/arc-operations-security-2026-10-23.json).
- 다음: Q12 설계 통합·구현 계약 고정.
