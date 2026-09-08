# 팬아웃 모드 (Phase 3 실행부 — v2.8, Codex 서브에이전트 병렬 스폰)

Phase 3의 검색 실행을 런타임 서브에이전트(`spawn_agent`) **병렬 스폰**으로 수행하는 모드. 원본 하네스 실측(2026-07-23): 6폭 버스트 6/6 무사고(3.8s), 리서치형(웹검색 수행) 5폭 5/5 무사고(16s). Codex 런타임에서 같은 폭이 안전하다는 실측은 아직 없으므로 **첫 실행은 폭 4-5로 시작**하고 무사고가 확인되면 5-6으로 올린다.

## 모드 선택 (Phase 3 진입 시 1회)

| 조건 | 모드 |
|---|---|
| 세션에서 `spawn_agent`로 서브에이전트를 병렬 스폰할 수 있고, 반환 JSON을 파일로 받을 수 있음 | **팬아웃 모드** (이 문서) — 폭 5-6 |
| 서브에이전트 스폰 불가·제한 (샌드박스·정책·구버전) | **배치 모드** — 기존 Rate-Limit Guard(2-3 동시, SKILL.md) |

판정을 `state.json`에 기록: `"exec_mode": "spawn-fanout" | "agent-batch"`.

## 에이전트 반환 스키마 (AGENT_RETURN_SCHEMA)

모든 리서치 에이전트는 이 스키마의 JSON **하나만** 반환한다. Codex의 `spawn_agent`에는 도구 계층 스키마 강제가 없으므로 프롬프트에 스키마를 싣고, 오케스트레이터가 수거 직후 `merge_agent_returns.py`로 파싱한다 — 파싱 실패 반환은 null 취급(누락 축으로 보고). 이 JSON이 곧 취합 입력이므로 수작업 병합이 사라진다.

```json
{
  "type": "object",
  "required": ["axis", "sources", "claims", "expand_leads", "queries_run", "search_count"],
  "properties": {
    "axis": {"type": "string"},
    "findings_summary": {"type": "string"},
    "sources": {"type": "array", "items": {"type": "object",
      "required": ["url", "title", "domain", "quality_rating"],
      "properties": {"url": {"type": "string"}, "title": {"type": "string"}, "domain": {"type": "string"},
        "date": {"type": "string"}, "valid_at": {"type": "string"}, "type": {"type": "string"},
        "quality_rating": {"type": "string", "enum": ["A", "B", "C", "D", "E"]},
        "access": {"type": "object"}}}},
    "claims": {"type": "array", "items": {"type": "object",
      "required": ["text", "risk", "claim_type", "source_urls"],
      "properties": {"text": {"type": "string"}, "risk": {"type": "string", "enum": ["high", "normal"]},
        "claim_type": {"type": "string", "enum": ["numeric", "legal", "causal", "descriptive", "executable"]},
        "source_urls": {"type": "array", "items": {"type": "string"}},
        "counter_search": {"type": "object", "properties": {"query": {"type": "string"}, "urls": {"type": "array", "items": {"type": "string"}}, "summary": {"type": "string"}}, "required": ["query"]},
        "conflicting": {"type": "boolean"}, "valid_at": {"type": "string"},
        "execution_proof": {"type": "object"}}}},
    "expand_leads": {"type": "array", "items": {"type": "object",
      "required": ["lead", "why", "angle"],
      "properties": {"lead": {"type": "string"}, "why": {"type": "string"}, "angle": {"type": "string"}}}},
    "queries_run": {"type": "array", "items": {"type": "string"}},
    "access_log": {"type": "array", "items": {"type": "object"}},
    "search_count": {"type": "integer"}
  }
}
```

## 스폰 템플릿 (주제·축에 맞춰 즉석 변형)

에이전트 프롬프트에는 기존 계약 전부를 포함한다: 예산 해제문·완료 정의·검색 크래프트(8-10 쿼리)·insane-search 위임(**비동기 기본 — 백그라운드 시작·빠른 수거·반환 전 전량 수거**, tool_strategy.md §비동기 위임)·R8·**검색 예산**(아래)·**AGENT_RETURN_SCHEMA JSON 단일 반환**. `{...}` 슬롯을 채워 사용.

