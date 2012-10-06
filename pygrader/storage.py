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

from __future__ import absolute_import

import calendar as _calendar
import configparser as _configparser
import email.utils as _email_utils
import io as _io
import os as _os
import os.path as _os_path
import re as _re
import sys as _sys
import time as _time

import pygrader as _pygrader
from . import LOG as _LOG
from .model.assignment import Assignment as _Assignment
from .model.course import Course as _Course
from .model.grade import Grade as _Grade
from .model.person import Person as _Person
from .todo import newer


_DATE_REGEXP = _re.compile('^([^T]*)(T?)([^TZ+-.]*)([.]?[0-9]*)([+-][0-9:]*|Z?)$')


def load_course(basedir):
    """Load a course directory.

    >>> from pygrader.test.course import StubCourse
    >>> stub_course = StubCourse(load=False)
    >>> course = load_course(basedir=stub_course.basedir)
    >>> course.name
    'Physics 101'
    >>> course.assignments  # doctest: +ELLIPSIS
    [<pygrader.model.assignment.Assignment object at 0x...>, ...]
    >>> course.people  # doctest: +ELLIPSIS
    [<pygrader.model.person.Person object at 0x...>, ...]
    >>> course.grades
    []
    >>> print(course.robot)
    <Person Robot101>
    >>> stub_course.cleanup()
    """
    _LOG.debug('loading course from {}'.format(basedir))
    config = _configparser.ConfigParser()
    config.read([_os_path.join(basedir, 'course.conf')],
                encoding=_pygrader.ENCODING)
    name = config.get('course', 'name')
    names = {'robot': [config.get('course', 'robot').strip()]}
    for option in ['assignments', 'professors', 'assistants', 'students']:
        names[option] = [
            a.strip() for a in
            config.get('course', option, fallback='').split(',')]
        while '' in names[option]:
            names[option].remove('')
    assignments = []
    for assignment in names['assignments']:
        _LOG.debug('loading assignment {}'.format(assignment))
        assignments.append(load_assignment(
                name=assignment, data=dict(config.items(assignment))))
    people = {}
    for group in ['robot', 'professors', 'assistants', 'students']:
        for person in names[group]:
            if person in people:
                _LOG.debug('adding person {} to group {}'.format(
                        person, group))
                people[person].groups.append(group)
            else:
                _LOG.debug('loading person {} in group {}'.format(
                        person, group))
                people[person] = load_person(
                    name=person, data=dict(config.items(person)))
                people[person].groups = [group]
    people = people.values()
    robot = [p for p in people if 'robot' in p.groups][0]
    grades = list(load_grades(basedir, assignments, people))
    return _Course(
        name=name, assignments=assignments, people=people, grades=grades,
        robot=robot)

def parse_date(string):
    """Parse dates given using the W3C DTF profile of ISO 8601.

    The following are legal formats::

      YYYY (e.g. 2000)
      YYYY-MM (e.g. 2000-02)
      YYYY-MM-DD (e.g. 2000-02-12)
      YYYY-MM-DDThh:mmTZD (e.g. 2000-02-12T06:05+05:30)
      YYYY-MM-DDThh:mm:ssTZD (e.g. 2000-02-12T06:05:30+05:30)
      YYYY-MM-DDThh:mm:ss.sTZD (e.g. 2000-02-12T06:05:30.45+05:30)

    Note that the TZD can be either the capital letter `Z` to indicate
    UTC time, a string in the format +hh:mm to indicate a local time
    expressed with a time zone hh hours and mm minutes ahead of UTC or
    -hh:mm to indicate a local time expressed with a time zone hh
    hours and mm minutes behind UTC.

    >>> import calendar
    >>> import email.utils
    >>> import time
    >>> ref = calendar.timegm(time.strptime('2000', '%Y'))
    >>> y = parse_date('2000')
    >>> y - ref  # seconds between y and ref
    0
    >>> ym = parse_date('2000-02')
    >>> (ym - y)/(3600.*24)  # days between ym and y
    31.0
    >>> ymd = parse_date('2000-02-12')
    >>> (ymd - ym)/(3600.*24)  # days between ymd and ym
    11.0
    >>> ymdhm = parse_date('2000-02-12T06:05+05:30')
    >>> (ymdhm - ymd)/60.  # minutes between ymdhm and ymd
    35.0
    >>> (ymdhm - parse_date('2000-02-12T06:05Z'))/3600.
    -5.5
    >>> ymdhms = parse_date('2000-02-12T06:05:30+05:30')
    >>> ymdhms - ymdhm
    30
    >>> (ymdhms - parse_date('2000-02-12T06:05:30Z'))/3600.
    -5.5
    >>> ymdhms_ms = parse_date('2000-02-12T06:05:30.45+05:30')
    >>> ymdhms_ms - ymdhms  # doctest: +ELLIPSIS
    0.45000...
    >>> (ymdhms_ms - parse_date('2000-02-12T06:05:30.45Z'))/3600.
    -5.5
    >>> p = parse_date('1994-11-05T08:15:30-05:00')
    >>> email.utils.formatdate(p, localtime=True)
    'Sat, 05 Nov 1994 08:15:30 -0500'
    >>> p - parse_date('1994-11-05T13:15:30Z')
    0
    """
    m = _DATE_REGEXP.match(string)
    if not m:
        raise ValueError(string)
    date,t,time,ms,zone = m.groups()
    ret = None
    if t:
        date += 'T' + time
    error = None
    for fmt in ['%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M',
                '%Y-%m-%d',
                '%Y-%m',
                '%Y',
                ]:
        try:
            ret = _time.strptime(date, fmt)
        except ValueError as e:
            error = e
        else:
            break
    if ret is None:
        raise error
    ret = list(ret)
    ret[-1] = 0  # don't use daylight savings time
    ret = _calendar.timegm(ret)
    if ms:
        ret += float(ms)
    if zone and zone != 'Z':
        sign = int(zone[1] + '1')
        hour,minute = map(int, zone.split(':', 1))
        offset = sign*(3600*hour + 60*minute)
        ret -= offset
    return ret

