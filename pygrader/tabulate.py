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

import math as _math  # for numpy workarounds and testing
import sys as _sys

_numpy_import_error = None
try:
    import numpy as _numpy
except ImportError as e:
    _numpy = None
    _numpy_import_error = e

from . import LOG as _LOG
from .color import standard_colors as _standard_colors
from .color import write_color as _write_color


def _mean(iterable):  # missing-numpy workaround
    """Return the mean of a list of items.

    >>> print(_mean([0,1,2,3,4,5,6]))
    3.0
    """
    length = len(iterable)
    return sum(iterable) / float(length)

def _std(iterable):  # missing-numpy workaround
    """Return the standard deviation of a list of items.

    >>> print(_std([0,1,2,3,4,5,6]))
    2.0
    """
    length = len(iterable)
    m = _mean(iterable)
    return _math.sqrt(sum((x-m)**2 for x in iterable) / length)

if _numpy is None:
    _statistics_container = list
else:
    _statistics_container = _numpy.array

def _statistic(iterable, statistic):
    """Calculate statistics on an list of numbers
    """
    global _numpy_import_error
    if _numpy_import_error:
        assert _numpy_import_error is not None
        _LOG.warning('error importing numpy, falling back to workarounds')
        _LOG.warning(str(_numpy_import_error))
        _numpy_import_error = None
    if statistic == 'Mean':
        if _numpy is None:  # work around missing numpy
            return _mean(iterable)
        else:
            return gs.mean()
    elif statistic == 'Std. Dev.':
        if _numpy is None:  # work around missing numpy
            return _std(iterable)
        else:
            return gs.std()
    else:
        raise NotImplementedError(statistic)

def tabulate(course, statistics=False, stream=None, use_color=None, **kwargs):
    """Return a table of student's grades to date
    """
    if stream is None:
        stream = _sys.stdout
    highlight,lowlight,good,bad = _standard_colors(use_color=use_color)
    colors = [highlight, lowlight]
    assignments = sorted(set(
            grade.assignment for grade in course.grades))
    students = sorted(set(grade.student for grade in course.grades))
    _write_color(string='Student', color=colors[0], stream=stream)
    for i,assignment in enumerate(assignments):
        string = '\t{}'.format(assignment.name)
        color = colors[(i+1)%len(colors)]
        _write_color(string=string, color=color, stream=stream)
    if len(assignments) == len(course.assignments):
        string = '\t{}'.format('Total')
        color = colors[(i+2)%len(colors)]
        _write_color(string=string, color=color, stream=stream)
    _write_color(string='\n', stream=stream)
    for student in students:
        _write_color(string=student.name, color=colors[0], stream=stream)
        for i,assignment in enumerate(assignments):
            try:
                grade = course.grade(student=student, assignment=assignment)
                gs = str(grade.points)
            except ValueError:
                gs = '-'
            string = '\t{}'.format(gs)
            color = colors[(i+1)%len(colors)]
            _write_color(string=string, color=color, stream=stream)
        if len(assignments) == len(course.assignments):
            string = '\t{}'.format(course.total(student))
            color = colors[(i+2)%len(colors)]
            _write_color(string=string, color=color, stream=stream)
        _write_color(string='\n', stream=stream)
    if statistics:
        _write_color(string='--\n', stream=stream)
        for stat in ['Mean', 'Std. Dev.']:
            _write_color(string=stat, color=colors[0], stream=stream)
            for i,assignment in enumerate(assignments):
                color = colors[(i+1)%len(colors)]
                grades = [g for g in course.grades
                          if g.assignment == assignment]
                gs = _statistics_container([g.points for g in grades])
                sval = _statistic(gs, statistic=stat)
                string = '\t{:.2f}'.format(sval)
                _write_color(string=string, color=color, stream=stream)
            if len(assignments) == len(course.assignments):
                gs = _statistics_container([course.total(s) for s in students])
                sval = _statistic(gs, statistic=stat)
                string = '\t{}'.format(sval)
                color = colors[(i+2)%len(colors)]
                _write_color(string=string, color=color, stream=stream)
            _write_color(string='\n', stream=stream)
