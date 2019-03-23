"""
Check if the program is attached to TTY.
"""
from __future__ import print_function
import os, sys


def main():
	print('TTY' if sys.stdin.isatty() else 'NOT_TTY')
	print(sys.stdout.fileno())


if __name__ == '__main__':
	main()