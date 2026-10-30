# Q27 a03 시험 준비 보완 독립 일반 검토

Q27-07-review-a02 / revision3: **지정된 후속 diff에서 수정 요청 사항을 발견하지 못했습니다.** a03은 테스트를 약화하거나 런타임 문제를 숨기는 변경으로 보이지 않습니다.

- [EX37 수정](../../tests/product/test_execution_financial.py#L276)은 자동 정리가 불가능한 `object()`를 실제 소유 자식 프로세스로 대체합니다. 기존 고정 거부 사유를 유지하고, 만료 deadline·5초 미만 반환·실패 표시·프로세스 분리·종료 회수·파이프 닫힘 assertion을 추가합니다. 런타임의 EOF 후 제한된 대기·kill/wait 경로와 부합합니다.
- [source refresh fixture 수정](../../tests/product/test_execution_financial.py#L307)은 `_auth` 무조건 통과 stub을 제거하고 실제 합성 정책·principal·발급 세션을 설치합니다. 금융 이벤트와 예약을 보존하며, 실제 인증과 현재 계좌 검증을 실행합니다. 빈 source history도 이 초기 fixture 문맥에 맞습니다.
- 기존 승인 v2의 record/head 설치는 원래 typed 승인 fixture의 상태 복원입니다. 신규 실시간 승인 권한 발급을 증명하지 않으며, `_put`의 버전 전이 검사를 완화하지도 않습니다.
- 반영액·예약 cutoff·불변 원본 source·현재 binding·stale query 거부와 상태 보존 assertion은 유지됩니다. `__wrapped__`와 메모리 `_commit`을 사용하는 금융 단위시험 경계는 기존 한계입니다. DB transaction 원자성이나 최종 저장 검증의 증거로 확대할 수 없습니다.

root 제공 관측은 최종 대상 2개 **PASS**(22.759초), 금융 모듈 21개 **PASS**(211.462초), skip 0입니다. CLI 종료 코드만으로 성공을 추론하지 않았습니다.

**NOT RUN:** 본 검토에서 테스트·Docker·네트워크·MCP·앱·agent는 실행하지 않았으며 전체 783개를 재검증하지 않았습니다. 파일 수정은 없고, 관련 런타임 3개와 금융 테스트의 반복 해시는 동일했습니다. 제공된 런타임·금융 테스트 해시와도 일치합니다. Q27 전체 완료 판정은 아닙니다.

실제 실행은 [증거](../evidence/execution-resume-review-a02-2026-10-30.json)를 따른다.
