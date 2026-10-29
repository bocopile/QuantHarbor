# SEC-paper-vault 로컬 암호화 저장 준비

기준: 2026-10-24, [SEC-DEC-002](../decisions/SEC-DEC-002-paper-vault.md),
[작업 카드](../tasks/SEC-paper-vault.md). 현재 상태는 **helper·모의53개·실제 합성 통합·독립 검토 통과, 운영 native 생성은 실패했으며 사용자가 현재 입력하기 어려워 비밀번호 입력 가능 시점 대기**다. 아래 구현 당시 기록과 현재 결과를 구분한다.
소유 파일은 helper·전용 시험·이 안내 세 개다. 공유 상태·승인·작업 카드는 root가 통합한다.

`scripts/bootstrap_paper_storage.py`는 새 macOS AES-256 APFS read/write UDIF 256MiB
이미지와 합성 canary만 취급한다. 키·계좌·금융값·기존 비공개 파일·API를 읽지 않는다.
이미지 하나를 256MiB로 생성하며 자동 확장하지 않는다. 원본·백업·복원 사본을 합쳐
약 768MiB와 메타데이터 여유가 필요하다. 백업은 같은 호스트의 복사여서 호스트 고장·분실에 대비한 백업이 아니다.

운영 진입과 별도 합성 통합 진입은 다음 두 가지뿐이다. **아래 명령은 후속 보안 검토와
호스트 실행 권한 확인 후 사용할 안내이며, 이번 구현에서 실행하지 않았다.**

```sh
python3.13 -I -S scripts/bootstrap_paper_storage.py bootstrap
python3.13 -I -S scripts/bootstrap_paper_storage.py synthetic-integration
```

두 진입 모두 macOS의 실제 `hdiutil` 생성·attach·detach를 실행한다. 두 번째도 단위시험이 아니다.
`--parent`에는 승인된 저장소 밖 절대 디렉터리만 지정할 수 있다. 이미지·장치·URL·임의 명령·기존
실행 재개를 받는 옵션은 없다. 인수를 오류 메시지에 반사하지 않는다. `-I -S`가 없으면 거부한다.

운영 기본 부모는 사용자 홈의 `Library/Application Support/QuantHarbor/paper`다.
합성 기본 부모는 `/private/tmp` 아래 난수 이름의 새 0700 디렉터리다. 각 실행은 부모 아래
`qh-paper-`와 난수 식별자로 구성한 새 0700 디렉터리를 만든다. helper는 경로를 stdout에
출력하지 않는다. 사용자는 로컬 Finder의 승인된 부모에서 새 디렉터리를 확인한다. 실제 경로·
비밀번호 창·개인 파일을 캡처하거나 채팅·공개 증거로 전달하지 않는다.

운영 비밀번호는 `-agentpass`의 native UI에서만 사용자가 입력한다. 생성과 원본 두 번·복원
한 번의 attach에서 입력 동작을 직접 확인해야 한다. **Keychain 저장 선택을 사용자가 해제한다.**
helper는 Keychain 선택을 강제하거나 실제 입력 여부를 관측하지 못한다. argv/env/일반 stdin으로
운영 비밀번호를 받지 않는다. UI를 사용할 수 없거나 취소하면 중단하며 다른 입력 방식으로 바꾸지 않는다.

합성 통합 진입만 `os.urandom(32)`에서 만든 64자 ASCII 값과 마지막 NUL을 메모리에서
`hdiutil -stdinpass`로 전달한다. 비밀번호를 파일·argv·env·보고서에 저장하지 않고 실행 종료 시
참조를 버린다. Python 메모리의 완전한 zeroization은 보장하지 않는다. 합성 실행 잔여 이미지는
비밀번호를 되찾을 수 없는 일회성 시험 자원이며 운영 저장소로 재사용할 수 없다.

실행 단계는 고정되어 있다.

1. `create`: umask077, 현재 uid·0700/0600, 링크 없는 부모와 새 대상, 저장소 밖 경계를 확인한다.
   다른 checkout/worktree의 `.git`도 메타데이터 존재만 검사해 거부한다. 부모 내용은 열거하지 않는다.
   `hdiutil create -size 256m -type UDIF -fs APFS -encryption AES-256`을 attach와 분리한다.
   root 실행·기존 대상·symlink·이미지 hardlink·약한 권한을 거부한다.
