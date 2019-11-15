"""
A manager to send to stdin of a subprocess.Popen objects in another thread.
There can be several ReadingProcs attached to ThreadStdinManager.
"""
from time import sleep
from threading import Thread
try:
    # python 3
    from queue import Queue, Full, Empty
except ImportError:
    # python 2
    from Queue import Queue, Full, Empty


from .core import ProcessIsDeadError


class ThreadStdinManagerAlreadyStartedError(Exception):
    """
    Raise the exception when the a user tries to start a manager
    has been already started.
    """
    pass


class ThreadStdinManagerAlreadyStoppedError(Exception):
    """
    Raise the exception when the a user tries to stop a manager
    has been already stopped.
    """
    pass


class ThreadStdinManagerNotAliveError(Exception):
	"""
    Raise the exception when the a user tries to send_stdin
    with a manager with not alive working thread (_job).
    """


class ThreadStdinManagerFullBufferError(Exception):
    """
    Raise the exception when the current message
    can not be send by ThreadStdinManager because 
    buffered messages have maximum allowed length.
    """
    def __init__(self, obj, msg):
        """
        Parameters
        ----------
        obj: ThreadStdinManager
            A ThreadStdinManager object which raises
            the exception.
        msg: str
            A message of the exception.
        """
        self.obj = obj
        self._msg = msg


    def __str__(self):
        return self._msg


class Message:
    """
    A class describing one ReadingProc item.    
    """
    def __init__(self, proc, msg):
        self.proc = proc
        self.msg = msg


class ThreadStdinManager:
    """
    A class to send to stdin of a subprocess.Popen object in another thread. 
    """
    def __init__(self, job_timeout=0.01, max_len=100):
        """
        Parameters
        ----------
        proc: subprocess.Popen
            An object whose stdin to use to send.
        job_timeout: float
            A time in seconds to sleep in sending job beetween messages checking.
        max_len: int
            A maximum allowed length of buffered messages (which has not been
            sent yet).
        """
        self._job_timeout = job_timeout
        self._max_len = max_len
        self._t = None
        self._q_exit = Queue(maxsize=1)
        self._messages = Queue(maxsize=max_len)  


    def __hash__(self):
        """
        A magic function to support placing ThreadStdinManager objects 
        to set (or use as dict keys).
        """
        return id(self)


    def __eq__(self, other):
        """
        A magic function to support comparing of ThreadStdinManager objects.
        Parameters
        ----------
        other: ThreadStdinManager
            Another ReadingProc object to compare to.
        """
        return id(self) == id(other)


    @property
    def alive(self):
        """
        Return True if ThreadStdinManager has been started.
        Otherwise return False.
        """
        return self._t is not None        


    @staticmethod
    def _job(messages, q_exit, job_timeout):
        """
        The sending job.
        Parameters
        ----------
        proc: subprocess.Popen
            An object whose stdin to use to send.
        messages: list
            Messages to handle.
        """
        while True:
            try:
                message = messages.get(timeout=job_timeout)
            except Empty:
                pass
            else:
                proc = message.proc
                msg = message.msg
                try:
                    proc.send_stdin(msg)
                except IOError:
                    # something wrong with the proc                
                    return
                except ProcessIsDeadError:
                    # process has been already terminated
                    return            
            finally:
                if q_exit.qsize() > 0:
                    return


    def start(self):
        """
        Start sending thread.
        """
        if self._t is not None:
            raise ThreadStdinManagerAlreadyStartedError('The manager has been already started.')
        self._t = Thread(target=self._job, args=(self._messages, self._q_exit, self._job_timeout))
        self._t.start()


    def send_stdin(self, proc, msg):
        """
        Add a new message to send.
        Parameters
        ----------
        proc: ReadingProc
            An object to send to.
        msg: bytes
            A message of bytes to send.
        """
        if self._t is None:
        	raise ThreadStdinManagerNotAliveError('The manager is not alive now.')
        try:
            message = Message(proc, msg)
            self._messages.put_nowait(message)
        except Full:
            raise ThreadStdinManagerFullBufferError( \
                self,
                'The message queue is full (max_len=%d).' % self._max_len)


    @property
    def queue_size(self):
        """
        Return a current length of message queue.
        """
        return self._messages.qsize()


    def stop(self, timeout=None):
        """
        Stop sending thread.
        It returns True if the job thread has been successfully terminated, 
        otherwise, in case of timeout, it returns False.
        """
        if self._t is None:
            raise ThreadStdinManagerAlreadyStoppedError('The manager has been already stopped.')
        self._q_exit.put_nowait(None)
        self._t.join(timeout)
        if not self._t.is_alive():
            self._q_exit.get_nowait()
            self._t = None
            return True
        self._q_exit.get_nowait()
        return False
