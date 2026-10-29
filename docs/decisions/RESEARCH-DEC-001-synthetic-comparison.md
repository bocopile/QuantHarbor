# RESEARCH-DEC-001 — PG02 합성 비교 명세

- 날짜: 2026-10-24
- 관련 작업: Q23 RESEARCH-local, PG02, EXEC-DEC-001
- 상태: 채택(합성 평가만)
- 결정 담당·요청 근거: root, 사용자 입력 없는 순차 작업·비교 후 전략 선택

## 요구와 확인 사실

Q20~22 로컬 판정 완료. 별도 제한 Astra/high 설계 자문을 받았으며 코드/시험은 아직 없다. PG02는 root 비교용 명세이고 실제 전략 선택은 PG03이다.

## 선택과 이유

[고정 JSON](../contracts/comparison-spec-v1.json)의 raw SHA256 `b24ec83a0cbbe1646fee64c2d433cf8d2c57831f58c8e2e746c0e9c371dc4bb4`를 평가 전 고정했다. 12시점·두 시장/비용/fold·세 기준전략으로24개 합성 실행을 비교한다. [추가 계약](../contracts/research-local-v1.md)에 TWR/흐름·낙폭·회전율·비용/원가·PIT·단위·체결·unknown을 명시했다. 90%투자 등 수치는 합성 가정이며 실제 정책 아님. fold재초기화·일일지정봉·다음봉체결·T+0을 명시하고 실제시장과 동일하다고 주장하지 않는다.

별도 범용 codec 복제 대신 기존 닫힌 registry를 additive 확장해 canonical 규칙을 하나로 유지한다. 기존 시세/원장/평가/보고와 frozen 설계는 보존한다. ExperimentResult는 향후 AI ResearchResult와 구별한다. 원가 결과는 별도로 제공해 기존 스냅샷을 소급 변경하지 않는다.

방법론 확인일2026-10-24: 외부흐름 경계의 하위기간 수익률 기하연결은 [GIPS Handbook](https://www.gipsstandards.org/standards/gips-standards-for-firms/gips-standards-handbook-for-firms/)을 참고했다. 미래 구성종목/생존편향 통제는 [QuantConnect Research Guide](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/research-guide)를 참고했다. 나머지 합성 수치와 지원범위는 root 설계 선택이다. GIPS 준수·투자성과 보증이 아니다.

## 미확인과 재검토 조건

현재 PG02의 합성 명세만 확정했으며 실험 통과·실제 데이터/LEAN·역사적 성과·전략 채택은 미완료다. actual PG01/03~05와 SG 관문을 해제하지 않는다. OOS를 본 뒤 가정을 바꾸려면 새 명세와 탐색 기록이 필요하다.