```python
# Phase 2에서 정한 3-6개 축. 축별 프롬프트에 검색 예산 N회 명시.
AXES = [{"key": "...", "prompt": "..."}, ...]
COMMON = "{공통 계약 블록 — 예산 해제·완료 정의·크래프트·위임·R8·검색 예산 · 마지막 줄: 위 AGENT_RETURN_SCHEMA를 따르는 JSON 하나만 출력}"

# Wave 1 — Fanout: 축 전부를 한 턴에 스폰(폭 5-6), 전부 수거
wave1 = [spawn_agent(agent_type="explorer", prompt=f"[axis:{a['key']}]\n{a['prompt']}\n{COMMON}") for a in AXES]
# 각 반환 JSON을 <session>/artifacts/agent_returns/wave1_{key}.json 으로 저장

# 리드 dedup 후 확장 1라운드 (깊이 추가는 오케스트레이터가 재스폰으로)
seen, leads = set(), []
for r in wave1:
    for l in r["expand_leads"]:
        k = l["lead"].lower()[:60]
        if k not in seen:
            seen.add(k); leads.append({**l, "from": r["axis"]})
leads = leads[:6]  # 확장 폭 상한 — 검색 예산과 함께 과확장 방지

# Wave 2 — Expand
wave2 = [spawn_agent(agent_type="explorer",
          prompt=f"확장 조사: {l['lead']}\n이유: {l['why']}\n제안 각도: {l['angle']}\n출처 축: {l['from']}\n{COMMON(검색 예산 4회)}")
         for l in leads]
```

오케스트레이터 후처리 (모든 스폰 수거 후):

```bash
# 1) 반환 JSON들을 배열 하나로 모아 세션에 저장
#    → <session>/artifacts/agent_returns.json  ([wave1..., wave2...])
# 2) 결정론 취합 — sources.jsonl / claim_ledger.jsonl / expansion_log.md / query_log.md 생성
python3 "$PLUGIN_ROOT/skills/insane-research-main/scripts/merge_agent_returns.py" --session "<session>"
# 3) 이후는 기존 파이프라인 그대로: 부족 주장 보강 → validate_ledger.py → 합성 → verify_report.py → eval_report.py
```

## 검색 예산 회계 (⚠️ 필수 — 세션 검색 캡 대응)

호스트 런타임은 세션당 웹검색 호출을 캡할 수 있고(원본 하네스 실측: 세션당 200회, 메인+모든 서브에이전트 합산), 초과분은 에러가 아니라 **조용한 빈 검색**이 된다. Codex의 정확한 상한은 문서화된 값을 확인하지 못했으므로 **200회를 보수적 기본 가정**으로 회계한다(`merge_agent_returns.py`의 `SEARCH_CAP_DEFAULT` 상수가 기준값). 규칙:

1. Phase 2에서 축당 검색 예산을 배분해 각 에이전트 프롬프트에 명시한다 (권장: 1라운드 축당 10회, 확장 에이전트 4회 — 축 5개+확장 6개 ≈ 74회).
2. 에이전트는 `search_count`를 반환하고, merge_agent_returns.py가 합산해 80% 초과 시 경고한다.
3. 진단 규칙: **검색이 갑자기 계속 빈 결과만 주면 캡 도달을 의심**한다 (에러가 아니므로 재시도 금지 — 이미 수집한 정보로 진행하거나 사용자에게 새 세션을 안내).
4. 같은 세션에서 리서치를 연속 실행하면 캡이 누적된다 — 대형 리서치는 새 세션 권장.

## 폭·안전 규칙

- 1라운드 폭 5-6, 확장 라운드 폭 ≤6. **한 번에 10 이상 제출 금지**(실측 검증 범위 밖 + 대형 워크플로 경고 임계).
- 스폰된 에이전트는 세션의 승인 정책·샌드박스를 상속한다 — 장시간 실행 전 웹 접근·셸 승인 설정을 확인(승인 프롬프트가 실행을 멈출 수 있음).
- 실패·파싱 불가 에이전트는 null로 취급한다 — null을 걸러낸 뒤 **누락 축을 반드시 보고**하고, 빠진 축은 배치 모드로 보충한다(조용한 커버리지 구멍 금지).
- 스폰 결과는 세션 스코프다 — 반환 JSON을 즉시 `artifacts/agent_returns/`에 파일로 남겨야 세션이 끊겨도 resume에서 재사용할 수 있다.
