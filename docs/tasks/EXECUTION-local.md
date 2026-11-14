# EXECUTION-local — Q27 합성 실행·위험·예약·복구

- 상태: 사용자 후속 요청으로 재개 (2026-10-29), Q27 미완료. [재개 카드](EXECUTION-resume-2026-10-29.md)
- 단계·선행조건: Q26 로컬 독립 판정, Q24 불변 후보, Q20 원장, execution-v1/operations-v1
- 요청 근거·범위: 사용자 비밀번호 입력 연기 및 입력 없는 순차 진행 지시, EXEC-DEC-001. I01-W/I02-W/I08-W 및 I03~07의 로컬 합성 범위
- 담당: root 계약/증거 통합 → 제한 설계 자문 → 단독 구현 → 독립 보안/일반 검토 → 독립 검증
- 입력 계약: frozen baseline-v1 및 선행 단계의 판정된 최신 파일 해시
- 소유 파일: execution-local-v1의 신규 실행 모듈·DB/UoW/broker·0003·시험/runner/안내 및 명시 통합 seam. 기존 변경·frozen 계약 보존, 작성자 한 명
- Git: codex/arc-contracts, 개발 기준 HEAD2fa8f1d. 2026-10-29 중단 시점 보존은 GIT-checkpoint-2026-10-29에서 수행
- 허용: 승인 소비·intent·현금/수량/위험 예약·outbox의 동일 transaction, 제출 직전 재검사, unknown 유지, 부분/역순/중복 체결, 별도 취소, 세대/fence, 중단·수동 재개
- 제외: 실제 증권사 submit/cancel, 키/계좌, 자금, 실전 egress·운영 격리 증명
- 시간·비용: 신규 제품 API 지출0, 실제 운영값 미정

## 현재 재개 — 2026-10-29

사용자 “분석 다되는데로 작업 진행해줘”로 패널별 설계 완료 후 기존 로컬 순차 구현·합성 검증·검토를 재개한다. 보존된 main에서 별도 Q27 작업 branch/worktree를 준비했고 source 교체의 pending 완료 예약 P2부터 확인한다. 실제 역할·검증 결과는 [재개 카드](EXECUTION-resume-2026-10-29.md)에 기록하며 과거 성공과 합산하지 않는다. 계좌·실제 주문·자금·외부 전송 범위는 확대하지 않는다.

## 이전 중단 상태 — 2026-10-29

사용자 요청으로 구현·제품 검증을 중단했다. 직전 pending 예약 P2 수정의 최종 인계는 확인되지 않았다. 현재 작성분을 보존하며 독립 재검토·최신전체 검증은 미실행이다. 아래 단계별 기록과 다음 순서는 과거 이력이며 자동 재개하지 않는다. [Git 보존 카드](GIT-checkpoint-2026-10-29.md).

## 산출물과 완료 기준

합성 주문부터 원장 반영까지 연결하고, DB 실패·중복 실행·결과 불명·철회 경합의 실제 시험 증거를 남긴다. 메모리 시험과 합성 DB 시험을 구분한다.

## 인계

- 실제 변경: 실행 모듈·DB/UoW·합성 broker 및 금융 정정 연결까지 부분 구현. 하단 단계별 증거 참조.
- 실행하지 않은 검증: 최신 정정본 actual DB27시나리오는 통과. 취소/재시작·용량/SQL 잔여 구현의 시험, 독립 검토·최종 전체 시험은 미실행.
- 남은 관문: 선행 로컬 판정 및 실제 연결용 PG/SG/AP는 별도 유지
- 다음: 정정본 actual DB 판정 → 취소/재시작 구현 → 용량/SQL → 독립 검토·최종 검증.

- Astra/high 자문을 root가 [계약](../contracts/execution-local-v1.md)·EXECUTION-DEC-001·고정40사례에 통합했다. fixture SHA256 `41756164ab565c611458d0d3dfeed236aaefa5d98973a76e04b04766c7ff46a1`. 단독 Sol/high 구현을 배정한다.

## 초기 부분 구현 반환 — 2026-10-25

