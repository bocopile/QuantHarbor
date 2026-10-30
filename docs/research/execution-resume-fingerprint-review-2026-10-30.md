# Q27 fingerprint 판독 수정 독립 일반 검토

a04 두 파일의 HEAD 대비 독립 정적 검토에서 **보고할 결함은 발견하지 못했습니다.**

- [execution_uow.py:24](../../src/quantharbor/adapters/execution_uow.py#L24): fingerprint만 Decimal로 검증합니다. float 변환·숫자 정규화 없이 원본 바이트를 해시하며, 일반 파서의 소수 거부는 유지됩니다.
- [execution_uow.py:198](../../src/quantharbor/adapters/execution_uow.py#L198): 모든 페이지를 조립·검증한 후 해시합니다. 중복 키·비유한 수·잘못된 UTF-8·추가 JSON 출력·잘못된 페이지는 실패 처리되며, 프로세스 종료와 이후 commit 차단 경로가 유지됩니다.
- SQL의 기존 22개 테이블 조회·행 정렬·페이지 스냅샷 범위는 유지됩니다. 행·필드 삭제는 없습니다.
- 기존 repository의 digest 재해시는 호환됩니다. 확인한 소비 경로에서 과거 고정 해시나 dict 반환에 대한 의존은 찾지 못했습니다. **해시값 자체는 이전 방식과 달라지며**, PostgreSQL 버전 간 의미적 canonical identity를 보장하지 않습니다.
- 추가 6개 테스트는 정밀 숫자, 행 변경·추가, 다중 페이지, 거부·정리를 확인하도록 작성됐습니다. 실제 pipe 범위는 이미 활성화된 repository UoW 분기이며, DB 인증·권한·SQL 동작을 입증하지 않습니다.

**Actual tests: NOT RUN.** root의 진행 중 five-case DB proof는 조회하거나 PASS로 간주하지 않았습니다. 최신 전체 제품 PASS 및 Q27 완료 판정도 하지 않습니다.

578개 공개 입력은 해시 비교에서 변경 0개였습니다. 최종 SHA-256:

```text
execution_uow.py
ad4433ee4542bdf16fb7df6416d09ec76d419f187a99b1589a58b8061fb0bd41

test_execution_sql.py
ccaa95854b200d4ed5c85b44e6e593b90ec2a3b0172dff43bc476820788efd6d
```

[실행 근거](../evidence/execution-resume-fingerprint-review-2026-10-30.json).
