## What's readingproc?

There is a class for easy reading `stdout` and `stderr` of any process. 
The next problems are solved:
* Read blocking when we try to read stdout/stderr of a process. 
* Stopping process properly. Just call one of the methods: `terminate()` or `kill()`.

### How to install

`pip install https://github.com/sergzach/readingproc/archive/master.zip`

### *Example*

Let's get `stdout` of `cat myfile`. To read iterate with `iter_run()` method.

```
from readingproc import ReadingProc

proc = ReadingProc('cat myfile')
proc.start()
for data in proc.iter_run(total_timeout=10.0):
	print(data.stdout.decode())
```

### 

### Supported Python versions
* 2.7
* 3.x