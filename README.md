## What's readingproc?

There is a class for easy reading `stdout` and `stderr` of any process. 
The next problems are solved:
* Read blocking when we try to read stdout/stderr of a process. 
* Stopping process properly. Just call one of the methods: `terminate()` or `kill()`.

### How to install

`pip install https://github.com/sergzach/readingproc/archive/master.zip`

### *Just an example*

Let's get stdout of `tail -f file` for *10 seconds*.

```
from readingproc import ReadingProc, TotalTimeout

max_read_seconds=10.0
proc = ReadingProc('tail -f my_file')
tail_content = b''
proc.start()
try:
	for data in proc.iter_run(total_timeout=max_read_seconds):
		tail_content += data.stdout
except TotalTimeout:
	pass
finally:
	tail_content = tail_content.decode() # convert from bytes to str
	print('Tail content if myfile is: {}'.format(tail_content))

```

### Supported Python versions
* 2.7
* 3.x