def parse_boolean(value):
    """Convert a boolean string into ``True`` or ``False``.

    Supports the same values as ``RawConfigParser``

    >>> parse_boolean('YES')
    True
    >>> parse_boolean('Yes')
    True
    >>> parse_boolean('tRuE')
    True
    >>> parse_boolean('False')
    False
    >>> parse_boolean('FALSE')
    False
    >>> parse_boolean('no')
    False
    >>> parse_boolean('none')
    Traceback (most recent call last):
      ...
    ValueError: Not a boolean: none
    >>> parse_boolean('')  # doctest: +NORMALIZE_WHITESPACE
    Traceback (most recent call last):
      ...
    ValueError: Not a boolean:

    It passes through boolean inputs without modification (so you
    don't have to use strings for default values):

    >>> parse_boolean({}.get('my-option', True))
    True
    >>> parse_boolean({}.get('my-option', False))
    False
    """
    if value in [True, False]:
        return value
    # Using an underscored method is hackish, but it should be fairly stable.
    p = _configparser.RawConfigParser()
    return p._convert_to_boolean(value)

def load_assignment(name, data):
    r"""Load an assignment from a ``dict``

    >>> from email.utils import formatdate
    >>> a = load_assignment(
    ...     name='Attendance 1',
    ...     data={'points': '1',
    ...           'weight': '0.1/2',
    ...           'due': '2011-10-04T00:00-04:00',
    ...           'submittable': 'yes',
    ...           })
    >>> print(('{0.name} (points: {0.points}, weight: {0.weight}, '
    ...        'due: {0.due}, submittable: {0.submittable})').format(a))
    Attendance 1 (points: 1, weight: 0.05, due: 1317700800, submittable: True)
    >>> print(formatdate(a.due, localtime=True))
    Tue, 04 Oct 2011 00:00:00 -0400
    """
    points = int(data['points'])
    wterms = data['weight'].split('/')
    if len(wterms) == 1:
        weight = float(wterms[0])
    else:
        assert len(wterms) == 2, wterms
        weight = float(wterms[0])/float(wterms[1])
    due = parse_date(data['due'])
    submittable = parse_boolean(data.get('submittable', False))
    return _Assignment(
        name=name, points=points, weight=weight, due=due,
        submittable=submittable)

def load_person(name, data={}):
    r"""Load a person from a ``dict``

    >>> from io import StringIO
    >>> stream = StringIO('''#comment line
    ... Tom Bombadil <tbomb@oldforest.net>  # post address comment
    ... Tom Bombadil <yellow.boots@oldforest.net>
    ... Goldberry <gb@oldforest.net>
    ... ''')

    >>> p = load_person(
    ...     name='Gandalf',
    ...     data={'nickname': 'G-Man',
    ...           'emails': 'g@grey.edu, g@greyhavens.net',
    ...           'pgp-key': '0x0123456789ABCDEF',
    ...           })
    >>> print('{0.name}: {0.emails} | {0.pgp_key}'.format(p))
    Gandalf: ['g@grey.edu', 'g@greyhavens.net'] | 0x0123456789ABCDEF
    >>> p = load_person(name='Gandalf')
    >>> print('{0.name}: {0.emails} | {0.pgp_key}'.format(p))
    Gandalf: [] | None
    """
    kwargs = {}
    emails = [x.strip() for x in data.get('emails', '').split(',')]
    emails = list(filter(bool, emails))  # remove blank emails
    if emails:
        kwargs['emails'] = emails
    nickname = data.get('nickname', None)
    if nickname:
        kwargs['aliases'] = [nickname]
    pgp_key = data.get('pgp-key', None)
    if pgp_key:
        kwargs['pgp_key'] = pgp_key
    return _Person(name=name, **kwargs)

