# insane-review 수정 작업 인수인계

작성일: 2026-10-01 (Asia/Seoul)

> **최신 상태는 §9(2026-10-01 후속)가 우선한다.** §1~§8은 중간 커밋 시점의 기록이다.

## 1. 현재 상태

- 저장소: `<저장소 루트>`
- 작업 브랜치: `fix/insane-review-reliability`
- 작업 시작 기준 HEAD: `d3b47fc`
- 대상: `plugins/insane-review-codex`의 엔진·문서·자체 테스트.
- 배포 메타데이터는 `0.6.8`, 변경 사항은 Unreleased 상태다.
- 로컬 수정과 합성 브라우저 검증은 진행했으나, **최신 수정본의 실제 ChatGPT 전송·회수는 아직 완료하지 못했다.**
- 최신 파일 선택 수정 이후 실제 전송을 재시도하기 전에 사용자가 작업을 중단했다. 이후 이 인수인계서 작성과 현재 작업의 커밋을 명시적으로 요청했다.
- 이번 커밋은 미완료 작업을 보존하는 중간 커밋이다. 최신 후보의 최종 리뷰·수용·릴리즈를 의미하지 않는다. push는 요청받지 않았다.
- 이 문서의 최신 상태가 아래에 언급한 과거 로컬 작업 기록보다 우선한다.

## 2. 배경과 수용 기준

격리 Chrome의 디버그 포트 기동 실패와 ChatGPT UI 검증 문제가 발생해 Aside로 전송·harvest를 우회했다. 사용자는 Aside에서 결과를 기다리며 추가 상태 확인을 호출하는 과정이 Codex 사용량 증가의 원인이라고 확인했다. S4라는 별도 제품 개선으로 범위를 넓히기보다 native insane-review 흐름 복구를 우선했다.

현재 작업에 대해 사용자는 Aside 대신 수정한 insane-review의 Chrome/CDP 경로로 실제 전송·회수를 검증하도록 승인했다. 일반적인 개인 설정의 Aside override와 구분해야 한다. 다른 프로젝트나 향후 모든 전송까지 승인된 것은 아니다.

실제 검증의 완료 기준:

1. 전용 Chrome/CDP 소유권과 로그인·Chat 모드 확인.
2. 정확한 ChatGPT 프로젝트에서 독립 대화 생성.
3. 실제 모델·추론 강도와 첨부 준비 상태 확인.
4. 현재 전체 소스 패키지를 한 번만 전송.
5. 그 대화의 user/assistant identity에 결속된 완성 응답을 native CLI로 저장.
6. manifest의 프로젝트·모델·패키지 hash·대화 URL·응답 provenance 검증.
7. 최신 후보의 독립 리뷰 findings 처리와 필요한 재리뷰 후 최종 수용.

Pro 비활성은 사용자가 설명한 계정 사용량/주간 한도 문제로 취급한다. 플러그인 결함으로 단정하지 않는다. Pro를 우선하며, 사용량 한도가 실제 확인된 경우에만 이미 승인된 Very high fallback을 사용할 수 있다. 실제 선택값과 이유를 기록하고 fallback을 Pro라고 부르지 않는다.

## 3. 구현한 변경

