## What's readingproc?

There is a class of easy reading `stdout` and `stderr` of any process.

### How to install

`pip install https://github.com/sergzach/readingproc/archive/master.zip`

### *Just an example*

Let's get stdout of `tail -f file` for 10 seconds.

```
from readingproc import ReadingProc, TotalTimeout

proc = ReadingProc('tail -f my_file')
tail_content = b''
proc.start()
try:
	for data in proc.iter_run():
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