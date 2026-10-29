# Q15 원격 CI 비활성 정의

[workflow 예제](../../config/ci/quality.workflow.example.yml)는 `.github/workflows` 밖에 있어 GitHub가 실행하지 않는다. 로컬 정의만 작성했으며 push·원격 실행·repository variable/secret·branch protection 변경은 하지 않았다.

공개 후보 검사는 `python3.13 -I -S scripts/check_quality.py`로 실행한다. script/PYTHONPATH shadow 모듈과 site 초기화를 배제한 CLI 진입이며 두 flag가 없으면 검사기 bootstrap이 거부한다. 품질 단위시험의 모듈 import는 별도의 신뢰된 개발 실행이다. 제어 파일의 비ASCII 공백·Docker parser directive·승인된 action tag 이외 inline 주석도 허용하지 않는다.

공식 [GitHub runner 문서](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)는 ubuntu-24.04-arm을 public/private 모두 나열한다(2026-10-23 확인). 계정별 사용 가능·무료 시간·비용은 아직 확인하지 않았다. 실제 활성화 전에 AP-06의 저장소/작업 권한과 AP-03의 비용 상한을 확인한다. 기존 비용0 범위에서 실행할 수 없으면 보류한다.

2026-10-23 GitHub 공식 API의 latest release와 tag commit을 확인해 [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) `3d3c42e5aac5ba805825da76410c181273ba90b1`, [setup-python v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0) `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`로 고정했다. checkout은 credentials를 보존하지 않으며 권한은 contents:read, 입력 trigger는 수동뿐이다. 주문·개인자료·운영키·보고 토큰을 CI에 제공하지 않는다.

이 정의의 원격 Python 배포·runner Docker 기능·타임아웃·모든 테스트 통과는 아직 미검증이다. 로컬 검증 결과를 GitHub 실행 결과로 표시하지 않는다. 활성화 시 이 고정 버전과 runtime-lock의 이미지·플랫폼을 다시 대조하고 disposable runner에서 검증한다. 상시 self-hosted runner에 비신뢰 PR 코드를 자동 실행하는 정의는 없다.