2. `canary`: `isencrypted -plist`의 boolean true를 확인하고, attach 결과와 현재 `hdiutil info`
   연결의 이미지 경로·모든 device·단일 mountpoint를 정확히 비교한다. `diskutil info -plist`의
   DeviceNode·MountPoint·APFS·쓰기 가능·owners 활성·VolumeName·VolumeUUID와 실제 block node,
   mount 여부, filesystem `st_dev == volume device st_rdev`, mount root의 uid·0700을 확인한다.
   dirfd를 연 뒤 재검사하고 나서야 `data` 0700과 `bootstrap-canary.bin` 0600을 새로 쓰고 fsync한다.
   `info`의 모든 이미지 항목에는 유효한 절대 `image-path`, 비어 있지 않은 `system-entities`,
   각 entity의 중복 없는 `/dev/disk…` device 문자열이 필수다. `mount-point`가 있으면 유효한
   절대 경로여야 한다. 경로의 제어문자·빈 구성요소·`.`·`..`를 거부하며 문자열만 검사한다.
   다른 이미지의 파일을 열지 않는다. 필수 metadata 누락·잘못된 구조는 unknown으로 거부한다.
   `images: []`와 `images: [{}]`를 구별하며, 후자는 닫힘·복사·attach의 근거가 될 수 없다.
   자기 이미지가 아닌 항목도 전체 검증한 뒤 결속/닫힘을 판정한다.
3. `lock`: 확인된 자기 whole device만 일반 detach한다. 현재 이미지 연결과 수집한 모든 device
   node가 사라지고 비마운트된 기존 빈 디렉터리로 돌아왔는지 확인한다. busy·불명확 상태는 실패다.
4. `reopen`: 사용자 재입력 attach 후 같은 VolumeUUID·전체 결속과 canary SHA-256을 확인하고 다시 잠근다.
5. `backup`: 원본 분리를 확인한 뒤 새 `backup.dmg`에 O_EXCL 복사·fsync한다. 원본 복사 전후와
   백업 hash, 암호화 boolean·소유·권한·서로 다른 inode를 확인한다.
6. `restore`: 닫힌 백업에서 새 `restore.dmg`를 복사하고 같은 검사를 한다. 원본·백업이 분리된
   상태에서 복원 사본만 `restore-mount`에 독립 attach하여 UUID·결속·canary를 확인한 뒤 detach한다.
7. `complete`: 세 이미지의 분리·암호화·권한·최종 hash를 다시 확인하고 마지막에 로컬
   `completion.json` 0600을 새로 쓰고 fsync한다. 공개 출력은 고정 단계·상태·사유뿐이다.

복사 직후 세 이미지의 전체 hash는 같아야 한다. 복원 사본은 read/write mount로 파일시스템
메타데이터가 바뀔 수 있으므로, 최종 전체 hash는 별도 기록한다. 원본과 닫힌 백업의 hash 불변,
복원 canary의 hash 일치를 각각 확인한다. read/write 이미지에 `hdiutil verify` checksum 검증을 주장하지 않는다.
`isencrypted=true`도 AES-256 자체의 독립 검출 결과가 아니다. 완료 기록은 AES-256 생성 옵션과
암호화 boolean을 구분한다.

