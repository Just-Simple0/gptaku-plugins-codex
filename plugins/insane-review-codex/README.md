# insane-review-codex

GPT Pro(웹 전용 — API 없음; 현 시점 최신 플래그십 모델의 Pro 추론)를 Codex CLI 안으로 끌어오는 브리지 플러그인. (v0.6.8 메타데이터, Unreleased 분기 수정 포함)

repomix로 관련 코드만 정밀 패킹 → 구독 ChatGPT 웹에 CDP 자동화로 투입 → 분석/리뷰 회수.
API 비용 0, 사용자의 ChatGPT 요금제로 동작.

## Unreleased 신뢰성 수정

배포 메타데이터는 0.6.8이며 현재 엔진에는 출시 전 Codex 분기 수정이 포함되어 있다. 전역 설치·캐시 갱신은 수행하지 않았다.

- 모델 선택 항목(`observed_selection`)과 실제 메뉴 표시(`actual_display`)를 보존한다. `최신`을 특정 버전으로 추정하지 않으며 effort는 정확히 비교한다.
- v2 manifest는 user/assistant ID가 일치할 때만 원 실행을 복구한다. URL-only와 구 manifest는 현재 마지막 user의 유일한 답변을 수동 회수하며 `original_run_bound=false`로 기록한다. 구 manifest는 보존한다.
- assistant DOM 본문만 회수하므로 Markdown 서식 일부가 달라질 수 있다. 동일 identity·본문·scoped 완료 증거의 연속 8초 안정과 저장 직전 재검증이 필요하다.
- 신규 대화 URL 포착은 별도 90초 제한(`INSANE_REVIEW_URL_CAPTURE_SECS`, 전체 대기 제한 이내)과 진행 출력을 사용한다. 위치 미확인 시 재전송하지 않는다.
- 가시적 오류/로그인 표면이 3초 연속 확인되면 회수를 중단한다. 일시적 오류와 조회 불가(`unknown`)는 완료 안정성 타이머를 초기화하며, `unknown`만으로 즉시 오류 종료하지 않는다. 원문 배너 대신 고정 분류만 출력한다.
- 실패/쿼터 복구는 user 결속이 저장된 manifest 경로를 우선 안내한다. user 미결속 URL 회수는 원 실행 복구가 아닌 수동 대안으로 명시한다.
- POSIX 패킹의 staging/raw log는 target 밖 임시 디렉터리 0700·파일 생성 시 0600으로 보호한다. config 실패는 실행 전에 중단하고 실패 산출물은 첨부하지 않는다. 삭제 대신 trash 또는 보존을 사용한다.
- Windows 패킹/브라우저 경로는 유지한다. raw 출력은 메모리 capture 후 정제 요약만 표시한다. POSIX 동등 ACL·후손 전체 종료·native ownership/concurrency는 미검증이다.
- macOS native CDP는 endpoint/profile 소유와 실행 잠금을 확인한다. 소유 미확인 프로세스를 자동 종료하지 않는다. 실제 Chrome/로그인 ChatGPT E2E는 별도 검증이다.
- POSIX native 잠금은 `TMPDIR`와 무관한 `/tmp/insane-review-locks-<uid>`(canonical 경로)에 보관하고 소유자·0700/0600 권한을 검사한다. 전송 준비 확인은 반복할 수 있으나 실제 click/Enter 시도는 한 번뿐이며, 클릭 결과 불명 시 재시도하지 않는다.
- Aside override는 유지한다. native 전환은 사용자 결정이며 UI 수정만으로 polling의 호출/토큰 문제가 해결됐다고 주장하지 않는다.

신규 자체 테스트(저장소 루트; pytest·beautifulsoup4·playwright 필요, 임시 fixture는 자동 삭제하지 않음):

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 python3 -m pytest plugins/insane-review-codex/tests -q -p no:tmpdir -p no:cacheprovider
```

기존 저장소 검증기 테스트의 7개 실패 기준선은 신규 suite 결과와 구분한다.

`tests/test_local_browser.py`는 설치된 macOS Chrome을 새 임시 프로필로 실행한다. 테스트 context는 offline 및 request abort로 외부 페이지를 차단하고 합성 DOM에서 실제 JS·파일 첨부를 검증한다. 개인 프로필을 사용하지 않고 브라우저를 다운로드하지 않는다. Chrome이 없으면 이 파일의 검사는 skip되며, 로그인된 ChatGPT E2E와는 별개다. 샌드박스가 Chrome/CDP나 후손 프로세스 검사를 차단하면 호스트 실행 결과와 구분해 기록한다.

## 사용 조건

- 크로미움 계열 브라우저 1개(Chrome/Brave/Comet/Edge 등) — 스크립트가 **전용(격리) 프로필 + 디버그포트 9222**로 띄운다(기본은 창을 숨긴 background 실행). 그 창에서 chatgpt.com 로그인 1회.
- Python 의존성: `pip install playwright pyperclip` (또는 `--check-env --install`)
- Node.js (npx — repomix 자동설치에 사용)

## 환경 점검 / 온보딩

```bash
# 저장된 브라우저가 있으면 조용히 자동 기동 후 점검 (평소엔 이것만)
python3 bin/pack_and_ask.py --ensure-env
# 순수 점검(부작용 없음) / 부족한 pip 패키지 자동설치
python3 bin/pack_and_ask.py --check-env
python3 bin/pack_and_ask.py --check-env --install
# 최초 1회: 브라우저 선택·실행(선택은 ~/.insane-review/config.json에 저장) + 실행 방식
python3 bin/pack_and_ask.py --list-browsers
python3 bin/pack_and_ask.py --launch-browser "Chrome"
python3 bin/pack_and_ask.py --set-launch-mode background   # background(기본)|foreground|headless(권장 안 함)
```

마지막 줄 `STATUS node=… deps=… browser=… login=… cookie=… saved_browser=… launch_mode=… mode=…`로 막힌 단계를 판단한다. 스킬(`skills/insane-review/SKILL.md`)이 이 분기를 번호 선택지로 안내한다.

## 기본 사용법

```bash
# 디렉토리를 통째로 패킹해 GPT Pro 리뷰 요청 (Pro 추론단계 자동 선택·검증, 플래그십 자동 추종)
python3 bin/pack_and_ask.py \
  --target ./src \
  --model pro \
  --prompt "이 모듈의 설계 리뷰를 해줘. 판정마다 파일:라인 인용 필수."

