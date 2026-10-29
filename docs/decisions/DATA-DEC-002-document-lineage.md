# DATA-DEC-002 — Q18 제한 문서 원문·출처·시점 저장

- 날짜: 2026-10-24
- 관련: Q18/E04, DATA-document-lineage, data-v1
- 상태: 채택 — 승인된 합성 구현 범위의 기술 선택
- 담당: qh_architect 읽기 자문·root 통합

## 결정과 근거

Q17 완료 후 공시·재무보고·뉴스의 원문/개정/관측/기업 연결/배치 manifest 5 개 고정형을 추가한다. Q16/Q17 등록형과 frozen7 계약은 유지한다. 표준 lib canonical 파일저장으로새 의존성없이합성 text 원문을보존한다. 원문 8KiB·배치 16claims/4MiB·canonical64KiB 상한이며전체 evidence 와 receipt 로재생한다.

기업은별도명시 entity/link context 를두고 Q16 종목 version/venue 와결속한다. ETF 발행인과 기초자산 노출은구분한다. publication unknown·latecorrection/conflict·현재 권리·신선도를명시하여미확인을확정근거로승격하지않는다. sourceURL/본문은자료이고자동접속/명령실행하지않는다.

대안은 Q17 시장 payload 확장·Parquet 에문서통합·외부 parser/크롤러도입이다. 기존시세계약의의미변경과새 의존성/실제권리확인을늘리므로현재범위에서는채택하지않는다. 실제장문재무보고·HTML/PDF·AI 해석·숫자추출은별도 확장이 필요하다.

## 영향과 검증

생산: domain/documents,application/document_ingest,adapters/document_files. 소비: 향후 Q23/Q25 연구,외부제공시목적별권리. serializer 고정추가만허용한다. 구현 후보안/일반검토와새 process 파일재현·기존회귀를수행한다. 설계채택은실제 source 권리 SG02/API/운영정책을해제하지않는다.
