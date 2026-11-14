**추가 P2 1건이며, 기존 일반 검토의 COMMIT 오류 분류 P2는 해결됐습니다. 내부2a 최종 수용은 보류합니다.**

- **P2 — 재연결 시 저장 함수 본문 손상을 검출하지 못함.** [product_artifacts.py:189](../../src/quantharbor/adapters/product_artifacts.py)은 `append_artifacts(jsonb,integer)`의 존재만 검사합니다. migration 기록·테이블을 유지한 채 함수 본문이 저장 없이 반환하도록 변경되면 factory 검사를 통과하고, [306행](../../src/quantharbor/adapters/product_artifacts.py)은 정상 종료와 marker만으로 저장 성공을 반환합니다. **최소 해결:** 새 factory에서 설치된 함수 정의를 기대 정의와 대조하여 불일치를 차단하십시오. schema 손상 거부 계약의 결손이며, 정적 분석 결과입니다. 실제 DB 재현은 하지 않았습니다.

- **기존 P2 해결:** [311행](../../src/quantharbor/adapters/product_artifacts.py)에서 ERROR 여부보다 검증된 불변 레코드 재조회를 우선합니다. 전체 일치→성공, 읽기 불가→unknown, 완료 ERROR+불일치→rollback, 그 외→unknown으로 분류합니다. target 전체 묶음 검증도 재조회에 포함되며 자동 재시도는 없습니다.

그 외 검토 범위에서는 추가 지적이 없습니다. 정확 타입 factory·기본 memory, ready/active/소유 lock·open-generation, 공유 gate/close, canonical/hash/목록 metadata·target 묶음, experiment 한정 fork 금지, 동일 transaction의 중복·충돌·참조·quota 처리를 확인했습니다. 임의 authority/SQL/DSN 복원이나 제품 소스의 tests/scripts import 경로는 발견하지 못했습니다. 금융 migration1~3, 제품 수명관리·image/compose pin, 금융 repository/UoW 파일은 HEAD와 일치했습니다.

**증거와 한계:**

- 직접 수행: 파일·계약·제한된 Git diff 읽기와 SHA 대조. 최종 `inputs.json` 기준 **시작·종료 11/11 일치**입니다. 이전 일반 검토의 source2 SHA를 기준으로 삼지 않았습니다.
- 제공된 actual a02 결과: **104.218초 FAIL**, 완료 check 5개 기록. COMMIT 후 확인 오류 해결 항목은 포함되지만 이후 `dataclasses.replace`→target identity 검증에서 `ContractError`로 종료했습니다. 소유9 SHA는 이번 입력과 일치합니다. 전체 실제 DB PASS가 아닙니다.
- 작성자 89 PASS·품질 지적0·CommitOutcome 4 PASS는 전달받은 결과이며 재실행하지 않았습니다. 초기 actual 44.461초 FAIL도 후속 성공으로 덮지 않습니다.
- `rootbefore` 덮어쓰기 사고와 원래 root680 전체 snapshot 부재로 **공개 전체 불변은 증명할 수 없습니다**. writertracked673 불변은 사용자 제공 root 재대조 결과로 구분합니다.
- [execution_uow.py:92](../../src/quantharbor/adapters/execution_uow.py)의 직접 `Popen`은 close gate를 거치지 않습니다. 내부5 후속이며, 내부2a 검토를 새 금융 조립 전체 수용으로 확대할 수 없습니다.
- 수정·시험·DB·원격·비밀/private 자료 접근·하위 agent·commit/push는 수행하지 않았습니다. status도 수정하지 않았습니다. 내부2b AI budget, 현재 권리, HTTP, 종합 조립, 15분 slot 및 **P28-03 전체는 미완료**입니다.
