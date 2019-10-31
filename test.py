"""
A testing executor with pytest.
"""

import pytest
import os
import sys
from contextlib import contextmanager
from collections import defaultdict, OrderedDict
import subprocess
import select
from time import time, sleep
from tempfile import gettempdir
from readingproc import     ReadingProc, \
                            TimeoutProc, \
                            ReadingSet, \
                            ChunkTimeout, \
                            TotalTimeout, \
                            ProcEnd, \
                            ProcessIsNotStartedError, \
                            WrongReadingSetItem
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

    proc = ReadingProc('{}'.format(path), stdin_terminal=stdin_terminal)
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
    proc = _run_script('test_tty.py && sleep 1')
    sleep(0.1)
    data = proc.read()
    assert b'NOT_TTY' in data.stdout


def _test_return_code(cmd):
    proc = ReadingProc(cmd)
    proc.start()
    assert proc.return_code is None
    sleep(4)
    return proc


@pytest.mark.return_code
def test_return_code1():
    proc = _test_return_code('sleep 3; nosuchcommand')
    assert proc.return_code is None
    proc.join()
    assert proc.return_code != 0


@pytest.mark.return_code
def test_return_code():
    proc = _test_return_code('sleep 3; echo "OK"')
    assert proc.return_code is None
    for data in proc.iter_run():
        pass
    assert proc.return_code == 0


def _terminate_or_kill(proc, i):
    """
    Perform process termination of killing depends on i % 2.
    Parameters
    ----------
    proc: ReadingProc instance
        A process to stop.
    i: int
        An index of a process in a collection.
    """
    if i % 2 == 0:
        proc.terminate()
    else:
        proc.kill()


def _assert_alives(reading_set, num_all, num_alives, num_dead):
    """
    Check number of all/alive/dead processes in ReadingSet object.
    """
    assert len(reading_set.get_all()) == num_all
    assert len(reading_set.get_alive()) == num_alives
    assert len(reading_set.get_dead()) == num_dead


@pytest.mark.reading_set
@pytest.mark.parametrize(   'cmd_read,num_procs,total_timeout,chunk_timeout,total_timeout_num,chunk_timeout_num,'
                            'stdout_lambda,stderr_lambda',
    [
        (       'tail -f {path}', 
                50, 
                5.0, 
                6.0, 
                1, 
                0, 
                lambda num_procs, l: all([b'patient_data' in x for x in l]), 
                lambda num_procs, l: all([len(x) == 0 for x in l])),
        (       'sleep 1 && tail -f {path}', 
                50, 
                5.0, 
                0.5, 
                0, 
                1, 
                lambda num_procs, l: len(l) < num_procs, 
                lambda num_procs, l: all([len(x) == 0 for x in l])),
        (       'nosuchcommand', 
                50, 
                5.0, 
                6.0, 
                0, 
                0, 
                lambda num_procs, l: all([len(x) == 0 in x for x in l]), 
                lambda num_procs, l: all([len(x) > 0 in x for x in l]))])
