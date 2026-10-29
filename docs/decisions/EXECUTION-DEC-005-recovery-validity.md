# EXECUTION-DEC-005 — 계좌 복구 유효성과 과거 주문 권한의 분리

- 날짜: 2026-10-27
- 관련 작업 ID: Q27 / EXECUTION-local, EXECUTION-DEC-004
- 상태: 채택 — 구현·실제 검증 전
- 결정 담당·요청 근거: root; 사용자의 순차 구현·검증 요청, 실제 합성 DB 반례와 Astra/high 읽기전용 설계 자문

## 요구와 확인 사실

[설계 자문](../research/execution-recovery-validity-design-2026-10-27.md), [실제 DB](../evidence/execution-database-lifecycle-fixes-2026-10-27.json)를 근거로 한다. 실제14사례는 13개 기능 경로와1개 만료 차단 진단이다. 만료 admission 종료는 저장되고 총필요행101→91로 감소했지만 새대사는 unresolved, 수동재개는 reconciliation_required로 거절됐다. 정적 입력상 approval 만료14:31:30과 원 request/실행정책 만료14:31:33을 구별한다. 아직 만료후 정상복구를 확인하지 않았다.

계약은 현재의 완전한 대사와 명시 권한으로 재개할 것을 요구한다. 과거 approval 하나를 선택해 그 TTL을 계좌 복구 조건으로 사용하는 것은 미지원 정정 경계와 달리 결함이다. 승인만료 한 줄 생략은 원 request 만료와 source 교체 순환을 남기므로 충분하지 않다.

## 선택과 이유

1. 주문용 validate_current는 원 Q24 source 재현·candidate/terms·approval/request TTL·정책 결속을 유지한다. 내부 현재 계좌 검사를 추출해 recovery/refresh/rebind/reconcile/resume에 재사용한다. 가짜 승인, TTL 연장, 공개 skip 플래그·callback·caller hash를 권한으로 사용하지 않는다. 승인 유무·첫 head 순서에 복구 결과가 의존하지 않아야 한다.
2. 계좌 전체 보유·통화·모든 실행 의무에 대해 잠긴 Q20 사건/원장, 실제 broker journal/query/manifest, Q21·Q23 계산, 현재 실행/target정책, 가격/FX/분류/매핑/달력/cost/capability와 소비하는 모든 자료의 현재 권리를 검증한다. 복구 유효구간은 실제 관측시각·freshness·권리·정책의 교집합이다. 과거 주문 request/approval TTL은 제외하지만 현재 정책/자료 만료는 계속 차단한다.
3. stopped에서 유효한 현재자료 결속→rebind/새 matched대사→명시 resume가 가능하도록 순환을 제거한다. 원자료와 정책이 만료되면 적법한 새 자료가 필요하며 정책 교체는 기존 policy 권한을 요구한다. runtime 권한만으로 정책을 바꾸지 않는다. 새 Q24 source 자체를 실제 재현해 검증하며 첫 과거 candidate가 새 source에 존재해야 한다고 요구하지 않는다. 원 candidate/terms/presentation/consumed/claim/명령/이력은 보존하고 비용을 계상한다. 옛 pending/approved로 신규 실행할 수 없게 한다.
4. 현재자료 결속과 reconciliation은 동일 계좌 registry gate·DB transaction·version/generation/fence/source CAS를 사용한다. 검증된 자료 identity·검증 버전·절대 유효구간을 결속하고 SQL closed shape/context/read-set·common_plan도 함께 검사한다. identity는 변경탐지이며 인증이 아니다. commit 전 registry 공유 금지, 실패 시 staged 입력도 rollback, COMMIT 유실은 DB 결속 관측으로만 해소하며 불명확하면 facade를 차단한다. 옛 matched 형식을 자동 승인하지 않는다.
5. 복구는 intent 생성·승인 소비·broker 전송 권한을 만들지 않는다. unknown/armed/prepared·미확정 비용·불일치 예약·미지원 정정·잘못된 manifest를 새자료만으로 해소하지 않는다. 신규 주문은 새 후보·승인과 기존 current_risk 및 SEC2 전송직전 시간 검사를 통과해야 한다. 원 승인 재사용·과거 intent 재전송·claim 해제는 금지한다.
6. DEC004 예약 수명주기·immutable evidence·owner분리와 모든 고정한도를 유지한다. 새로운 선택적 갱신은 미래 의무까지 사전 확보한다. 필수 완료는 rows/bytes 각각 actual+remaining 비증가를 입증한다. 새 필드/원본 보존 비용이 기존 예약에 들어간다고 추정만으로 처리하지 않는다.

## 영향·대안·소유권

실제 API·키·자금·운영 정책 값은 바꾸지 않는다. 미출시 Q27 합성 schema의 추가 결속이므로 새 임시 DB 검증을 사용하며 옛 snapshot의 자동 호환을 주장하지 않는다. frozen baseline7·fixture2·migration0001/0002는 불변이다. root는 본 결정·계약·작업·증거·상태를 통합한다.

단독 구현자는 application/execution.py, adapters/postgres_execution.py, 필요한 application/target.py 순수 seam, domain/execution.py·ports/execution.py·serialization·execution_uow.py·0003, execution 단위/SQL/제어/저장시험·합성 helper·check_execution.py·개발안내를 소유한다. 기본28파일에 target.py를 더한29파일을 버전 추적한다. Q24/Q26 공개 의미를 변경하지 않는다. 불필요한 전체 재설계 대신 기존 신뢰 구성·계산·저장 경계를 재사용한다.

## 미확인과 재검토 조건

구현·성공복구·새후보 실행·fresh source 순환·권한/정책/권리/금융 음성·SQL경합/rollback/응답유실·복사본 용량은 미검증이다. 자문 검증행렬을 추가 수용조건으로 적용한다. 단위→root 실제DB→독립 보안/일반 검토→최신전체 DB/제품·품질/고정40 순서로 판정한다. Q27 partial을 유지하며 P28은 완료판정 뒤다.
