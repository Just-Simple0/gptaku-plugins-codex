import io
import errno
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import stat
import subprocess
import sys

from bs4 import BeautifulSoup
import pytest


class Element:
    def __init__(self, tag, page):
        self.tag, self.page = tag, page

    def query_selector_all(self, selector):
        return [Element(t, self.page) for t in self.tag.select(selector)]

    def query_selector(self, selector):
        found = self.query_selector_all(selector)
        return found[0] if found else None

    def get_attribute(self, key):
        value = self.tag.attrs.get(key)
        return " ".join(value) if isinstance(value, list) else value

    def inner_text(self):
        return self.tag.get_text()

    def is_visible(self):
        return not self.tag.has_attr("hidden")

    def is_enabled(self):
        return not self.tag.has_attr("disabled")

    def as_element(self):
        return self

    def evaluate_handle(self, script, selector=None):
        import soupsieve
        if "closest" in script:
            for tag in (self.tag, *self.tag.parents):
                if soupsieve.match(selector, tag):
                    return Element(tag, self.page)
            return NullHandle()
        if "DOCUMENT_POSITION_PRECEDING" in script:
            user = self.tag.find_previous(attrs={"data-message-author-role": "user"})
            return Element(user, self.page) if user else NullHandle()
        raise AssertionError(script)

    def evaluate(self, script, *args):
        if "n.contains(b)" in script:
            return args[0].tag in (self.tag, *self.tag.parents)
        if "closest" in script:
            selector = re.search(r"closest\('([^']+)'\)", script).group(1)
            return self.evaluate_handle("closest", selector).as_element() is not None
        raise AssertionError(script)

    def click(self, **kwargs):
        self.page.clicks.append(self.tag.name)
        if self.tag.has_attr("data-reasoning-slider"):
            self.page.slider(2)  # observed pointer midpoint jump
        if self.tag.get("role") == "menuitemradio":
            for tag in self.page.soup.select('[role="menuitemradio"]'):
                if tag.get("data-model-selected") != "true":
                    tag["aria-checked"] = "false"
            self.tag["aria-checked"] = "true"


class NullHandle:
    def as_element(self):
        return None


class Keyboard:
    def __init__(self, page):
        self.page = page

    def press(self, key):
        if key == "Escape":
            return
        if not self.page.focused:
            raise AssertionError("keyboard without focus")
        self.page.keys.append(key)
        slider = self.page.soup.select_one('[role="slider"]')
        self.page.slider(int(slider["aria-valuenow"]) + (1 if key == "ArrowRight" else -1))


class Page(Element):
    def __init__(self, html):
        self.soup = BeautifulSoup(html, "html.parser")
        super().__init__(self.soup, self)
        self.url = "https://chatgpt.com/c/11111111-1111-1111-1111-111111111111"
        self.keyboard = Keyboard(self)
        self.focused = False
        self.clicks = []
        self.keys = []
        self.preserve_trigger_label = False

    def slider(self, value):
        self.soup.select_one('[role="slider"]')["aria-valuenow"] = str(value)
        if not self.preserve_trigger_label:
            label = ["Instant", "Medium", "High", "Extra High", "Pro"][value]
            self.soup.select_one('#trigger').string = label

    def evaluate(self, script, *args):
        if "location.href" in script:
            return self.url
        if "document.activeElement" in script:
            self.focused = True
            return True
        if "vs.map(Number)" in script:
            selector = re.search(r"root.querySelectorAll\('([^']+)'\)", script).group(1)
            scope = args[0].tag if args and args[0] is not None else self.soup
            sliders = scope.select(selector)
            if len(sliders) != 1:
                return None
            values = [sliders[0].get(key) for key in ('aria-valuemin', 'aria-valuenow', 'aria-valuemax')]
            if any(v is None or not re.fullmatch(r'\d+', v) for v in values):
                return None
            low, now, high = map(int, values)
            return [now, high] if low <= now <= high else None
        if "document.scrollingElement" in script:
            return True
        raise AssertionError(script)


def current_html(stop=False, answer=True):
    return '''<div contenteditable="true" role="textbox" data-composer-markdown style="min-height:20px"></div>
    <button id="trigger" aria-label="ChatGPT 모델 선택" data-codex-intelligence-trigger="true">추론 수준</button>
    <div role="menu" data-radix-menu-content aria-labelledby="trigger">
      <div role="menuitem" data-model-picker-view-toggle>6\nPro</div>
      <div role="menuitem" data-reasoning-slider><span role="slider" aria-valuemin="0" aria-valuenow="4" aria-valuemax="4"></span></div>
      <div role="menuitemradio" aria-checked="true" data-model-selected="true">최신</div>
      <div role="menuitemradio" aria-checked="false">GPT-other</div>
    </div><div data-turn-key="u1">
    <div data-chatgpt-search-unit-key="t:0:user" data-content-search-unit-key="t:0:user" data-chatgpt-search-message-ids="u1 u1">question</div>''' + (
        '<div data-chatgpt-search-unit-key="t:2:assistant" data-content-search-unit-key="t:2:assistant" data-chatgpt-search-message-ids="a1 a1">answer</div><button type="button" aria-label="복사"></button>' if answer else "") + '</div>' + (
        '<button type="button" aria-label="중지"></button>' if stop else "")


def manual_binding(page):
    return {"chat_url": page.url, "original_run_bound": False, "harvest_mode": "manual_latest_user", "phase": "MANUAL_SELECT"}


def pack_args(target, output):
    return dict(target=target, include="README.md", ignore=None, compress=False, style="markdown", token_budget=None, out_path=output)


def test_current_identity_terminal_dom_only(engine, monkeypatch):
    page = Page(current_html())
    assert engine.msg_id_set(page) == {"u1", "a1"}
    binding = manual_binding(page)
    assert engine.response_snapshot(page, binding) == (("a1",), "answer")
    assert binding["sent_user_ids"] == ["u1"]
    assert binding["assistant_ids"] == ["a1"]
    assert page.clicks == []


def test_thinking_zero_units_is_streaming(engine):
    page = Page(current_html(stop=True, answer=False))
    assert engine.streaming_state(page) == "streaming"
    assert engine.response_snapshot(page, manual_binding(page)) is None


@pytest.mark.parametrize("html", ["<div></div>", '<button aria-label="Copy"></button><button data-testid="send-button"></button>'])
def test_unsupported_never_terminal(engine, html):
    assert engine.streaming_state(Page(html)) == "unknown"


