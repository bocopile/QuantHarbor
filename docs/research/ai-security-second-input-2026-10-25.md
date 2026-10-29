**CHANGES REQUIRED — P1 2건, P2 3건.** 아래는 실행 재현 없이 코드·테스트를 대조한 정적 지적입니다.

1. **P1 / AS1 — 현재 원천 확인 실패에도 표시 API가 과거 본문을 반환합니다.**  
   [application/investment_ai.py:603](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:603)  
   정상 문서 결과를 저장한 뒤 같은 repository에 문서 없는 `Sources`를 주입하여 `current_result`를 호출하면, `partial/missing_source`와 함께 과거 `complete` 객체·인용 본문이 반환됩니다. 원천 hash 변경으로 `invalid`가 되어도 같습니다. 캐시 재호출의 은닉 처리를 표시 API에도 적용하여, 현재 사용권리를 확인할 수 없는 본문을 반환하지 않아야 합니다.

2. **P1 / AS3 — inline query를 응답에서 생략하면 검토 요청의 query 권한을 우회합니다.**  
   [application/investment_ai.py:579](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:579)  
   client가 허용된 `dispatcher.execute(document_view)`를 실행하고 `response.queries=()`로 반환하면 실제 영수증을 가진 정상 결과가 저장됩니다. 이후 `allowed_queries=()`인 검토 요청도 `accepted`가 됩니다. 검사는 응답 선언만 순회합니다. **실제 `result.query_receipts`의 query까지** 원래 요청과 검토 요청의 권한 교집합으로 재검사해야 합니다.

3. **P2 / AS4 — 정산 예외가 여전히 `dispatched`와 미차단 scope를 남깁니다.**  
   [synthetic_investment_ai.py:365](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_investment_ai.py:365), [application/investment_ai.py:523](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:523)  
   주입 clock이 시작 `08초` → dispatch `09초` → 정산 `08초` → 최종 `10초`를 반환하는 입력이면, 시각 검증이 usage 예외 처리 전에 실패합니다. `unknown_charge` 전환 없이 결과 저장도 거부되며, 다음 window에서는 남은 동시성 슬롯으로 신규 호출이 가능합니다. 전송 후 정산 실패를 원자적으로 불명 청구·scope 차단으로 확정하되 기존 정상 정산은 보존해야 합니다.

4. **P2 / AS3·AS5 회귀 — 중복 호출 경쟁으로 실제 완료 결과가 저장되지 않습니다.**  
   [synthetic_investment_ai.py:204](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_investment_ai.py:204)  
   A가 `owner=True`를 획득하고 예약 전에 멈춘 사이, 동일 attempt의 B가 먼저 예약·호출·정산하면 B는 `owner=False`라 완료 결과를 저장하지 않습니다. 이후 A는 결과 없는 정산 attempt를 만나 `blocked/budget`를 생성·저장할 수 있습니다. 소유권 결정과 예약을 결속하고 비소유자의 신규 dispatch를 막아야 합니다. 기존 중복 시험은 dispatch 이후에만 경쟁을 만듭니다.

5. **P2 / 저장 원자성 — 검토 저장 실패가 마지막 저장 슬롯을 소비합니다.**  
   [application/investment_ai.py:586](/Users/okestro/projects/QuantHarbor/src/quantharbor/application/investment_ai.py:586), [synthetic_investment_ai.py:245](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_investment_ai.py:245)  
   저장소에 한 슬롯만 남긴 뒤 정상 검토를 요청하면 review request는 저장되지만 review 저장은 `capacity`로 실패합니다. 예외 처리는 `_processed`만 복구하여 request가 남고, eviction 없는 저장소의 마지막 슬롯이 소진됩니다. request와 review의 공간을 함께 확인하고 함께 저장하거나 rollback해야 합니다.

