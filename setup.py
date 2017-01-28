#!/usr/bin/env python
from setuptools import setup

setup(
    name="Matrix-NEB",
    version="0.0.2",
    description="A generic bot for Matrix",
    author="Kegan Dougal",
    author_email="kegsay@gmail.com",
    url="https://github.com/Kegsay/Matrix-NEB",
    packages = ['neb', 'plugins'],
    license = "LICENSE",
    install_requires = [
        "matrix_client",
        "Flask",
        "python-dateutil"
    ],
    dependency_links=[
        "https://github.com/matrix-org/matrix-python-sdk/tarball/v0.0.5#egg=matrix_client-0.0.5"
    ]
)
