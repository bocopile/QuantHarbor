# Q27 재개 독립 보안 검토

검토 branch: codex/q27-resume-20261029, source SHA256 6cf7c1b52a4920b6e7a6c62873216a1bf118b24eb7b720cb4f352a70d5b11046. 실제 실행 시간/입력은 [증거](../evidence/execution-resume-security-2026-10-30.json)를 따른다.

root 반환 — **Q27-06-security-a01 / revision1: 마지막 P2는 수정 범위에서 정적으로 해결됐으며, 추가 차단 지적은 없습니다.** 독립 정적 검토이고 테스트는 실행하지 않았습니다.

- **기존 P2 발생조건·영향:** 같은 세대의 challenge 발급 후 source를 교체하면 완료 예약이 삭제되어, 후속 용량 소진 시 거절 receipt 저장이 실패할 수 있었습니다.
- **해결 근거:** `src/quantharbor/adapters/postgres_execution.py:514`는 pending/approved를 무효화하면서 `_pending_budget`만 보존합니다. `src/quantharbor/adapters/synthetic_approval.py:167`는 같은 세대·receipt 없는 명령만 계산합니다. `execute → _commit(release=True)`가 완료된 명령 몫을 제외하고 마지막 예약을 해제합니다. **확인 수준: 코드·계약 정적 확인. 이 P2의 수정 차단 사유는 해소됐습니다.**
- **보안 경계:** runtime/policy 권한 검사, nonce·actor/session/generation 결속, invalidated 대상 신규 challenge 거부를 유지합니다. 동일 source는 무변경 반환하고, 다른 source를 반복 적용해도 이미 invalidated인 승인 예약은 보존됩니다. 변경 경로는 consumed·unknown 금융 예약·claim을 해제하거나 새 실행권한을 만들지 않습니다. DB 저장 전 검사와 commit 이후 registry 반영·실패 복구 경로도 유지됩니다.
- **시험 변경 검토:** `tests/product/test_execution_control.py:116`의 approve 4행은 기존 AS2와 `_COMPLETION`에 부합합니다. repository에서 저장 실패 예외를 확인하고 발급 actor로 결과를 조회하는 수정도 기존 API 경계와 일치합니다. 제공된 `_finish` 심볼은 현 파일에 없으며 실제 완료 경로인 `execute/_commit`을 검토했습니다.

작성자 집중3개 PASS·519.075초는 실행 보고로 구분했습니다. [DB 결과](../evidence/execution-resume-pending-database-2026-10-30.json)의 3사례 PASS·281.84초와 지정 SHA 일치는 확인했지만, DB 실행·원시 SQL 검증을 독립 재수행하지 않았습니다. 포화 경계 전체, schema/state·전체 권한 행렬·경합·응답유실의 최신 전체 판정까지 입증하는 자료는 아닙니다.

**잔여 완료 조건:** 일반 독립 검토와 동일 최종 입력의 최신 전체 실제DB·제품/품질·고정40 판정입니다. Q27 전체 완료나 실계좌·전체시스템 안전을 보증하지 않습니다.

종료 전 source/test SHA는 요청값과 일치했고 diff SHA도 시작값 `85c2f34d…dfe`와 일치했습니다. 파일·DB·설정·Git 변경, 테스트, Docker, 외부 도구, 추가 agent, 자동 재시도 모두 없었습니다. 최종 확인: **2026-10-30 10:46:10 KST**, 약 113초.