- Repomix 패킹: 실패 결과를 성공 패키지로 사용하지 않도록 차단하고, 보호된 staging/log, signal·timeout·후손 프로세스 처리와 원자적 발행을 보강했다. 진단 출력은 정제하며 삭제는 trash 또는 보존으로 처리한다.
- Native 브라우저: endpoint/executable/profile 소유권과 TMPDIR에 독립적인 POSIX 실행 잠금을 검증한다. 소유 미확인 프로세스를 자동 종료하지 않는다. Windows의 동등한 ownership/concurrency 검증은 미완료로 표시한다.
- ChatGPT UI: 현행 composer·응답·Chat/Work·모델/effort UI를 지원하고, 선택 후와 전송 직전에 재검증한다. 모델 항목·표시 텍스트·effort provenance를 구분한다.
- 슬라이더 우선: 사용자가 승인한 정책에 따라 유효한 연결 slider가 확인된 경우 trigger의 충돌하는 effort 메타데이터를 제외한다. 잘못된 slider, 보이는 canonical label 충돌은 계속 차단한다.
- 첨부: 관측한 `파일 등 추가` 및 `사진 및 파일 추가 컴퓨터에서 업로드` 접근성 버튼으로 FileChooser를 연다. 메뉴 role을 가정하지 않고 유일한 보이는 업로드 버튼을 요구한다. current adapter의 임의 file-input 직접 선택 fallback은 제거했다.
- 첨부 준비: 기존 첨부/진행 상태를 거부하고, 정확한 실행 파일명 버튼·일치하는 제거 버튼·업로드 완료·활성 Send를 연속 두 번 확인한다. legacy/unknown live adapter는 계속 차단한다.
- 전송: 본문·composer·첨부·전송 버튼을 한 동기 JS 동작 안에서 다시 확인한다. 실제 활성화 시도는 한 번이며 결과 불명은 재전송하지 않는다. current adapter에는 Enter fallback이 없다.
- Harvest: v2 manifest로 URL 및 user/assistant identity를 결속한다. streaming/완료 증거·동일 본문이 연속 8초 안정된 뒤 저장 직전에 재검증한다. 기본 timeout은 강제답변을 누르지 않으며, 명시적 강제답변은 provenance에 남긴다.
- 문서: README, CHANGELOG, SKILL.md에 Unreleased 동작과 검증 한계를 반영했다.
- 테스트: `tests/conftest.py`, `test_reliability.py`, `test_local_browser.py`, `test_n1_n4_browser.py`, `test_pack_cancellation.py`를 추가했다.

## 4. 최근 실제 실행과 남은 불확실성

사용한 Chrome/CDP는 9225, 테스트용 전용 프로필과 config를 환경 변수로 지정했다. `--check-env`에서 `browser=ok login=ok cookie=ok mode=chat`이 확인됐다. 실제 실행은 아래 프로젝트 진입과 `effort=pro` 사전검증까지 통과했다.

프로젝트 이름:

`gptaku-plugins-codex · 1797b9ea`

프로젝트 홈:

`https://chatgpt.com/g/g-p-<PROJECT_ID>-gptaku-plugins-codex-1797b9ea/project`

최근 두 실제 실행은 모두 전송 전에 실패했다:

| 실행 패키지 | 실패 사유 | 전송 상태 |
| --- | --- | --- |
| `pack_gptaku-plugins-codex_20261001_092101_96368_772ad9.md` | `selected_file_mismatch` | CLI가 미전송을 명시 |
| `pack_gptaku-plugins-codex_20261001_092922_99898_016f64.md` | 진단 분류 후 `selected_file_count_mismatch` | CLI가 미전송을 명시 |

두 번째 사유는 FileChooser의 input에서 조회한 파일 수가 1이 아니었다는 뜻이다. **정확히 0개였다는 추가 계측은 없었다.** 당시 사용자 보고에서 0개로 표현했지만 확정된 증거보다 강한 표현이었다.

최신 엔진은 `FileChooser.set_files()` 직후 input의 FileList를 다시 읽는 검사를 제거했다. UI change handler가 임시 input을 초기화하는 경우 정상 첨부를 실패로 판정할 수 있기 때문이다. 정확한 경로를 FileChooser에 전달한 뒤, 위의 보이는 첨부 준비 검증과 전송 직전 검증을 통과해야만 전송한다. **실제 ChatGPT가 input을 초기화한 것이 원인이라는 판단은 아직 가설이며, 최신 엔진의 실제 재실행으로 확인해야 한다.**

인수인계 과정에서 해당 fixture의 `clearInputAfterChange` 변수 전달 누락을 수정했다. 실제 FileList가 초기화된 경우 0개, 유지된 경우 1개인지 단언을 추가했다. 따라서 초기화 상황을 포함한 테스트 결과를 이제 실제 단언으로 확인했다.

이전 일부 시도는 새 탭에서 일반적인 전송 준비 오류로 끝났다. 전용 Chrome을 ChatGPT에 다시 진입시킨 후 환경 점검 및 이후 프로젝트/모델 단계는 통과했지만, 그 초기 오류의 근본 원인은 확정하지 못했다.

CUA에서 별도의 Claude 관리 ChatGPT 탭과 `hello.txt` 첨부, Chrome debugging 표시가 관측됐다. 이는 native 실행의 첨부 성공 증거가 아니다. 재개 시 다른 브라우저 제어 작업과 충돌하지 않는지 확인하고 정확한 전용 세션을 사용해야 한다.

## 5. 검증과 리뷰 상태

