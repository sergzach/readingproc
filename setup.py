#coding=utf-8

import sys
from setuptools import setup

setup(
    name='readingproc',        
    version='0.2.0',        
    description='A class for easy reading output and interacting with stdin, stdout, stderr of '
                'another process (simplifying using subprocess).',
    author='Sergey Zakharov',
    author_email='sergzach@gmail.com',
    packages=['readingproc'],
    package_dir={'readingproc': 'readingproc'},
    python_requires='>=2.7',
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    classifiers = [
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: Freely Distributable',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.0',
        'Programming Language :: Python :: 3.1',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: System :: Monitoring',
        'Topic :: System :: Logging'
    ]
)