- 소유17파일 SHA를 root가 대조했다. 신규33 첫 실행27통과·1실패·5오류 후 실패6만 수정 재실행해 통과, 영향 회귀14통과. 이후 안전 보완의 미실행 범위는 [부분 구현 증거](../evidence/execution-implementation-partial-2026-10-25.json)에 구분한다. 최신33전체 통과나 Q27 완료로 기록하지 않는다.
- 현재 원천 갱신·정정/비용·취소 handoff·복구·정확 저장 예산·SQL 제약은 잔여다. root actual DB 검사→결함 수정→잔여 구현→독립 검토/전체 검증을 순차 진행한다.

## root 실제 합성 DB 최초 검사

- 197.860초·exit0·16검사묶음·임시DB5개 cleanup·소유17hash불변. [실제 DB 증거](../evidence/execution-database-initial-2026-10-25.json). partial이며 fixed40전체 완료가 아니다. 승인/체결 단계별 rollback, Q20 실제 projection, partial/settlement A598, handoff전후 crash unknown/noresend, 보호철회, 실제DBlock경합을 확인했다.
- EX03의 완전한 두candidate동시입장/반대winner, EX05실제응답유실, EX27취소handoff, EX34closedSQL권한 불변식은 아직 미검증이다. 이를 검사 이름만으로 통과 처리하지 않는다.
- 다음 단독 구현: 현재source/query갱신·다중가격/수정/cumulative·known/unknown비용·매도/settlement·경쟁/응답유실 검증 보강. 그 뒤 취소/재시작·용량/SQL제약, 독립검토/전체실행.

## 금융 처리 부분 반환 — 2026-10-25

- 소유18파일 중11수정·root SHA/보호파일 대조. 초기focused47·회귀14, 신규조회4 중2오류 후 실패2+신규2통과, 부분확정비용1통과. 서로 다른 고정본으로 최종54전체 통과라고 합산하지 않는다. [부분 인계](../evidence/execution-financial-partial-2026-10-25.json). 공개505findings0·팀/diff·보호파일 불변.
- 수정본 actual DB runner 15시나리오는 root 실행 전이다. 누계 선행 정정/후속 의존, Q23 정정 이력 재생, 비용0 정정, 결제후 정정 해소·위험 음성 실제DB 행렬은 잔여다. 취소/재시작·정확용량·SQL제약도 유지한다.

## 수정본 실제 DB 판정·정정 연결 보완

- root actual PostgreSQL 551.427초·15시나리오·30검사묶음·ownDB15정리·소유18hash불변. [금융 DB 증거](../evidence/execution-database-financial-2026-10-25.json). EX03두실제동시요청/양쪽winner·EX05실제COMMIT응답프레임유실·EX08새조회후다음실제승인·EX20/21/23/24/26/38/39경제/rollback을 확인했다. 독립검토·전체제품과제어/용량/SQL은남았다.
- [EXECUTION-DEC-002](../decisions/EXECUTION-DEC-002-correction-performance-scope.md): 고정EX26의미지원정정차단은보존하며, Q20정상정정후Q23현재위험연결이막히는부분을별도보완한다. additive research helper/새 execution_research 및관련시험소유를명시한다. 다음단독구현자는이필수연결과실제위험음성/최종거절검증누락을담당한다.

## 정상 정정 연결 반환

- 소유22파일 SHA 및 보호파일 불변을 root가 대조했다. 최신 동일 고정본 전용75·영향21 통과, 고정 비교24 유지. [인계](../evidence/execution-correction-partial-2026-10-25.json). 새 DB runner27시나리오는 root 실행 중이며 완료 판정 전이다. EX09 상세 비영 예약/조회후사용량 분해, 제어/복구, 용량/SQL, 독립검토/최종전체는 남아 있다.

## 정정본 actual DB 완료·제어 구현 착수

- Q27 정정본 actual PostgreSQL27시나리오·42검사묶음 통과(1032.689초), ownDB27정리·22hash불변·stderr0. [DB 증거](../evidence/execution-database-correction-2026-10-25.json). 정상정정 후 다음승인·독립성과·위험음성·실제issuer최종거절을 확인했다. 단독 취소/재시작 구현을 배정하며 용량/SQL·독립검토·최종전체는 남겨 local7/10을 유지한다.

## 제어 구현 반환·실제 DB 집중 검증

