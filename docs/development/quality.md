# Q15 로컬 품질 검사

현재 공개 개발 산출물과 Q12 계약·Q13 런타임·Q15 비활성 CI 정의를 읽기 전용으로 검사한다. Python 3.13 표준 라이브러리와 설치된 Git을 사용하며 패키지를 설치하지 않는다.

```sh
python3.13 -I -S scripts/check_quality.py
python3.13 -m unittest discover -s tests/quality -v
```

품질 CLI는 인자를 받지 않는다. JSON 요약을 출력하고 통과는 exit0, 검사 실패는 exit1, 잘못된 인자는 exit2다. 탐지 원문·문맥·예외 본문·절대 경로를 출력하지 않는다. 안전한 공개 상대 경로 또는 고정 reason만 반환한다.

CLI는 `-I -S`를 모두 요구한다. sys 내장 모듈만 읽은 최상단 bootstrap에서 flags를 검사하고, 부족하면 stdlib import 전에 고정 JSON과 exit2로 거부한다. `-I`는 script/PYTHONPATH의 shadow 모듈을 제외하고 `-S`는 site 초기화를 생략한다. 비격리 Python이 bootstrap 전에 이미 실행한 site 코드를 되돌릴 수 없으므로 처음부터 위 명령을 사용한다. 전용 단위시험은 신뢰된 개발 경로에서 검사 모듈을 import하며 이 CLI 진입 경계와 구분한다.

## 읽기 경계

Git의 현재 index와 미추적·비무시 후보를 `ls-files -z`로 조회하고 `check-ignore --no-index --stdin -z`로 무시 여부를 대조한다. 과거 commit·blob·diff 내용은 읽지 않는다. 정상 전역/저장소 exclude 규칙을 유지하고 Git Hook·fsmonitor를 끈다. 스캐너는 전역 설정 파일을 직접 열거나 출력하지 않는다.

비무시라는 사실만으로 공개 파일로 취급하지 않는다. `docs`, `src`, `scripts`, `tests`, `migrations`, `containers`와 명시한 루트 문서·공개 config·`.codex` 역할/설정·프로젝트 Skill만 허용한다. config 예제는 `.example`, `.synthetic`, `.fixture`의 명시 suffix와 허용된 텍스트 확장자를 요구한다. 공개 예제에도 실제 자료를 넣을 수 있다는 뜻은 아니다.

`.env`·local 설정·private/keys/credentials·운영 runtime·DB/key/log 파일 등 보호 이름과 미분류 후보는 내용을 열기 전에 거부한다. 예제 suffix가 보호 이름을 해제하지 않는다. 제품 소스의 `src/quantharbor/runtime/*.py`는 운영 데이터 경로와 구분해 허용한다. 무시된 미추적 실제 설정·운영 파일은 후보 목록에 포함하지 않는다. 이미 tracked인 보호 파일은 ignore 여부와 관계없이 이름 위반으로 실패하며 내용은 읽지 않는다.

파일과 모든 경로 구성요소를 `O_NOFOLLOW` descriptor로 열고 일반 파일·hardlink1·크기를 검사한다. symlink, 경로 탈출, 읽는 도중 변경, 알 수 없는 형식·binary·비UTF-8을 거부한다. 한 파일1MiB, 누적16MiB, 목록2MiB, 후보4096개를 한도로 하며 Git 조회는 명령별5초를 적용한다. 이후 계약/lock 검사는 이 읽기 경계를 통과한 메모리 스냅샷만 사용한다. 악성 host 관리자나 검사 후 변경까지 막는 배포 통제는 아니다.

## 검사 내용

- 모든 후보 Python 소스를 AST로 파싱한다. 분석 파일을 import하거나 실행하지 않는다. domain은 현재 필요한 계산용 stdlib 및 domain 내부 import만 허용하고 대표적인 파일·프로세스·외부 I/O 호출과 동적 실행을 거부한다. 이 제한된 AST 규칙은 동적 우회 전체를 증명하는 sandbox가 아니다.
- `docs/contracts/baseline-v1.json`의 버전·필수 파일 집합7개·SHA-256을 대조한다. 경로 추가/누락·계약 drift는 실패하며 manifest를 자동 재생성하지 않는다.
- `runtime-lock.json`, Dockerfile, Compose, 비활성 CI의 이미지 digest·Python/플랫폼·명시된 의존성0을 대조한다. inventory의 해당 이미지와 package/notice 기록·hash 형식을 확인한다. 검사 중 Docker를 실행하거나 실제 이미지의 라이선스를 다시 읽지는 않는다.
- Docker/Compose/CI는 현재 승인된 제한 형식과 정확히 대조한다. 공백은 ASCII space/LF만 허용하고 Docker parser directive를 거부한다. 일반 YAML 파서가 아니며 anchors·별도 명령·새로운 구조는 통과시키지 않는다. inline 주석은 지정된 action SHA 뒤의 ASCII tag 주석만 허용하며 Docker/실행 명령의 inline 주석은 제거하지 않는다. CI action은 지정된 두 공식 action과 확인·채택한 각각의 정확한 commit SHA를 요구한다. 다른 40자리 SHA도 변경으로 거부한다. read 권한·수동 trigger·환경/명령·비활성 파일 위치를 확인한다. 정의 변경 시 관련 정책과 검토도 함께 갱신한다.
- private-key header와 지정한 GitHub/Slack/API/AWS 형식의 고신뢰 패턴을 검사한다. 변수명·일반 password 대입·범용 entropy는 탐지 근거로 사용하지 않는다. 알려진 공개 AWS 문서용 dummy 하나만 정확한 값으로 제외하며 테스트 canary는 조각을 합성해 만든다. 테스트 디렉터리 전체를 탐지 예외로 두지 않는다.

정규식 통과는 모든 비밀·개인 금융 자료의 부재나 전체 취약점 감사 통과를 뜻하지 않는다. key prefix가 없는 임의 비밀·새 토큰 형식·개인 자료의 의미·외부 의존성 취약점·역사적 Git 유출은 이 검사로 확인하지 않는다.

## 실행하지 않는 동작과 검증 범위

품질 CLI는 테스트·Docker·네트워크·자동 수정·commit·원격 작업을 실행하지 않는다. 테스트 명령은 사용자가 승인한 범위에서 따로 실행한다. 전용 quality 테스트는 임시 합성 저장소에만 Git index/fixture를 만들며 실제 저장소의 Git 상태를 변경하거나 commit하지 않는다.

Q15 전용 테스트는 공개/무시/보호 경로, symlink·hardlink·탈출·크기·binary, NUL 파일명, 탐지·출력 가림, AST 경계, 계약 drift·manifest 공격, 의존성/inventory/이미지/비활성 CI 변경 실패를 확인한다. 기존 ENV·product·isolation 테스트와 Docker 재현은 이 CLI의 검사 결과에 포함하지 않는다. 독립 검토/실행 결과는 작업 카드와 증거를 따른다.

[CI 정의](ci-definition.md)는 비활성 예제다. 이 문서와 로컬 검사의 통과는 원격 실행·GitHub 권한·비용·저장소 보호 규칙 설정의 승인이나 검증을 뜻하지 않는다.
