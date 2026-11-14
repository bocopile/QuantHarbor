# Q27 재개 독립 일반 검토

검토 branch: codex/q27-resume-20261029. 실제 시간/입력은 [증거](../evidence/execution-resume-review-2026-10-30.json)를 따른다.

root 반환 — **Q27-07-review-a01 / revision2: 추가 지적 0건, 검토 범위 내 차단 없음. 마지막 P2는 정적으로 해결됐습니다.**

- `src/quantharbor/adapters/postgres_execution.py:513`는 pending/approved를 무효화하면서 `_pending_budget`의 같은 세대·receipt 없는 명령 비용만 보존합니다. 미완료 명령이 없으면 해제하며, 반복 source 교체도 기존 예약을 유지합니다. 기존 `execute`·`_commit`이 receipt 저장 후 잔여액을 다시 계산하고 마지막 완료 시 해제하는 흐름을 확인했습니다.
- `tests/product/test_execution_control.py:144`의 approve 9→4행 교정은 채택된 AS2와 `_COMPLETION`에 일치합니다. 저장 실패를 `repo.execute`에서 검사하는 것은 application의 예외 변환 경계에 맞고, 발급 actor의 `command_result` 조회도 기존 권한 검사와 일치합니다. 결함 은폐나 검사 약화는 확인하지 못했습니다.
- 세 회귀의 정적 검토에서 혼합 명령·만료·rollback·정확한 잔여 예약·반복 교체·terminal 신규 발급 거부·replay·원본 이력·신규 intent/claim/전송 없음 검사를 확인했습니다.

작성자 집중 3개 PASS·519.075초는 **작성자 보고**입니다. [실제 DB 결과 JSON](../evidence/execution-resume-pending-database-2026-10-30.json)은 root의 3개 집중 사례 PASS와 입력 불변을 기록합니다. 독립 재실행 증거로 취급하지 않았습니다.

남은 조건은 최신 동일본의 **전체 DB 84 시나리오, 제품·품질, fixed40 및 필요한 schema/state/권한 검사에 대한 최종 판정**입니다. 집중 결과를 합산해 Q27 전체 완료로 판단할 수 없습니다.

본 검토는 **테스트 미실행·독립 정적 검토**입니다. 파일·DB·설정·Git 변경, Docker·네트워크·추가 agent 실행은 없었습니다. 반환 직전 source/test SHA256은 지정값과 모두 일치했습니다. 전체 시스템·실계좌 안전 보증은 검토 범위 밖입니다.
