**P2 1건: source 교체가 미완료 명령의 Q26 완료 예약을 삭제합니다.**

- 위치: [postgres_execution.py:535](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/postgres_execution.py:535), 특히 540행의 `holds.pop(identity,None)`.
- 조건: 같은 세대에서 withdraw/revoke challenge 발급 → 실행 전 source 교체 → 후속 발급으로 Q26 용량 소진 → 기존 challenge 실행.
- 영향: challenge/nonce는 남지만 완료 예약은 사라집니다. 거절 receipt 저장에 필요한 공간을 [별도 Q26 검사](/Users/okestro/projects/QuantHarbor/src/quantharbor/adapters/synthetic_approval.py:154)가 거부할 수 있습니다. SQL 공통 예약만으로 이 검사를 보장하지 못합니다. 정적 결함이며 포화 실패는 재현하지 않았습니다.
- 최소 수정: 무효화 시 같은 세대 미완료 challenge의 잔여 완료 예약을 유지하고, source 교체 비용은 별도 사전 확보하십시오.

검토 범위에서 추가 P1은 확인하지 않았습니다. SEC2의 최종 DB 종료 후 전송 직전 시간 검사와 DEC005의 주문 TTL/현재 계좌 검증 분리를 확인했습니다.

소유29·baseline7·fixture2·0001/0002는 **검토 전후 모두 일치**합니다. 최신 DB의 before/after29, runner·handoff 해시도 일치하며, 집중19의 assertion을 대조했습니다. 이전 승인만료·빈계좌 양성은 이전 runner 증거로 구분했습니다.

테스트·Docker·네트워크·수정은 수행하지 않았습니다. 잔여 관문은 위 P2 확인·수정, 일반 독립 검토, 최신 전체84 DB·제품/품질·fixed40 최종 판정입니다. 실제 OS·자격증명·broker 연동은 기존 별도 관문으로 유지합니다.