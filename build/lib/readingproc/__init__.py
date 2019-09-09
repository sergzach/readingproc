"""
Class ReadingProc supports:
    Iteration on process output and getting stdout and stderr.
    Send to process stdin.
    Timeouts: to get new output chunk (chunk_timeout) and all process execution (total_timeout).
"""

__all__ = [ 'ReadingProc', 
            'TimeoutProc',
            'ProcessData', 
            'ChunkTimeout', 
            'TotalTimeout', 
            'ProcessIsNotStartedError', 
            'ReadingSet',
            'ReadingItemData',
            'ProcEnd',
            'ReadingItemTimeoutTimes',
            'ProcessIsDeadError',
            'NotInReadingSetError',
            'DontCallWhenIterRunError',
            'WrongReadingSetItem']

import os
import signal
from contextlib import contextmanager
import subprocess
import select
from time import sleep, time
import pty
import shlex
from .unblock_read import set_read_flags, unblock_read


class ProcessData:
    """
    A class descibing an item which is returned in every iteration 
    of the loop ReadingProc.iter_run().
    """
    def __init__(self, stdout, stderr):
        self.stdout = stdout
        self.stderr = stderr


class ProcessIsNotStartedError(Exception): 
    """
    The exception occurs when we call some methods of ReadingProc before calling start().
    """
    pass
class ProcessIsDeadError(Exception):
    """
    The exception occurs when the process is already dead.
    """
class ChunkTimeout(Exception): 
    """
    The exception occurs when chunk_timeout occurs while executing iter_run() of ReadingProc.
    """
    pass
class TotalTimeout(Exception): 
    """
    The exception occurs when total_timeout occurs while executing iter_run() of ReadingProc.
    """
    pass


@contextmanager
def _unblock_read(proc):
    """
    Context manager to temporary unblock read while reading process stdout/stderr.
    """        
    stdout_flags = unblock_read(proc.stdout)
    stderr_flags = unblock_read(proc.stderr)
    try:
        yield proc
    finally:
        set_read_flags(proc.stdout, stdout_flags)
        set_read_flags(proc.stderr, stderr_flags)


def _check_started(f):
    """
    Decorator for ReadingProc functions. 
    Checks if started (at least start() method was called and process was not stopped).
    """
    def inner(self, *args, **kwargs):
        if self._proc is None:
            raise ProcessIsNotStartedError('Call start() first to run the process.')
        return f(self, *args, **kwargs)

    return inner


