#!/usr/bin/env python

"""
TextRazor
=========

The official Python SDK for the TextRazor Text Analytics API (https://textrazor.com).

TextRazor makes it easy to build Named Entity Extraction, Disambiguation and Linking, Word Sense Disambiguation, Topic Classification, Relation Extraction and many other Natural Language Processing features into your applicaton.

"""

from setuptools import setup, find_packages

setup(
    name='textrazor',
    version='1.0.1',
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
