**revision4 판정: 기존 3건 중 2건 해결, cookie 잔존 수명 1건은 부분 해결입니다.**

1. **security-a01 #1 — 해결.** 독립적인 256bit cookie secret과 origin-memory proof를 함께 검증하고 origin·서버/조회 세대에 결속합니다. 다른 로컬 포트에서 cookie만 확보해도 인증이 완성되지 않습니다. [계약:26](../contracts/product-read-v1.md)

2. **security-a01 #2 — 해결.** 세대별 cookie 이름, 요청 generation의 정확한 cookie 선택, 해당 세대만 종료하는 규칙이 지연된 `Set-Cookie`의 다른 세대 변경을 차단합니다. 성공·오류 처리 전 epoch/generation 검증도 명시됐습니다. [계약:28](../contracts/product-read-v1.md), [응답 순서:71](../contracts/product-read-v1.md)

3. **review-a01 #1 — P2, 부분 해결.** 고아·종료 세대도 포함하는 장부와 재시작 보존은 보완됐지만, **고정 `Expires`만으로 지연 수신 시 브라우저 수명 연장을 배제할 수는 없습니다.** `Date`를 기준으로 시계 차이를 보정하는 브라우저에서는 발급 당시 `Date=t0`, `Expires=t0+300초`인 응답을 늦게 받으면 그 지연이 만료 보정에 포함될 수 있습니다. 서버 장부는 원래 만료에 슬롯을 반환하지만 브라우저에는 해당 cookie가 남아, 새 발급과 겹칠 수 있습니다. 발급 `Max-Age`를 생략하는 것만으로 이 경로가 닫히지는 않습니다. [계약:26](../contracts/product-read-v1.md), [장부:28](../contracts/product-read-v1.md)

   최소 보완은 지원 브라우저의 `Date/Expires` 보정과 허용할 응답 지연 상한을 반영해 **브라우저 최대 잔존시각과 장부 슬롯 회수시점을 맞추는 규약**입니다. 이는 잔여 cookie에 따른 헤더 크기·축출 문제이며, 서버의 만료·proof·권리 검사 우회로 판정하지 않습니다.

그 밖에 변경 범위의 새로운 실질 문제는 확인하지 못했습니다. 위 잔여 지적은 정적 계약 판단이며 실행 재현 결과가 아닙니다. 파일 수정·재귀 위임·웹·시험·실제 금융 행위 없음. **HTTP/브라우저/재시작 검증 NOT RUN**, Q27·FUP-P28-002 완료 관문 유지입니다.

최종 contract SHA-256 — 검토 전후 동일:
`6ec66d1491e537d4d1f8710f4c4d731d75c4d80c8197f7df5e4e112c671231a1`