class ReadingProc(object):
    """
    The main class which can construct object to read process stdout and send to it's stdin.
    """
    # read chunk - make it closer to size you read frequently
    # (in case of too small chunk program could not be fast enough to gather all chunks of
    # incoming data)
    _DEFAULT_READ_CHUNK = 4096 # 4K

    def __init__(self, cmd, shell=True, read_chunk=_DEFAULT_READ_CHUNK, stdin_terminal=False):
        """
        The class constructor.
        Parameters
        ----------
        cmd: str
            Shell command to execute.
        shell: bool
            Use intermediate shell between calling python script and process (True) or not (False). True by default.
        read_chunk: int
            Chunk of buffer when reading. Can be adjusted to small values to optimize memory of Python program or to \
            big values if a process which we try to read sends a lot of information to stdout (Python interpreter \
            can hang trying to catch all the output if the value is too small). Default value is \
            ReadingProc._DEFAULT_READ_CHUNK.
        stdin_terminal: bool
            Set to True if the program requires virtual terminal to work properly. Example: when calling \
            docker command. Default value is False.
        """
        self._cmd = cmd
        self._proc = None
        self._pid = None
        self._stdin_terminal = stdin_terminal
        self._shell = shell
        self._read_chunk = read_chunk
        self._chunk_time = None
        self._total_time = None


    def __del__(self):
        if self._proc is not None:
            self.kill()


    @property
    def pid(self):
        """
        Use this function to get a PID.
        If shell==True, this is the process ID of the spawned shell.
        To get source correct pid construct ReadingProc with shell=False.
        """
        return self._pid    


    def __hash__(self):
        """
        A magic function to support placing ReadingProc objects to set.
        """
        return id(self)


    def __eq__(self, other):
        """
        A magic function to support comparing of ReadingProc objects.
        Parameters
        ----------
        other: ReadingProc
            Another ReadingProc object to compare to.
        """
        return id(self) == id(other)


    def start(self):
        """
        Run the process (call the function after the constructor and before iter_run()).
        """
        self._proc = self._get_subprocess()
        self._pid = self._proc.pid
        self._return_code = None


    @_check_started
    def send_stdin(self, s_bytes):
        """
        Send bytes to stdin of a target process.
        """
        self._proc.stdin.write(s_bytes)
        self._proc.stdin.flush()


    @_check_started
    def iter_run(self, chunk_timeout=None, total_timeout=None):
        """
        Iterate raw byte output (not waiting starting a new line).
        Parameters
        ----------
        chunk_timeout: float
            Timeout to read one item in iter_run() loop.
        total_timeout: float
            Timeout from start executing process; can only occurs in iter_run() loop.
        """
        self._init_timeouts()
        
        try:
            with self._register_poll():
                while self._proc.poll() is None:
                    with _unblock_read(self._proc):
                        result = self._yield_ready_read()
                        self._check_timeouts(chunk_timeout, total_timeout)    
                        if result is not None:
                            self._update_chunk_time()
                            yield result                    

                with _unblock_read(self._proc):
                    result = self._yield_ready_read()
                    if result is not None:
                        yield result
        except:
            raise
        else:            
            self.join()
            self._proc = None


    @_check_started
    def read(self):
        """
        Non-blocking read (unlike iter_run()). Read till the end of data.
        If there is no data returns None, otherwise returns ProcessData object.
        """
        if self.alive:
            with self._register_poll():
                with _unblock_read(self._proc):
                    return self._yield_ready_read()
        else:
            raise ProcessIsDeadError('Can not read. The process is already dead.')



    def kill(self):
        """
        Kill the process (send SIGKILL).
        """
        self._stop_proc(signal.SIGKILL)


    def terminate(self):
        """
        Try to terminate the process (send SIGTERM).
        """
        self._stop_proc(signal.SIGTERM)


    @property
    def alive(self):
        """
        True if a target process is alive.
        """
        return self._proc is not None and self._proc.poll() is None


    def join(self):
        self._proc.communicate()
        self._return_code = self._proc.returncode


    @property
    def return_code(self):
        return self._return_code


    @contextmanager
    def _register_poll(self):
        self._do_register_poll()
        try:
            yield
        finally:
            self._do_unregister_poll()


    def _do_register_poll(self):
        self._poll_stdout = select.poll()
        self._poll_stderr = select.poll()

        self._poll_stdout.register(self._proc.stdout, select.POLLIN)
        self._poll_stderr.register(self._proc.stderr, select.POLLIN)


    def _do_unregister_poll(self):
        self._poll_stdout.unregister(self._proc.stdout)
        self._poll_stderr.unregister(self._proc.stderr)    


    def _init_timeouts(self):
        """
        Set item_time and total_time to current time.
        """
        cur_time = time()
        self._chunk_time = cur_time
        self._total_time = cur_time            


    def _read_while(self, fp):
        buff = b''

        while True:
            try:
                chunk = os.read(fp.fileno(), self._read_chunk)

                if len(chunk) == 0:
                    break
                
                buff += chunk                
            except OSError:
                break

        return buff


    def _yield_ready_read(self):
        stdout = b''
        stderr = b''

        if self._poll_stdout.poll(0):
            stdout = self._read_while(self._proc.stdout)
        if self._poll_stderr.poll(0):
             stderr = self._read_while(self._proc.stderr)

        if len(stdout) > 0 or len(stderr) > 0:
            return ProcessData(stdout, stderr)
        else:
            return None


    def _get_subprocess(self):
        if not self._shell and issubclass(self._cmd.__class__, str):
            args = shlex.split(self._cmd)
        else:
            args = self._cmd

        if not self._stdin_terminal:
            proc = subprocess.Popen( \
                args=args, 
                stdout=subprocess.PIPE,                 
                stderr=subprocess.PIPE,    
                stdin=subprocess.PIPE,
                preexec_fn=os.setpgrp,    
                shell=self._shell)
        else:
            master, slave = pty.openpty()

            proc = subprocess.Popen( \
                args=args, 
                stdout=subprocess.PIPE,                
                stderr=subprocess.PIPE,                
                stdin=slave,
                preexec_fn=os.setpgrp,
                shell=self._shell,                
                close_fds=True)

            os.close(slave)

        return proc


    def _update_chunk_time(self):
        self._chunk_time = time()


    def _check_timeouts(self, chunk_timeout, total_timeout):
        """
        Check if timeouts are expired.
        """
        cur_time = time()

        if chunk_timeout is not None and cur_time > self._chunk_time + chunk_timeout:
            raise ChunkTimeout('Item timeout expired.')
        elif total_timeout is not None and cur_time > self._total_time + total_timeout:
            raise TotalTimeout('Total timeout expired.')


    def _stop_proc(self, sig):
        if self.alive:
            self._kill_pg(self._proc, sig)
        try:
            if self._proc is not None:
                self._proc.communicate()
            else:
                raise ProcessIsNotStartedError( 'The process has been already terminated via kill()'
                                                ' or terminate() or it has not been started via start().')
        except ValueError:
            pass
        finally:
            self._proc = None


    @staticmethod
    def _kill_pg(proc, sig):
        os.killpg(os.getpgid(proc.pid), sig)


