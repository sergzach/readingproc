"""
A testing executor with pytest.
"""

import pytest
import os
import sys
from contextlib import contextmanager
import subprocess
import select
from time import time, sleep
from readingproc import ReadingProc, ChunkTimeout, TotalTimeout, ProcessIsNotStartedError
from readingproc.unblock_read import set_read_flags, get_read_flags, unblock_read


_CUR_PATH = os.path.dirname(os.path.realpath(__file__))


def _check_fragment(lines, fragment):
    content = '\n'.join(lines)
    assert fragment in content


def _get_lines(proc, is_err=False):
    lines = []
    for data in proc.iter_run():        
        content = data.stdout
        if is_err:
            content += data.stderr
        lines.append(content.decode())
    return lines


def _get_test_script_path(name):
    return os.path.join(_CUR_PATH, 'test_scripts/{}'.format(name))


def _run_script(name, stdin_terminal=False):
    path = _get_test_script_path(name)

    proc = ReadingProc('python {}'.format(path), stdin_terminal=stdin_terminal)
    proc.start()

    return proc


@pytest.mark.common_test
def test_common():
    proc = ReadingProc(['ls', _CUR_PATH], shell=False)
    proc.start()    
    lines = _get_lines(proc)

    _check_fragment(lines, 'readingproc')
    _check_fragment(lines, 'test.py')

    prev_time = time()

    proc = ReadingProc('sleep 3')
    proc.start()
    lines = _get_lines(proc)

    assert time() - prev_time >= 3.0
    assert len(lines) == 0

    hello_world = 'Hello_world!'

    proc = ReadingProc('echo {}'.format(hello_world))
    proc.start()
    lines = _get_lines(proc, True)

    _check_fragment(lines, hello_world)


@pytest.fixture
def timeout_proc():
    proc = ReadingProc('sleep 10 && echo "success"')        
    proc.start()
    return proc


@pytest.mark.timeouts_test
@pytest.mark.parametrize( \
    'chunk_timeout,total_timeout',
    [
        (5.0, None),
        (9.0, None),        
        (5.0, 6.0)
    ]
)
def test_timeouts_chunk_timeout(timeout_proc, chunk_timeout, total_timeout):
    with pytest.raises(ChunkTimeout):
        for data in timeout_proc.iter_run(chunk_timeout=chunk_timeout, total_timeout=total_timeout):
            pass


@pytest.mark.timeouts_test
@pytest.mark.parametrize( \
    'chunk_timeout,total_timeout',
    [
        (None, 5.0),
        (None, 6.0),
        (6.0, 5.0),        
    ]
)
def test_timeouts_total_timeout(timeout_proc, chunk_timeout, total_timeout):
    with pytest.raises(TotalTimeout):
        for data in timeout_proc.iter_run(chunk_timeout=chunk_timeout, total_timeout=total_timeout):
            pass


@pytest.mark.timeouts_test
def test_timeouts_continue(timeout_proc):
    try:
        for data in timeout_proc.iter_run(chunk_timeout=5.0, total_timeout=6.0):
            pass
    except ChunkTimeout:
        try:
            for data in timeout_proc.iter_run(chunk_timeout=4.0, total_timeout=2.0):
                pass
        except TotalTimeout:
            stdout = b''
            for data in timeout_proc.iter_run():
                stdout += data.stdout

            assert b'success' in stdout
            return
    
    raise Exception('Continue test failed.')


def _check_pid(pid):
    cmd = 'ps ax | awk \'{print $1}\' | xargs'
    proc = ReadingProc(cmd)
    proc.start()
    stdout = ''
    for data in proc.iter_run():
        stdout += data.stdout.decode()

    return '{}'.format(pid) in stdout


def _test_kill(timeout_proc, method_name):
    try:
        for data in timeout_proc.iter_run(chunk_timeout=1.0):
            pass
    except ChunkTimeout:
        assert _check_pid(timeout_proc.pid)
        getattr(timeout_proc, method_name)()
        try:
            for data in timeout_proc.iter_run():
                pass
        except ProcessIsNotStartedError:
            assert not _check_pid(timeout_proc.pid)
            return

    raise Exception('Kill test failed.')


@pytest.mark.kill_test
def test_kill(timeout_proc):
    _test_kill(timeout_proc, 'kill')


@pytest.mark.kill_test
def test_terminate(timeout_proc):
    _test_kill(timeout_proc, 'terminate')


def _test_start_after_kill(timeout_proc, method_name):
    try:
        for data in timeout_proc.iter_run(chunk_timeout=1.0):
            pass
    except ChunkTimeout:
        assert _check_pid(timeout_proc.pid)
        getattr(timeout_proc, method_name)()
        assert not _check_pid(timeout_proc.pid)
        timeout_proc.start()
        stdout = b''
        for data in timeout_proc.iter_run():
            stdout += data.stdout
        assert b'success' in stdout


@pytest.mark.kill_test
def test_start_after_kill(timeout_proc):
    _test_start_after_kill(timeout_proc, 'kill')


@pytest.mark.kill_test
def test_start_after_terminate(timeout_proc):
    _test_start_after_kill(timeout_proc, 'terminate')


def _test_send_stdin(proc):
    msg = b'hello\n'
    end_msg = b'.\n'
    max_cnt = 11
    proc.send_stdin(msg)
    stdout = b''
    try:
        for i, data in enumerate(proc.iter_run(total_timeout=0.5)):
            stdout += data.stdout
            if i == max_cnt:
                proc.send_stdin(end_msg)
                break
            else:
                proc.send_stdin(msg)                
    finally:
        stdout = stdout.decode().replace('\n', '')
        msg = msg.decode().replace('\n', '')
        end_msg = end_msg.decode()
        assert stdout == msg * (max_cnt + 1)


@pytest.mark.send_stdin
@pytest.mark.timeout(1.0)
def test_send_py_stdin():
    _test_send_stdin(_run_script('echo_input.py'))


@pytest.mark.send_stdin
@pytest.mark.timeout(1.0)
def test_send_cat_stdin():
    cmd = 'cat'
    proc = ReadingProc(cmd)
    proc.start()
    _test_send_stdin(proc)    



def _check_stdin_terminal(stdin_terminal):
    proc = _run_script('test_tty.py', stdin_terminal)

    for data in proc.iter_run():
        line = data.stdout + data.stderr
        assert b'NOT_TTY' not in line


@pytest.mark.stdin_terminal
def test_stdin_terminal():
    _check_stdin_terminal(stdin_terminal=True)


@pytest.mark.stdin_terminal
@pytest.mark.xfail(strict=True)
def test_no_stdin_terminal():
    _check_stdin_terminal(stdin_terminal=False)


@contextmanager
def _test_alive():
    proc = _run_script('test_tty.py')
    assert proc.alive
    yield proc
    assert not proc.alive    


@pytest.mark.alive
def test_alive():
    with _test_alive() as proc:
        proc.terminate()

    with _test_alive() as proc:
        proc.kill()

    with _test_alive() as proc:
        for data in proc.iter_run():
            pass


@pytest.mark.read
def test_read():
    proc = _run_script('test_tty.py')
    sleep(0.1)
    data = proc.read()
    assert b'NOT_TTY' in data.stdout
