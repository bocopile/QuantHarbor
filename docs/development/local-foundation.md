# 로컬 합성 개발 기반

Q13은 Python 기본형·canonical 직렬화·비활성 CLI와 임시 PostgreSQL의 재현 기반이다. 실제 계좌·외부 API·주문·지속 실행은 포함하지 않는다.

## 재현

로컬 Docker Desktop의 Unix socket context와 Compose가 필요하다. 현재 고정 이미지는 linux/arm64 전용이다. 다른 아키텍처는 digest를 별도로 확인해야 한다. 호스트 Python 3.13으로 저장소 루트에서 실행한다.

```sh
python3.13 scripts/check_foundation.py
```

스크립트는 UUID 이름의 합성 전용 Compose 프로젝트를 만들고 검사 후 제거한다. 앱 컨테이너에서 고정 Python과 전용 테스트 개수·성공, 설정 기동을 확인한다. PostgreSQL에서 migration 재적용·checksum 변경 거부·실패 transaction rollback·정확한 소수 저장·dump/restore를 검사한다. 다른 프로젝트를 종료하지 않는다. 실패 출력은 고정 이유 코드이며 원시 환경·SQL 오류를 기록하지 않는다. 강제 프로세스 종료나 Docker 장애 시 자동 정리가 보장되지는 않는다.

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -v
PYTHONPATH=src python3.13 -m quantharbor status
```

호스트 검사는 개발 편의용이다. 재현 기준 Python은 runtime-lock의 3.13.17이며 호스트 3.13.12 결과와 구분한다. 패키지를 전역 설치하지 않으며 현재 실행은 PYTHONPATH 기반이다.

## 경계

컨테이너는 비특권 사용자·읽기 전용 root·network none·capability 제거·메모리/프로세스/CPU 상한을 사용한다. host mount·포트·영속 볼륨·자동 재시작은 없다. DB는 tmpfs의 합성 자료만 사용한다. Dockerfile context는 공개 소스·제품 테스트·합성 설정만 허용한다. buildx 메타데이터는 임시 경로를 사용해 사용자 전역 설정을 변경하지 않는다.

설정의 wall time·CPU time·입출력 크기 등의 모든 값이 이 단계에서 실행 통제로 구현된 것은 아니다. 연구 실행의 자원 초과·환경 교차·liveness·canary 격리 실험은 Q14에서 수행한다. 이 DB dump 검증도 실제 운영 백업·보존 정책을 대신하지 않는다.

## 고정 의존성

[runtime-lock](../../config/runtime-lock.json), [이미지 구성 목록](../evidence/base-runtime-inventory-2026-10-23.json), [선정 결정](../decisions/BASE-DEC-001-runtime.md)을 따른다. 애플리케이션 Python 외부 패키지는 현재 0개다. 이미지 내 OS 패키지와 라이선스는 별도 목록에 남긴다. 취약점 부재·재배포 법률 검토를 완료한 의미는 아니다.