class TimeoutProc(ReadingProc):
    """
    Similar to ReadingProc.
    The class also allows to specify custom total_timeout and chunk_timeout
    (as arguments of the constructor) if the current object is iterated 
    by ReadingSet.iter_run().
    """
    def __init__(self, *args, **kwargs):
        """
        The constructor. For more details see the constructor of ReadingProc.
        Keyword arguments
        -----------------
        total_timeout: float
            A total_timeout associated with a process.
        chunk_timeout: float:
            A chunk_timeout associated with a process.
        """
        self.total_timeout = kwargs.pop('total_timeout', None)
        self.chunk_timeout = kwargs.pop('chunk_timeout', None)
        super(TimeoutProc, self).__init__(*args, **kwargs)



class ProcEnd(Exception): 
    """
    The exception can occur in ReadingSet.iter_run() loop when process has been terminated
    for some reason without calling ReadingProc.kill() or ReadingProc.terminate().
    """
    pass


class ReadingItemData:
    """
    A class descibing an item which is returned in every iteration 
    of the loop ReadingSet.iter_run().
    """
    def __init__(self, stdout, stderr, exception):
        self.stdout = stdout
        self.stderr = stderr
        self.exception = exception


class ReadingItemTimeoutTimes:
    """
    Stoging the data about the most recent times of TotalTimeout and ChunkTimeout 
    of ReadingProc in ReadingSet.
    """
    def __init__(self):
        """
        The constructor.
        Parameters
        ----------
        total_timeout_time: float
            The time() of the most recent total_timeout.
        chunk_timeout_time: float
            The time() of the most recent chunk_timeout.
        """
        self._total_timeout_time = None
        self._chunk_timeout_time = None


    def reset_total_timeout(self):
        self._total_timeout_time = time()


    def reset_chunk_timeout(self):
        self._chunk_timeout_time = time()


    def is_total_timeout(self, total_timeout):
        """
        It returns True if total_timeout expired.
        Parameters
        ----------
        total_timeout: float
            A number of seconds in total_timeout.
        """
        return time() - self._total_timeout_time > total_timeout


    def is_chunk_timeout(self, chunk_timeout):
        """
        It returns True if chunk_timeout expired.
        Parameters
        ----------
        chunk_timeout: float
            A number of seconds in chunk_timeout.
        """        
        return time() - self._chunk_timeout_time > chunk_timeout


class NotInReadingSetError(Exception):
    """
    It raises when a user tries to return back into a ReadingSet a ReadingProc
    which has never been in the ReadingSet.
    """
    pass


class DontCallWhenIterRunError(Exception):
    """
    It raises when a user tries to make the next operations on ReadingSet object in 
    iter_run loop:
        reading_set |= other_reading_set.
        reading_set -= other_reading_set.
    """
    pass


class WrongReadingSetItem(Exception):
    """
    It raises when a user tries to interract with an item of wrong type to a ReadingSet object.
    """
    pass


