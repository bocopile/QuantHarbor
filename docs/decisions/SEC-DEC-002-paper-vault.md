# SEC-DEC-002 — 첫 모의 조회용 로컬 암호화 저장소

- 날짜: 2026-10-24
- 관련 작업 ID: Q19, SEC-paper-vault, PG01, AP05
- 상태: 채택 — 새 저장소 준비 기준, 실제 검증 전
- 결정 담당·요청 근거: 사용자가 KIS 모의 조회1회와 저장소 밖 새 로컬 암호화 영역 준비 승인. root 통합·qh_architect 읽기 자문

## 요구와 확인 사실

실제 금융값·키는 Git/채팅에 넣지 않으며, 실제 조회 전에 암호화 저장·주입·보존·복원 프로필을 확인해야 한다. macOS26.6.2의 기본 hdiutil 도움말/로컬 man과 [Apple 공식 가이드](https://support.apple.com/en-gb/guide/disk-utility/dskutl11888/mac)를 확인했다. 기존 FileVault 상태는 unknown이다.

## 선택과 이유

새 AES-256 암호화 APFS read/write UDIF `.dmg`를 사용한다. 최초 기술 용량은256MiB이며 자동 확장하지 않는다. 새 소유 영역 아래 원본·닫힌 백업·비활성 복원 사본만 만든다. 같은 호스트 복사는 디스크 고장/분실 대비 백업이 아니다. 단일 SPARSE 영속 형식과 별도 암호화 라이브러리 도입은 피한다. 신규 의존성·유료 비용0이다.

운영 비밀번호는 native UI의 `-agentpass`로 사용자가 입력한다. argv/env/모델/공개 파일/일반 stdin으로 받지 않는다. Keychain 저장 선택은 해제하며 helper가 이를 자동 강제했다고 주장하지 않는다. 생성/재마운트 시 실제 입력 동작을 확인한다. 별도 합성 통합 시험에서만 임시 난수 비밀번호를 메모리→hdiutil stdin으로 전달할 수 있고 저장·출력·운영 재사용하지 않는다.

## 구현 경계

- 기본 부모는 사용자 Library/Application Support/QuantHarbor/paper, 각 실행은 새 고유 디렉터리다.0700/0600·현재 uid·symlink/하드링크/기존 대상 거부, 저장소 밖 확인, umask077. 부모 메타데이터만 검사하고 기존 파일 내용을 탐색하지 않는다.
- CLI는 고정 작업만 제공한다. 일반 shell/URL/device 입력·sudo·-ov·강제 detach·기존 디스크 포맷·자동 삭제·평문 fallback은 없다. Python -I -S 진입과 고정 시스템 바이너리/최소 환경을 사용한다.
- 실제 create 전 helper·모의 명령/경로 검증을 보안 검토한다. 합성 hdiutil 실행은 임시 자기 자원에만, 운영 create는 사용자 승인된 새 영역에만 적용한다.
- create는 attach와 분리한다. isencrypted 결과 true와 AES256 생성 옵션 증거를 구분한다. attach 결과·현재 hdiutil 이미지 연결·mountpoint·filesystem device·APFS·소유/권한을 대조한 뒤에만 내부 파일을 쓴다. attach 여부 불명확하면 작업을 중단한다.
- mount 전 빈 디렉터리와 mount 후 volume root는 구분한다. 내부 data루트0700·파일0600. 비마운트된 빈 경로에는 어떤 실제값도 쓰지 않는다. 같은 사용자 악성 프로세스/관리자까지 격리한다는 보장은 없다.
- subprocess 출력은 bounded 캡처·고정 사유만 보고한다. 비밀번호 입력 창은 화면 캡처하지 않는다. 취소/timeout/이상 시 자동 재시도하지 않고 상태 불명확/미완료를 명시한다.
- 합성 canary+hash를 fsync한 뒤 detach(device 제거)·재입력 attach·내용hash를 확인한다. busy detach를 성공으로 표시하지 않는다. read/write 이미지에 hdiutil verify checksum 검증을 주장하지 않는다.
- 닫힘이 확인된 원본만 새 파일에 복사·전후hash/암호화/권한 확인. 원본 분리 상태에서 새 복원 사본을 별도 mountpoint로 검증하고 detach한다. 완료 metadata는 마지막에 남긴다. 실제 자료 보존/삭제 정책은 별도로 확정한다.
- 공개 출력은 단계/고정 성공·실패 상태만. 필요한 로컬 경로는 사용자에게만 전달하며 공개 증거에 저장하지 않는다. 실제 금융자료·원시 API·키를 bootstrap helper가 읽지 않는다.

## 미확인과 재검토 조건

native 비밀번호 창·OS 권한·이미지 생성/마운트/잠금/복원은 아직 미검증이다. 기본 sandbox가 device 작업을 허용하지 않으면 승인된 범위의 권한 검토를 거치며 우회하지 않는다. 저장소 준비는 PG01 수치·계좌별 지원/권리·키주입·보존·실제 transport 완료가 아니다. 모의 주문·실전 접속은 계속 미승인이다.

## 호스트 합성 시험에 따른 보정 — 2026-10-24

첫 실제 시험에서 AES-256 이미지 생성·암호화 boolean 확인·APFS attach는 성공했으나 장치 결속 검사에서 중단했다. 이 호스트는 새 이미지의 block device를 현재 uid 소유로 생성하고, APFS root를 -mode0700에도0755로 만들었다. canary 쓰기는 미실행이다. root가 정확한 새 이미지/장치/마운트 결속을 확인해 일반 detach하고 모든 자기 device 소멸을 확인했다. 기존 자료·운영 비밀번호는 사용하지 않았다.

검증 기준 보정: block device owner는 root 또는 현재 uid만 허용하며 이미지·device·mount·st_dev 결속은 유지한다. 새 원본의 첫 canary 단계에만 current uid의0700/0755 root를 전체 결속 검증 후 fd로 열어0700으로 설정하고 fsync한다. 이후 strict 재검증 전에는 data/canary를 만들지 않는다. 일반 조회·재열기·복원은 처음부터0700을 요구한다. 다른 소유자·그룹/기타 쓰기 권한·불일치 마운트는 계속 거부한다. device 자체 권한은 변경하지 않는다. 운영 helper/UI 검증은 후속이며 실제 값은 넣지 않는다.