모든 도구는 고정 시스템 바이너리와 리스트 argv, shell 없이 호출한다. 자식 환경은
PATH·LANG·LC_ALL·HOME만 전달하고 stdin은 운영에서 DEVNULL이다. macOS 런타임은
`__CF_USER_TEXT_ENCODING`을 자동 삽입할 수 있다. stdout와 stderr 합계는 256KiB로 제한하며,
초과·오류 시 원문을 공개하지 않는다. 일반 조회30초·create/attach180초·detach60초 제한이다.
시간 초과·취소 시 자기 subprocess group에 SIGKILL을 보내고 직접 자식의 회수를 최대5초 기다린다.
CLI/main thread의 SIGTERM은 취소 예외로 전환되어 이 정리 경로에 진입한다. 자식 생성 도중
SIGTERM은 process handle 확보 직후 처리하며, 정리·취소 보고 중 반복 SIGTERM은 무시한다.
SIGTERM 취소 보고는 고정 단계·`result: fail`·`reason: command_cancelled`·
`state: incomplete_or_unknown`만 포함한다. 회수 시간 초과는 `command_timeout`으로 보고한다.
호출 종료 시 성공·실패·취소 모두 이전 SIGTERM handler를 복원한다. runner 직접 호출도
같은 취소/정리 경계를 사용하며 main의 scope와 중첩 시 정리·보고 후에 복원한다.
helper 자체에 대한 SIGKILL·프로세스 강제 종료·전원 장애는 handler/finally를 실행하지 못하므로
정리나 보고를 보장하지 않는다. 네이티브 agent가 자기 subprocess group 밖에서 계속 동작할 수
있어, 그룹 종료·직접 자식 회수만으로 디스크 상태를 성공이나 안전한 잠금으로 추정하지 않는다.

실패 상태는 항상 `incomplete_or_unknown`이다. 자동 재시도·재개·덮어쓰기·강제 detach·sudo·
자원 삭제·평문 대체는 없다. 실패한 새 디렉터리와 이미지, 불명확한 mount를 보존한다.
사용자가 root와 자기 자원을 식별하고 별도 수동 대응해야 한다. helper를 다시 실행하면 다른 새
자원을 만들 뿐 기존 상태를 복구하지 않는다. 모의 시험의 임시 fixture 정리는 시험 코드에만 있다.

현재 확인과 후속 조건은 다음과 같다.

- 전용 시험은 고정 명령 구성·전체 모의 단계·경로/owner/권한/링크/FIFO/inode 교체·마운트
  결속·canary 변조·분리 실패·닫힌 복사와 변조·출력 제한·timeout·최소 환경·오류 비노출을 다룬다.
  SV1 회귀는 빈 info 항목·필수 경로/목록 누락·잘못된 타입/경로/device·중복 device·혼합 항목을
  거부한다. SV2 회귀는 실제 합성 Python 자식·손자의 준비를 기다려 부모에 SIGTERM을 보내고,
  정리 중 두 번째 실제 SIGTERM도 보낸다. 양쪽 파일 잠금 해제로 실행 종료를 확인하고 직접
  자식 회수·정제 보고·handler 복원을 검증한다. 실패한 red 실행의 잔여 합성 group도 시험이 정리한다.
  명령 모델의 파일은 합성 fixture이며 실제 암호화 증거가 아니다.
- native UI, Keychain 해제, APFS 256MiB 생성 가능 여부, 실제 plist 필드와 filesystem dev_t,
  전체 생성/분리/재입력/복원은 미실행이다. OS가 용량·형식·권한·엄격한 결속 검사를 충족하지
  못하면 불가능 조건을 보고하고 중단한다. 용량을 늘리거나 검사를 생략하지 않는다.
- 이번 구현 역할은 기본 운영 경로 접근과 device 변경을 실행하지 않았다. 현재 sandbox 거부는
  정상 제한이며, 후속 실제 실행에는 root의 권한 검토가 필요하다. 기존 Hook 신뢰를 우회하지 않는다.
- POSIX uid/mode 검사와 nofollow dirfd를 적용한다. 같은 사용자 악성 프로세스·관리자 격리,
  ACL/확장 권한의 종합 감사, 전원 장애 내구성·OS 비밀번호 캐시·메모리 잠금은 증명하지 않는다.
- 완료 범위는 합성 canary 저장 프로필뿐이다. 실제 정책·키 입력/주입·자료권리·보존/삭제 정책·
  재해 복구·실제 transport·PG01·SG01/02·Q19 전체 완료는 별도다. 운영값을 넣기 전 root가
  실제 빈 영역 검증과 비공개 입력 절차를 확인해야 한다.

이번 범위에서 실행할 로컬 검증은 다음뿐이다.

```sh
python3.13 -I -S -m unittest discover -s tests/quality -p test_paper_storage.py -v
python3.13 -I -S scripts/check_quality.py
```

Docker·DB·기존 제품 시험·실제 합성 통합 진입·운영 bootstrap·금융 API·네트워크·Git 변경은
이 구현 검증에 포함하지 않는다. 전용 시험 결과와 세 파일 SHA-256은 worker 반환 시 root에 전달한다.

