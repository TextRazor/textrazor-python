#!/usr/bin/env python

from setuptools import setup

setup(
    name='textrazor',
    version='1.4.1',
    description='Official Python SDK for TextRazor (https://textrazor.com).',
    long_description=open('README.rst').read(),
    author='TextRazor Ltd.',
    author_email='toby@textrazor.com',
    url='https://textrazor.com/',
    license='MIT',
    py_modules=['textrazor'],
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development'
    ]
)
