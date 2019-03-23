## ReadingProc contructor(cmd, shell=True, read_chunk=4096, stdin_terminal=False)

## ReadingProc methods and attributes

### Attribute alive
True if a process is alive.

### Attribute pid
Use this function to get a PID.
If shell==True, this is the process ID of the spawned shell.
To get source correct pid construct ReadingProc with shell=False.

### Method start()
Run the process (call the function after the constructor and before iter_run()).

### Method iter_run(chunk_timeout=None, total_timeout=None)
Iterate raw byte output (not waiting starting a new line).
Parameters:
chunk_timeout: float
 Timeout to read one item in iter_run() loop.
total_timeout: float
 Timeout from start executing process; can only occurs in iter_run() loop.

### Method kill()
Kill the process (send SIGKILL).

### Method terminate()
Try to terminate the process (send SIGTERM).

### Class ProcessData(stdout, stderr)
A class descibing an item which is returned in every loop of ReadingProc.iter_run(). Access to stdout got: `data.stdout`, stderr: `data.stderr`.

### Exception ProcessIsNotStartedError
It occurs when we call some methods of ReadingProc before calling start().

### Exception ChunkTimeout
It occurs when chunk_timeout occurs while executing iter_run() of ReadingProc.

### Exception TotalTimeout
The exception occurs when total_timeout occurs while executing iter_run() of ReadingProc.

