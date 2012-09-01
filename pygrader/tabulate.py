# Copyright (C) 2012 W. Trevor King <wking@drexel.edu>
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

import sys as _sys

try:
    import numpy as _numpy
except ImportError:
    raise  # TODO work around

from .color import standard_colors as _standard_colors
from .color import write_color as _write_color


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
                gs = _numpy.array([g.points for g in grades])
                if stat == 'Mean':
                    sval = gs.mean()
                elif stat == 'Std. Dev.':
                    sval = gs.std()
                else:
                    raise NotImplementedError(stat)
                string = '\t{:.2f}'.format(sval)
                _write_color(string=string, color=color, stream=stream)
            if len(assignments) == len(course.assignments):
                gs = _numpy.array([course.total(s) for s in students])
                if stat == 'Mean':
                    sval = gs.mean()
                elif stat == 'Std. Dev.':
                    sval = gs.std()
                else:
                    raise NotImplementedError(stat)
                string = '\t{}'.format(sval)
                color = colors[(i+2)%len(colors)]
                _write_color(string=string, color=color, stream=stream)
            _write_color(string='\n', stream=stream)