def test_reading_set_metrics(   cmd_read,
                                num_procs,
                                total_timeout, 
                                chunk_timeout,
                                total_timeout_num,
                                chunk_timeout_num,
                                stdout_lambda, 
                                stderr_lambda):
    """
    A basic test of ReadingSet.
    Parameters
    ----------
    cmd_read: str
        A reading command.
    num_procs: int
        A number of writing/reading procs (e.g. num_procs for each of the categories).
    total_timeout: float
        Using total_timeout as argument for ReadingSet.iter_run().
    chunk_timeout: float
        Using chunk_timeout as argument for ReadingSet.iter_run().
    total_timeout_num: int
        A number of total_timeouts for every patient (this is the same number for each patient). Can be 0 or 1. Stop the process.
    chunk_timeout_num: int
        A number of chunk_timeouts for every patient (this is the same number for each patient). Can be 0 or 1. Stop the process.
    stdout_lambda: function
        A function to check content of stdout.
    stderr_lambda: function
        A function to check content of stderr.
    """
    # prepare the data
    patient_indices = range(num_procs)
    path = os.path.join(gettempdir(), 'patient_%(index)d')
    cmd_write = 'watch -n 1 echo "patient_data%(index)d" >>{path}'.format(path=path)
    cmd_read = cmd_read.format(path=path)
    write_procs = []
    read_procs = {}
    total_timeouts = defaultdict(lambda: 0)
    chunk_timeouts = defaultdict(lambda: 0)
    proc_ends = defaultdict(lambda: 0)
    stdouts = defaultdict(lambda: b'')
    stderrs = defaultdict(lambda: b'')
    # initialize procs
    for patient_index in patient_indices:
        write_procs.append(ReadingProc(cmd_write % dict(index=patient_index)))
        patient_path = path % dict(index=patient_index)
        read_procs.update({ReadingProc(cmd_read % dict(index=patient_index)): patient_path})
    # start checking
    write_set = ReadingSet()
    for i, write_proc in enumerate(write_procs):
        write_set.add(write_proc)
    read_set = ReadingSet()
    for read_proc in read_procs:
        read_set.add(read_proc)
    # start all the processes
    write_set.start_all()
    read_set.start_all()
    # check all/dead/alive before starting iterating all process outputs
    _assert_alives(write_set, num_procs, num_procs, 0)
    # iterating gathering statistics on read_set
    i = 0
    for proc, data in read_set.iter_run(total_timeout=total_timeout, chunk_timeout=chunk_timeout):        
        if data.exception != None:
            if isinstance(data.exception, TotalTimeout):
                total_timeouts[proc] += 1
                alive_before_kill = len(read_set.get_alive())
                _terminate_or_kill(proc, i)
                assert alive_before_kill - len(read_set.get_alive()) == 1
            elif isinstance(data.exception, ChunkTimeout):
                chunk_timeouts[proc] += 1
                alive_before_kill = len(read_set.get_alive())
                _terminate_or_kill(proc, i)
                assert alive_before_kill - len(read_set.get_alive()) == 1
            elif isinstance(data.exception, ProcEnd):
                proc_ends[proc] += 1
        else:
            stdouts[proc] += data.stdout
            stderrs[proc] += data.stderr
        i += 1
    # check statistics    
    assert all([x == total_timeout_num for x in total_timeouts.values()])    
    assert all([x == chunk_timeout_num for x in chunk_timeouts.values()])    
    assert all([x == 1 for x in proc_ends.values()])
    assert stdout_lambda(num_procs, stdouts.values())
    assert stderr_lambda(num_procs, stderrs.values())
    assert all([x == 1 for x in proc_ends.values()])
    # clean the data
    write_set.kill_all()
    read_set.terminate_all()    
    # check alive after stop_all()
    _assert_alives(read_set, num_procs, 0, num_procs)
    _assert_alives(write_set, num_procs, 0, num_procs)
    # cleanup after the test,
    # remove patient files
    for patient_index in patient_indices:
        os.remove(path % dict(index=patient_index))


@pytest.mark.reading_set
def test_reading_set_operations():
    """
    Check the operations: |, -, &.
    Check exceptions when trying to operate with arguments of wrong types.
    """
    # check exception when trying to add objects of wrong types
    r1 = ReadingSet()
    with pytest.raises(WrongReadingSetItem):
        r1 |= set([2])
    with pytest.raises(WrongReadingSetItem):        
        r = set([2]) | r1
    with pytest.raises(WrongReadingSetItem):
        r1 -= set([2])
    with pytest.raises(WrongReadingSetItem):
        r = set([2]) - r1
    with pytest.raises(WrongReadingSetItem):
        r1 = r1 & set([2])
    with pytest.raises(WrongReadingSetItem):
        r1 = set([2]) & r1
    proc1 = ReadingProc('echo ok')
    proc2 = ReadingProc('echo ok')
    proc3 = ReadingProc('echo ok')
    r1 |= set([proc1, proc2, proc3])
    r2 = ReadingSet([proc2, proc3])
    assert r2 & r1 == r1 & r2
    assert r2 & r1 == r2
    assert r2 & r1 == ReadingSet([proc2, proc3])
    assert r1 & r2 == set([proc2, proc3])
    assert r1 | r2 == r2 | r1
    assert r1 | r2 == r1
    r1 | r2 == ReadingSet([proc2, proc1, proc3])
    r1 | r2 == set([proc1, proc2, proc3])
    assert r1 - r2 == ReadingSet([proc1])
    assert r1 - r2 == set([proc1])
    assert r2 - r1 == ReadingSet([])
    assert r2 - r1 == set([])
    assert set([proc1, proc2]) == ReadingSet([proc2, proc1])
    assert ReadingSet([proc2, proc1]) == set([proc1, proc2])
    assert ReadingSet([proc2, proc1]) == ReadingSet([proc1, proc2])


