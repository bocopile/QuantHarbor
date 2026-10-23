# ENV-controls — 모델·도구·권한 설정 순차 적용

- 기준일: 2026-10-20
- 상태: 진행 — 설정 로드와 후속 합성 권한 검증 완료, 신뢰·감사 등 잔여 항목 있음
- 관련 작업: ENV-04·05·06·07·08·09
- 요청 근거: 사용자의 “순차적으로 작업 진행해줘” 요청
- 담당: 주 담당 1명. 병렬 agent·별도 모델 작업 없음
- 선행: ENV-bootstrap의 역할·작업 계약과 프로젝트 설정 배치
- 소유 파일: `.codex/config.toml`, `config/ai/development-policy.toml`, 개발 환경 문서·ENV 카드·status·README
- 범위: 기존 설정의 비민감 필드 확인, 프로젝트 도구 제한·선택형 권한 프로필 구성, 로컬 설정·Skill·Hook 목록 조회
- 최초 범위 밖: 전역 설정/인증 변경, 모델 대화 실행, 테스트·격리 행동 검증, Hook 신뢰 변경, 외부 메시지·계좌·주문. 후속 사용자 전체 실행 요청에 따른 합성 검증은 [ENV-validation](ENV-validation.md)에서 수행했다.

## 수행 순서와 결과

1. 기존 전역 설정에서는 모델 `gpt-6-luna`, 추론 `high`, workspace-write를 확인했다. 프로젝트는 이를 덮어쓰지 않는다. 이는 로컬 CLI 기본값이며 현재 앱 대화의 모델이나 실제 API 사용 자격을 입증하지 않는다.
2. 코드 탐색 MCP에 설치된 `codebase-memory-mcp` 실행 파일과 도구 11개의 허용 목록을 프로젝트 설정으로 기록했다. 그래프 삭제·ADR 수정·trace 적재 도구는 이 목록에 넣지 않았다. 인덱싱은 로컬 그래프를 변경하는 기능으로 남겨 저장소 탐색 규칙을 유지했다.
3. 앱의 기본 destructive/open-world 도구 허용을 끄고, 쓰기 도구는 `writes` 승인 모드를 설정했다. 개별 앱/도구 재정의와 메타데이터에 영향을 받으므로 모든 외부 변경을 강제 차단했다고 표현하지 않는다.
4. `qh_review`와 `qh_development` 권한 프로필을 정의했다. 각각 기본 read-only/workspace를 확장하고 명령 네트워크를 끄며 지정된 credential·운영정보 경로 읽기를 제한한다. 현재 부모 세션에는 선택하지 않았다. MCP·connector·브라우저 권한은 이 명령 샌드박스의 적용 범위 밖이다.
5. 로컬 app-server의 `config/read`, `skills/list`, `hooks/list`만 조회했다. 대화·turn을 생성하지 않았고 Hook·MCP 업무 도구·모델을 실행하지 않았다. 임시 SQLite 상태 디렉터리를 사용하고 프로세스를 종료했다. 전체 설정·credential·원시 로그는 저장소에 저장하지 않았다.

## 설정 조회에서 확인한 사실

비민감 필드만 선택한 [설정 조회 요약](../evidence/env-config-2026-10-20.json)을 보존했다. 전체 설정·통신 원문·인증 정보는 포함하지 않는다.

| 항목 | 결과 | 한계 |
|---|---|---|
| 프로젝트 설정 | strict-config를 사용하는 app-server 로더에서 성공 | 현재 열린 앱 대화에 모든 변경이 즉시 반영됐다는 증거는 아님 |
| 코드 탐색 MCP | 허용 도구 11개, `writes` 승인 모드 확인; 후속 현재 대화 도구 목록도 11개 일치 | 다른 connector와 개별 앱 권한의 포괄 검증은 아님 |
| 앱 기본값 | destructive=false, open_world=false, 승인 모드 writes | 개별 설정·도구 메타데이터에 따라 달라짐 |
| 권한 프로필 | qh_review·qh_development 로드, 후속 명령별 프로필 선택으로 합성 검증 10개 통과 | 현재 앱 세션 기본 권한을 바꾸거나 운영 격리를 검증하지 않음 |
| 프로젝트 Skills | 3개 모두 enabled=true, 발견 오류 0 | 대표 행동 검증은 별도 |
| 프로젝트 Hook | SessionStart 1개, enabled=true, trustStatus=untrusted, 목록 오류 0 | 신뢰 승인·실행 안 함 |
| 역할 6개 | 기존 TOML 파일 보존 | config/read의 agents 객체에는 standalone 역할 목록이 나오지 않아 로드 여부 미확인 |

설정에서 전역 Notion MCP와 node_repl의 연결은 유지됐다. 코드 탐색 서버의 allowlist가 다른 서버·앱 connector를 제한하는 것은 아니다.

## 실패와 수정

- 초기 조회는 사용자 Codex 상태 DB에 대한 샌드박스 쓰기 제한으로 시작하지 못했다. 임시 상태 DB로 분리한 뒤에도 로컬 실행 제약이 있어 승인된 조회 실행을 사용했다.
- strict 로더는 transport 없는 MCP 테이블을 거부했다. 프로젝트 설정에도 PATH에서 확인한 실행 파일 이름을 명시했다. 불완전한 Notion 재정의는 제거해 기존 연결을 유지했다.
- 수정 후 같은 설정 조회가 종료 코드 0으로 완료됐다. 이전 실패를 설정 검증 성공으로 대체해 숨기지 않는다.

## 남은 순서

1. ENV-04: 선택 가능한 모델 목록 7개와 추론 수준을 `model/list`로 조회했다. 실제 추론·가격 검증은 아니다. 후속 [ENV-runtime-controls](ENV-runtime-controls.md)에서 합성 검증기에 15초/명령·120초/명령 묶음·자동 재시도 0회를 강제했다. 추가 유료 runner는 생성하지 않는다. 계정 전체 월 예산·한도는 미정이다.
2. ENV-06·08: 현재 대화 도구 목록과 명령 프로필 합성 검증 완료. 역할별 실제 실행과 운영 격리는 미완료다.
3. ENV-07: 합성 검증기의 완료 감사 기록을 구현·검증했다. 전체 도구 호출 감사는 별도다. 시작 안내 Hook은 사용자 신뢰 이후 실행 확인하며 현재 신뢰 상태를 우회하지 않는다.
4. ENV-10·11: 사용자가 전체 순차 실행과 기존 ENV 완료 조건 유지를 선택했다. 합성 권한 검증은 실행했고, Slack 대상·최초 메시지 승인을 구체적인 초안과 함께 확인 중이다.

ENV 전체 완료·ARC 착수 조건은 아직 충족하지 않았다. 위 최초 설정 조회 이후의 검증은 ENV-validation 기록을 따른다. 독립 검토, 계좌 연결, Slack 전송, commit·push는 수행하지 않았다.

## 근거

2026-10-20 로컬 CLI 0.162.1의 공식 JSON Schema와 설정 조회, [MCP 설정](https://learn.chatgpt.com/docs/extend/mcp), [권한 프로필](https://learn.chatgpt.com/docs/permissions), [설정 참조](https://learn.chatgpt.com/docs/config-file/config-reference)를 확인했다. 설정 프로필은 명령 실행 범위이며 모든 도구의 권한 경계를 대신하지 않는다.