- 최신 input 사후검사 제거 전 전체 plugin suite: **247 passed, 122.00s**. 이는 과거 후보 결과이며 최신 전체 suite 결과로 표시하지 않는다.
- 최신 첨부 수정의 집중 UI 검증: **10 passed, 61 deselected, 20.69s**. 업로드 버튼 이름 5종 × input 초기화 여부 2종을 확인했다. 초기화 여부에 대한 실제 FileList 단언을 포함한다.
- 엔진 문법 검사는 최신 엔진에 대해 통과했다. 인수인계 전 `git diff --check`도 통과했다.
- 합성 브라우저 테스트는 로그인된 ChatGPT E2E를 입증하지 않는다. 현재 전체 suite 재실행과 실제 전송·회수 검증이 남아 있다.
- 이전 F1–F3 묶음은 독립 ChatGPT Pro 및 Gemini Ultra 리뷰에서 APPROVE를 받았다. 슬라이더 우선 수정도 독립 최종 리뷰에서 APPROVE를 받았다. 이후 native 첨부 변경까지 승인됐다고 확장하지 않는다.
- Native attachment plan의 웹 리뷰는 전송 결함으로 완료하지 못했다. Gemini 계획 리뷰는 조건부 승인이었고, 최신 후보의 최종 독립 리뷰와 수용은 미완료다.
- 최신 전송이 성공하면 `.insane-review/native-review-prompt-20261001.md`의 독립 최종 코드 리뷰 요청을 같은 대화에서 harvest해야 한다. 미완성 응답이나 모델/effort 미검증 응답을 리뷰 완료로 취급하지 않는다.

## 6. 패키지와 로컬 근거

마지막 사전 감사 패키지:

`.insane-review/native-live-verification-20261001/pack_gptaku-plugins-codex_20261001_093641_3548_35cf6a.md`

- 범위: `plugins/insane-review-codex/**`, 압축 없음.
- 크기: 402,612 bytes.
- SHA-256: `37075175aa351f195bbed2d3c7b8e449f4f640579a1d9b7f8598239b9a1c4251`.
- 감사 당시 16/16 파일이 작업본과 일치하고, `rg` 파일 목록과 누락/추가 없이 일치했다.
- Repomix security screening이 활성 상태였고 suspicious-exclusion 경고가 없었다.
- **이후 인수인계 과정에서 테스트 변수 전달과 단언을 수정했으므로, 이 패키지는 최신 테스트와 다르다. 다음 전송 전에 재패킹·재감사가 필요하다.** 엔진 자체는 그 이후 바뀌지 않았다.

현재 엔진 SHA-256:

`99806f3634b5e1ceed9ac7f5c13939689fef8b3e3eab8f683a37ae15ef60400b`

현재 `tests/test_n1_n4_browser.py` SHA-256:

`9f984c920319f61a1da0ea08fc69f46b12ac9482648b9aacf6e0fc4e29e82f11`

주요 로컬 기록:

- `.insane-review/source-audit-native-live-2026-10-01.json`
- `.insane-review/native-execution-fix-2026-10-01.md` (과거 상태가 포함되어 있으므로 이 문서 우선)
- `.insane-review/native-attachment-plan-20261001.md`
- `.insane-review/native-review-prompt-20261001.md`
- `.insane-review/disposition-final-rereview-f1-f3-2026-09-30.md`
- `.insane-review/response-final-slider-priority-review-2026-09-30.md`

`.insane-review/`의 대용량 패키지·로컬 리뷰 기록은 이번 커밋에 포함하지 않는다. 다른 컴퓨터에서 clone하면 이 자료는 없다. 이 문서에 남긴 상태와 hash를 기준으로 새 패키지·리뷰 근거를 만들어야 한다. 인증 쿠키/자격증명은 인수인계서에 저장하지 않는다.

## 7. 실제 수정본으로 재개하는 방법

설치된 이름만 보고 최신 작업본이 실행된다고 가정하지 말 것. 최근 실제 실행은 **저장소의 `plugins/insane-review-codex/bin/pack_and_ask.py`를 직접 호출**했다.

테스트 캐시의 다음 두 엔진은 현재 작업본과 다르다:

- `~/.codex/plugins/cache/gptaku-codex-worktree-test-20260930/insane-review-codex/0.6.8/bin/pack_and_ask.py`
- `~/.codex/plugins/cache/gptaku-codex-worktree-test-20260930/insane-review-worktree-test/0.6.8/bin/pack_and_ask.py`