@pytest.mark.reading_set
def test_reading_set_alives():
    """
    Check correct work of get_all(), get_dead() and get_alive().
    Check correct support of operations |=, -=
    """
    cmd = 'watch -n 1 echo OK'
    num_procs = 50
    read_set = ReadingSet()
    for i in range(num_procs):
        proc = ReadingProc(cmd)
        read_set |= ReadingSet([proc])
    _assert_alives(read_set, num_procs, 0, num_procs)
    read_set.start_all()
    _assert_alives(read_set, num_procs, num_procs, 0)
    read_set.terminate_all()
    _assert_alives(read_set, num_procs, 0, num_procs)
    # now start each process before calling start_all()
    read_set = ReadingSet()
    for i in range(num_procs):
        proc = ReadingProc(cmd)
        if i % 2 == 0:
            proc.start()
            read_set |= ReadingSet([proc])
        else:
            read_set |= ReadingSet([proc])
            proc.start()
    _assert_alives(read_set, num_procs, num_procs, 0)
    read_set.start_all()
    _assert_alives(read_set, num_procs, num_procs, 0)
    all_procs = list(read_set.get_all())
    all_procs[0].kill()
    _assert_alives(read_set, num_procs, num_procs - 1, 1)
    alive_procs = list(read_set.get_alive())
    alive_procs[-1].kill()
    _assert_alives(read_set, num_procs, num_procs - 2, 2)
    for proc in alive_procs[0:-1]:
        proc.kill()
    _assert_alives(read_set, num_procs, 0, num_procs)
    read_set.kill_all()
    _assert_alives(read_set, num_procs, 0, num_procs)
    # check terminate_all()
    read_set = ReadingSet()
    for i in range(num_procs):
        proc = ReadingProc(cmd)
        read_set.add(proc)
    read_set.start_all()
    _assert_alives(read_set, num_procs, num_procs, 0)
    read_set.terminate_all()
    _assert_alives(read_set, num_procs, 0, num_procs)


def _reading_set_return_back(cmd, num_procs, do_return_back, compare_method):
    """
    A part of test_reading_set_return_back().
    Parameters
    ----------
    cmd: str
        A command to execute.
    num_procs: int
        A number of processes to check.
    do_return_back: bool
        Do return back a process after it has been ended?
    compare_reversed: list
        A list to compare the result.
    """
    read_set = ReadingSet()
    for i in range(num_procs):
        proc = ReadingProc(cmd % (i + 1))
        read_set.add(proc)
    read_set.start_all()
    returned_procs = OrderedDict()
    # check returning and starting the process
    i = 0
    for proc, data in read_set.iter_run():
        if isinstance(data.exception, ProcEnd):            
            proc.start()
            if do_return_back:
                read_set.return_back(proc)
            if proc not in returned_procs:
                returned_procs[proc] = 0
            returned_procs[proc] += 1
            i += 1
        if len(returned_procs) >= num_procs:
            break
    assert compare_method(num_procs, list(returned_procs.values())[::-1])


@pytest.mark.reading_set
def test_reading_set_return_back():
    """
    Check correct working of ReadingProc.return_back().
    """    
    cmd = 'sleep %d'
    num_procs = 50
    _reading_set_return_back(   cmd, 
                                num_procs, 
                                True, 
                                lambda num_procs, reversed_returned_nums: \
                                    list(sorted(reversed_returned_nums)) == reversed_returned_nums and \
                                    reversed_returned_nums[-1] > reversed_returned_nums[0] * 1.5)
    _reading_set_return_back(   cmd, 
                                num_procs, 
                                False, 
                                lambda num_procs, reversed_returned_nums: \
                                     reversed_returned_nums == [1] * num_procs)


@pytest.mark.reading_set
def test_timeout_proc():
    """
    Check using timeouts by ReadingSet assigning via TimeoutProc.
    """    
    num_procs = 50
    cmd = 'sleep 5; echo OK; sleep 5'
    # prepare the data for statistics
    total_timeouts = defaultdict(lambda: 0)
    chunk_timeouts = defaultdict(lambda: 0)
    proc_ends = defaultdict(lambda: 0)    
    data_got = defaultdict(lambda: 0)
    read_set = ReadingSet()
    # total_timeout in milliseconds
    for i, proc_num in enumerate(range(num_procs)):
        if i % 2 == 0:
            proc = TimeoutProc(total_timeout=proc_num + 1, cmd=cmd)
        else:
            proc = TimeoutProc(chunk_timeout=proc_num + 1, cmd=cmd)            
        read_set.add(proc)
    read_set.start_all()
    for proc, data in read_set.iter_run():
        if data.exception is not None:
            if isinstance(data.exception, TotalTimeout):
                total_timeouts[proc] += 1
            elif isinstance(data.exception, ChunkTimeout):
                chunk_timeouts[proc] += 1
            elif isinstance(data.exception, ProcEnd):
                proc_ends[proc] += 1
        else:
            data_got[proc] += 1

    # check statistics
    assert 5 <= len(total_timeouts) <= 6
    assert [x == 1 for x in total_timeouts.values()]
    assert 3 <= len(chunk_timeouts) <= 5
    assert [x == 1 for x in chunk_timeouts.values()]
    assert len(proc_ends) == num_procs - len(total_timeouts) - len(chunk_timeouts)
    assert len(data_got) == num_procs - len(chunk_timeouts)


@pytest.mark.work_dir
def test_work_dir():
    """
    Testing cwd option.
    """
    proc = ReadingProc('cat echo_input.py', cwd=os.path.join(_CUR_PATH, 'test_scripts'))
    proc.start()
    output_lines = []
    error_lines = []
    for data in proc.iter_run():
        output_lines.append(data.stdout.decode())
        error_lines.append(data.stderr.decode())
    assert all([l == '' for l in error_lines])
    output = '\n'.join(output_lines)
    assert '__main__' in output