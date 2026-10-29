# Q24 2차 독립 검토

**Changes required — P2 2건.** 실제 소스와 추가 테스트 본문을 정적으로 검토했습니다.

1. **P2 · T5 — 과거 증거의 현재 grant가 원본 권리에 결속되지 않습니다.**  
   [application/target.py:74](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:74)  
   과거 `risk_points` 또는 `daily_usage_inputs`의 `current_rights.rights_ref`만 다른 값으로 바꾸고 dataset·목적·유효기간을 유지하면, `_current_rights`는 통과합니다. 이후 `_historical_point`가 원래 snapshot의 grant로 치환하여 재검증하므로 참조 불일치가 사라집니다. 이는 [개발 안내:9](/Users/okestro/projects/QuantHarbor/docs/development/target.md:9)의 다른 `rights_ref` 대체 금지와 어긋납니다. 과거 증거와 현재 grant의 권리 참조도 대조해야 합니다.

2. **P2 · T6 — 추가 과거 입력의 불완전한 FX 자료가 일간사용 계산에 쓰일 수 있습니다.**  
   [application/target.py:445](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:445)  
   `daily_usage_inputs`에 실제 재생 가능한 불완전 snapshot을 넣어도 [124행](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:124)은 완전성을 요구하지 않습니다. FX 선택 역시 `view.held_reasons`만 확인하고 Q17 quality·missing scope·`MarketProof.usable`을 확인하지 않습니다.  
   예를 들어 USD990 매도에 기존 검증 FX가3이고, 추가 `partial` 자료에 더 최신인 원본 FX1과 누락된 expected event가 있으면 FX1을 선택하여 일간사용을990으로 계산할 수 있습니다. 미완결 근거는 차단해야 합니다. 환산에 사용하는 해당 proof의 완전성을 검사해야 합니다.

| 항목 | 정적 판정 |
|---|---|
| T1 | PASS — 사건별 잔여 payable·정산·정확 참조 대조, 채권 상계 방지, H/U/D 중복 처리 확인 |
| T2 | PASS — 직접 생성·parse·repository에서 가격상한/하한과 정책·요청 현금하한 재결속 |
| T3 | PASS — 정상 이력에서 명시 series의 최신 적격 봉과 실제 보유 price ref 대조 |
| T4 | PASS — 유지할 타시장 보유와 실제 주문의 capability·세션 검사 구분 |
| T5 | 만료 교집합 보완 확인. 위 현재 grant 결속 누락 잔존 |
| T6 | 전량매도 후 독립 통화·과거 FX 해소 확인. 위 완전성 누락 잔존 |

과거 FX의 원본 여부와 effective/published/observed/ingested cutoff 검사는 확인했습니다.

**해시:** 추가 테스트2개 포함 소유 **12/12**, 시작·종료 모두 최신 수정 증거와 일치했습니다. baseline **7/7**도 manifest와 일치하며 불변입니다.

**테스트는 실행하지 않았습니다.** 파일·root 문서 수정, subagent, 네트워크, 비공개 자료 접근, Docker, Git 변경은 수행하지 않았습니다.