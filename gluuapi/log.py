# -*- coding: utf-8 -*-
# The MIT License (MIT)
#
# Copyright (c) 2015 Gluu
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import os
import logging
import tempfile


def create_file_logger(filepath="", log_level=logging.DEBUG, name=""):
    filepath = filepath or tempfile.mkstemp()[1]
    logger = logging.getLogger(name or __name__)
    logger.setLevel(log_level)
    ch = logging.FileHandler(filepath)
    ch.setLevel(log_level)
    fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s  - %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def create_tempfile(suffix="", prefix="tmp", dir_="/tmp"):
    if not os.path.exists(dir_):
        os.makedirs(dir_)

    _, fp = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir_)
    return fp
