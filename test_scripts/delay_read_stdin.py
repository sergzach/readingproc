#!/usr/bin/env python3

from __future__ import print_function
import sys
from time import sleep

"""
Read stdin with a delay.
"""

def main():
    while True:
        timeout = float(sys.argv[1])
        input_len = int(sys.argv[2])
        sleep(timeout)
        data = sys.stdin.read(input_len)
        sys.stdout.write(data)
        sys.stdout.flush()


if __name__ == '__main__':
    main()