두 캐시의 SHA-256은 `0cc53bf6ee431c17623d0ae24af1da03748d61a469d671177d9e63b70edbfe59`였다. 캐시 파일은 자동 동기화되지 않는다. 최신 검증에는 저장소 엔진을 직접 사용하고, 전역/versioned 캐시를 임의로 패치하지 않는다.

테스트 환경 지정:

```sh
cd <저장소 루트>
export INSANE_REVIEW_CDP_PORT=9225
export INSANE_REVIEW_PROFILE=/private/tmp/insane-review-livecheck-20260930-profile
export INSANE_REVIEW_CONFIG=/private/tmp/insane-review-test-config-20261001.json
python3 plugins/insane-review-codex/bin/pack_and_ask.py --browser chrome --check-env
```

위 `/private/tmp` 파일/프로필은 로컬 임시 자원이며 재개 시 존재 여부와 소유권을 확인해야 한다. 새 프로필에 개인 프로필의 쿠키/자격증명을 복사하지 않는다. 실제 로그인 벽을 확인한 경우에만 사용자 로그인을 요청한다. 과거 실행은 정확한 Repomix 1.15.0 캐시를 사용하는 `/private/tmp/insane-review-npx-shim`과 `NPM_CONFIG_OFFLINE=true`도 사용했다. shim이 없으면 복구 여부와 네트워크/캐시 상태를 확인한다.

재개 순서:

1. 현재 branch/source 상태를 읽고 최신 엔진을 직접 호출하는지 확인한다.
2. 위 환경 점검과 전용 세션·프로젝트·실제 모델/effort를 확인한다.
3. 전체 plugin suite를 한 번 실행하고 필요한 실패만 처리한다.
4. `--pack-only`로 최신 전체 plugin 소스를 만들고, 포함 파일/작업본 일치/크기/SHA-256/secret screening을 감사한다.
5. 아래 실제 실행을 한 번 수행한다. 실행 중 같은 전용 Chrome을 CUA나 다른 controller로 조작하지 않는다.
6. 전송 전 실패면 원인을 확인해 수정한다. 전송 결과 불명 또는 manifest/대화 URL이 있으면 같은 대화부터 검사하고 `--harvest`로 재개한다. 잠재적으로 전송된 리뷰를 다시 보내지 않는다.
7. native 완료 응답과 provenance를 확인하고 독립 리뷰 findings를 처분한다. 필요한 재리뷰와 최종 수용 후에만 완료를 선언한다.

전체 suite:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  plugins/insane-review-codex/tests -q -p no:tmpdir -p no:cacheprovider
```

실제 실행 (이 문서 작성 중에는 실행하지 않음):

```sh
python3 plugins/insane-review-codex/bin/pack_and_ask.py \
  --target <저장소 루트> \
  --include 'plugins/insane-review-codex/**' --ignore '.insane-review/**' \
  --prompt-file .insane-review/native-review-prompt-20261001.md \
  --model pro --attach --browser chrome \
  --project 'gptaku-plugins-codex · 1797b9ea' \
  --retries 0 --max-wait 3600 \
  --out-dir .insane-review/native-live-verification-20261001
```

fresh clone에서 prompt가 없으면 현재 전체 소스/테스트에 대해 native 소유권·동시성·로그인·모델/effort·패킹·첨부·한 번 전송·identity harvest를 독립 검토하도록 새 prompt를 만든다. 실제 결함만 근거/재현/영향과 함께 보고하고 APPROVE/REVISE 판정 및 실제 모델/effort를 요청한다. 과거 실행의 모델이나 성공 여부를 새 실행의 사실로 넣지 않는다.

manifest가 생성된 후에는 위 전용 환경에서 다음처럼 회수한다:

```sh
python3 plugins/insane-review-codex/bin/pack_and_ask.py \
  --browser chrome --harvest '<그 실행의 manifest 경로>' \
  --out-dir .insane-review/native-live-verification-20261001