def test_identity_query_failure_not_empty(engine, monkeypatch):
    page = Page(current_html(answer=False))
    assert engine.msg_id_set(page) == {"u1"}
    monkeypatch.setattr(page, "query_selector_all", lambda selector: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        engine.msg_id_set(page)
    assert engine.streaming_state(page) == "unknown"


@pytest.mark.parametrize("extra", ['<button type="button" aria-label="복사"></button>', '<div data-message-author-role="assistant" data-message-id="a2">other</div>'])
def test_ambiguous_scoped_copy(engine, extra):
    page = Page(current_html())
    page.soup.select_one('[data-turn-key]').append(BeautifulSoup(extra, "html.parser"))
    assert engine.node_copy_button(engine.message_nodes(page, "assistant")[0]) is None


def test_copy_in_code_not_terminal(engine):
    page = Page(current_html())
    button = page.soup.select_one('[aria-label="복사"]')
    button.wrap(page.soup.new_tag("pre"))
    assert engine.response_snapshot(page, manual_binding(page)) is None


def test_other_assistant_same_text_rejected(engine):
    page = Page(current_html())
    binding = manual_binding(page)
    engine.response_snapshot(page, binding)
    page.soup.select_one('[data-chatgpt-search-unit-key$=assistant]')["data-chatgpt-search-message-ids"] = "a2"
    with pytest.raises(RuntimeError, match="assistant 변경"):
        engine.response_snapshot(page, binding)


def test_manual_pending_user_does_not_use_older_reply(engine):
    page = Page(current_html())
    page.soup.append(BeautifulSoup('<div data-turn-key="u2"><div data-chatgpt-search-unit-key="t2:0:user" data-chatgpt-search-message-ids="u2">new</div></div>', "html.parser"))
    binding = manual_binding(page)
    assert engine.response_snapshot(page, binding) is None
    assert binding["sent_user_ids"] == ["u2"]


def test_clipboard_whole_content_comparison(engine):
    expected = "a" * 200
    assert not engine.clipboard_matches("user prompt" + expected, expected)
    assert engine.clipboard_matches(expected, expected)


def test_exact_effort_and_display_provenance(engine, monkeypatch):
    page = Page(current_html())
    monkeypatch.setattr(engine.time, "sleep", lambda n: None)
    ok, proof = engine.select_model(page, "pro")
    assert ok and proof["observed_selection"] == "최신" and proof["actual_display"] == "6\nPro"
    assert proof["effort"] == "pro"
    assert not engine.select_model(page, "pro", require_model="6")[0]
    assert engine.canonical_effort("High") != engine.canonical_effort("Extra High")


def test_neutral_caption_slider_effort_and_success_output_are_sanitized(engine, monkeypatch, capsys):
    page = Page(current_html())
    model_marker = 'PRIVATE_SELECTED_MODEL_MARKER'
    display_marker = 'PRIVATE_MODEL_DISPLAY_MARKER'
    page.soup.select_one('[data-model-selected]').string = model_marker
    page.soup.select_one('[data-model-picker-view-toggle]').string = display_marker
    monkeypatch.setattr(engine.time, "sleep", lambda n: None)
    ok, proof = engine.select_model(page, "pro")
    output = capsys.readouterr()
    assert ok and proof["observed_selection"] == model_marker
    assert proof["actual_display"] == display_marker and proof["effort"] == "pro"
    assert "추론 수준" not in output.out + output.err
    assert model_marker not in output.out + output.err
    assert display_marker not in output.out + output.err
    assert "effort=pro" in output.out
    assert not engine.select_model(page, "pro", require_model="6")[0]


def test_live_picker_shape_slider_overrides_effort_attribute_without_movement(engine, monkeypatch):
    page = Page(current_html())
    trigger = page.soup.select_one('#trigger')
    trigger['data-selected-reasoning-effort'] = 'standard'
    monkeypatch.setattr(engine.time, "sleep", lambda _n: None)

    ok, proof = engine.select_model(page, "pro")

    assert ok
    assert proof["observed_selection"] == "최신"
    assert proof["actual_display"] == "6\nPro"
    assert proof["effort"] == "pro" and proof["slider"] == (0, 4, 4)
    assert trigger.get_text(strip=True) == "추론 수준"
    assert trigger['data-selected-reasoning-effort'] == 'standard'
    assert not page.focused and not page.keys
    assert not engine.select_model(page, "pro", require_model="6")[0]


def test_live_picker_slider_overrides_effort_attribute_after_movement(engine, monkeypatch):
    page = Page(current_html())
    trigger = page.soup.select_one('#trigger')
    trigger['data-selected-reasoning-effort'] = 'standard'
    page.preserve_trigger_label = True
    page.slider(3)
    assert trigger.get_text(strip=True) == "추론 수준"
    monkeypatch.setattr(engine.time, "sleep", lambda _n: None)

    ok, proof = engine.select_model(page, "pro")

    assert ok and proof["effort"] == "pro" and proof["slider"] == (0, 4, 4)
    assert proof["observed_selection"] == "최신" and proof["actual_display"] == "6\nPro"
    assert trigger.get_text(strip=True) == "추론 수준"
    assert trigger['data-selected-reasoning-effort'] == 'standard'
    assert page.focused and page.keys == ["ArrowRight"]
    assert page.soup.select_one('[role="slider"]')['aria-valuenow'] == '4'


def test_focus_keyboard_avoids_pointer_midpoint(engine, monkeypatch):
    page = Page(current_html())
    page.slider(1)
    monkeypatch.setattr(engine.time, "sleep", lambda n: None)
    assert engine.select_model(page, "pro")[0]
    assert page.focused and not page.clicks
    assert page.soup.select_one('[role="slider"]')["aria-valuenow"] == "4"


def test_unlinked_menu_rejected(engine, monkeypatch):
    page = Page(current_html())
    page.soup.select_one('[role="menu"]')["aria-labelledby"] = "wrong"
    monkeypatch.setattr(engine.time, "sleep", lambda n: None)
    assert not engine.select_model(page, "pro")[0]


class Clock:
    def __init__(self):
        self.now = 0.0
    def monotonic(self):
        return self.now
    def sleep(self, duration):
        self.now += duration


def test_continuous_stability_restarts_after_unknown(engine, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(engine, "time", clock)
    monkeypatch.setattr(engine, "MIN_WAIT_SECS", 0)
    monkeypatch.setattr(engine, "detect_quota_block", lambda p: None)
    monkeypatch.setattr(engine, "error_surface_state", lambda p: "clear")
    monkeypatch.setattr(engine, "streaming_state", lambda p: "absent")
    snap = (("a1",), "unchanged")
    monkeypatch.setattr(engine, "response_snapshot", lambda p, b, **kw: None if 5 <= clock.now < 7 else snap)
    saves = []
    result = engine.wait_for_turn_response(None, max_wait=25, binding={"chat_url": "url", "phase": "ASSISTANT_BOUND"},
        save_response=lambda p, b, s: saves.append(clock.now) or True)
    assert result[0] == "ok" and saves == [15.0]


def test_secure_create_rejects_existing_and_symlink(engine, tmp_path):
    path = tmp_path / "log"
    with engine.secure_create(path) as f:
        f.write(b"private")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        engine.secure_create(path)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(OSError):
        engine.secure_create(link)


def test_private_workspace_target_overlap(engine):
    with pytest.raises(RuntimeError):
        engine.private_workspace(Path("/"))


def test_config_failure_prevents_spawn(engine, tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(engine.shutil, "which", lambda n: "npx")
    monkeypatch.setattr(engine, "secure_create", lambda p: (_ for _ in ()).throw(PermissionError(13, "denied")))
    monkeypatch.setattr(engine, "run_packer", lambda *a: pytest.fail("spawn after config failure"))
    with pytest.raises(SystemExit, match="준비 실패"):
        engine.pack_repo(**pack_args(target, tmp_path / "out.md"))


def test_success_secure_stage_then_publish(engine, tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    out = tmp_path / "out.md"
    monkeypatch.setattr(engine.shutil, "which", lambda n: "npx")
    def run(cmd, root):
        config = json.loads(Path(cmd[cmd.index("--config") + 1]).read_text())
        assert config["security"]["enableSecurityCheck"]
        assert not root.resolve().is_relative_to(target.resolve())
        stage = Path(cmd[cmd.index("-o") + 1])
        assert stat.S_IMODE(stage.stat().st_mode) == 0o600
        assert not out.exists()
        stage.write_text("## File: README.md\nhello\n")
        return 0, "Total Tokens: 7\nTotal Files: 1\n"
    monkeypatch.setattr(engine, "run_packer", run)
    assert engine.pack_repo(**pack_args(target, out)) == (out, 7)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_failure_raw_logs_not_printed_or_published(engine, tmp_path, monkeypatch, capsys):
    target = tmp_path / "target"
    target.mkdir()
    out = tmp_path / "out.md"
    monkeypatch.setattr(engine.shutil, "which", lambda n: "npx")
    monkeypatch.setattr(engine, "run_packer", lambda *a: (1, "secret-marker EACCES"))
    with pytest.raises(SystemExit) as exc:
        engine.pack_repo(**pack_args(target, out))
    assert "secret-marker" not in str(exc.value) + capsys.readouterr().out
    assert not out.exists()


def test_real_child_output_stays_private(engine, tmp_path, capsys):
    rc, text = engine.run_packer([sys.executable, "-c", "print('private-marker')"], tmp_path)
    assert rc == 0 and "private-marker" in text
    assert "private-marker" not in capsys.readouterr().out
    assert stat.S_IMODE((tmp_path / "pack.log").stat().st_mode) == 0o600


def test_timeout_reaps_direct_child(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "REPOMIX_TIMEOUT", 0.1)
    with pytest.raises(subprocess.TimeoutExpired):
        engine.run_packer([sys.executable, "-c", "import time; time.sleep(20)"], tmp_path)


def test_windows_runner_preserves_capture_without_posix_args(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "_posix", lambda: False)
    calls = []
    def run(cmd, **kw):
        calls.append(kw)
        return subprocess.CompletedProcess(cmd, 0, "Total Files: 1", "")
    monkeypatch.setattr(engine.subprocess, "run", run)
    assert engine.run_packer(["npx"], tmp_path)[0] == 0
    assert calls[0]["capture_output"] is True
    assert not {"start_new_session", "umask", "creationflags"} & calls[0].keys()
    assert not (tmp_path / "pack.log").exists()


def test_file_lock_concurrency(engine, tmp_path):
    path = tmp_path / "lock"
    with engine.file_lock(path):
        with pytest.raises(BlockingIOError):
            with engine.file_lock(path):
                pass


def test_manifest_atomic_binding_preserved(engine, tmp_path):
    path = tmp_path / "manifest.json"
    state = {"schema_version": 2, "original_run_bound": False, "sent_user_ids": ["u1"], "assistant_ids": ["a1"]}
    engine.persist_binding(path, state)
    assert json.loads(path.read_text()) == state
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_attachment_wrapper_hashes_only_user_body(engine):
    page = Page(current_html())
    user = page.soup.select_one('[data-chatgpt-search-unit-key$=user]')
    del user['data-content-search-unit-key']
    user.clear()
    user.append(BeautifulSoup('<span>source-package.md</span><div data-content-search-unit-key="t:0:user"><div data-user-message-bubble>question</div></div><span>edit action</span>', 'html.parser'))
    binding = {'chat_url': page.url, 'original_run_bound': True, 'baseline_user_ids': [],
               'baseline_assistant_ids': [], 'sent_text_sha256': hashlib.sha256(b'question').hexdigest()}
    assert engine.response_snapshot(page, binding) == (('a1',), 'answer')
    assert len(engine.message_nodes(page, 'user')) == 1


@pytest.mark.parametrize('surface,expected', [
    ('<div role="alert" hidden>error</div>', 'clear'),
    ('<div role="alert"></div>', 'clear'),
    ('<div role="dialog">파일 업로드 완료</div>', 'clear'),
    ('<div role="alert">Something went wrong</div>', 'error'),
    ('<button data-testid="login-button">로그인</button>', 'error'),
])
def test_visible_semantic_error_surfaces(engine, surface, expected):
    page = Page(current_html() + surface)
    assert engine.error_surface_state(page) == expected
    assert (engine.response_snapshot(page, manual_binding(page)) is None) == (expected != 'clear')


def test_error_surface_query_failure_unknown(engine, monkeypatch):
    page = Page(current_html())
    monkeypatch.setattr(page, 'query_selector_all', lambda s: (_ for _ in ()).throw(OSError()))
    assert engine.error_surface_state(page) == 'unknown'


def legacy_html(slider=False):
    return '''<div id="prompt-textarea" contenteditable="true"></div>
    <button id="trigger" class="__composer-pill" aria-haspopup="menu">Pro</button>
    <div role="menu" aria-labelledby="trigger" data-state="open" ''' + ('data-testid="composer-intelligence-picker-content"' if slider else '') + '''>
    <div role="menuitemradio" aria-checked="true" data-model-selected="true">GPT-example</div>
    <div role="menuitemradio" aria-checked="true">Pro</div>''' + (
        '<div role="menuitem" data-model-reasoning-effort-slider><span role="slider" aria-valuemin="0" aria-valuenow="4" aria-valuemax="4"></span></div>' if slider else '') + '''</div>
    <section data-turn="user"><div data-message-author-role="user" data-message-id="u1">question</div></section>
    <section data-turn="assistant"><div data-message-author-role="assistant" data-message-id="a1">answer</div><button data-testid="copy-turn-action-button"></button></section>'''


@pytest.mark.parametrize('slider', [False, True])
def test_legacy_radio_and_slider_success(engine, monkeypatch, slider):
    page = Page(legacy_html(slider))
    monkeypatch.setattr(engine.time, 'sleep', lambda n: None)
    assert engine.select_model(page, 'pro', require_model='GPT-example')[0]
    assert engine.response_snapshot(page, manual_binding(page)) == (('a1',), 'answer')


@pytest.mark.parametrize('slider', [False, True])
def test_legacy_unchecked_model_rejected(engine, monkeypatch, slider):
    page = Page(legacy_html(slider))
    page.soup.select_one('[data-model-selected]')['aria-checked'] = 'false'
    monkeypatch.setattr(engine.time, 'sleep', lambda n: None)
    assert not engine.select_model(page, 'pro')[0]


def test_launcher_rc_zero_does_not_preempt_cdp_ready(engine, tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(engine, 'time', clock)
    monkeypatch.setattr(engine, 'profile_dir_for', lambda n: tmp_path / 'profile')
    monkeypatch.setattr(engine, 'get_launch_mode', lambda: 'background')
    monkeypatch.setattr(engine, 'host_os', lambda: 'mac')
    monkeypatch.setattr(engine, '_save_config_key', lambda *a: None)
    class Launcher:
        def poll(self):
            return 0
    monkeypatch.setattr(engine.subprocess, 'Popen', lambda *a, **kw: Launcher())
    monkeypatch.setattr(engine, 'is_port_open', lambda: clock.now >= 3)
    monkeypatch.setattr(engine, 'cdp_browser_ok', lambda: True)
    monkeypatch.setattr(engine, 'endpoint_identity', lambda *a: {'verified': True})
    assert engine.launch_browser_exe('/fake/browser', 'fake')
    assert clock.now >= 3


def test_endpoint_ownership_checks_exact_profile(engine, tmp_path, monkeypatch):
    exe = str(tmp_path / 'browser')
    profile = (tmp_path / 'profile').resolve()
    def run(cmd, **kw):
        if cmd[0] == 'lsof':
            output = f'p42\nn127.0.0.1:{engine.CDP_PORT}\n'
        else:
            output = {'args=': f'{exe} --user-data-dir={profile} --no-first-run', 'comm=': exe, 'lstart=': 'start1'}[cmd[-1]]
        return subprocess.CompletedProcess(cmd, 0, output, '')
    monkeypatch.setattr(engine.subprocess, 'run', run)
    monkeypatch.setattr(engine.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(json.dumps({'webSocketDebuggerUrl': f'ws://127.0.0.1:{engine.CDP_PORT}/devtools/browser/id'}).encode()))
    assert engine.endpoint_identity(exe, profile)['pid'] == 42
    with pytest.raises(RuntimeError, match='프로필'):
        engine.endpoint_identity(exe, tmp_path / 'different')


@pytest.mark.parametrize('deny_probes', [False, True])
def test_real_descendant_timeout_cleanup(engine, tmp_path, monkeypatch, deny_probes):
    monkeypatch.setattr(engine, 'REPOMIX_TIMEOUT', 0.3)
    real_killpg, real_popen = os.killpg, subprocess.Popen
    procs, signals, denied = [], [], []
    def spawn(*args, **kwargs):
        assert kwargs['start_new_session'] is True
        proc = real_popen(*args, **kwargs)
        procs.append(proc)
        return proc
    def killpg(pgid, sig):
        assert procs and pgid == procs[0].pid
        if sig:
            signals.append(sig)
        elif deny_probes and signal.SIGKILL not in signals:
            denied.append(pgid)
            raise PermissionError(errno.EPERM, 'synthetic signal-0 denial')
        return real_killpg(pgid, sig)
    monkeypatch.setattr(engine.subprocess, 'Popen', spawn)
    monkeypatch.setattr(engine.os, 'killpg', killpg)
    child = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(20)"
    parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",' + repr(child) + ']); time.sleep(20)'
    with pytest.raises(subprocess.TimeoutExpired):
        engine.run_packer([sys.executable, '-c', parent], tmp_path)
    assert procs[0].returncode is not None  # direct child was reaped
    if deny_probes:
        assert denied and signals == [signal.SIGTERM, signal.SIGKILL]
    with pytest.raises(ProcessLookupError):
        real_killpg(procs[0].pid, 0)


@pytest.mark.parametrize('mode', ['url', 'legacy', 'manual_v2', 'run_v2'])
@pytest.mark.parametrize('outcome', ['ok', 'error', 'quota'])
def test_manual_cli_saves_bound_dom_result(engine, tmp_path, monkeypatch, mode, outcome):
    from types import SimpleNamespace
    page = Page(current_html())
    page.goto = lambda *a, **k: None
    page.close = lambda: None
    opened = []
    ctx = SimpleNamespace(new_page=lambda: opened.append(1) or page)
    class PW:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
    monkeypatch.setattr(engine, 'sync_playwright', PW)
    monkeypatch.setattr(engine, 'connect_cdp', lambda p: object())
    monkeypatch.setattr(engine, 'pick_context', lambda b: ctx)
    monkeypatch.setattr(engine, 'ensure_browser', lambda a: True)
    monkeypatch.setattr(engine, 'resolve_browser', lambda a: ('mock', '/mock'))
    monkeypatch.setattr(engine, '_guard_dialogs', lambda *a: None)
    monkeypatch.setattr(engine, 'hide_browser_if_background', lambda: None)
    monkeypatch.setattr(engine, 'login_state', lambda p: 'ok')
    clock = Clock()
    monkeypatch.setattr(engine, 'time', clock)
    if outcome == 'error':
        monkeypatch.setattr(engine, 'error_surface_state', lambda p: 'error' if clock.now >= 6 else 'clear')
    if outcome == 'quota':
        monkeypatch.setattr(engine, 'detect_quota_block', lambda p: clock.now >= 6)
    source = page.url
    if mode != 'url':
        source = str(tmp_path / 'input.json')
        data = {'chat_url': page.url, 'run_tag': 'old'}
        if mode.endswith('v2'):
            data.update(schema_version=2, original_run_bound=mode == 'run_v2', sent_user_ids=['u1'], assistant_ids=['a1'],
                        baseline_user_ids=[], baseline_assistant_ids=[], phase='ASSISTANT_BOUND')
        Path(source).write_text(json.dumps(data))
    monkeypatch.setattr(sys, 'argv', ['pack_and_ask.py', '--harvest', source, '--out-dir', str(tmp_path), '--max-wait', '60'])
    if outcome != 'ok':
        with pytest.raises(SystemExit) as exc:
            engine.main()
        manifest = list(tmp_path.glob('manifest_*.json'))[0]
        assert f"--harvest '{manifest}'" in str(exc.value)
        assert '--harvest' in str(exc.value) and f"--harvest '{page.url}'" not in str(exc.value)
        assert len(opened) == 1 and not list(tmp_path.glob('response_*.md'))
        if outcome == 'error':
            assert json.loads(manifest.read_text())['last_wait_status'] == 'visible_error'
        return
    engine.main()
    manifests = list(tmp_path.glob('manifest_*.json'))
    data = json.loads(manifests[0].read_text())
    assert data['phase'] == 'COMPLETE' and data['original_run_bound'] is (mode == 'run_v2')
    assert data['sent_user_ids'] == ['u1'] and data['assistant_ids'] == ['a1']
    assert list(tmp_path.glob('response_*.md'))[0].read_text().endswith('answer\n')


def test_explicit_force_flag_records_forced_state(engine, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(engine, 'time', clock)
    monkeypatch.setattr(engine, 'MIN_WAIT_SECS', 0)
    monkeypatch.setattr(engine, 'detect_quota_block', lambda p: None)
    monkeypatch.setattr(engine, 'error_surface_state', lambda p: 'clear')
    monkeypatch.setattr(engine, 'streaming_state', lambda p: 'streaming')
    monkeypatch.setattr(engine, 'response_snapshot', lambda p, b, **kw: None)
    clicks = []
    monkeypatch.setattr(engine, 'click_answer_now', lambda p: clicks.append(clock.now) or True)
    monkeypatch.setattr(engine, 'bound_user_is_latest', lambda p, b: True)
    binding = {'chat_url': 'url', 'sent_user_ids': ['u1'], 'phase': 'USER_BOUND'}
    assert engine.wait_for_turn_response(None, max_wait=3, force_after=1, binding=binding)[0] == 'timeout'
    assert clicks == [1.0] and binding['forced_answer'] is True
    clicks.clear()
    engine.wait_for_turn_response(None, max_wait=3, binding={'chat_url': 'url', 'sent_user_ids': ['u1']})
    assert clicks == []


def test_presave_change_restarts_wait(engine, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(engine, 'time', clock)
    monkeypatch.setattr(engine, 'MIN_WAIT_SECS', 0)
    monkeypatch.setattr(engine, 'detect_quota_block', lambda p: None)
    monkeypatch.setattr(engine, 'error_surface_state', lambda p: 'clear')
    monkeypatch.setattr(engine, 'streaming_state', lambda p: 'absent')
    monkeypatch.setattr(engine, 'response_snapshot', lambda p, b, **kw: (('a1',), 'answer'))
    saves = []
    def save(*args):
        saves.append(clock.now)
        return len(saves) == 2
    assert engine.wait_for_turn_response(None, max_wait=30, binding={'chat_url': 'url'}, save_response=save)[0] == 'ok'
    assert saves == [8.0, 16.0]


def test_conflicting_effort_label_fails_without_movement(engine, monkeypatch, capsys):
    page = Page(current_html())
    page.soup.select_one('#trigger').string = 'High'
    monkeypatch.setattr(engine, 'time', Clock())
    ok, proof = engine.select_model(page, 'pro')
    output = capsys.readouterr()
    assert not ok and proof is None
    assert page.soup.select_one('[role="slider"]')['aria-valuenow'] == '4'
    assert not page.keys and not page.focused
    assert 'slider current=4/4' in output.out
    assert 'effort=pro' in output.out and 'label effort=high' in output.out


def test_visible_effort_conflict_at_three_blocks_before_slider_movement(engine, monkeypatch, capsys):
    page = Page(current_html())
    trigger = page.soup.select_one('#trigger')
    trigger['data-selected-reasoning-effort'] = 'standard'
    page.slider(3)
    trigger.string = 'High'
    assert trigger.get_text(strip=True) == 'High'
    monkeypatch.setattr(engine, 'time', Clock())

    ok, proof = engine.select_model(page, 'pro')
    output = capsys.readouterr()

    assert not ok and proof is None
    assert page.soup.select_one('[role="slider"]')['aria-valuenow'] == '3'
    assert not page.keys and not page.focused
    assert 'slider current=3/4' in output.out
    assert 'effort=extra_high' in output.out and 'label effort=high' in output.out


@pytest.mark.parametrize('current', [1, 3])
def test_pro_unavailable_max_three_never_moves(engine, monkeypatch, capsys, current):
    page = Page(current_html())
    slider = page.soup.select_one('[role="slider"]')
    slider['aria-valuenow'] = str(current)
    slider['aria-valuemax'] = '3'
    page.soup.select_one('#trigger').string = '추론 수준'
    monkeypatch.setattr(engine.time, 'sleep', Clock().sleep)
    ok, proof = engine.select_model(page, 'pro')
    output = capsys.readouterr()
    assert not ok and proof is None
    assert slider['aria-valuenow'] == str(current)
    assert not page.keys and not page.focused
    assert f'slider max=3' in output.out
    assert f'current effort={engine.EFFORT_BY_INDEX[current]}' in output.out


def test_after_model_is_not_validated_from_before(engine, monkeypatch):
    page = Page(current_html())
    monkeypatch.setattr(engine, 'time', Clock())
    def move(p, idx, scope=None):
        page.soup.select_one('[data-model-selected]').string = 'different model'
        return True
    monkeypatch.setattr(engine, '_set_effort_slider', move)
    assert not engine.select_model(page, 'pro')[0]


def test_pipe_progress_is_flushed_before_child_finishes(engine, tmp_path):
    import selectors
    source = Path(engine.__file__)
    script = ('import importlib.util; from pathlib import Path; '
              f's=importlib.util.spec_from_file_location("engine",{str(source)!r}); '
              'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
              f'm.run_packer([{sys.executable!r},"-c","import time; time.sleep(0.5)"],Path({str(tmp_path)!r}))')
    proc = subprocess.Popen([sys.executable, '-B', '-c', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=3)
            assert '패킹 실행 중'.encode() in proc.stdout.readline()
            assert proc.poll() is None
        assert proc.wait(timeout=5) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()
        proc.stderr.close()


def test_invalid_v2_never_downgrades_to_manual(engine, tmp_path, monkeypatch):
    source = tmp_path / 'invalid.json'
    source.write_text(json.dumps({'schema_version': 2, 'chat_url': Page(current_html()).url}))
    monkeypatch.setattr(sys, 'argv', ['pack_and_ask.py', '--harvest', str(source), '--out-dir', str(tmp_path)])
    monkeypatch.setattr(engine, 'ensure_browser', lambda a: pytest.fail('invalid v2 must stop before browser'))
    with pytest.raises(SystemExit, match='manifest 파싱 실패'):
        engine.main()


@pytest.mark.parametrize('failure', ['pre_send', 'send_unknown', 'visible_error', 'url_timeout'])
def test_cli_failure_phase_no_retransmission(engine, tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    page = Page(current_html())
    page.goto = lambda *a, **k: None
    page.close = lambda: None
    class PW:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
    monkeypatch.setattr(engine, 'sync_playwright', PW)
    monkeypatch.setattr(engine, 'connect_cdp', lambda p: object())
    monkeypatch.setattr(engine, 'pick_context', lambda b: SimpleNamespace(new_page=lambda: page))
    monkeypatch.setattr(engine, 'ensure_browser', lambda a: True)
    monkeypatch.setattr(engine, 'resolve_browser', lambda a: ('mock', '/mock'))
    monkeypatch.setattr(engine, '_guard_dialogs', lambda *a: None)
    monkeypatch.setattr(engine, 'hide_browser_if_background', lambda: None)
    monkeypatch.setattr(engine, 'login_state', lambda p: 'no' if failure == 'pre_send' else 'ok')
    monkeypatch.setattr(engine, 'ensure_chat_mode', lambda p: (True, 'chat'))
    monkeypatch.setattr(engine, 'put_text', lambda *a: None)
    monkeypatch.setattr(engine, 'composer_has_prompt', lambda *a: True)
    monkeypatch.setattr(engine, 'time', Clock())
    clicks = []
    def click(p, *args):
        clicks.append(1)
        if failure == 'send_unknown':
            raise OSError('delivery unknown')
        if failure == 'url_timeout':
            p.url = 'https://chatgpt.com/'
        if failure == 'visible_error':
            p.soup.append(BeautifulSoup('<div role="alert">Something went wrong private-marker</div>', 'html.parser'))
    monkeypatch.setattr(engine, 'click_send', click)
    monkeypatch.setattr(sys, 'argv', ['pack_and_ask.py', '--no-project', '--prompt', 'question', '--retries', '3', '--out-dir', str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        engine.main()
    assert len(clicks) == (0 if failure == 'pre_send' else 1)
    expected = {'pre_send': '전송 전 실패', 'send_unknown': '전송 시도 결과', 'url_timeout': '전송 시도 결과', 'visible_error': '가시적 오류'}
    assert expected[failure] in str(exc.value)
    assert 'private-marker' not in str(exc.value)
    assert not list(tmp_path.glob('response_*.md'))


def test_probe_ownership_does_not_persist_profile_owner(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(engine, 'BROWSER_PROFILE_DIR', tmp_path / 'profile')
    monkeypatch.setattr(engine, '_load_config', lambda: {})
    monkeypatch.setattr(engine, '_save_config_key', lambda *a: pytest.fail('read-only probe must not save config'))
    assert engine.profile_dir_for('browser', persist_owner=False) == tmp_path / 'profile'


def test_cdp_connect_rechecks_endpoint_before_and_after(engine, tmp_path, monkeypatch):
    from types import SimpleNamespace
    expected = {'executable': '/mock', 'profile': str(tmp_path), 'pid': 1}
    monkeypatch.setattr(engine, '_NATIVE_IDENTITY', expected)
    states = iter([expected, dict(expected, pid=2)])
    monkeypatch.setattr(engine, 'endpoint_identity', lambda *a: next(states))
    calls = []
    pw = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=lambda url: calls.append(url) or object()))
    with pytest.raises(RuntimeError, match='연결 후'):
        engine.connect_cdp(pw)
    assert len(calls) == 1


def test_current_marker_never_falls_back_to_legacy_identity(engine):
    page = Page(legacy_html() + '<div data-composer-markdown></div>')
    assert engine.ui_adapter(page) == 'current'
    assert engine.message_nodes(page, 'assistant') == []


def test_windows_native_keeps_explicit_unverified_status(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(engine, '_posix', lambda: False)
    monkeypatch.setattr(engine.subprocess, 'run', lambda *a, **k: pytest.fail('no POSIX ownership probe on Windows'))
    assert engine.endpoint_identity('browser.exe', tmp_path)['ownership_verification'] == 'legacy_unverified'


def test_timeout_never_publishes_partial_pack(engine, tmp_path, monkeypatch):
    target = tmp_path / 'target'
    target.mkdir()
    output = tmp_path / 'out.md'
    monkeypatch.setattr(engine.shutil, 'which', lambda n: 'npx')
    def timeout(cmd, root):
        Path(cmd[cmd.index('-o') + 1]).write_text('partial')
        raise subprocess.TimeoutExpired(cmd, 1)
    monkeypatch.setattr(engine, 'run_packer', timeout)
    with pytest.raises(SystemExit, match='타임아웃'):
        engine.pack_repo(**pack_args(target, output))
    assert not output.exists()


def test_legacy_slider_outside_picker_moves_using_actual_selector(engine, monkeypatch):
    page = Page(legacy_html(True).replace('data-testid="composer-intelligence-picker-content"', ''))
    page.slider(2)
    monkeypatch.setattr(engine, 'time', Clock())
    menu = engine.selection_state(page)['menu']
    assert engine._slider_value(page, menu) == (0, 2, 4)
    assert engine._set_effort_slider(page, 4, menu)
    assert engine._slider_value(page, menu) == (0, 4, 4)
    assert page.focused and not page.clicks


@pytest.mark.parametrize('kind', ['unrelated', 'duplicate', 'invalid'])
def test_slider_selector_and_values_fail_closed(engine, kind):
    page = Page(current_html())
    if kind == 'unrelated':
        del page.soup.select_one('[data-reasoning-slider]')['data-reasoning-slider']
    elif kind == 'duplicate':
        page.soup.select_one('[data-reasoning-slider]').append(BeautifulSoup('<span role="slider"></span>', 'html.parser'))
    else:
        page.soup.select_one('[role="slider"]')['aria-valuemin'] = '5'
    with pytest.raises(RuntimeError):
        engine.selection_state(page)


@pytest.mark.parametrize('max_wait,expected', [(3600, 90), (2, 2)])
def test_url_capture_independent_deadline_and_progress(engine, monkeypatch, capsys, max_wait, expected):
    clock = Clock()
    monkeypatch.setattr(engine, 'time', clock)
    page = Page(current_html())
    page.url = 'https://chatgpt.com/'
    binding = {'phase': 'SEND_PENDING'}
    assert engine.wait_for_turn_response(page, max_wait=max_wait, binding=binding)[0] == 'sent_unknown_location'
    assert clock.now == expected
    output = capsys.readouterr().out
    assert '0s | phase=WAIT_CONVERSATION_URL' in output
    if expected == 90:
        assert '15s | phase=WAIT_CONVERSATION_URL' in output
        assert binding['last_wait_status'] == 'sent_unknown_location'


def test_delayed_url_binds_and_completes_without_resend(engine, monkeypatch):
    clock = Clock()
    page = Page(current_html())
    monkeypatch.setattr(engine, 'time', clock)
    monkeypatch.setattr(engine, 'MIN_WAIT_SECS', 0)
    monkeypatch.setattr(engine, 'current_url', lambda p: p.url if clock.now >= 2 else 'https://chatgpt.com/')
    binding = manual_binding(page)
    binding.pop('chat_url')
    bound = []
    assert engine.wait_for_turn_response(page, max_wait=30, binding=binding, on_bound=bound.append)[0] == 'ok'
    assert bound == [page.url] and clock.now == 10 and not page.clicks


@pytest.mark.parametrize('state,expected_time,status', [('persistent', 3, 'error'), ('transient', 15, 'ok'), ('unknown', 15, 'ok'), ('unknown_forever', 25, 'timeout')])
def test_error_grace_and_unknown_stability(engine, monkeypatch, capsys, state, expected_time, status):
    clock = Clock()
    page = Page(current_html())
    monkeypatch.setattr(engine, 'time', clock)
    monkeypatch.setattr(engine, 'MIN_WAIT_SECS', 0)
    def surface(p):
        if state == 'persistent':
            return 'error'
        if state == 'unknown_forever':
            return 'unknown'
        return ('error' if state == 'transient' else 'unknown') if 5 <= clock.now < 7 else 'clear'
    monkeypatch.setattr(engine, 'error_surface_state', surface)
    saved = []
    result = engine.wait_for_turn_response(page, max_wait=25, binding=manual_binding(page),
        save_response=lambda *a: saved.append(clock.now) or True)
    assert result[0] == status and clock.now == expected_time
    assert saved == ([expected_time] if status == 'ok' else [])
    assert not page.clicks


def test_error_banner_raw_text_never_printed(engine, monkeypatch, capsys):
    page = Page(current_html() + '<div role="alert">Something went wrong private-banner-marker</div>')
    monkeypatch.setattr(engine, 'time', Clock())
    assert engine.wait_for_turn_response(page, max_wait=30, binding=manual_binding(page))[0] == 'error'
    assert 'private-banner-marker' not in capsys.readouterr().out


def test_offline_cache_diagnostic_precedes_registry(engine):
    assert '캐시 누락' in engine.safe_child_summary('npm ENOTCACHED request https://registry.npmjs.org/private-marker')
    assert 'private-marker' not in engine.safe_child_summary('npm ENOTCACHED private-marker')


def test_recovery_hint_requires_user_binding(engine, tmp_path):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{}')
    binding = {'chat_url': Page(current_html()).url, 'schema_version': 2, 'original_run_bound': False, 'assistant_ids': []}
    assert '수동 latest-user' in engine.recovery_hint(binding, manifest)
    binding['sent_user_ids'] = ['u1']
    manifest.write_text(json.dumps(binding))
    assert f"--harvest '{manifest}'" in engine.recovery_hint(binding, manifest)


@pytest.mark.parametrize('raises', [False, True])
def test_actual_click_send_dispatches_once(engine, monkeypatch, raises):
    from types import SimpleNamespace
    dispatches, trials = [], []
    def dispatch(*args):
        dispatches.append(1)
        if raises:
            raise OSError('dispatch happened; acknowledgement lost')
        return True
    button = SimpleNamespace(is_visible=lambda: True, is_enabled=lambda: True,
                             click=lambda **kw: trials.append(kw))
    page = SimpleNamespace(query_selector_all=lambda s: [button])
    monkeypatch.setattr(engine, 'ui_adapter', lambda p: 'fixture')
    monkeypatch.setattr(engine, '_DISPATCH_ADAPTERS', {'fixture': {'click': True, 'evidence': 'unit fixture only'}})
    monkeypatch.setattr(engine, '_guarded_dispatch', dispatch)
    if raises:
        with pytest.raises(OSError):
            engine.click_send(page, 'prompt', object())
    else:
        assert engine.click_send(page, 'prompt', object())
    assert dispatches == [1] and trials == [{'trial': True}]


def test_click_send_read_failure_never_authorizes_enter(engine, monkeypatch):
    from types import SimpleNamespace
    def query(selector):
        raise OSError('read failure')
    page = SimpleNamespace(query_selector_all=query)
    monkeypatch.setattr(engine, 'ui_adapter', lambda p: 'fixture')
    monkeypatch.setattr(engine, '_DISPATCH_ADAPTERS', {'fixture': {'click': True, 'enter': True, 'evidence': 'fixture'}})
    monkeypatch.setattr(engine, '_guarded_dispatch', lambda *a: pytest.fail('dispatch after read failure'))
    with pytest.raises(OSError):
        engine.click_send(page, 'prompt', object())


@pytest.mark.parametrize('surface', ['quota', 'error', 'login'])
def test_unbound_url_checks_error_and_quota(engine, monkeypatch, surface):
    clock = Clock()
    page = Page(current_html())
    page.url = 'https://chatgpt.com/'
    if surface == 'error':
        page.soup.append(BeautifulSoup('<div role="alert">Something went wrong</div>', 'html.parser'))
    if surface == 'login':
        page.soup.append(BeautifulSoup('<button data-testid="login-button">Log in</button>', 'html.parser'))
    if surface == 'quota':
        monkeypatch.setattr(engine, 'detect_quota_block', lambda p: True)
    monkeypatch.setattr(engine, 'time', clock)
    binding, persisted = {'phase': 'SEND_PENDING'}, []
    result = engine.wait_for_turn_response(page, max_wait=120, binding=binding, persist=lambda b: persisted.append(dict(b)))
    assert result[0] == ('quota' if surface == 'quota' else 'error')
    assert clock.now <= 3 and persisted and not page.clicks


@pytest.mark.parametrize('shared', ['both', 'profile', 'endpoint'])
def test_native_lock_across_real_process_tmpdirs(engine, tmp_path, shared):
    import selectors
    first_tmp, second_tmp = tmp_path / 'tmp-a', tmp_path / 'tmp-b'
    first_tmp.mkdir()
    second_tmp.mkdir()
    profile = tmp_path / 'profile'
    endpoint = 'http://127.0.0.1/lock-test-' + tmp_path.name
    child = '''import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('ir',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.CDP_URL=sys.argv[3]
try:
    with m.native_guard(Path(sys.argv[2])):
        print('ACQUIRED',flush=True)
        if sys.argv[4]=='hold': sys.stdin.readline()
except BlockingIOError:
    print('REJECTED',flush=True)
'''
    args = [sys.executable, '-B', '-c', child, str(Path(engine.__file__).resolve())]
    first_env = dict(os.environ, TMPDIR=str(first_tmp))
    second_env = dict(os.environ, TMPDIR=str(second_tmp))
    proc = subprocess.Popen(args + [str(profile), endpoint, 'hold'], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=first_env)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=10)
            assert proc.stdout.readline().strip() == b'ACQUIRED'
        second_profile = str(profile if shared != 'endpoint' else tmp_path / 'other-profile')
        second_endpoint = endpoint if shared != 'profile' else endpoint + '-other'
        result = subprocess.run(args + [second_profile, second_endpoint, 'once'], env=second_env,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0 and result.stdout.strip() == 'REJECTED'
    finally:
        proc.communicate(b'release\n', timeout=10)
    result = subprocess.run(args + [str(profile), endpoint, 'once'], env=second_env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout.strip() == 'ACQUIRED'


@pytest.mark.parametrize('error,expected', [(errno.EPERM, True), (errno.ESRCH, False)])
def test_group_probe_errno_classification(engine, monkeypatch, error, expected):
    def probe(pid, sig):
        assert sig == 0
        raise OSError(error, 'synthetic probe')
    monkeypatch.setattr(engine.os, 'killpg', probe)
    assert engine._group_alive(424242) is expected


def test_unexpected_group_probe_error_is_not_absence(engine, monkeypatch):
    def probe(pid, sig):
        raise OSError(errno.EIO, 'synthetic probe')
    monkeypatch.setattr(engine.os, 'killpg', probe)
    with pytest.raises(OSError):
        engine._group_alive(424242)


@pytest.mark.parametrize('denial', ['probe', 'term', 'all_signals'])
def test_owned_group_permission_denial_reaches_kill(engine, monkeypatch, denial):
    from types import SimpleNamespace
    clock = Clock()
    monkeypatch.setattr(engine, 'time', clock)
    signals, waits, polls = [], [], []
    proc = SimpleNamespace(pid=424242, poll=lambda: polls.append(1) or -9,
                           wait=lambda timeout: waits.append(timeout) or -9)
    def killpg(pgid, sig):
        assert pgid == proc.pid
        if sig:
            signals.append(sig)
            if denial == 'all_signals' or (denial == 'term' and sig == signal.SIGTERM):
                raise PermissionError(errno.EPERM, 'synthetic signal denial')
        elif denial == 'all_signals' or signal.SIGKILL not in signals:
            raise PermissionError(errno.EPERM, 'synthetic probe denial')
        else:
            raise ProcessLookupError(errno.ESRCH, 'gone')
    monkeypatch.setattr(engine.os, 'killpg', killpg)
    if denial == 'all_signals':
        with pytest.raises(RuntimeError, match='그룹 신호 권한 거부'):
            engine._stop_pack_group(proc, owned_pgid=proc.pid)
        assert not waits and 4 <= clock.now < 4.2
    else:
        engine._stop_pack_group(proc, owned_pgid=proc.pid)
        assert len(waits) == 1 and 0 <= waits[0] <= 2
    assert signals == [signal.SIGTERM, signal.SIGKILL] and polls


@pytest.mark.parametrize('invalid', ['mismatch', 'zero', 'current_group'])
def test_cleanup_refuses_unowned_group(engine, monkeypatch, invalid):
    from types import SimpleNamespace
    pid = os.getpgrp() if invalid == 'current_group' else 0 if invalid == 'zero' else 424242
    group = pid + 1 if invalid == 'mismatch' else pid
    monkeypatch.setattr(engine.os, 'killpg', lambda *a: pytest.fail('unauthorized group signal'))
    with pytest.raises(RuntimeError, match='소유 session/group 불일치'):
        engine._stop_pack_group(SimpleNamespace(pid=pid), owned_pgid=group)


def test_denied_cleanup_never_publishes_pack(engine, tmp_path, monkeypatch):
    from types import SimpleNamespace
    target = tmp_path / 'target'
    target.mkdir()
    output = tmp_path / 'out.md'
    signals = []
    monkeypatch.setattr(engine, 'time', Clock())
    monkeypatch.setattr(engine, 'REPOMIX_TIMEOUT', 0.3)
    monkeypatch.setattr(engine.shutil, 'which', lambda n: 'npx')
    def spawn(cmd, **kwargs):
        assert kwargs['start_new_session'] is True
        Path(cmd[cmd.index('-o') + 1]).write_text('partial synthetic output')
        return SimpleNamespace(pid=424242, poll=lambda: None,
                               wait=lambda **kw: pytest.fail('unbounded/false-success wait'))
    def killpg(pgid, sig):
        assert pgid == 424242
        if sig:
            signals.append(sig)
        raise PermissionError(errno.EPERM, 'synthetic permission denial')
    monkeypatch.setattr(engine.subprocess, 'Popen', spawn)
    monkeypatch.setattr(engine.os, 'killpg', killpg)
    with pytest.raises(SystemExit, match='실행/종료 확인 실패'):
        engine.pack_repo(**pack_args(target, output))
    assert signals == [signal.SIGTERM, signal.SIGKILL] and not output.exists()