- Q27 제어 후속10파일 보완·소유23/보호490 SHA root대조. 고정본1 집중15·영향39, 고정본2 신규/직접영향7 통과를 분리한다. [부분 인계](../evidence/execution-control-partial-2026-10-25.json). root는 DB검사 table allowlist 누락2개를 보완하고 경계6·공개515findings0·팀/diff를 확인했다. [runner 보완](../evidence/execution-control-root-runner-fix-2026-10-25.json). root actual DB21 집중 시나리오를 실행하며 최신 전체46 DB·전체제품·독립검토는 아직 미실행. retired_commands의 Q26/Q27 예산 귀속은 미확정이며 저장 자문에서 확인한다. local7/10 유지.

## root DB 복구 지적·수정

- Q27 실제DB 집중21 중11시나리오·22검사 통과 후 격리기록 복구의 restart_state 불일치로 중단, 생성12개 모두 정리했다. [실패 보존](../evidence/execution-database-control-initial-2026-10-25.json). 원인은 local quarantine alias를 issuer ID로 검증한 것이며 실제 red1 후 typed 원래ID 검증으로 수정·관련2통과. [수정](../evidence/execution-control-root-repair-2026-10-25.json). 수정 영향의 정상복구와 실패/미실행 후속을 합친 실제DB11개를 이어 검사한다. 최신 전체 통과 아님.

## 제어 실제 DB 부분 판정·저장 설계 인계

- Q27 복구ID 수정 후 실제DB11시나리오·11검사 통과(472.565초), ownDB11정리·소유23hash불변. [제어 DB 판정](../evidence/execution-database-control-2026-10-25.json). 초기의 앞10개와 수정후11개가 두 버전의 집중21 범위를 충족하며 최신전체46이나고정40완료를뜻하지않는다. 다음 Astra/high 읽기전용 저장/SQL 설계 자문을 배정한다. archive예산 귀속·EX09/11정밀통합·SQL제약·독립검토·최종전체는 잔여, local7/10 유지.

## 2026-10-25 저장·SQL 구현 착수

- Q27 저장/SQL 읽기 전용 자문 완료·소유23 현재 DB 버전 불변 대조. 최초 fill+정정7의 원장255행을 확인하여 고정192행 내 발급 전 manifest 거절, owner별 완료 예약, archive 중복 제거, 고정 SQL 권한 전달·bounded 전송을 EXECUTION-DEC-003으로 채택했다. 단독 구현을 배정하며 실제 검증 전이다. local7/10 유지, 비밀번호/Q19는 계속 연기한다.

## 저장/SQL 부분 반환

- Q27 저장/SQL12파일 보완·소유28/보호497 SHA와 로그를 root가 대조했다. 최종고정본 집중17·영향24·공개525findings0·팀/diff 통과. [부분 인계](../evidence/execution-storage-partial-2026-10-25.json). 실제DB55시나리오는 작성만 되었으며 먼저 migration/경제 smoke를 수행한다. 공통 완료 예약 상계·EX11·active3/terminal-third·대규모 전송 실제DB·독립검토/최신전체는 잔여다. local7/10 유지.

## 실제 DB 저장 SQL 보완

- Q27 실제DB에서 migration CASE 구문, 초기version -1/aggregate에 대한 원장전용parser 오용, JSON추출/키제거 우선순위 오류를 발견·수정했다. 원장0001/0002는 유지하고 bounded execution parser를 분리했다. 동일 SQL/권한/입력에서 stderr만 진단용으로 수집한 실제 기본흐름12묶음 통과(119.143초), ownDB정리. [수정·증거](../evidence/execution-storage-root-repairs-2026-10-26.json). 표준 전체runner·추가저장/SQL·독립판정은 잔여다.

## 2026-10-27 재개·저장 보호 철회 진단

- 앞선 실제 저장 집중검증에서 EX09 수량7/8·EX11 400+100+50 및 반대매도 미상계·SQL AUTH/CLOSED·예산 독립계산 등 7시나리오/10검사 통과 후 보호 철회에서 실패했다. [초기 결과](../evidence/execution-database-storage-focused-initial-2026-10-26.json). 컨트롤러 표시권한을 잘못 요구한 runner를 반환된 consumed 승인 참조로 보완했다.
- 이전 진단 실행은 자동 승인 심사의 사용량 한도로 실행되지 않았다. 이번 재개에서 같은 승인 경로로 실제 진단 실행: 63.408초·execution_auth 실패·ownDB 정리. 같은 트랜잭션에서 발급/소비한 보호 철회 challenge를 SQL이 기존 DB evidence로만 찾는 경로가 원인이다. [진단](../evidence/execution-storage-withdraw-diagnostic-2026-10-27.json). 단독 구현자가 원자적 철회 경계, 공통 완료예약, terminal-third, 전송검증을 보완한다. 최신전체·독립검토는 미실행, Q27 진행 중·로컬7/10 유지.

