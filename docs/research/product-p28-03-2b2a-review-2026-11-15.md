# P28-03 내부 2b-2a 별도 컨텍스트 검토 기록 (PR #7, 2026-11-15)

대상: PR #7(`merge/qh-local-delivery-20261030`, tip `4c24015`)의 코드 3커밋. 주 대상 파일은 `src/quantharbor/adapters/product_ai.py`, `synthetic_investment_ai.py`, `tests/product/test_product_ai.py`, `tests/product/test_product_ai_core.py`와 이들이 의존하는 `migrations/product/0002_ai.sql`·`product_schema.py`다.

**검토의 성격과 한계.** 일반 검토와 보안 검토는 각각 새 컨텍스트에서 읽기 전용으로 수행했지만, 같은 세션의 orchestrator가 띄운 에이전트이므로 사람 검토나 다른 모델 공급자의 검토가 아니다. NZ-SECURITY-03(실전 관문의 독립 검토 정의)이 정해지기 전에는 이를 PG-05·Q32의 독립 검토 충족으로 기록하지 않는다. 두 검토 모두 정적 판독이며 **테스트·DB·Docker를 실행하지 않았다.** 개발 쪽 증거 JSON의 PASS는 자기 보고이고 SHA 일치만 대조했다. 줄 번호는 `4c24015` 기준이다.

## 결론

- 두 검토 모두 P0·P1을 찾지 못했다. 투자 AI 경로가 금융 쓰기·승인·원장·정책 변경으로 가는 코드는 diff에 없고, 연결되지 않은 호출(dispatch·settle·settle_unknown·finish·execute*)은 `product_ai_bridge_required`로 닫혀 있으며 상태 불명이면 차단(fail-closed)이다. 코드 변경은 지정 4파일뿐이고 migrations·`product_schema.py`·금융 코어·도메인·application은 바뀌지 않았다. 모듈 docstring의 "execution, query and processed transitions remain closed"는 코드와 일치한다.
- 그러나 **수용(accepted) 판정에 필요한 증거는 아직 없다.** 최종 SHA의 전체 시험 PASS 기록과 실제 PostgreSQL 경로 시험이 없다. 이 PR은 계속 "수용 전"으로 표기해야 한다.

## 지적

| ID | 출처 | 심각도 | 요약 | 권고 |
|---|---|---|---|---|
| S1 | 보안 | P2 | 체크포인트 게시 SQL 함수(`ai_publish`)는 op 화이트리스트만 보고 예산 의미(소비량 감소 방지·revision 단조성)를 검사하지 않는다(`0002_ai.sql:50-82`). 증명은 Python phase bridge에만 있다. 함수 EXECUTE는 PUBLIC 기본값이고 0001/0002에 GRANT/REVOKE가 없다(`product_schema.py:105`는 `proacl IS NULL` 요구). 같은 DB에 접속하는 다른 role이 소비 기록이 비워진 체크포인트를 revision 비교만 맞춰 게시할 수 있다. | 전용 role에만 EXECUTE를 주고 PUBLIC REVOKE, 테이블 직접 DML REVOKE, 최소한 opcode별 단조성 검사. 또는 "단일 role 로컬 전용" 가정을 `docs/security.md`에 명시. 실제 role/GRANT 구성은 확인하지 못했다. |
| S2 | 보안 | P2 | 예산 정책(`AIBudgetPolicy`)과 `reserve`의 시각 `at`이 모두 호출자 입력이고 서버 시계·신뢰 출처에 묶이지 않는다(`product_ai.py:812-815,853`, `synthetic_investment_ai.py:327`). 같은 scope의 겹치는 window는 거부되나 첫 정책이 이긴다. 정책을 쓸 수 있는 호출자가 큰 한도를 먼저 등록하면 한도가 자기 선언이 된다. | 정책은 호스트 신뢰 설정에서만 주입, `budget_policy` 작성자 분리, `at`은 서버 단조시계로 제한. 투자 AI 호출자에게 repository 핸들을 직접 주는지는 미확인. |
| R1 | 일반 | P2 | 실제 PostgreSQL 증거를 재현할 수 없고 범위가 좁다. 증명 스크립트(`ai-core-proof-a0x.py`)가 저장소에 없고 a02 PASS는 7항목이며 `NOT_RUN`에 dispatched 복구 SQL fault fixture·closing 용량 포화·최대 payload가 남아 있다. build JSON은 구 SHA에서 196건 PASS, fixes JSON은 `current_199: RUNNING`이다. 최종 SHA의 전체 단위시험 PASS 기록은 확인하지 못했다. | 최종 SHA에서 전체 시험 결과를 증거에 기록하고 a02 스크립트를 증거와 함께 보관. |
| R2 | 일반 | P2 | 핵심 불변식 시험이 모두 `MemoryWire` mock 위에서 돈다(`test_product_ai_core.py:20-26`이 `ensure_schema`와 `_Pipe`를 patch). SQL 함수·권한·실제 psql은 이 시험들에서 실행되지 않는다. S1을 겨냥한 음성 시험도 없다. | 실제 DB에서 cancel·restart_reconcile 경로의 CAS·ack 소실·마커 불변을 확인. |
| S3 | 보안 | P3 | 재시작 복구 플래그가 프로세스 내 `database._product_ai_shared`에만 있다. 두 번째 프로세스가 factory를 열면 `reserved`를 전부 취소하고 `dispatched`를 `settle_unknown`한다. 현재는 dispatch 미연결이라 영향 없음. | dispatch 연결 전에 프로세스 간 단일 writer(advisory lock + owner lease) 요구. |
| S4 | 보안 | P3 | 영수증 한도 검사가 `asdict`+`json.dumps`이고 다른 경로는 `canonical_bytes`라 직렬화가 이중이다. float는 `parse_float`로 거부되어 실악용 경로는 못 찾음. | 한도 계산을 `canonical_bytes`로 통일. |
| S5 | 보안 | P3 | 오류 변환이 `OSError`/`TimeoutExpired`만 잡고 나머지는 전파된다. stderr는 저장하지 않아 민감정보 노출은 없다. `product_database.py`의 psql 인자·env 정화는 확인하지 못했다. | 해당 모듈 별도 검토. |
| R3 | 일반 | P3 | 커밋 성공 뒤 deadline 만료나 `_check` 실패가 나면 예외를 던지고 `failed`를 래치한다. 호출자는 결과를 알 수 없지만 DB에는 예약이 확정된다. 재시작 시 recovery가 취소하므로 안전하나 이 경로 시험은 못 찾음. | 문서화와 시험 추가. |
| R4 | 일반 | P3 | memory 코어와 파리티가 다르다. 퍼사드 `append`가 `sources=`를 조용히 무시하고 오류 타입이 다르다(`LedgerStorageError('bridge_required')` 대 `ContractError`). 2b-2a 범위에서는 의도된 폐쇄. | 문서화, 2b-2b에서 정렬. |
| R5 | 일반 | P3 | `test_budget_scope_window_role_request_attempt_and_concurrency_not_bypassed`가 `reason=='budget'`과 `writes==1`만 보고 어느 cap이 발동했는지 구분하지 않는다. | cap별 단언 보강. |
| R6 | 일반 | P3 | 두 퍼사드 경쟁 시험은 프로세스 내 락과 `MemoryWire` CAS만 검증한다. 프로세스 간 경쟁은 시험하지 않는다. | 범위 명시. |
| R7 | 일반 | P3 | 모든 읽기가 `product_gate`를 잡고 전체 체크포인트를 rehydrate하며 reserve 한 번에 `_transition`이 3회 실행된다. 조회 단계도 `Opcode.APPEND`로 라벨됨. | 2b-2b 전에 정리. |

