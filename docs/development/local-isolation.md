# 로컬 합성 연구 격리

Q14의 `DockerResearchRunner`는 신뢰된 호스트 제어기에서 호출한다. 비신뢰 연구 Python 코드와 명시한 합성 데이터를 stdin JSON으로 전달하며 Docker 옵션·이미지·환경·mount를 작업자가 지정할 수 없다. 모델이나 자료 문자열은 권한 근거로 사용하지 않는다.

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests/product -v
PYTHONPATH=src python3.13 scripts/check_isolation.py
```

고정 이미지가 로컬에 있어야 하며 자동 다운로드하지 않는다. 로컬 Unix Docker endpoint만 사용한다. endpoint 확인 이후 Docker 제어 명령은 호출별 빈 private DOCKER_CONFIG/HOME을 사용하며, 컨테이너 Env는 고정 이미지 기본값과 명시 항목의 정확한 집합만 허용한다. [Docker proxy 설정](https://docs.docker.com/engine/cli/proxy/)이 컨테이너 환경으로 자동 전달될 수 있어 부모 환경변수 제한만으로 충분하지 않다.

고정 정책은 image digest/arm64, user10001, network none, readonly, capability 제거, no-new-privileges, host mount 없음, PID16, 메모리128MiB와 swap 추가0, CPU quota1, 실행 wall5초, 프로세스별 hard CPU2초, tmpfs16MiB, input1MiB, stdout+stderr합산1MiB, logging none이다. 전체 작업의 CPU 합산2초 제한은 아니다. 생성·정리에는 별도 짧은 제어 timeout이 있으므로 함수 전체가5초 이내에 반환한다는 보장은 없다.

현재 runner는 위 고정 정책만 적용한다. `runtime.synthetic.toml`의 범위 검증은 임의 값 변경을 runner에 동적으로 적용하는 API가 아니다. 정책을 바꾸려면 코드·검증을 함께 변경한다. [Docker 자원 제한](https://docs.docker.com/engine/containers/resource_constraints/), [로그 저장](https://docs.docker.com/engine/logging/configure/), [Python hard resource limit](https://docs.python.org/3.13/library/resource.html)을 2026-10-23 확인했다.

동일 사용자 제어기는 보호된 고정 lock inode에 flock을 잡는다. 동시 작업은 기다리는 무한 큐 대신 거부하며 재시도는 하지 않는다. stale 기록은 UUID·Docker endpoint/daemon identity fingerprint를 결속한다. 대상 불일치·미확인·기존 형식은 기록을 보존하고 새 작업을 차단한다. 정확한 UUID·이름·소유 label이 일치하는 자기 컨테이너만 정리한다. 자식 Docker client가 끝났다는 이유로 정리를 성공 처리하지 않는다. create 응답이 불명확할 수 있으므로 최초 목록의 부재만으로 marker를 지우지 않는다. 정확한 자기 객체 관측·삭제·삭제 후 부재 확인이 필요하다. 외부에서 객체를 삭제했거나 삭제 직후 controller가 종료돼 marker만 남아도 자동 해제하지 않는다. 그런 경우 해당 daemon의 생성 결과와 정리를 수동 확인해야 하며, marker 임의 삭제를 정상 복구로 안내하지 않는다. 실패 시 marker를 남기고 다음 실행도 정리 확인 전 차단한다.

`SyntheticBinding`은 모의/실전·다른 계좌/namespace·금융 쓰기를 거부한다. `SyntheticController`와 liveness는 신뢰된 호스트 내부의 합성 제어 구조이며 실제 사용자 인증이 아니다. 만료·단절 뒤 갱신만으로 재개되지 않는다. 실제 승인/dispatch/egress 연동은 Q26/27에서 검증한다.

private 경로 검사는 기존 합성 경로의 metadata만 읽는다. repository·symlink·소유권/권한·hardlink 조건을 확인하지만 이후 별도 open의 안전성·ACL·디스크 암호화를 보장하지 않는다. 실제 비밀파일은 조회하지 않았다. 호스트 관리자·Docker daemon·고정 이미지·trusted controller를 신뢰하며 그 자체의 침해 방지는 이 경계 밖이다. wall timeout은 살아 있는 controller가 강제한다. controller SIGKILL·호스트 종료·daemon 장애 뒤5초 종료는 보장하지 않으며 stale 확인 전 새 실행을 차단한다.

## 검증 기록

구현자 자기 검증: 제품39개, 실제Docker12개 통과. 최초2회는 network none에서도 kernel tunnel interface가 존재한다는 점을 반영하지 못한 테스트 가정으로 실패했다. 정책을 완화하지 않고 Docker 실제 설정·IPv4 route 없음·외부 연결 ENETUNREACH를 기준으로 고쳤다. 보안·독립 검토와 독립 실행 결과는 [작업 카드](../tasks/SEC-local-boundaries.md)에 기록한다.

보안 검토의 Docker proxy 자동주입·다른 endpoint에서 stale 정리 오판2건을 수정했다. 구현자 수정 회귀는 경계 단위23개·실제Docker13개 통과다. 다른 실제 daemon을 생성/접속하지 않고 identity 불일치는 합성 단위시험으로 검증했다. 보안 재검토·독립 검증은 아직 진행 전/중이다.

최종 독립 검증: 제품47개·실제Docker13개·foundation8개/제품47개 통과. 보안/일반 지적 수정 및 재검토 완료. 상세 버전은 [검증 증거](../evidence/sec-local-validation-2026-10-23.json)를 따른다. 위 자기 검증·재검토 대기 문장은 당시 기록이다.
