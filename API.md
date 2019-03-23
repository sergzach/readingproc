## ReadingProc methods and attributes

### ReadingProc contructor(cmd, shell=True, read_chunk=4096, stdin_terminal=False)
The class constructor.

**Parameters**

`cmd: str`

Shell command to execute.

`shell: bool`

Use intermediate shell between calling python script and process (True) or not (False). True by default.

`read_chunk: int`

Chunk of buffer when reading. Can be adjusted to small values to optimize memory of Python program or to big values if a process which we try to read sends a lot of information to stdout (Python interpreter can hang trying to catch all the output if the value is too small). Default value is `ReadingProc._DEFAULT_READ_CHUNK`.

`stdin_terminal: bool`

Set to True if the program requires virtual terminal to work properly. Example: when calling docker command. Default value is False.

### Method iter_run(chunk_timeout=None, total_timeout=None)
Iterate raw byte output (not waiting starting a new line).

**Parameters**

`chunk_timeout: float`

Timeout to read one item in iter_run() loop.

`total_timeout: float`

Timeout from start executing process; can only occurs in iter_run() loop.

### Attribute alive
True if a target process is alive.

### Attribute pid
Use this function to get a PID.
If shell==True, this is the process ID of the spawned shell.
To get source correct pid construct ReadingProc with shell=False.

### Method send_stdin(s_bytes)
Send bytes to stdin of a target process.

### Method start()
Run the process (call the function after the constructor and before iter_run()).

### Method kill()
Kill the process (send SIGKILL).

### Method terminate()
Try to terminate the process (send SIGTERM).

## Classes to work with reading data and exceptions

### Class ProcessData(stdout, stderr)
A class descibing an item which is returned in every loop of ReadingProc.iter_run(). Access to stdout got: `data.stdout`, stderr: `data.stderr`.

### Exception ProcessIsNotStartedError
It occurs when we call some methods of ReadingProc before calling start().

### Exception ChunkTimeout
It occurs when chunk_timeout occurs while executing iter_run() of ReadingProc.

### Exception TotalTimeout
The exception occurs when total_timeout is expired while executing iter_run() of ReadingProc.

