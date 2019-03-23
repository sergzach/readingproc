"""
Class ReadingProc supports:
	Iteration on process output and getting stdout and stderr.
	Send to process stdin.
	Timeouts: to get new output chunk (chunk_timeout) and all process execution (total_timeout).
"""

__all__ = [	'ReadingProc', 
			'ProcessData', 
			'ChunkTimeout', 
			'TotalTimeout', 
			'ProcessIsNotStartedError', 
			'ChunkTimeout', 
			'TotalTimeout']

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
	A class descibing an item which is returned in every loop of ReadingProc.iter_run().
	"""
	def __init__(self, stdout, stderr):
		self.stdout = stdout
		self.stderr = stderr


class ProcessIsNotStartedError(Exception): 
	"""
	The exception occurs when we call some methods of ReadingProc before calling start().
	"""
	pass
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


class ReadingProc:
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


	def start(self):
		"""
		Run the process (call the function after the constructor and before iter_run()).
		"""
		self._proc = self._get_subprocess()
		self._pid = self._proc.pid


	def send_stdin(self, s_bytes):
		self._check_started()
		self._proc.stdin.write(s_bytes)
		self._proc.stdin.flush()


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
		self._check_started()

		self._init_timeouts()

		self._poll_stdout = select.poll()
		self._poll_stderr = select.poll()

		self._poll_stdout.register(self._proc.stdout, select.POLLIN)
		self._poll_stderr.register(self._proc.stderr, select.POLLIN)

		try:
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
			self._unregister_poll()
			raise
		else:
			self._unregister_poll()
			self._proc.communicate()
			self._proc = None


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


	def _check_started(self):
		if self._proc is None:
			raise ProcessIsNotStartedError('Call start() first to run the process.')				


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


	def _unregister_poll(self):
		self._poll_stdout.unregister(self._proc.stdout)
		self._poll_stderr.unregister(self._proc.stderr)	


	def _stop_proc(self, sig):
		self._kill_pg(self._proc, sig)
		self._proc.communicate()
		self._proc = None


	@staticmethod
	def _kill_pg(proc, sig):
		os.killpg(os.getpgid(proc.pid), sig)