```

## 8. 파일 소유와 커밋 범위

현재 묶음의 통합 및 인수인계는 이 대화의 orchestrator가 담당했다. 과거 worker의 미완료 배정은 로컬 기록에 남아 있으며, 이번 문서 작업에 별도 worker를 새로 생성하지 않았다.

이번 중간 커밋 대상은 `handoff.md`, 변경된 plugin 엔진·README·CHANGELOG·SKILL.md, 위 자체 테스트 5개다. 다른 plugin이나 전역 설정은 커밋 범위에 포함하지 않는다. commit 식별자는 완료 후 Git log에서 확인한다.

## 9. 2026-10-01 후속: 실제 ChatGPT 검증과 회수·소유권 수정

결론: 수정한 엔진으로 첨부 → 전송 → user 결속 → 완료 판정 → 회수가 실제 ChatGPT(Pro, 프로젝트 `gptaku-plugins-codex · 1797b9ea`)에서 CLI 한 번으로 끝까지 동작했다. 전체 suite 310 passed.

### 실제 UI에서 확인한 사실 (코드 근거가 된 실측)
- 업로드 항목(`사진 및 파일 추가 컴퓨터에서 업로드`)은 role 없는 `<button>`이고 composer 폼 밖 BODY 아래 DIV 안에 있다. 메뉴에는 `id`/`aria-controls`가 없다. "+" 버튼과 left가 같고 세로로 인접(간격 20px)하다(새 채팅·프로젝트 화면 모두).
- 첨부 직후 모든 `input[type=file]`의 `.files`는 비어 있다(사후 FileList 검사는 근거가 될 수 없다). 업로드 중에는 `role=progressbar`의 `aria-label="<파일명> 업로드 중"`이 나타나고 Send가 `aria-disabled=true`이며 파일명 버튼은 완료 후에만 생긴다.
- 긴 user 메시지는 접혀(`… 더 보기`) 표시되고 마크다운 렌더링이 백틱을 지운다(정확 해시 불일치, 지문 lite 일치로 통과).
- 응답에 코드 블록이 있으면 어시스턴트 노드 안에 `복사` 버튼이 여러 개 생긴다. 턴 단위 복사 버튼은 응답 길이와 무관하게 노드 밖 툴바에 1개 있다.
- 스레드 스크롤러는 `flex-direction: column-reverse`(scrollTop=0이 맨 아래). SPA가 URL의 프로젝트 슬러그를 잠깐 뗐다 붙인다.

### 수정한 결함
- 회수: ① 접힘·마크다운으로 인한 본문 해시 불일치 → 지문(`sent_text_fingerprint`: lite/skeleton/numbers/ops, 해시만 저장). ② 코드 블록 복사 버튼 때문에 완료 판정이 영구 실패. ③ `column-reverse`에서 `tail_confirmed` 오판. ④ URL 문자열 비교를 `/c/<대화ID>` 비교로. 응답의 `ChatGPT 답변:` 접두어 제거. 실패 사유는 고정 목록에 있는 것만 정제 출력.
- 독립 리뷰 2회 반영: 업로드 소유권(메뉴 정렬·인접), 프로젝트 캐시 origin 검증, 탐색한 프로젝트의 unknown/auth 시 새 프로젝트 생성 금지, 진행 표시 규칙 통일(원래 있던 `rf` 정규식 `{3}` 버그 포함), 제거 버튼 규칙 통일, 강제답변 대상 확인, `Chrome`과 절대경로의 프로필 identity.
- 새 테스트는 핵심 로직을 하나씩 망가뜨려(변이) 실제로 실패하는지 확인했다.

### 실행 기록 (로컬, 커밋 제외)
- 리뷰 응답 요약: `.insane-review/native-live-review-result-2026-10-01.md`. 소형 스모크(더미 파일)와 긴 프롬프트 검증은 둘 다 75초, `phase=COMPLETE`.
- 긴 프롬프트 검증: 1,139자, 화면 표시 `… 더 보기` 확인, 정확 해시 불일치 / lite·골격·숫자·연산자 일치.

### 알려진 한계 / 다음 작업
- 업로드 메뉴가 **위로** 열리는 경우(아래쪽 composer)는 실측하지 못했다(규칙은 위/아래를 모두 처리하도록 작성, 테스트는 아래로 열리는 경우만).
- 접힌 표시가 본문을 실제로 잘라내는 아주 긴 프롬프트는 관측하지 못했다(그 경우 수동 `--harvest <URL>`).
- Windows의 동등한 소유권·동시성 검증은 여전히 미완료다.
- 덮개를 닫으면 Mac이 잠들어 실행이 멈춘다(`caffeinate -i`로는 못 막음). 실행 중에는 덮개를 열어 둔다. 중단돼도 manifest(`--harvest <manifest>`)로 재전송 없이 이어 회수할 수 있다.
- 이 중간 커밋도 push·릴리즈·전역 설치를 의미하지 않는다.