class ReadingSet:
    """
    A class to support reading pipes of many processes in one loop.
    """

    def __init__(self, s=set()):
        """
        Initially ReadingSet is empty.
        """
        self._set = set(s)
        self._active_procs = None 


    @staticmethod
    def _check_item(proc):
        """
        Check an item to add to the set.
        proc: object
            An item to check
        """
        if not isinstance(proc, ReadingProc):
            raise WrongReadingSetItem(  'You try to interract with item(s) of wrong type(s), '
                                        'e.g. not describing processes.')


    @classmethod
    def _check_items(cls, sequence):
        """
        Check that every item of sequence has the appropriate type.
        """
        all([cls._check_item(x) for x in sequence])            


    def add(self, other):
        """
        Works similar to .add method of set.
        Parameters
        ----------
        other: ReadingProc
            An object to add to the current set.
        """
        self._check_item(other)
        self._set.add(other)


    def remove(self, other):
        """
        Works similar to .remove method of set.
        Parameters
        ----------
        other: ReadingProc
            An object to remove from the current set.
        """
        self._check_item(other)
        self._set.remove(other)    


    def _get_other_set(self, other):
        """
        Extract a set from `other` (it could be ReadingSet or just a set).
        Parameters
        ----------
        other: ReadingSet or set
            An object to extract a set.
        """
        return other._set if isinstance(other, ReadingSet) else other


    def _operation_or(self, other):
        """
        Works similar to operation | of set.
        Do not call in iter_run() loop.
        Parameters
        ----------
        other: ReadingSet or set
            An object to add to the current set.
        """
        self._check_items(other)
        if self._active_procs is not None:
            raise DontCallWhenIterRunError('Do not call the operation in iter_run loop.')
        return ReadingSet(self._set | self._get_other_set(other))


    def __or__(self, other):
        """
        Works similar to operation | of set.
        Do not call in iter_run() loop.
        Parameters
        ----------
        other: ReadingSet or set
            An object to add to the current set.
        """
        return self._operation_or(other)


    def __ror__(self, other):
        """
        Works similar to operation | of set.
        Do not call in iter_run() loop.
        Parameters
        ----------
        other: ReadingSet or set
            An object to add to the current set.
        """
        return self._operation_or(other)


    def _operation_and(self, other):
        """
        Works similar to operation & of set.
        Do not call in iter_run() loop.
        Parameters
        ----------
        other: ReadingSet or set
            An object to add to the current set.
        """
        self._check_items(other)
        return ReadingSet(self._set & self._get_other_set(other))


    def __and__(self, other):
        """
        Works similar to operation & of set.
        Do not call in iter_run() loop.
        Parameters
        ----------
        other: ReadingSet or set
            An object to add to the current set.
        """
        return self._operation_and(other)


    def __rand__(self, other):
        """
        Works similar to operation & of set.
        Do not call in iter_run() loop.
        Parameters
        ----------
        other: ReadingSet or set
            An object to add to the current set.
        """
        return self._operation_and(other)


    def _operation_sub(self, first, second):
        """
        Works similar to operation - of set.
        Do not call in iter_run() loop.
        Parameters
        ----------
        other: ReadingSet or set
            An object to subtract from the current set.
        """   
        self._check_items(first)
        self._check_items(second)
        if self._active_procs is not None:
            raise DontCallInIterRunError('Do not call the operation in iter_run loop.')
        return ReadingSet(self._get_other_set(first) - self._get_other_set(second))


    def __sub__(self, other):
        """
        Works similar to operation - of set.
        Do not call in iter_run() loop.
        Parameters
        ----------
        other: ReadingProc
            An object to subtract from the current set.
        """
        return self._operation_sub(self, other)


    def __rsub__(self, other):
        """
        Works similar to operation - of set.
        Do not call in iter_run() loop.
        Parameters
        ----------
        other: ReadingProc
            An object to subtract from the current set.
        """
        return self._operation_sub(other, self)


    def __eq__(self, other):
        """
        Compares the current reading set to another ReadingSet/set.        
        Parameters
        ----------
        other: ReadingSet or set
            An object to compare with the current set.
        """
        return self._set == self._get_other_set(other)


    def __contains__(self, proc):
        """
        Returns True if the proc in the current set.
        proc: ReadingProc
            A proc to check.
        """
        self._check_item(proc)
        return proc in self._set


    def __len__(self):
        """
        Return the number of elements in the ReadingSet.
        """
        return len(self._set)


    def __iter__(self):
        return (x for x in self._set)


    @staticmethod
    def _extract_timeout_arg(proc, timeout_field, default_timeout):
        """
        A core function to extract a timeout from TimeoutProc or 
        use a default_timeout.
        """
        if isinstance(proc, TimeoutProc):
            proc_timeout = getattr(proc, timeout_field)
            return default_timeout if proc_timeout is None else proc_timeout            
        else:
            return default_timeout


    @classmethod
    def _extract_total_timeout(cls, proc, default_total_timeout):
        """
        Extract total_timeout from TimeoutProc or use a default_total_timeout.
        """
        return cls._extract_timeout_arg(proc, 'total_timeout', default_total_timeout)


    @classmethod
    def _extract_chunk_timeout(cls, proc, default_chunk_timeout):
        """
        Extract chunk_timeout from TimeoutProc or use a default_chunk_timeout.
        """
        return cls._extract_timeout_arg(proc, 'chunk_timeout', default_chunk_timeout)


    def iter_run(self, total_timeout=None, chunk_timeout=None):
        """
        Works with output and timeouts exceptions of all processes which are in the current set.
        It yields ReadingSetData object with stdout, stderr and timeout information 
        of a corresponding process.
        Parameters
        ----------
        chunk_timeout: float
            The default timeout to read one item in iter_run() loop.
        total_timeout: float
            The default timeout from start executing process; can only occurs in iter_run() loop.
        """
        # a set containing ReadingProcs which was not terminated
        self._active_procs = set(self._set)
        timeout_times = {}
        for active_proc in self._active_procs:
            timeout_times[active_proc] = ReadingItemTimeoutTimes()
            timeout_time = timeout_times[active_proc]
            timeout_time.reset_total_timeout()
            timeout_time.reset_chunk_timeout()
        while len(self._active_procs) > 0:
            # a set of procs to remove later (cannot remove when iterating)
            remove_active_procs = set()
            active_procs_copy = set(self._active_procs)
            for proc in active_procs_copy:
                try:
                    process_data = proc.read()
                    # check result and if no result then check timeouts
                    if process_data is not None:
                        yield   proc, \
                                ReadingItemData(    stdout=process_data.stdout, 
                                                    stderr=process_data.stderr,
                                                    exception=None)
                    else:
                        timeout_time = timeout_times[proc]
                        use_total_timeout = self._extract_total_timeout(proc, total_timeout)
                        use_chunk_timeout = self._extract_chunk_timeout(proc, chunk_timeout)
                        if use_total_timeout is not None and timeout_time.is_total_timeout(use_total_timeout):
                            self._active_procs.remove(proc)
                            timeout_time.reset_total_timeout()
                            yield   proc, \
                                    ReadingItemData(  \
                                        stdout=None,
                                        stderr=None,
                                        exception=TotalTimeout( 'No result while read pid '
                                                                '<{}> in ReadingSet.'.format(proc.pid)))
                        elif use_chunk_timeout is not None and timeout_time.is_chunk_timeout(use_chunk_timeout):
                            self._active_procs.remove(proc)
                            timeout_time.reset_chunk_timeout()
                            yield   proc, \
                                    ReadingItemData( \
                                        stdout=None,
                                        stderr=None,
                                        exception=ChunkTimeout( 'No result while read pid '
                                                                '<{}> in ReadingSet.'.format(proc.pid)))
                # checking alive raising an exception if needed
                except ProcessIsDeadError:
                    # remove from a primary container: from self._active_procs, not from copy
                    # to let a user call return_back() correctly when yielding to him (next)
                    self._active_procs.remove(proc)
                    yield   proc, \
                            ReadingItemData(    \
                                stdout=None,
                                stderr=None,
                                exception=ProcEnd(  'The proc with pid '
                                                    '<{}> has been ended.'.format(proc.pid)))                
        # reset _active_procs not to call return_proc outside the iter_run
        # because it has not any sense
        self._active_procs = None


    def return_back(self, proc):
        """
        Move ReadingProc object back into active_procs to continue the iteration.
        It's a safe operation checking existence of ReadingProc object 
        in the current ReadingSet; in case of occuring the exception ProcEnd and 
        starting ReadingProc again use the function instead of set operations.
        Notice: when a new iter_run() loop of the same ReadingSet object is started 
        all disactivated in a most recent iter_run() loop ReadingProcs are returned back 
        automatically.
        """
        if proc in self._set:
            self._active_procs |= {proc}
        else:
            raise NotInReadingSetError( 'You try to return back an object which '
                                        'has never been in the current ReadingSet.')


    def get_all(self):
        """
        Get a set of all ReadingProc objects.
        """
        return ReadingSet(self._set)


    def get_alive(self):
        """
        Get a set of all ReadingProc objects which is currently alive.
        """
        return ReadingSet(set([x for x in self._set if x.alive]))


    def get_dead(self):
        """
        Get a set of not alive ReadingProc objects.
        """
        return ReadingSet(set([x for x in self._set if not x.alive]))


    def start_all(self):
        """
        Start all ReadingProcs which are in the set.
        """
        for proc in self.get_all():
            proc.start()


    def _stop_all(self, method_name):
        """
        Stop helper, stop all ReadingProcs which are in the set.
        """
        for proc in self.get_all():
            if proc.alive:
                getattr(proc, method_name)()


    def kill_all(self):
        """
        Kill all ReadingProcs which are in the set.
        """
        self._stop_all('kill')


    def terminate_all(self):
        """
        Terminate all ReadingProcs which are in the set.
        """
        self._stop_all('terminate')