def load_grades(basedir, assignments, people):
    "Load all grades in a course directory."
    for assignment in assignments:
        for person in people:
            if 'students' in person.groups:
                try:
                    yield load_grade(basedir, assignment, person)
                except IOError:
                    continue

def load_grade(basedir, assignment, person):
    "Load a single grade from a course directory."
    _LOG.debug('loading {} grade for {}'.format(assignment, person))
    path = assignment_path(basedir, assignment, person)
    gpath = _os_path.join(path, 'grade')
    g = parse_grade(_io.open(gpath, 'r', encoding=_pygrader.ENCODING),
                    assignment, person)
    #g.late = _os.stat(gpath).st_mtime > assignment.due
    g.late = _os_path.exists(_os_path.join(path, 'late'))
    npath = _os_path.join(path, 'notified')
    if _os_path.exists(npath):
        g.notified = newer(npath, gpath)
    else:
        g.notified = False
    return g

def parse_grade(stream, assignment, person):
    "Parse the points and comment from a grade stream."
    try:
        points = float(stream.readline())
    except ValueError:
        _sys.stderr.write('failure reading {}, {}\n'.format(
                assignment.name, person.name))
        raise
    comment = stream.read().strip() or None
    return _Grade(
        student=person, assignment=assignment, points=points, comment=comment)

def assignment_path(basedir, assignment, person):
    return _os_path.join(basedir,
                  _filesystem_name(person.name),
                  _filesystem_name(assignment.name))

def _filesystem_name(name):
    for a,b in [(' ', '_'), ('.', ''), ("'", ''), ('"', '')]:
        name = name.replace(a, b)
    return name

def set_notified(basedir, grade):
    """Mark `grade.student` as notified about `grade`
    """
    path = assignment_path(
        basedir=basedir, assignment=grade.assignment, person=grade.student)
    npath = _os_path.join(path, 'notified')
    _touch(npath)

def set_late(basedir, assignment, person):
    path = assignment_path(
        basedir=basedir, assignment=assignment, person=person)
    Lpath = _os_path.join(path, 'late')
    _touch(Lpath)

def save_grade(basedir, grade):
    "Save a grade into a course directory"
    path = assignment_path(
        basedir=basedir, assignment=grade.assignment, person=grade.student)
    if not _os_path.isdir(path):
        _os.makedirs(path)
    gpath = _os_path.join(path, 'grade')
    with _io.open(gpath, 'w', encoding=_pygrader.ENCODING) as f:
        f.write('{}\n'.format(grade.points))
        if grade.comment:
            f.write('\n{}\n'.format(grade.comment.strip()))
    set_notified(basedir=basedir, grade=grade)
    set_late(
        basedir=basedir, assignment=grade.assignment, person=grade.student)

def _touch(path):
    """Touch a file (`path` is created if it doesn't already exist)

    Also updates the access and modification times to the current
    time.

    >>> from os import listdir, rmdir, unlink
    >>> from os.path import join
    >>> from tempfile import mkdtemp
    >>> d = mkdtemp(prefix='pygrader')
    >>> listdir(d)
    []
    >>> p = join(d, 'touched')
    >>> _touch(p)
    >>> listdir(d)
    ['touched']
    >>> _touch(p)
    >>> unlink(p)
    >>> rmdir(d)
    """
    with open(path, 'a') as f:
        pass
    _os.utime(path, None)

def initialize(basedir, course, dry_run=False, **kwargs):
    """Stub out the directory tree based on the course configuration.
    """
    for person in course.people:
        for assignment in course.assignments:
            path = assignment_path(basedir, assignment, person)
            if dry_run:  # we'll need to guess if mkdirs would work
                if not _os_path.exists(path):
                    _LOG.debug('creating {}'.format(path))
            else:
                try:
                    _os.makedirs(path)
                except OSError:
                    continue
                else:
                    _LOG.debug('creating {}'.format(path))
