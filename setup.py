#!/usr/bin/env python
from setuptools import setup

setup(
    name="Matrix-NEB",
    version="0.0.1",
    description="A generic bot for Matrix",
    author="Kegan Dougal",
    author_email="kegsay@gmail.com",
    url="https://github.com/Kegsay/Matrix-NEB",
    packages = ['neb', 'plugins'],
    license = "LICENSE",
    install_requires = [
        "pytumblr",
        "requests",
        "Flask"
    ],
    dependency_links=[
        "git+ssh://git@github.com/tumblr/pytumblr.git",
    ],
)
