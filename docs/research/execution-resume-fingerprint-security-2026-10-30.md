# Q27 fingerprint 판독 수정 독립 보안 검토

**Q27-06-fingerprint-security-a02 / revision4: a04 diff에서 차단 사유나 새 결함을 발견하지 못했습니다.** 검토 범위는 지정된 두 파일의 HEAD 대비 변경과 fingerprint·SQL 페이지 문맥입니다.

- [Decimal 허용](../../src/quantharbor/adapters/execution_uow.py#L24)은 fingerprint 본문에만 적용됩니다. 일반 load/replay/events·상태·금융 메시지의 엄격한 파싱은 유지됩니다.
- [해시 계산](../../src/quantharbor/adapters/execution_uow.py#L198)은 모든 페이지를 조립하고 검증한 원본 바이트 전체를 사용합니다. 필드 제거, float 반올림, 숫자 정규화에 따른 값 합치기가 없습니다. 중복 키·NaN/Infinity·UTF-8·추가 출력 거부와 페이지·hex·크기·시간·rollback·계좌 제한도 유지됩니다.
- [SQL 문맥](../../migrations/0003_synthetic_execution.sql#L386)은 행 정렬 후 JSONB를 만들고, 페이지 시작 시 UTF-8 바이트를 고정합니다. 최종 fingerprint는 `SHA256(JSON문자열(SHA256(원본바이트).hexdigest()))`입니다. 코드 주석과 테스트에 이 구조가 명시되어 있으며, 기존 fingerprint와의 동일성이나 표현 형식 변경 간 호환성은 보장하지 않습니다.
- [신규 테스트](../../tests/product/test_execution_sql.py#L26)는 실제 로컬 pipe에서 `_exchange → _read → call → repository.fingerprint` 경계를 통과합니다. repository는 이미 활성화된 UoW 분기를 사용하므로 생성·권한·실제 SQL 검증을 입증하지 않습니다. 일부 잘못된 페이지 검사는 `_select` 모킹입니다.

**검증 실행: NOT RUN.** 전달받은 6개·26개 PASS와 이전 171 PASS를 독립 실행 증거로 재인증하지 않았습니다. 실제 DB 수정 검증은 미확인이며, 전체 제품/Q27 완료 판정이 아닙니다. 파일 변경 없이 검토했고 root probe에 관여하지 않았습니다. 전체 578개 해시 재대조는 수행하지 않았습니다.

[실제 실행](../evidence/execution-resume-fingerprint-security-2026-10-30.json). 검토자의 실제DB 미확인은 해당 역할 범위이며 root의 후속 실제 검증은 별도 증거다.