AS2의 필수 의존성 도출·누락 거부·현재 조회 검증, AS5의 잠금 기반 요청 누적 quota, 임의 결과/검토 재봉인 차단은 확인했습니다. 이 범위에서 별도 추가 지적은 없습니다.

소유 **12/12**, baseline **7/7**, spec **1/1**, 총 **20개** 해시가 검토 전후 동일합니다. 소유 파일은 최신 수정 증거, baseline은 `baseline-v1.json`, spec은 고정 SHA와 일치합니다. 정확한 SHA-256은 다음과 같습니다.

```text
docs/development/investment-ai.md
3700ce7b2f92849fc196c8b4bebcda4749d20a121974b627f56b832eb1a6fe4d
src/quantharbor/adapters/synthetic_investment_ai.py
ef0670ae1c84566ba89c151b3a416f69aca9abc75f31dd3fcd1a81dc7fff5a7e
src/quantharbor/application/investment_ai.py
954565265fba7520dac69aa6de8602662132375ade99454b188efda27eeeb19c
src/quantharbor/domain/investment_ai.py
8a02b37f4da642cf3ab6f3d79b55cab3c18776ae8ef25f4a5458f2dbcc2c247d
src/quantharbor/domain/serialization.py
99e6c37650ef9ac1e88577644ec99b38b6efdd9c00ef0448b4e1563c30ba6ab1
src/quantharbor/ports/investment_ai.py
9630a387aab0f8b27dfc461160fab51200b51936b6411aa2b64e2b2d984285c4
tests/product/synthetic_investment_ai.py
0678d7c0810297f350d9b57a2146f018ae49df425058ed32ad99024441de48c0
tests/product/test_investment_ai.py
25f7994b242a98f8286cd7f072ed99e8eef9f082116f41ec8b6df1656bcb8c18
tests/product/test_investment_ai_bounds.py
684965fab6141da0546c716916e4cf95fb655e39ce8accd4830bb01725c9a3f1
tests/product/test_investment_ai_evaluation.py
a15f187dcedfe68c976078a8ce6e2e8795e2d34ac9c9a649e6f395422f0bceb3
tests/product/test_investment_ai_security.py
920fb64aac91134121dd775a7f748372165f39fa97f53404016c07f59e3caf92
tests/product/test_investment_ai_sources.py
5100ba01cc2677dd1b5a1e9f720c2da144313598a72591d7fa600c0cdda33a90
docs/architecture.md
18ea3b3ec6544fd13c7f4083420e70160e2c3fb607e28ada7ec53f1cf2c15833
docs/contracts/serialization-v1.md
bc2a266bfd0c14812a47cc43b2e971efa848962d210cdbad822502caec38baa8
docs/implementation-backlog.md
c2c916bae7f1602f3898e1fab3e038b581c53823bde32c1734ebf2f894073165
docs/decisions/ARC-DEC-004-implementation-baseline.md
bff5b7e8ea44b1fe9beb2a76fd763202ae8df626058fbe70ff5c56eec342011b
docs/contracts/data-v1.md
72a445a05bec315753ae48323c440d2d854e9832147c42660e42fd8e2116b099
docs/contracts/execution-v1.md
c61c56d74846d5995a04c39dc9d92fbd82b15e2dab93312ff90b51397d2b5e59
docs/contracts/operations-v1.md
15cd0dd3d0b6706a356d6f79ee5c09c85d7840f012a9eb55781c98191543ca2d
docs/contracts/ai-evaluation-spec-v1.json
726411c4f367720820d7d47cc829e0baedca39254718c90c31a8bb8058004f3f
```

테스트 정의 **66개**를 확인했으며 **`tests_executed=false`**입니다. 증거의 제품 521·전용 66·고정 24 통과는 구현자 실행 기록입니다. 수정·root 증거 쓰기·subagent·네트워크·private 접근·Docker·Git 변경은 하지 않았습니다. 합성 응답 간 합의는 실제 독립 모델 평가로 인정하지 않았습니다.