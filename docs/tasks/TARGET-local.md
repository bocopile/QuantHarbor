# TARGET-local — Q24 합성 목표안·주문 후보

- 상태: 로컬 합성 범위 완료
- 단계·선행조건: EXEC-DEC-001, Q23 로컬 성과/전략 판정, Q21 snapshot과 고정 execution-v1
- 요청 근거·실행 범위: 입력 없는 잔여 작업 순차 진행; G05/G06/G07 연구 단계. 실제 전략·자금·위험·주문 승인은 별도
- 담당: root 통합 → 제한 설계 자문 → 단독 구현 → 독립 검토/검증
- 입력: execution-v1 TargetPlan/OrderCandidate/Risk 경계, Q16 catalog/calendar, Q19 미해결 broker semantics, Q21/Q23 읽기 모델
- 소유: target-local-v1 명시 신규 target 도메인/앱/port/adapter·additive serializer·합성 시험·개발 안내. 기존 계약 의미 보존
- Git 기준: codex/arc-contracts HEAD2fa8f1d, 기존 변경 보존, 새 commit/remote 없음
- 허용: 공개 코드·합성 정책/계좌/시세/주문 상태·실행 없는 후보 생성 시험. 실제 값·키·계좌·주문/환전/취소 없음
- 검증: full/partial/생략·unknown·자금/노출·최악부담·lot/tick·미체결/예약·시각/환경/권리·hash/불변
- 시간·비용: 새 유료0, 활성 worker/writer 각1

## 산출물과 완료 기준

명시 합성 제약에 맞는 목표와 불변 후보를 만들고, 필수 정책/가격/대사/가용금 의미가 미확인이면 거부한다. 후보 생성은 승인·예약·주문이 아니다. 실제 PG01/PG03 및 공급자 관문을 우회하지 않는다.

## 인계

- 실제 변경: 추가 계약·결정·합성 목표/후보 구현10파일 및 구현 증거.
- 확인: Q21 available/reserved/broker capacity와 open orders는 unknown이므로 현재 snapshot만으로 후보 제출 가능성을 선언할 수 없다.
- 미실행: 실제 전략/운영 정책 채택·승인/예약/전송·계좌 연결.
- 다음: Q25 합성 AI 계약 설계.

- Q23 독립 판정·비교 산출물 완료. 제한 Astra/high 설계 자문을 배정한다. 구현/검증 미실행.

- Astra/high 자문을 root가 target-local-v1/TARGET-DEC-001에 통합했다. 단독 Sol/high 구현자에게 배정, 구현/검증 아직 미실행. root 동시 저장소 쓰기를 중단한다.

- Q24 구현 반환10파일hash 일치. 구현자 제품421(Q24 41)·품질87·공개396findings0·팀/diff·고정7파일불변. 독립 검토를 배정하며 아직 로컬완료로 집계하지 않는다. [구현 증거](../evidence/target-implementation-2026-10-24.json).

- Q24 독립 검토 T1~T6(P1 2/P2 4) 지적: 원장채무 누락·복원 제약 결속·정상 시계열/타시장/전체입력 만료/전량매도 후 일간사용. 단독 구현자에게 실제 red→수정→회귀를 배정한다. 기존421통과는 과거 자기 검증으로 보존. [지적](../evidence/target-review-initial-2026-10-24.json).

- Q24 T1~T6 실제 red9시험/10실패/오류0 및 추가FX1실패 후6파일 보완. 제품448·품질87·공개402findings0·소유12hash/고정7파일불변. 독립 재검토를 배정한다. [수정](../evidence/target-review-fixes-2026-10-24.json).

- Q24 2차 검토 T1~4 PASS, T5b 과거권리참조/T6b 과거FX완전성 P2 2건 잔존. 단독 구현자에게 실제 재현·보완을 배정한다. [2차 지적](../evidence/target-review-second-2026-10-24.json).

- Q24 T5b/T6b red4실패/오류0 후3파일 수정. 제품455(Q24 75)·품질87·공개405findings0·12hash/고정7파일불변. 별도 진단문 시험오류1은 수정·신규7시험통과로 구분한다. 독립 최종 재검토 배정. [수정](../evidence/target-review-fixes2-2026-10-24.json).

- 최종 재검토 PASS·12hash/고정7파일 불변. 독립 Luna/high 검증자를 배정한다.

- 독립 제품455·품질87·공개410findings0·팀/diff·12hash/고정7파일불변 PASS. root 실제API로 후보2개 예시 생성, 계획부담704/여력96. 로컬5/10 완료·전체18/36/Q19대기 유지.