## 양쪽이 확인한 양호한 점

- 허용 외 호출 차단: `_Pipe.publish`는 APPEND·RESERVE·CANCEL·RESTART_RECONCILE 외 opcode를 거부하고(`product_ai.py:573-575`) 비-APPEND는 phase 동일성·owner·generation·입력 digest·재유도한 book 바이트 일치를 요구한다. 외부 repository의 `_product_store` 대입은 거부된다.
- 원자성·멱등성: reserve는 request·policy·attempt·hold를 한 번의 publish로 커밋한다. 커밋 응답 유실·CAS 충돌·미확정 커밋은 재전송 없이 readback과 공유 latch로 닫힌다. 같은 payload는 `(a, False)`, 다른 payload는 `ContractError`다.
- 예산: 재시도 정책 0회 강제, 동시 reserve는 프로세스 락과 DB의 `pg_advisory_xact_lock`·`FOR UPDATE`·CAS로 직렬화, 포화 상태에서도 cancel 통과.
- 비밀·네트워크: HTTP·socket·urllib·requests·logging·print 없음, 합성 격리(`client_profile=='synthetic'`) 강제.
- 입력 검증: 중복 키·NaN·float·비정규 base64·길이 상한(raw 64KiB, 인코딩 32MiB, 청크 1024개) 거부, 체크포인트 재생성 비교.
- 시험: 락 타임아웃, 위조 phase, 외부 repo 주입, 미연결 경로 차단, lost ack, CAS 충돌, latch, 마커 위조 등 음성 시험이 풍부하다.

## 확인 못 한 것

- 어느 검토도 시험을 실행하지 않았다. 증거 JSON의 `protected_public_files_verified` 등 파일 보호 주장은 대조하지 못했다.
- `MemoryWire.publish`가 실제 SQL보다 느슨한지, `docs/contracts/product-ai-persistence-v1.md`·`ai-local-v1`·이전 검토 지적(a01/a02)·`docs/security.md`와의 항목별 회귀 대조는 하지 않았다. 도메인 `ResearchRequest`의 `allowed_queries ⊆ ROLE_QUERIES[role]` 검증 위치(요청 단계)와 `product_database.py` env 처리도 미확인이다.

## merge 판단에 필요한 것 (제안, 결정은 사용자)

- 코드 결함 기준 merge 차단 사유는 없다. 두 검토 모두 "수용 판정"이 아니라 "결함을 못 찾음"이다.
- merge 전에 권고되는 것: (1) S1·S2를 미해결 후속 항목으로 기록(실제 role/GRANT가 단일 role 로컬 개발이라는 전제를 `docs/security.md`에 명시할지 결정), (2) R1의 최종 SHA 전체 시험 결과 확보(시험 실행은 사용자 요청이 있을 때만 한다), (3) 증거 문서가 실제 PG 통과를 주장하는 부분과 mock 시험을 구분해 정정.
- 수용(accepted)에 추가로 필요한 증거: 최종 SHA의 `test_product_ai_core`·`test_product_ai` 전체 결과, 실제 PostgreSQL에서 다른 role로 `ai_publish` 직접 호출 음성 시험, cancel·restart_reconcile·dispatched 복구 fault fixture·closing 용량 포화, 두 프로세스 reserve와 `_recover` 경합, 변조된 `ai_state`(해시는 맞고 의미가 틀린 경우) 거부, 함수 본문·`proacl` 변경 시 `ensure_schema` 거부.
