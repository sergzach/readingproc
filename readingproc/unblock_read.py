"""
Functions to block/{restore flags} read.
"""
from os import O_NONBLOCK
from fcntl import fcntl, F_GETFL, F_SETFL

def set_read_flags(f, flags):
	fcntl(f, F_SETFL, flags)


def get_read_flags(f):
	return fcntl(f, F_GETFL)


def unblock_read(f):
	"""
	Context manager to temporary unblock read while 
	"""
	flags = get_read_flags(f) # get current p.stdout flags
	set_read_flags(f, flags | O_NONBLOCK)
	return flags