2026-10-24 SV1·SV2 수정 자기 검증: 위 전용 명령으로 수정 전48개 실행에서 실패31건
(서브테스트 포함, 실패 메서드8개)을 재현했다. 기본 SIGTERM으로 부모가 종료된 뒤 합성
자식이 살아남아 잠금을 유지하는 것도 확인했다. 수정 후48개 모두 통과했고, 반복 SIGTERM과
기존 custom handler의 정상/실패 후 복원 확인을 보강한 최종48개도 모두 통과했다.
공개 품질 명령은283파일·findings0·exit0이었다. 초기38개 통과 기록과
[초기 독립 보안 검토의 SV1·SV2](../evidence/paper-vault-security-initial-2026-10-24.json)는
수정 전 증거다. 이번 수정의 독립 재검토·실제 hdiutil 합성 통합·native UI·새 빈 운영 영역
생성/마운트/잠금/복원은 미실행이다. 이 결과로 Q19 전체 완료나 실제 저장 준비를 선언하지 않는다.

2026-10-24 재검토 보완: 정상 명령의 정리 구간에서 처음 받은 SIGTERM도 기록한 뒤 정리가 끝나면 취소를 전파한다. root가 해당 실패1건을 재현하고 수정했으며 전용49개가 통과했다. 기존 반복 취소·자식 회수·handler 복원 회귀도 포함한다. 이 보완은 독립 재검토 전이며 실제 이미지 실행은 여전히 미실행이다.

호스트 보정: 첫 실제 합성 시험에서 생성·암호화·attach 후 device owner/root mode 가정 차이로 중단했고 canary 쓰기 전에 멈췄다. 정확히 해당 시험 이미지만 일반 detach하여 device 소멸을 확인했다. SEC-DEC-002 보정에 따라 device owner는 root/현재 uid만 허용하고, 새 원본 첫 마운트의0755 root는 전체 결속·fd identity 확인 후0700으로 바꿔 strict 재검증한다. 재열기/복원은 이 예외가 없다. root가 보정 전4회귀 오류를 확인한 후53개 통과를 확인했다. 이는 실제 전체 통합 통과나 운영 저장소 준비 완료를 의미하지 않는다.

2026-10-24 실제 합성 재시험: 새 AES-256/APFS256MiB 이미지의 canary 쓰기·detach·재attach·닫힌 백업·독립 복원·전체detach가 통과했다. root가 완료 metadata와 세 이미지 최종hash/0600/current uid를 대조했다. 일회용 합성 stdin 비밀번호만 사용했고 운영 native UI·Keychain 해제·사용자 비밀번호는 미검증이다. 수정된 호스트 처리의 최종 독립 검토 후 운영 영역을 준비한다.

## 운영 native 시도 결과

2026-10-24 일반/최종 보안 검토와 품질75개·공개289파일 검사를 통과한 뒤 승인된 새 운영 영역에서 bootstrap을1회 시도했다. create 단계가 command_failed/incomplete_or_unknown으로 종료됐다. 새 사용자 전용 디렉터리만 확인됐고 vault.dmg·completion.json·마운트는 없었다. 비밀번호 창 표시/취소 여부는 아직 사용자에게 확인하지 못했으며 원인을 임의로 확정하지 않는다. 운영 암호화 저장소 완료가 아니다.

운영 명령의 자동 재시도·평문 비밀번호 대체는 하지 않는다. 사용자에게 창 표시 여부만 요청했으며 비밀번호 자체는 받지 않는다. 입력 경로가 실제 확인되기 전 키·정책 입력과 API 실행을 진행하지 않는다. 합성 시험 원본/백업/복원 자원은 root가 자기 이미지의 분리·파일 목록·uid/권한을 확인하고 별도 정리했다. 운영 시도 디렉터리와 기존 자료는 삭제하지 않았다.

2026-10-24 후속 응답: 사용자가 현재 비밀번호 입력이 어렵다고 알려 입력 가능 시점까지 대기한다. 기존 준비/조건부 조회 승인은 유지한다. 이전 창 표시 여부와 실패 원인은 미확인이고, 사용자 입력 가능 알림 후 native 경로 확인부터 재개한다.
