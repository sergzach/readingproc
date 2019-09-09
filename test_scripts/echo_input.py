#!/usr/bin/env python3

"""
Echo stdin back to user.
"""
from __future__ import print_function
import sys
from time import sleep


def main():
    line = None
    while line != '.':
        try:
            line = raw_input()
        except NameError:
            line = input()
        sys.stdout.write(line)
        sys.stdout.flush()


if __name__ == '__main__':
    main()