- Q27 저장 후속7파일 보완·소유28/보호500/로그SHA root 대조. 최종 동일고정본 집중21·영향4·공개533findings0·팀/diff 통과. [후속 인계](../evidence/execution-storage-followup-2026-10-27.json). 원자적 철회 결속·공통 완료예약·오류 후 커밋 차단을 보완했다. terminal-third는 특정 실제로컬 경로85+48=133>128로 미완료, 실제DB·전체증명·독립검토는 잔여다. root 실제DB 검증을 시작한다.

- Q27 후속 실제DB4시나리오/9검사묶음 실행·246.446초·ownDB4정리·소유28불변. [실제 DB](../evidence/execution-database-storage-followup-2026-10-27.json). root는 SQL alias/issuer 필드명/원문hash와참조hash 구별 및 검사기Boolean응답을 실제 실패 후 보완했다. 철회 결속13음성+양성/replay, 포화후체결·정정·취소·철회·복구, 실제9,437,209bytes전송과rollback/EOF/timeout/COMMIT응답유실 확인. terminal-third는85+48>128 음성 관측이며 양성 통과가 아니다. 공통 완료예약의 전체 충분성과 누적3번째 수용은 설계 담당에게 순차 자문 후 해결한다. local7/10, Q27진행중 유지.

## 2026-10-27 복구 완료 의무·반복 수용 보완 착수

Astra/high 설계 자문 반환·소유28 SHA 현재 일치. 18행 예약의 rebind 반례·재대사 의무 손실·미완료 command map 의존과 같은 세대 완료 lookup 회수안을 EXECUTION-DEC-004로 채택했다. 단독 Sol/high 구현을 배정한다. 새 구현·실제DB·독립/전체 검증 전이며 Q27 진행 중. 대시보드 등 확장 계획은 Q27 판정 후 Q28에서 시작한다.

## 2026-10-27 완료 의무 보완 반환·실제 DB 착수

- 단독 구현자가 소유7파일 보완·최종 src/tests 집중15통과(339.229초), 이전 영향9통과를 반환했다. root 소유28/보호520/로그 SHA 대조. SQL 마지막 회수 guard는 집중검사 이후 수정됐고 실제 DB 미실행이다. 역할은 인계JSON 작성 후 1800초 제한으로 종료됐으며 미종료 기록 명령0이다. [인계 증거](../evidence/execution-completion-implementation-2026-10-27.json). Q27은 partial이다.
- 공개 품질 검사에서 root가 확장 계획 문구를 넣은 frozen implementation-backlog의 해시 불일치1건을 발견했다. 해당 문단만 제거해 원래 baseline SHA와 정확히 일치시켰고 baseline manifest는 유지했다. 확장 계획은 product-delivery-plan·부모/하위 큐에 보존했다.
- 다음: 새6개와 기존 저장/SQL/전송 경로 실제DB 집중검사 → 결함 보완 → 독립 검토·최신전체 판정. 대시보드 P28은 Q27 판정 뒤 순차 착수하며 실제 비밀번호/API·금융 권한은 미사용이다.

## 2026-10-27 실제 DB 복구 예약 보정

- 새 SQL의 PL/pgSQL 변수/조회별칭 충돌을 실제 DB에서 발견해 `stage_item(value)`로 수정했다. 첫 실패6.909초·ownDB1정리, 수정본3시나리오/7검사 통과 후 재대사 경로에서 completion 검사 실패(274.223초·ownDB4정리). 각 실패 증거를 보존했다.
- 실패1경로 진단87.899초·ownDB1정리: 새 조회+대사로 actual60→62행인데 남은 예약12→11행으로 줄어 합계72→73이 됐다. 기존 조회가 저장됐다는 이유로 다음 새 조회 행을 제외한 것이 원인이다. [진단](../evidence/execution-database-completion-diagnostic-2026-10-27.json).
- root가 새 조회/대사2행·393216bytes, stop+재대사3행·458752bytes, 세션13행·1376256bytes, 다음 공유 복구29행·3211264bytes를 예약하도록 보완했다. 계좌/owner 한도와 fixture는 그대로다. 행/bytes 전체 충분성·기존 정상 경로는 수정본 실제DB10시나리오에서 검증 중이며 아직 통과 판정 전이다. Q27 partial 유지.

