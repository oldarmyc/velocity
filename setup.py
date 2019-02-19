#!/usr/bin/env python3


from setuptools import setup
from setuptools import find_packages


setup(
    name='velocity',
    version='0.1.0',
    url='https://github.com/oldarmyc/velocity.git',
    license='BSD',
    author='Dave Kludt',
    author_email='oldarmyc@gmail.com',
    description='Library to interact with swift containers',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    install_requires=[
        'asyncio;python_version<"3.4"',
        'aiohttp',
        'aiofiles',
        'requests'
    ],
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
