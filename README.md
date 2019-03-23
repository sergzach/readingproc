## What's readingproc?

There is a class for simple reading `stdout` and `stderr` of any process. 
The next problems are solved:
* Read blocking when we try to read stdout/stderr of a process. 
* Stopping process properly. Just call one of the methods: `terminate()` or `kill()`.

### Supported Python versions
* 2.7
* 3.x

### How to install

`pip install https://github.com/sergzach/readingproc/archive/master.zip`

### *Example*

Let's get `stdout` of `cat myfile`. To read iterate with `iter_run()` method.

```python
from readingproc import ReadingProc

proc = ReadingProc('cat myfile')
proc.start()
for data in proc.iter_run():
    print(data.stdout.decode())
```

### *More examples*

*Tailing file and return control when there is no new information for 10 seconds.*

```python
from readingproc import ReadingProc, ChunkTimeout

proc = ReadingProc('tail -f myfile')
proc.start()

try:
    for data in proc.iter_run(chunk_timeout=10.0):
        print(data.stdout.decode())
except ChunkTimeout:
    # there were no new lines for the last 10 secs
    print('Error. No new lines for 10 seconds.')    
```

*Read output for 60 seconds. If the duration exceeds then exception TotalTimeout occurs.*
```python
from readingproc import ReadingProc, TotalTimeout

proc = ReadingProc('cat myfile; sleep 70; echo OK')
proc.start()

try:
    for data in proc.iter_run(total_timeout=60.0):
        print(data.stdout.decode())
except TotalTimeout:
    print('60 seconds passed but the process still alive.')
    # lets terminate the process
    proc.terminate()
```

*Getting control when expired, make some actions then continue reading output.*

```python
from readingproc import ReadingProc, TotalTimeout

expired = False

proc = ReadingProc('cat myfile; sleep 70; echo OK')
proc.start()
try:
    for data in proc.iter_run(total_timeout=60.0):
        print(data.stdout.decode())
except TotalTimeout:
    expired = True
    # process is not finished yet... Continue reading.
    for data in proc.iter_run():
        print(data.stdout.decode())
finally:
    print('Process done, expiration status: {}.'.format(expired))
```

[API Reference](API.md)