# Q24 독립 검토 지적

정적 검토이며 실제 재현 시험은 수정 단계에서 수행한다.

**Changes needed — P1 2건, P2 4건.** 전체 구현 소스를 정적으로 검토했습니다.

1. **P1 — 미결제 지급채무가 H에서 누락될 수 있습니다.** [application/target.py:170](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:170)  
   원장에 `unsettled_payable=-500`이 있어도 합성 obligations가 비면 H=0입니다. USD L/B=1000과 타통화 현금이 충분한 계좌에서는 실제 여력500을 넘는 USD600 매수가 적격이 될 수 있습니다. 미결제 원장 사건과 의무 목록의 완전성을 대조해야 합니다.

2. **P1 — 직접 생성·복원·저장으로 요청 제약을 우회합니다.** [domain/target.py:731](/Users/okestro/projects/QuantHarbor/src/quantharbor/domain/target.py:731)  
   정상 계획의 요청 매수한계를100→90 또는 현금목표를900으로 바꾸고 관련 해시·참조를 재생성해도, 기존 가격100 주문과 현금하한0 계산을 유지할 수 있습니다. repository도 이를 수용합니다. 명시 가격과 현금목표를 계획 계산에 재결속해야 합니다.

3. **P2 — 정상 시계열을 중복 종목으로 거부합니다.** [application/target.py:272](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:272)  
   같은 종목의 서로 다른 두 원본 봉이 선택되면 `ContractError`입니다. Q21의 명시 가격 선택·최신 시점과 일치하는 봉을 해소해야 합니다.

4. **P2 — 유지할 타시장 보유 때문에 후보가 차단됩니다.** [application/target.py:293](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:293)  
   KR 주문만 요청해도 scope 밖 US 보유에 현재 정규장을 요구합니다. 정상 KR/US 혼합 계좌에서는 두 정규장이 겹치지 않습니다. 전체계좌 평가와 실제 주문의 세션 검사를 구분해야 합니다.

5. **P2 — 후보 만료가 전체 의존 입력을 반영하지 않습니다.** [application/target.py:415](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:415)  
   NAV에 사용하는 별도 FX 자료의 권리·신선도가5초 후 끝나도, USD 종목 후보는 자기 자료만 기준으로30초까지 유효할 수 있습니다. 계좌 제약 계산에 사용한 모든 입력의 유효기간을 교차해야 합니다.

6. **P2 — 당일 전량 매도한 종목이 후속 제안을 막습니다.** [application/target.py:509](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/target.py:509)  
   당일 매도한 A가 현재 보유·요청 scope에서 빠지면, 유효한 사건·비용·시장 자료가 있어도 `market.get(A)`가 없어 차단됩니다. 일간 사용량의 환산 근거를 현재 보유 목록과 독립적으로 해소해야 합니다.

704 정상 제안, full/partial, 비중·비용 산식과 원천 재검증 연결도 확인했습니다. **테스트는 실행하지 않았습니다.**

소유 **10/10 파일은 시작·종료 모두 증거 해시와 일치하고 불변**입니다. target 계약·채택 설계·결정 및 frozen baseline **7/7도 불변**, Q23 spec은 고정 해시와 일치합니다. 검토 중 status/TARGET 카드는 변경됐으며, 검토자는 파일을 수정하지 않았습니다.