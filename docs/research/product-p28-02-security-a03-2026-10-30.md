**revision 5 독립 정적 재검토: 기존 3건 모두 계약 수준 해결. 지정 변경 범위에서 추가 실질적 보안 지적은 없습니다.**

| 원래 지적 | 해결 판정·근거 |
|---|---|
| cookie 포트 간 공유 | **해결.** 인증 cookie 없이 origin의 closure 메모리에 토큰을 보관하고 명시 헤더로 전달합니다. `credentials: omit`과 정확한 origin/Host·세대·현재 권리 검사를 규정합니다. [22행](../contracts/product-read-v1.md), [26행](../contracts/product-read-v1.md) |
| 역순 Set-Cookie가 다른 세대 변경 | **해결.** 로그인·종료를 포함한 모든 응답에 Set-Cookie가 없어 브라우저의 자동 인증상태 변경 경로가 제거됐습니다. 지연 본문은 epoch/request 검증 후 폐기합니다. [28행](../contracts/product-read-v1.md), [73행](../contracts/product-read-v1.md) |
| 브라우저 cookie 만료·누적 | **해결.** cookie를 발급하지 않으므로 기존 `Date/Expires` 보정·잔존 헤더·축출 문제와 cookie 장부 요구가 적용되지 않습니다. 서버 세션은 미채택·상실 토큰까지 합계 8개, 절대만료 300초로 제한합니다. [28행](../contracts/product-read-v1.md) |

새 token 흐름에서도 구체적인 계약 상충은 확인하지 못했습니다. 종료 요청은 현재 토큰으로 먼저 구성한 뒤 epoch 증가·토큰/표시 삭제를 거쳐 단회 발송하며, 응답 또는 timeout에 발송 버퍼를 해제합니다. 이전 epoch의 로그인·오류·종료 응답이 새 상태를 변경하지 못하도록 명시돼 있습니다. 서버 digest·세대 결속·현재 권리 재검사와 금융 CLI/IPC·liveness 분리도 유지됩니다.

JavaScript 메모리 노출은 문서가 명시한 제한으로 평가했습니다. 자체 정적 스크립트·CSP·`textContent`·영속/URI/로그 저장 금지와 상충하는 요구는 발견하지 못했으며, 이를 별도 미결정 범위로 확대하지 않습니다.

**미실행:** 구현·HTTP·브라우저·공격 재현·IPC·재시작 시험은 **NOT RUN**입니다. 실제 동작의 PASS 판정이 아니며 **P28-06/P29 수용 관문을 유지**합니다. 파일 수정·재귀 위임·웹·시험·실제 금융 행위는 수행하지 않았습니다. status/카드의 revision4 기록 갱신은 주 담당 통합 사항입니다.

최종 계약 SHA-256 — 검토 중 두 차례 대조 동일:
`35f6ed51edb43e04711f3dcec290c553bc4a5af201467a3110ae1bc64edd0977`

기준 Git HEAD:
`80403ab3b8ef322e7d38e8554b42f263bb37cbae`