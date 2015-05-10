"""
Gluu API
--------

Gluu cluster management API.
"""
import codecs
import os
import re
import sys
from setuptools import setup
from setuptools import find_packages
from setuptools.command.test import test as TestCommand


def find_version(*file_paths):
    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, *file_paths), 'r') as f:
        version_file = f.read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


class PyTest(TestCommand):
    user_options = [("pytest-args=", "a", "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = []

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest

        errno = pytest.main(self.pytest_args)
        sys.exit(errno)


setup(
    name="gluuapi",
    version=find_version("gluuapi", "__init__.py"),
    url="https://github.com/GluuFederation/gluu-flask",
    license="MIT",
    author="Gluu",
    author_email="info@gluu.org",
    description="Gluu cluster management API",
    long_description=__doc__,
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        "flask-restful-swagger",
        "Flask-RESTful",
        "Flask",
        "crochet",
        "docker-py==1.1.0",
        "salt==2014.7.0",
        "pyzmq==14.5.0",
        "tinydb",
        "jsonpickle",
        "netaddr",
    ],
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Environment :: Web Environment",
        "Framework :: Flask",
        "Intended Audience :: Developers",
        "License :: OSI Approved",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
        "Operating System :: POSIX :: Linux",
        "Topic :: Internet",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
    ],
    include_package_data=True,
    entry_points={
        "console_scripts": ["gluuapi=gluuapi.cli:main"],
    },
    tests_require=[
        "pytest-cov",
        "pytest",
    ],
    cmdclass={"test": PyTest},
)
