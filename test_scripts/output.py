"""
Output as many random bytes as required at first parameter (it's output length).
"""
import sys
import string


def main():
    l = int(sys.argv[1])
    ch = 'h'

    for i in range(l):
        sys.stdout.write(ch)
    


if __name__ == '__main__':
    main()