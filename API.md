# readingproc

Class ReadingProc supports:
 Iteration on process output and getting stdout and stderr.
 Send to process stdin.
 Timeouts: to get new output chunk (chunk_timeout) and all process execution (total_timeout).

## ProcessData
```python
ProcessData(self, stdout, stderr)
```

A class descibing an item which is returned in every loop of ReadingProc.iter_run().

## ProcessIsNotStartedError
```python
ProcessIsNotStartedError(self, /, *args, **kwargs)
```

The exception occurs when we call some methods of ReadingProc before calling start().

## ChunkTimeout
```python
ChunkTimeout(self, /, *args, **kwargs)
```

The exception occurs when chunk_timeout occurs while executing iter_run() of ReadingProc.

## TotalTimeout
```python
TotalTimeout(self, /, *args, **kwargs)
```

The exception occurs when total_timeout occurs while executing iter_run() of ReadingProc.

## ReadingProc
```python
ReadingProc(self, cmd, shell=True, read_chunk=4096, stdin_terminal=False)
```

The main class which can construct object to read process stdout and send to it's stdin.

# ReadingProc
```python
ReadingProc(self, cmd, shell=True, read_chunk=4096, stdin_terminal=False)
```

The main class which can construct object to read process stdout and send to it's stdin.

## alive

True if a process is alive.

## pid

Use this function to get a PID.
If shell==True, this is the process ID of the spawned shell.
To get source correct pid construct ReadingProc with shell=False.

## start
```python
ReadingProc.start(self)
```

Run the process (call the function after the constructor and before iter_run()).

## iter_run
```python
ReadingProc.iter_run(self, chunk_timeout=None, total_timeout=None)
```

Iterate raw byte output (not waiting starting a new line).
Parameters
----------
chunk_timeout: float
 Timeout to read one item in iter_run() loop.
total_timeout: float
 Timeout from start executing process; can only occurs in iter_run() loop.

## kill
```python
ReadingProc.kill(self)
```

Kill the process (send SIGKILL).

## terminate
```python
ReadingProc.terminate(self)
```

Try to terminate the process (send SIGTERM).