## 2026-10-27 완료 의무 실제 DB 후속 통과·독립 검토

- root SQL 예약29행 보정으로 정상/두controller/무효화복구·terminal-third 실제 수용/전송까지 앞선5시나리오9검사를 통과했다. active3는131>128행으로 발급이 먼저 거절돼 완료 approve의 중복lookup3행을 기존 API로 추가 회수했다. 이어 거절 명령의 내부 approve 권한 문맥 잔류를 발견하고 저장 직전 원 요청 handle/action 재인증을 추가했다. 한도·SQL 인증 비교·원본 history/hold는 유지했다.
- 최신 실제DB6시나리오11검사묶음·380.178초·ownDB6정리·소유28전후불변. auth/CLOSED·active3 실제gate거절·조회회수/pending보호/replay/응답유실·포화후완료·기존terminal음성·전송/rollback 통과. [DB](../evidence/execution-database-completion-followup-2026-10-27.json), [root 수정](../evidence/execution-completion-root-repairs-2026-10-27.json). 이후 안내문만 갱신했고 실제 DB runtime source와 일치한다. 이전5와 최신6을 최신전체로 합산하지 않는다.
- 다음 제한 Astra/high 독립 보안 검토 → Sol/high 일반 검토 → 최신전체61 DB/제품·품질/고정40 판정. Q27 partial·로컬7/10·전체18/36·확장12 pending 유지. 사용자 비밀번호는 계속 보류하며 현재 결정 요청은 없다.

## 2026-10-27 독립 보안 P1 두 건·실제 재현 착수

- 제한 Astra/high 독립 정적 검토가 SEC1 보호 approver disconnect의 재대사 예약 누락, SEC2 최종 DB검사 이후 submit/cancel 직전 현재 시각 재검사 누락을 반환했다. 소유28·baseline7·fixture 전후 일치. [검토](../evidence/execution-completion-security-initial-2026-10-27.json). 검토자는 시험을 실행하지 않았다.
- root가 같은 합성 경로의 실제DB3사례(보호disconnect, DB최종검사 후31초 경과 submit/cancel)를 재현 중이다. 재현 후 좁은 범위 단독 수정→영향검사/실제DB→독립 재검토를 진행한다. 일반 검토·최신전체 판정은 이후다. 기존 통과를 취소하지 않되 Q27 전체완료 근거로 쓰지 않는다.

## 2026-10-27 보안 반례 실제 재현·수정 배정

- root 실제 합성 PostgreSQL3사례·149.883초·ownDB3정리·소유28불변. 보호 approver disconnect는 completion guard로 rollback되어 세션2개가 running 상태로 남았다. 실제 최종 DB검사 후 합성 시계31초 경과 시 submit/cancel 모두 broker 수신1회가 발생했다. [실제 red](../evidence/execution-completion-security-red-2026-10-27.json). 이는 결함 재현이며 제품 통과가 아니다.
- SEC1의 종료 후 재대사 행/bytes 사전 예약과 SEC2의 DB I/O 완료 후 실제 전송 직전 만료 검사를 단독 Sol/high 구현자에게 배정한다. 한도·원본 증거·보호 검사·미확정 전송 보유를 유지하며 focused 회귀 후 실제DB·독립 재검토·최신전체를 진행한다. Q27 partial, 확장12 pending.

## 2026-10-27 보안 수정 반환·실제DB 검증

- 단독 Sol/high 수정6파일·소유28/보호531/로그 SHA root대조. SEC2 red2실패→green2, 유효기간2 통과. 최종고정본 영향35통과+잘못된 검사 클래스 지정2오류 후 올바른2만169.504초 통과, 소스 불변. 공개559findings0·팀/diff 통과. [수정](../evidence/execution-completion-security-fixes-2026-10-27.json).
- SEC1 noncontroller 종료4행/524288bytes와 기존13행 슬롯 내 상계를 보완하고 SEC2 최종DB commit/close 이후 실제handoff 직전 내부 유효시간 검사를 추가했다. 현재 root 실제DB11 집중검사→추가 승인종료 예약 의심 실제진단→독립 재검토/일반 검토→최신전체66·제품/품질·고정40 순서다. 추가 의심은 미확인으로 유지하며 Q27 partial/확장12 pending이다.

