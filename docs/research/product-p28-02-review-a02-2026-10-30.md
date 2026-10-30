**revision 5 독립 최종 정적 검토: 지적 0건.** 기존 설계 7건·보안 2건과 추가 cookie 잔존 수명 1건은 계약 수준에서 해결됐습니다.

- [인증 규약](../contracts/product-read-v1.md): cookie/Set-Cookie 미사용, `credentials: omit`, origin 메모리 토큰·명시 헤더·세대·현재 권리 결속이 일관됩니다. 절대만료 300초·고아 포함 8세션으로 제한됩니다.
- [로그아웃 순서](../contracts/product-read-v1.md): 현재 token으로 단회 요청 구성 → epoch 증가·기존 pending 취소·장기 token/화면 삭제 → 발송 → 응답/timeout 시 버퍼 해제에 구체적 상충이 없습니다.
- [응답 처리](../contracts/product-read-v1.md): 본문·오류 처리에 앞서 발송 epoch와 요청 결속을 검사하며, 이전 epoch의 로그인·종료·401/403/410 응답은 폐기합니다. 금융·ControlSession·liveness 권한 분리도 유지됩니다.

최종 계약 SHA-256 — 두 차례 대조 동일:
`35f6ed51edb43e04711f3dcec290c553bc4a5af201467a3110ae1bc64edd0977`

기준 Git HEAD:
`80403ab3b8ef322e7d38e8554b42f263bb37cbae`

**실제 HTTP·브라우저·IPC 시험: NOT RUN.** 실제 제품 PASS나 완료 판정으로 확대하지 않으며, **Q27·FUP-P28-002 및 P28-06/P29 수용 관문을 유지**합니다. 파일 수정·재귀 위임·웹·시험·금융 행위는 수행하지 않았습니다.