# 순수 질문만 (코드 없이)
python3 bin/pack_and_ask.py \
  --model pro --force-answer-after 90 \
  --prompt "비동기 큐 설계에서 backpressure를 어떻게 다루면 좋을까?"

# 타임아웃·중단 뒤 회수만 (재전송 없이)
python3 bin/pack_and_ask.py --harvest '<채팅URL 또는 .insane-review/manifest_*.json>'
```

응답은 **현재 프로젝트의 `.insane-review/response_*.md`**에 저장된다. 전송 직후 대화 URL이 `.insane-review/manifest_*.json`에 기록되어 프로세스가 죽어도 `--harvest`로 회수할 수 있다.

## agent-council 웹 멤버로 등록

`skills/insane-review/references/council-setup.md` 참고.

```bash
# council 계약 검증 (stdout=응답만, stderr=로그)
python3 bin/pack_and_ask.py --council --model pro \
  --force-answer-after 60 "한 문장으로: 1+1은?" 2>/dev/null
```

## 주요 플래그

| 플래그 | 설명 |
|--------|------|
| `--target <dir>` | 패킹 대상 디렉토리 (생략 시 프롬프트-only) |
| `--include <glob>` | repomix 포함 글롭 (정밀 선별) |
| `--model pro` | 추론단계 Pro 선택·검증 (플래그십 자동 추종) |
| `--require-model "<이름>"` | 모델명 고정 핀 (부분 일치; 불일치 시 fail-closed — 플래그십 교체 시 갱신 필수) |
| `--force-answer-after N` | N초 후 리즈닝 강제 종료 (빠른 의견용; 정밀 리뷰엔 쓰지 말 것) |
| `--max-wait N` | 응답 최대 대기 초 (기본 20분, Pro 검증 시 자동 60분) |
| `--harvest <URL\|manifest>` | 전송 없이 기존 대화에서 완료된 응답만 회수 |
| `--pack-only` | 패킹만 하고 전송하지 않음 |
| `--council` | agent-council 멤버 모드 — 응답만 stdout |
| `--retries N` | 결속된 응답의 회수 재시도. 전송 결과 불명이면 재전송하지 않음 |
| `--delete-pack` | 회수 후 `/usr/bin/trash`로 이동. 도구가 없으면 보존 |
| `--browser <이름\|경로>` | 자동화 브라우저 (생략: config 저장값 → 첫 감지) |
| `--launch-browser <이름>` | 전용 프로필+디버그포트로 실행하고 선택 저장 |
| `--set-launch-mode <모드>` | `background`(기본)/`foreground`/`headless` 저장 |
| `--project "<이름>"` / `--no-project` | ChatGPT 프로젝트 그룹핑 이름 지정 / 끄기 |
| `--check-env` / `--ensure-env` | 순수 점검 / 저장 브라우저 자동기동 + 점검 |
| `--install` | `--check-env`와 함께 — pip 의존성 자동설치 |

## 파일 구조

```
insane-review-codex/
  .codex-plugin/plugin.json       — 플러그인 메타데이터
  skills/insane-review/
    SKILL.md                      — 스킬 실행 지시서 (온보딩 분기 + 리뷰 절차)
    references/council-setup.md  — agent-council 등록 가이드
  bin/
    pack_and_ask.py               — repomix 패킹 + ChatGPT CDP 브리지 (Codex 분기 수정 포함)
  shared/questioning-policy.md    — 번호형 선택지 질문 규약
  assets/                         — 아이콘 등 (예비)
  .gitignore
  CHANGELOG.md
  README.md
```

## 주의사항

- **`--compress` 금지** (정밀 리뷰 시): 함수 본문이 제거돼 GPT가 구현을 추측하게 된다.
- **`--force-answer-after` 금지** (정밀 리뷰 시): Pro 추론을 중간에 끊는다. 명시적 빠른 의견·council 요청에만 사용하며 클릭 성공은 manifest에 `forced_answer=true`로 기록한다. 기본 timeout은 강제답변 없이 종료한다.
- **ChatGPT Chat/Work 토글**: Work 모드엔 Pro 추론단계가 없다. 스크립트가 전송 전에 Chat으로 자동 전환하고, 실패하면 fail-closed로 중단한다.
- git submodule 안의 파일은 부모 레포 루트에서 패킹하면 repomix가 제외한다 — 서브모듈 디렉토리를 `--target`으로 직접 지정하라.
- 실행 중 전용 브라우저 창을 조작하지 말 것(background 모드면 창이 숨어 있다).
- 응답은 플러그인 내부가 아닌 **현재 작업 디렉토리의 `.insane-review/`**에 저장된다.
