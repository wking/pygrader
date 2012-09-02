# Copyright (C) 2012 W. Trevor King <wking@tremily.us>
#
# This file is part of pygrader.
#
# pygrader is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# pygrader is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# pygrader.  If not, see <http://www.gnu.org/licenses/>.

import logging as _logging
import sys as _sys


# Define ANSI escape sequences for colors
_COLORS = [
    'black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white']

USE_COLOR = True
GOOD_DEBUG = _logging.DEBUG + 2
BAD_DEBUG = _logging.DEBUG + 4


def standard_colors(use_color=None):
    """Return a list of standard colors

    >>> highlight,lowlight,good,bad = standard_colors()
    >>> (highlight,lowlight,good,bad)
    (None, 'blue', 'green', 'red')
    """
    if use_color is None:
        use_color = USE_COLOR
    if use_color:
        highlight = None
        lowlight = 'blue'
        good = 'green'
        bad = 'red'
    else:
        highlight = lowlight = good = bad = None
    return (highlight, lowlight, good, bad)

def _ansi_color_code(color):
    r"""Return the appropriate ANSI escape sequence for `color`

    >>> _ansi_color_code('blue')
    '\x1b[34m'
    >>> _ansi_color_code(None)
    '\x1b[0m'
    """
    if color is None:
        return '\033[0m'
    return '\033[3%dm' % (_COLORS.index(color))

def color_string(string, color=None):
    r"""Wrap a string in ANSI escape sequences for coloring

    >>> color_string('Hello world', 'red')
    '\x1b[31mHello world\x1b[0m'
    >>> color_string('Hello world', None)
    'Hello world'

    It also works with non-unicode input:

    >>> color_string('Hello world', 'red')
    '\x1b[31mHello world\x1b[0m'
    """
    ret = []
    if color:
        ret.append(_ansi_color_code(color))
    ret.append(string)
    if color:
        ret.append(_ansi_color_code(None))
    sep = ''
    if isinstance(string, str):  # i.e., not unicode
        ret = [str(x) for x in ret]
        sep = ''
    return sep.join(ret)

def write_color(string, color=None, stream=None):
    r"""Write a colored `string` to `stream`

    If `stream` is `None`, it defaults to stdout.

    >>> write_color('Hello world\n')
    Hello world

    >>> from io import StringIO
    >>> stream = StringIO()
    >>> write_color('Hello world\n', 'red', stream)
    >>> stream.getvalue()
    '\x1b[31mHello world\n\x1b[0m'
    """
    if stream is None:
        stream = _sys.stdout
    stream.write(color_string(string=string, color=color))
    stream.flush()


class ColoredFormatter (_logging.Formatter):
    def __init__(self, *args, **kwargs):
        super(ColoredFormatter, self).__init__(*args, **kwargs)
        self.colored = None  # `None` to use USE_COLOR; True/False to override

    def format(self, record):
        s = super(ColoredFormatter, self).format(record)
        if self.colored or (self.colored is None and USE_COLOR):
            highlight,lowlight,good,bad = standard_colors()
            if record.levelno <= _logging.DEBUG:
                color = lowlight
            elif record.levelno <= GOOD_DEBUG:
                color = good
            elif record.levelno <= BAD_DEBUG:
                color = bad
            elif record.levelno <= _logging.INFO:
                color = highlight
            else:
                color = bad
            return color_string(string=s, color=color)
        return s
