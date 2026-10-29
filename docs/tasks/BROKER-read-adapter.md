# BROKER-read-adapter — Q19 조회 어댑터와 모의 연결 준비

- 상태: AP05 조건부 조회 승인 확보·새 암호화 영역 준비 (Q19 전체 미완료)
- 선행: Q18 합성 문서 계보·저장 독립 검증 완료; Q12 BrokerQueryResult·Q14 경계·Q16 식별/시간
- 요청 근거: 전체 잔여 작업 순차 구현·필요 합성 검증. I01-R·I02-R·I08-R
- 담당: root 공식 근거/계약 통합 → 설계 자문 → 단독 구현 → 보안/일반 검토 → 독립 검증
- 입력: data-v1 BrokerQueryResult, operations-v1 환경/권한, B-DEC-001 KIS 설계 대상·키움 대안, PG-01/SG-01·02/AP-05
- 소유: broker 조회 계약·ports·합성 adapter·KIS 응답 정규화/제한 조회 경계·연결 준비 예제·관련 합성 회귀. 공통 계약/상태 root
- Git: codex/arc-contracts HEAD2fa8f1d, 기존 변경 보존, 추가 commit/worktree/원격 변경 없음
- 도구/비용: 공식 공개 명세 읽기, 로컬 합성 구현·검증, 신규 유료0. 계좌/키/실제 API/주문/환전 호출 없음
- 검증: 환경·계좌참조·권한·scope binding, 성공빈값/partial/error/unsupported/unknown, pagination·유량/시각·정규화·정확소수·반복cursor·계약 변경 거부

## 산출물과 완료 기준

공통 조회 계약과 합성 어댑터, 공식 명세에 근거한 KIS 조회 변환·허용 경로를 준비한다. 계좌별 보유·현금·주문·체결을 요청 범위·완전성·관측시점과 함께 반환하고 오류를 빈 잔고로 표시하지 않는다. 단위·필드 포함 관계·모의 지원이 확인되지 않은 값은 unknown/unsupported로 남긴다. 실제 자격·지원/권리·정책이 미완료면 연결을 차단한다.

로컬 합성 구현과 실제 연결 검증을 구분한다. PG-01 모의 자금/위험/승인 정책, SG-01 계좌별 capability, 필요한 SG-02 자료 권리, AP-05 대상·권한 승인과 비공개 키 주입 없이는 실제 조회를 실행하지 않는다. 합성 시험만으로 Q19 전체를 완료하지 않는다. 2026-10-24 EXEC-DEC-001 사용자 순서 변경에 따라 Q20 이후 입력 없는 로컬 하위 범위는 별도 순차 진행한다.

## 인계

- 실제 변경: 카드와 공식 명세 조사·20개 공개 파일 URL/해시 기록 작성. 고정 커밋의 조회 후보9종, 모의 지원 미확인3종과 현금/체결 식별 한계를 정리했다. 설계 담당에게 읽기 자문을 순차 배정했다.
- 계약: [broker-read-v1](../contracts/broker-read-v1.md), [BROKER-DEC-001](../decisions/BROKER-DEC-001-read-adapter.md), [연결 준비안](../development/paper-connection-preparation.md). root가 통합했고 foundation_implementer에 아래 소유 파일만 단독 위임한다.
- 구현 소유: src/quantharbor/{domain,ports,application}/broker_read.py, adapters/kis_read.py, adapters/synthetic_broker.py, domain/serialization.py의 additive 등록, tests/product/*broker*·*kis_read*, docs/development/broker-read.md. root는 구현 반환 전 쓰기를 중단한다.
- 구현 반환: 전용25·제품152·품질22·공개267findings0·팀6/36/110 자기 검증 통과. 최초2실패를 수정했으며10파일 해시를 [구현 증거](../evidence/broker-read-implementation-2026-10-24.json)에 기록했다.
- 검토: S1/S2 보안과 R1/R2 일반 지적을 재현·수정해 재검토를 통과했다. 최신 자기 시험 전용37·제품164·품질22 통과. [최신10파일](../evidence/broker-read-review-fixes-2026-10-24.json).
- 독립 실행: 제품164(조회37 포함)·품질22·공개275findings0·팀6/36/110·diff 검사 통과.10파일 실행 전후 hash 불변. [최종 증거](../evidence/broker-read-validation-2026-10-24.json).
- 미실행: 실제 계좌별 지원/권리·정책값·비공개 암호화 저장/주입·transport·연결/조회. Q19 전체 미완료다. DB/Docker/기존 저장 회귀는 해당 변경이 없어 반복하지 않았다.
- 사용자 결정: KIS 모의 계좌1개·로컬 수동 조회1회(정책/지원 확인 후)의 AP05 범위, 비공개 운영 영역/입력 방식. 실제 값은 공개 예제나 채팅에 받지 않는다. [연결 준비안](../development/paper-connection-preparation.md)과 [비활성 입력 구조](../../config/paper-onboarding.example.json)를 검토 대상으로 제시한다.
- 다음: 사용자 결정과 비공개 정책/지원·권리 확인 → 실제 transport/주입 구현·검토 → 승인된 조회 검증 → Q19 완료 판정. 이후 사용자 순서 변경에 따른 Q20 로컬 착수는 EXEC-DEC-001을 따른다.

## 2026-10-24 승인 이후 재개

사용자가 KIS 조회 승인·모의계좌/API 준비됨 및 새 저장소 밖 로컬 암호화 영역 준비를 선택했다. AP05 범위는 토큰 발급과 지정 조회1회로 기록했으며 같은 승인을 다시 요청하지 않는다. PG01 실제 값·지원/권리·안전한 저장/주입 검증은 남아 있다. [SEC-paper-vault](SEC-paper-vault.md)에서 선행 저장 영역을 준비한다.
