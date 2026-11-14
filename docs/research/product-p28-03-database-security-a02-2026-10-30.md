**실질 보안 지적 0건.** 두 파일의 변경분에서 신규 보안 경계 위반을 발견하지 못했습니다.

검토 범위도 확인했습니다. 현재 파일에서 Binds 수정과 신규 회귀 두 개만 메모리상 되돌리면 최초 보안검토의 SHA와 각각 일치합니다. `postgres_ledger.py`와 Compose의 SHA도 최초 검토와 동일합니다. 파일은 수정하지 않았습니다.

- **FUP-P28-005 — 원래 문제 해소, 종결 가능.** [Binds 조건](../../src/quantharbor/adapters/product_database.py)은 기존 `None`·빈 목록에 정확한 자기 named volume의 단일 `:rw` 표현만 추가 허용합니다. 별도의 Mounts `Type=volume`·Name·목적지·RW 검사, volume labels·CreatedAt·driver·options 검사, container/image·네트워크·권한·host mount 거부는 유지됩니다. 정상 표현의 오거부를 해소한 제한적 허용이며 임의 host bind 허용으로 확대되지 않습니다.
- [신규 회귀](../../tests/product/test_product_database.py)는 정상 표현의 재개·종료와 다른 source·host 경로·target·mode·추가 bind의 거부를 확인하도록 작성되어 있습니다. 거부 도우미는 실패뿐 아니라 자원 변경 명령이 없었는지도 검사합니다. [수정 증거](../evidence/product-p28-03-binds-fix-2026-10-30.json)의 수정 전 26개 중 ERROR 1 → 수정 후 26 PASS와 [root 실제 DB 증거](../evidence/product-p28-03-actual-db-a02-2026-10-30.json)의 8.205초·9항목 PASS는 현재 SHA와 일치합니다. 해당 실행 결과는 root의 별도 증거로 판정에 반영했습니다.

**FUP-P28-004 — 준비 불일치 해소는 근거로 뒷받침되지만, 초기 원인 전체 독립확정은 보류합니다.**

private stderr의 고정 말단만 집계해 a01 명령 인자 assertion 16건, a02 컨테이너 guard 오류 14건과 stop 횟수 assertion 1건을 확인했습니다. 공개 진단과 일치하며 원문은 보고서에 옮기지 않았습니다.

현재 [test double](../../tests/product/test_product_database.py)은 생산 코드의 Compose 인자 위치와 필수 labels에 부합합니다. [공개 타임라인](../evidence/product-p28-03-mock-fixture-diagnostic-2026-10-30.json)에는 a01→a03 사이 test 파일 수정 두 번만 기록되어 있어, 이 구간을 생산 guard 완화로 통과시켰다는 근거는 없습니다. a03 22 PASS·최종 24 PASS·현재 26 PASS 기록도 구분해 확인했습니다.

다만 수정 전 mock 전체 bytes와 상세 수정 내역이 없어, 각 실패의 정확한 필드 원인과 stop 횟수 실패의 인과관계까지 모두 독립 확정할 수는 없습니다. 따라서 **현재 코드의 안전성 지적은 0건이지만, 과거 원인 전체 확정을 요구하는 FUP-P28-004의 무조건 종결은 보류**합니다.

최종 SHA-256은 검토 시작·종료 시 동일했습니다.

```text
product_database.py
a2ea638571113dc8369ec45431dcf71b93a1b4b1a45a9091c4bf53fbedbae9a6
test_product_database.py
5b0c3ac418aaafa32cb5a26a2ee81efa9211791a9eefbc717ce48f8f4fb03eb1
postgres_ledger.py
f047fea5e274338e1c3f8ad415bfb3a6f850f4fb2bef4e292e80a2473f88cfc9
compose.product.synthetic.yaml
82028dc230cbf4d8d0265abe16926bd4277814048245e7236d82514e30c4d4db
```

**실제 보안시험: NOT RUN.** 시험·Docker·웹·재귀 위임·Git 변경은 수행하지 않았습니다. 이번 판정은 지정 delta에 한정되며 P28-03 전체 완료 판정은 아닙니다.