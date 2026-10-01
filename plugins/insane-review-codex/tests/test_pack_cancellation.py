"""Real process/CLI cancellation and publication acknowledgement-loss checks."""
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

import pytest


DRIVER = r'''
import importlib.util,json,os,signal,subprocess,sys
from pathlib import Path
source,root,mode=sys.argv[1:];root=Path(root)
spec=importlib.util.spec_from_file_location('engine',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original_handler=signal.getsignal(signal.SIGTERM)
original_context=m._PACK_OPERATION.get()
target=root/'target';target.mkdir();(target/'README.md').write_text('synthetic')
output=root/'output';output.mkdir()
m.shutil.which=lambda name: sys.executable
real_spawn=m.subprocess.Popen
def spawn(cmd,**kw):
    stage=cmd[cmd.index('-o')+1]
    text='## File: README.md\n'+'x'*2200000
    code='from pathlib import Path; import time; Path('+repr(stage)+').write_text('+repr('## File: README.md\n')+'+"x"*2200000); print("Total Files: 1\\nTotal Tokens: 7",flush=True)'
    if mode in ('running','repeated','spawn'):
        child='import os,signal,time,json;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('+repr(str(root/'descendant.json'))+').write_text(json.dumps({"pid":os.getpid(),"pgid":os.getpgrp(),"sid":os.getsid(0)}));time.sleep(30)'
        code+=';import subprocess,sys; subprocess.Popen([sys.executable,"-c",'+repr(child)+']);time.sleep(30)'
    proc=real_spawn([sys.executable,'-B','-c',code],**kw)
    (root/'spawned.json').write_text(json.dumps({'pid':proc.pid,'pgid':os.getpgid(proc.pid),'sid':os.getsid(proc.pid)}))
    if mode=='spawn': os.kill(os.getpid(),signal.SIGTERM)
    return proc
m.subprocess.Popen=spawn
real_stop=m._stop_pack_group
def stop(proc,**kw):
    (root/'cleanup-started').write_text('ready')
    return real_stop(proc,**kw)
m._stop_pack_group=stop
real_publish=m._publish_pack
def publish(stage,out):
    (root/'destination.json').write_text(json.dumps(str(out)))
    return real_publish(stage,out)
m._publish_pack=publish
real_checkpoint=m._pack_checkpoint
def checkpoint(phase):
    if mode=='handoff' and phase=='operation_return':
        operation=m._PACK_OPERATION.get()
        assert not operation.cancelled
        real_checkpoint(phase)
        assert signal.getsignal(signal.SIGTERM)!=original_handler
        os.kill(os.getpid(),signal.SIGTERM)
        assert operation.cancelled, 'temporary handler did not latch SIGTERM'
        (root/'handoff-latched').write_text(operation.outcome)
        return
    if phase=='copy_after_chunk':
        assert not list(output.glob('pack_*.md')), 'partial final artifact exposed'
        (root/'copy-observed').write_text('final absent')
    if mode=='copy_error' and phase=='copy_after_chunk': raise OSError('synthetic copy error')
    if mode==phase:
        if phase=='publication_gate':
            real_checkpoint(phase)
            os.kill(os.getpid(),signal.SIGTERM)
            return
        os.kill(os.getpid(),signal.SIGTERM)
    real_checkpoint(phase)
m._pack_checkpoint=checkpoint
real_link=m.os.link
def link(src,dst):
    if mode=='collision': Path(dst).write_text('pre-existing collision')
    real_link(src,dst)
    if mode=='after_link': os.kill(os.getpid(),signal.SIGTERM)
    if mode in ('ack_loss','ack_loss_cancel'):
        if mode=='ack_loss_cancel': os.kill(os.getpid(),signal.SIGTERM)
        raise OSError(5,'synthetic acknowledgement loss after real link')
m.os.link=link
def browser(*a):
    (root/'browser-called').write_text('unexpected')
    raise AssertionError('downstream browser forbidden')
m.ensure_browser=browser
sys.argv=['pack_and_ask.py','--target',str(target),'--include','README.md','--out-dir',str(output)]+(['--pack-only'] if mode=='normal' else [])
try:
    m.main()
finally:
    (root/'handler-restored').write_text(str(signal.getsignal(signal.SIGTERM)==original_handler))
    (root/'context-restored').write_text(str(m._PACK_OPERATION.get() is original_context))
'''


def wait_file(path, proc, timeout=8):
    deadline = time.monotonic() + timeout
    while not path.exists() and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), f'missing fixture barrier: {path.name}'


