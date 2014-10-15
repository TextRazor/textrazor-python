#!/usr/bin/env python

"""
TextRazor
=========

The official Python SDK for the TextRazor Text Analytics API (https://textrazor.com).

TextRazor offers a comprehensive suite of state-of-the-art natural language processing functionality, with easy integration into your applications in minutes. TextRazor helps hundreds of applications understand unstructured content across a range of verticals, with use cases including social media monitoring, enterprise search, recommendation systems and ad targetting.

Read more about the TextRazor API at https://www.textrazor.com.

"""

from setuptools import setup, find_packages

setup(
    name='textrazor',
    version='1.0.2',
    description='Official Python SDK for TextRazor (https://textrazor.com).',
    long_description=__doc__,
    author='Toby Crayston',
    author_email='toby@textrazor.com',
    url='https://textrazor.com/',
    license='MIT',
    py_modules=['textrazor'],
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Topic :: Software Development'
    ]
)
