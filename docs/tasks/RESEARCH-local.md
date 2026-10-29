# RESEARCH-local — Q23 합성 전략·성과 비교

- 상태: 로컬 합성 범위 완료
- 단계·선행조건: EXEC-DEC-001, Q20~22 로컬 판정, 평가 전 root PG-02 비교 명세 확정
- 요청 근거·실행 범위: 비밀번호 없는 잔여 작업 순차 진행; F07/G01~04 합성 하위 범위. 사용자는 비교안을 본 뒤 전략을 선택
- 담당: root 명세 통합, 제한 Astra/high 설계 자문, 단독 Sol/high 구현, 독립 검토/검증
- 입력: data/execution/operations/serialization-v1, Q17 시장증빙, Q20 원장, Q21 스냅샷, Q22 보고, policy-gates PG02
- 소유: 신규 domain/research.py, application/research.py, ports/research.py, adapters/synthetic_research.py, research/__init__.py·metrics.py·costing.py·strategies.py, additive domain/serialization.py, tests/product/*research* 및 test_performance.py/test_costing.py, docs/development/research.md. 기존 원장/시장/평가/보고/frozen 계약은 보존
- Git 기준: codex/arc-contracts HEAD2fa8f1d, 기존 변경 보존, 새 commit/remote 없음
- 허용: 공개 소스·합성 자료·재현 시험·방법론 공식 문서 읽기. 실제 계좌/시장자료/키/외부 모델/주문 없음
- 검증: 독립 산식 예제, 외부 입출금·비용·환율·낙폭·회전율, 시점/권리/버전/분할기간·미확인·재현 hash
- 시간·비용: 새 유료0, 활성 worker/writer 각1

## 산출물과 완료 기준

평가용 가정을 먼저 버전 고정하고, 동일 합성 조건의 현금/기준 전략 비교와 성과/비용 산출물을 재현한다. 실제 수익성 우열·전략 채택·LEAN 호환 검증을 합성 결과로 주장하지 않는다. 실제 전략 선택은 PG03에 남긴다.

## 인계

- 실제 변경: 고정 합성 비교 명세, 성과/원가/전략 구현14파일 및 독립 검토·검증 증거.
- 확인 사실: GIPS 공식 handbook의 TWR 외부흐름 경계/기하연결과 QuantConnect 공식 연구 안내의 미래정보/생존편향 설명을 2026-10-24 확인.
- 미실행: 실제 역사적 성과·실제 전략 채택·LEAN 호환·실계좌 검증.
- 다음: Q24 합성 목표안·후보 설계. 실제 전략 채택은 PG03에 유지.

- Q22 로컬 독립 판정 완료로 선행조건 충족. 제한 qh_review 부모 Astra/high에 구체 설계 자문을 배정한다. root PG02 명세 확정 전 전략 실험은 실행하지 않는다.

- Astra/high 자문을 root가 research-local-v1·RESEARCH-DEC-001·comparison-spec-v1.json에 통합하고 PG02 합성 명세를 고정했다. [설계 증거](../evidence/research-design-2026-10-24.json). 단독 Sol/high 구현자를 배정하며 root 동시 쓰기를 중단한다. 실제 실험/검증은 아직 미실행.

- 구현자 반환14파일hash와 동결spec SHA 일치. 제품375(Q23 27)·품질87·공개374findings0·diff 통과. 고정24개 모두complete, 재실행manifest/result hash일치. [구현 증거](../evidence/research-implementation-2026-10-24.json). 독립 검토/검증 전 로컬완료로 집계하지 않는다.

- Q23 독립 검토 R1: bound 성과 API의 연구 목적 권리 누락 P2를 확인했다. 정적 지적이며 재현·수정·회귀를 단독 구현자에게 배정한다. 고정 비교 spec은 변경하지 않는다. [지적](../evidence/research-review-initial-2026-10-24.json).

- Q23 R1 실제 red 4시험/18실패/오류0 후4파일 수정. 제품380·품질87·24실행재현·14hash/spec확인. 독립 재검토를 배정한다. [수정 증거](../evidence/research-review-fixes-2026-10-24.json).

- R1 독립 재검토 PASS·14hash/spec불변. 독립 검증자에게 최종 실행을 배정한다.

- 독립 제품380·품질87·공개379findings0·팀/diff·14hash/고정7파일불변 PASS. root 실제API로24개 비교표·hash JSON 생성 완료. 로컬4/10 완료; 전체18/36·Q19 대기 유지.