## 2026-10-27 보안 수정 실제DB 부분 통과·활성3 발급 제한

- 수정본 actualDB11계획 중 앞9개(새보안5·복구3·terminal-third) 통과 후 active3 admission challenge 발급이 execution_capacity로 실패했다. 702.068초·ownDB10정리·소유28불변. [실제 결과](../evidence/execution-database-security-fixes-initial-2026-10-27.json). 포화후완료는 이 실행에서 미실행이다. 세션 종료 미래 예약2행 추가로 기존 경계 fixture가 실제 admission gate에 닿지 못한 영향으로 추정하며 산식/경로를 확인한다. 한도/guard는 낮추거나 우회하지 않는다.
- 승인 종료 예약 의심은 별도 실제DB 진단 후 수정 범위를 확정한다. Q27 partial·최신전체/독립 재검토는 미실행이다.

## 2026-10-27 예약 수명주기 보완 배정

- 실제 승인 revoke는 성공했으나 matched rebind 뒤 총필요행90→91로 증가했다(bytes는 감소). 포화 heartbeat 진단은 기존 session budget에 먼저 걸려 revoke 실패 근거가 아니다. active3의 보호철회0/1회 대안도 Q26용량에 먼저 걸렸으므로 채택하지 않는다. [진단](../evidence/execution-security-adjacent-diagnostics-2026-10-27.json).
- root는 noncontroller의 추가재대사2행을 이미 약속된 resume 복구의 수명주기에 결속하고, 승인 revoke/withdraw 완료가 재대사를 무효화할 때 필요한1행을 사전예약하도록 단독 Sol/high 후속 보완을 배정한다. 기존 active3 fixture를 임의로 약화하거나 한도를 증액하지 않는다. 보호종료 guard/행·bytes와 회귀/실제DB/독립검토는 후속 판정이다.

## 2026-10-27 완료 예약 수명주기 수정 반환

- 단독 Sol/high 소유4파일 보완·소유28/보호초기531/최종공개snapshot/로그SHA root대조. SQL 집중4·공개562findings0·팀/diff 통과, 기존66 시나리오 보존·새7/총73 작성. [인계](../evidence/execution-lifecycle-fixes-2026-10-27.json). 실제DB는 구현자가 실행하지 않았다.
- noncontroller repair는 resume 의무가 있을 때 확보한다. 승인 자체 종료 예약과 발급 명령 예약을 별도 보존하고, 보호명령5/복구6행 및 approved7/복구8~9행과 bytes·실제completion guard를 보완했다. root 실제DB 집중14를 실행한다.
- 만료 approval을 복구 validate_current가 다시 요구하는 기존 경계는 정적 잠재 장애다. 새 expired-target 사례는 종료 원자성과 복구 차단을 구분하며 성공 복구라고 집계하지 않는다. 실제 관측 후 별도 계약/소스 보완 필요성을 판단한다. 독립/최신전체 판정은 잔여, Q27 partial.

## 2026-10-27 예약 수명주기 실제DB 완료·만료 복구 설계

- actualDB14시나리오/14검사·1015.326초·ownDB14정리·소유28전후/현재 일치. 보호revoke/withdraw/atomic/복수미처리/명령만료·SEC1·active3 실제gate·포화·복구3·terminal-third 경로를 확인했다. [실제 결과](../evidence/execution-database-lifecycle-fixes-2026-10-27.json). 13개 기능 경로와1개 expired-target 차단 관측을 구분하며 만료후 성공재개를 주장하지 않는다.
- 승인만료 종료는 저장됐으나 실제 새대사 unresolved/recovery_readset_unresolved·manualresume reconciliation_required를 관측했다. 과거approval TTL을 validate_current가 복구에도 요구한다. 제한 Astra/high 읽기전용 설계 자문으로 현재계좌 검증과 과거승인 실행권한을 구분하는 최소보완을 판단한다. 이전권한/한도/hold/unknown·원본이력 보존. Q27 partial·독립검토/최신전체73·제품/품질은 잔여다.

## 2026-10-27 복구 유효성 분리 채택

