## What's readingproc?

There is a class for simple reading `stdout` and `stderr` of any process. 
The next problems are solved:
* Reading blocking when trying to read stdout/stderr of a process. 
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

*Reading output of several processes in one loop.*

```python
from readingproc import ReadingSet, ReadingProc

# download all javascript files using by a google.com
url = 'https://google.com'
html_content = ''
# firstly download the main page
proc = ReadingProc('wget -O {}'.format(url))
for proc in proc.iter_run():
    html_content += proc.stdout.decode()
# parse all js urls at the page
re_js = '<script src=[\'"]'
```

*Read output for 60 seconds. If time is up then TotalTimeout occurs.*
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

*Getting control when expired, make some actions and continue reading.*

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

*Reading pipes of many processes in one loop.*
```python
from readingproc import ReadingProc, ReadingSet

patient_procs = {
    'John': ReadingProc('tail -f /tmp/patient1.log'),
    'Mike': ReadingProc('tail -f /tmp/patient2.log'),
    'Helene': ReadingProc('tail -f /tmp/patient3.log')
}

reading_set = ReadingSet()
for log in patient_procs:
    proc = ReadingProc('tail -f {}'.format(log))
    reading_set.add(patient_logs)

# start all reading processes which have not been started yet
reading_set.start_all()

for data in reading_set.iter_run(total_timeout=10.0, chunk_timeout=1.0):
    # ReadingProc supports the equal comparing
    if data.reading_proc == patient_procs['John']:
        # extracting necessary data
        is_total_timeout = data.is_total_timeout
        is_chunk_timeout = data.is_chunk_timeout
        # stdout and stderr are None in case of any timeout
        stdout = data.stdout
        stderr = data.stderr
        if is_chunk_timeout:
            print('Alarm! John\'s device does not respond.')
            # do not listen Mike and Helene any more
            reading_set -= patient_procs['Mike']
            reading_set -= patient_procs['Helene']

# terminate all the processes which are alive
reading_set.terminate_all()
```



### Example Notes

The examples are for `Python 3`. For `Python 2` you create the same code. `data.stdout` and `data.stderr` in `Python 2` have `str` type, in `Python 3` they both have `bytes` type (processes send bytes which can be decoded into strings).

[A very short API](API.md)