@pytest.mark.parametrize('mode,code,outcome', [
    ('normal', 0, 'COMMITTED'),
    ('running', 143, 'CANCELLED_BEFORE_PUBLICATION'),
    ('repeated', 143, 'CANCELLED_BEFORE_PUBLICATION'),
    ('spawn', 143, 'CANCELLED_BEFORE_PUBLICATION'),
    ('before_validation', 143, 'CANCELLED_BEFORE_PUBLICATION'),
    ('copy_after_chunk', 143, 'CANCELLED_BEFORE_PUBLICATION'),
    ('copy_closed', 143, 'CANCELLED_BEFORE_PUBLICATION'),
    ('publication_gate', 143, 'COMMITTED'),
    ('after_link', 143, 'COMMITTED'),
    ('before_completion_report', 143, 'COMMITTED'),
    ('handoff', 143, 'COMMITTED'),
    ('ack_loss', 2, 'PUBLICATION_OUTCOME_UNKNOWN'),
    ('ack_loss_cancel', 2, 'PUBLICATION_OUTCOME_UNKNOWN'),
    ('collision', 2, 'PUBLICATION_OUTCOME_UNKNOWN'),
    ('copy_error', 1, 'DEFINITELY_NOT_COMMITTED'),
])
def test_actual_cli_publication_outcomes(engine, tmp_path, mode, code, outcome):
    driver = tmp_path / 'driver.py'
    driver.write_text(DRIVER)
    log = tmp_path / 'driver.log'
    with engine.secure_create(log) as stream:
        proc = subprocess.Popen([sys.executable, '-B', str(driver), str(Path(engine.__file__).resolve()), str(tmp_path), mode],
                                stdout=stream, stderr=stream, start_new_session=True)
        try:
            if mode in ('running', 'repeated'):
                wait_file(tmp_path / 'descendant.json', proc)
                os.kill(proc.pid, signal.SIGTERM)
                if mode == 'repeated':
                    wait_file(tmp_path / 'cleanup-started', proc)
                    os.kill(proc.pid, signal.SIGTERM)
                    os.kill(proc.pid, signal.SIGTERM)
            assert proc.wait(timeout=15) == code
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=8)
    text = log.read_text()
    assert (tmp_path / 'handler-restored').read_text() == 'True'
    assert (tmp_path / 'context-restored').read_text() == 'True'
    assert not (tmp_path / 'browser-called').exists()
    if mode == 'handoff':
        assert (tmp_path / 'handoff-latched').read_text() == 'COMMITTED'
    identity = json.loads((tmp_path / 'spawned.json').read_text())
    with pytest.raises(ProcessLookupError):
        os.killpg(identity['pgid'], 0)
    finals = list((tmp_path / 'output').glob('pack_*.md'))
    records = list((tmp_path / 'output').glob('.insane-review-publish-*/*.json'))
    states = [json.loads(p.read_text()) for p in records]
    if outcome == 'COMMITTED' or mode.startswith('ack_loss'):
        assert len(finals) == 1
        expected = hashlib.sha256(('## File: README.md\n' + 'x' * 2200000).encode()).hexdigest()
        assert hashlib.sha256(finals[0].read_bytes()).hexdigest() == expected
        assert any(s['outcome'] == outcome and s['sha256'] == expected for s in states)
        assert stat.S_IMODE(finals[0].stat().st_mode) == 0o600
        if code == 143:
            assert 'pack 발행 완료:' in text and '후속 작업 중단' in text
            assert '패킹 발행 전 취소' not in text
    elif mode == 'collision':
        assert len(finals) == 1 and finals[0].read_text() == 'pre-existing collision'
    else:
        assert not finals
    if code:
        assert outcome in text and '[pack-only] 산출물' not in text
    if code == 2:
        assert '파일 존재 여부 미확정' in text and '패킹 발행 전 취소' not in text
    assert 'downstream browser forbidden' not in text
    # Incomplete temps remain private and never appear as a completed output.
    if (tmp_path / 'copy-observed').exists():
        assert 'complete.tmp' not in text


def test_signal_disposition_restored_on_spawn_failure(engine, tmp_path, monkeypatch):
    prior = signal.getsignal(signal.SIGTERM)
    def fail(*a, **kw):
        raise OSError('synthetic spawn failure')
    monkeypatch.setattr(engine.subprocess, 'Popen', fail)
    with pytest.raises(SystemExit) as exc:
        engine.run_packer(['synthetic'], tmp_path)
    assert exc.value.code == 1 and signal.getsignal(signal.SIGTERM) == prior


@pytest.mark.parametrize('outcome,code', [('COMMITTED', 143), ('PUBLICATION_OUTCOME_UNKNOWN', 2)])
def test_exception_decision_follows_handler_handoff(engine, monkeypatch, capsys, outcome, code):
    prior = signal.getsignal(signal.SIGTERM)
    context = engine._PACK_OPERATION.get()
    real_signal = signal.signal
    handoffs = []
    def handoff(signum, handler):
        if handler == prior:
            operation = engine._PACK_OPERATION.get()
            assert operation is not None and not operation.cancelled
            os.kill(os.getpid(), signal.SIGTERM)
            assert operation.cancelled
            handoffs.append(operation.outcome)
        return real_signal(signum, handler)
    monkeypatch.setattr(engine.signal, 'signal', handoff)
    with pytest.raises(SystemExit) as caught:
        with engine._pack_operation() as operation:
            operation.outcome = outcome
            operation.path = 'synthetic-complete-pack'
            raise SystemExit(17)
    assert caught.value.code == code and handoffs == [outcome]
    assert signal.getsignal(signal.SIGTERM) == prior
    assert engine._PACK_OPERATION.get() is context
    assert outcome in capsys.readouterr().out


def test_nested_pack_context_preserved_on_system_exit(engine):
    previous = engine._PACK_OPERATION.get()
    prior = signal.getsignal(signal.SIGTERM)
    with pytest.raises(SystemExit) as caught:
        with engine._pack_operation() as outer:
            try:
                with engine._pack_operation() as inner:
                    assert inner is outer
                    raise SystemExit(19)
            finally:
                assert engine._PACK_OPERATION.get() is outer
    assert caught.value.code == 19
    assert engine._PACK_OPERATION.get() is previous
    assert signal.getsignal(signal.SIGTERM) == prior
