# VALUATION-local — Q21 합성 평가·대사·스냅샷

- 상태: 로컬 합성 범위 완료
- 단계·선행조건: EXEC-DEC-001 순서 변경, Q20 로컬 독립 검토/검증 완료, Q16~19 합성 가격/환율·조회 계약
- 요청 근거·범위: 입력 없는 잔여 작업 순차 구현·합성 검증; F04/05/06 로컬 하위 범위
- 담당: root 통합 → 제한 qh_review/Astra-high 설계 → 단독 구현 → 독립 검토/검증
- 입력: 고정 data-v1/serialization-v1, ledger-local-v1, market/broker-read 추가 계약. Q20 검증 SHA는 ledger-validation-final 증거
- 소유: domain/valuation.py, application/valuation.py, ports/valuation.py, adapters/synthetic_valuation.py, additive serializer, tests/product/*valuation* 및 docs/development/valuation.md. 확정 계약·카드/상태는 root
- Git 기준: codex/arc-contracts HEAD2fa8f1d, 기존 변경 보존. 새 commit/remote 변경 없음
- 허용 범위: 공개 소스/문서·합성 fixture 구현/시험, 새 유료0. 실제 데이터·계좌·비밀번호·키·외부 API 없음
- 검증: 가격/환율/정밀도/시각/권리·scope·완전성·현금 분류·허용 오차·중복/역순·재생·canonical 실패 사례
- 제약: worker/writer 각1, 실제 대사 완료 주장 금지. Q23 원가/성과 계산 정책은 미확정으로 보존

## 산출물과 완료 기준

원장 수량을 보존하는 평가, 원통화·기준통화의 명시 환율/반올림, 부분 평가 소계와 NAV의 구별, scope/시각/의미가 검증된 합성 대사, 불변 스냅샷과 계보를 구현한다. 시세/원가/환율이 없거나 조회 의미가 불명확하면 unknown/incomplete로 남긴다. 실제 Q19 연결이 없는 상태에서 실제 계좌 matched를 만들지 않는다.

## 인계

- 실제 변경: 합성 평가/대사/스냅샷·저장소·additive codec·시험/안내10파일. 상세 버전은 최종 증거 참조.
- 확인: 기존 BrokerObservation은 mapping_unknown·source_only·현금 포함 관계 unknown을 유지하므로 자동 확정 대사 입력으로 승격할 수 없다.
- 미실행: 실제 계좌 대사·운영 영속성. 로컬 구현/독립 검토/검증은 완료.
- 다음: Q22 로컬 보고 완료 후 Q23을 순차 진행 중. 아래는 단계별 인계 연혁.

- Astra/high 설계 반환을 root가 valuation-local-v1·VAL-DEC-001에 통합했다. [설계 증거](../evidence/valuation-design-2026-10-24.json). 소유 제품/시험/안내와 additive serializer를 단독 구현자에 배정하며 root 동시 쓰기를 중단한다.

- 구현자 반환: 소유10파일 hash 일치·제품288(Q21 62)·품질87·공개330findings0·diff 통과. [구현 증거](../evidence/valuation-implementation-2026-10-24.json). 독립 Sol/high 검토를 배정하며 실제 계좌 대사·운영 저장은 미실행이다.

- 일반 검토 P1 2/P2 1건을 정적 추적으로 발견했다. [검토 증거](../evidence/valuation-review-initial-2026-10-24.json). 구현자에게 실제 재현→수정→회귀를 배정한다. Q22 구현은 Q21 로컬 판정 후다.

- 실제 red75개 중11메서드49assertion실패/오류0 → 수정 후75통과. 전체301·품질87·공개334findings0·diff통과,10hash일치. [수정 증거](../evidence/valuation-review-fixes-2026-10-24.json). 독립 재검토 뒤 최종 검증한다.

- V1~V3 독립 재검토 PASS·10hash일치, 정상 빈계좌/부분입력 회귀 검토 완료. [판정](../evidence/valuation-review-final-2026-10-24.json). 별도 Luna/high 최종 테스트를 배정한다.

- 최종 독립 검증: 제품301·품질87·공개336findings0·팀6/36/110·diff 통과, 실행 전후10hash불변. [최종 증거](../evidence/valuation-validation-final-2026-10-24.json). 실제 계좌 대사/운영 저장은 미실행이며 Q21 전체 완료와 구별한다. 다음 Q22 로컬 보고.