- Astra/high 읽기전용 자문 exit0·소유28/baseline7/fixture2 root SHA대조. 과거 approval TTL이 현재 계좌 복구를 막는 결함으로 판정하여 EXECUTION-DEC-005를 채택했다. 현재자료/정책의 유효성은 유지하며 원 주문 권한과 계좌 대사를 분리한다.
- 단독 Sol/high가 관련29파일 범위의 최소 구현·집중검사를 담당한다. 실제DB 성공복구·독립검토·최신전체는 아직 미실행이며 Q27 partial·확장12 pending이다. 사용자 결정 요청과 비밀번호 입력은 현재 필요없다.

## 2026-10-27 복구 유효성 구현 인계·실제DB 착수

- Sol/high 단독 구현13파일·소유29/보호530/로그23 SHA root대조·역할 exit0. 현재 계좌 검증을 원 주문 TTL과 분리하고 typed 대사 유효구간·SQL/CAS·source 원본 보존·registry commit 결속을 보완했다. [인계](../evidence/execution-recovery-validity-fixes-2026-10-27.json).
- application10·영향21·최종저장2·이전target14/storage19 통과를 버전별로 구분한다. 공개567findings0·팀/diff 통과. 기존73+신규11 실제DB84는 작성만 했으며 root 집중21부터 실행한다. actualDB·독립검토·최신전체/고정40 판정 전으로 Q27 partial·확장12 pending 유지.

## 2026-10-27 복구 실제DB 첫 양성·검사 준비 보정

- actual 집중21의 첫 만료 승인 사례는 새대사 matched→수동재개 running·옛승인 재사용 효과0을 확인했다. 다음 empty 사례에서 최초 선택적 복구 준비를 필수 완료 비증가로 잘못 검사해 중단(84.043초·ownDB2정리·소유29불변). 초기 실패를 보존했다.
- root는 empty만 정상 stop 이후 선택적 rebind로 새 resume 의무를 사전 확보하고, 이후 명시resume의 비증가를 검사하도록 runner를 수정했다. runtime/SQL/한도는 불변이다. 미실행 후속20 실제DB를 이어 실행하며 Q27 partial 유지.

- empty 정상복구 통과 후 request 사례의 선택적 추가대사를 필수복구로 검사한 두 번째 runner 오류를 진단했다. 같은 SQL/입력에서 matched·valid_to14:33:10, plan rebind0/resume1, 합계71→72행/4962392→4965040bytes를 확인했다(35.571초·ownDB1정리). root가 선택적 사전용량과 후속 필수resume 비증가를 구분하도록 runner만 수정했다. runtime/SQL은 인계본 불변, 후속19 actualDB 실행 중이다.

## 2026-10-27 복구 실제DB 후속19 통과·독립 보안 검토

- root actualDB 후속19시나리오/19검사·1203.171초·ownDB19정리·소유29전후/현재일치. request/policy/freshsource/runtime권한/unknown/cost/rights·rollback/실제COMMIT응답유실/SQL결속·기존복구·SEC1/SEC2·active3/terminalthird/포화완료를 확인했다. [DB 증거](../evidence/execution-database-recovery-validity-2026-10-27.json).
- 앞선 만료승인 및 빈계좌 양성은 runtime/SQL동일한 이전runner 증거이며 최신전체84와 합산하지 않는다. 다음 제한 Astra/high 독립 보안 검토→일반 검토→최신전체 DB/제품·품질/고정40 판정이다. Q27 partial·로컬7/10·확장12 pending, 사용자 결정 현재없음.

## 2026-10-27 독립 보안 P2·미완료 명령 예약 실제 재현

- Astra/high 독립 읽기검토 exit0·소유29/baseline7/fixture2/0001/2 불변. source교체 무효화가 pending Q26 완료hold를 삭제하는 P2 한 건을 반환했다. 추가 P1은 없으며 포화 실패는 정적 우려로 구분했다.
- root actualDB1·52.799초·ownDB1정리·소유29불변으로 발급revoke/nonce가 남은 채 hold0 vs필요4행/262144bytes를 확인했다. 포화후명령실패를 실제 재현했다고 확대하지 않는다. 단독 Sol/high에게 기존 _pending_budget에 따라 pending잔여만 보존하는 최소수정·회귀를 배정한다. Q27 partial, 독립재검토/일반/전체는 잔여.
