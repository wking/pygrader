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

from . import LOG as _LOG
from . import ENCODING as _ENCODING
from .model.assignment import Assignment as _Assignment
from .model.course import Course as _Course
from .model.grade import Grade as _Grade
from .model.person import Person as _Person
from .todo import newer


_DATE_REGEXP = _re.compile('^([^T]*)(T?)([^TZ+-.]*)([.]?[0-9]*)([+-][0-9:]*|Z?)$')


def load_course(basedir):
    _LOG.debug('loading course from {}'.format(basedir))
    config = _configparser.ConfigParser()
    config.read([_os_path.join(basedir, 'course.conf')])
    names = {}
    for option in ['assignments', 'professors', 'assistants', 'students']:
        names[option] = [
        a.strip() for a in config.get('course', option).split(',')]
    assignments = []
    for assignment in names['assignments']:
        _LOG.debug('loading assignment {}'.format(assignment))
        assignments.append(load_assignment(
                name=assignment, data=dict(config.items(assignment))))
    people = {}
    for group in ['professors', 'assistants', 'students']:
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
    grades = list(load_grades(basedir, assignments, people))
    return _Course(assignments=assignments, people=people, grades=grades)

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

def load_assignment(name, data):
    r"""Load an assignment from a ``dict``

    >>> from email.utils import formatdate
    >>> a = load_assignment(
    ...     name='Attendance 1',
    ...     data={'points': '1',
    ...           'weight': '0.1/2',
    ...           'due': '2011-10-04T00:00-04:00',
    ...           })
    >>> print('{0.name} (points: {0.points}, weight: {0.weight}, due: {0.due})'.format(a))
    Attendance 1 (points: 1, weight: 0.05, due: 1317700800)
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
    return _Assignment(name=name, points=points, weight=weight, due=due)

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
    >>> print('{0.name}: {0.emails}'.format(p))
    Gandalf: ['g@grey.edu', 'g@greyhavens.net'] | 0x0123456789ABCDEF
    >>> p = load_person(name='Gandalf')
    >>> print('{0.name}: {0.emails} | {0.pgp_key}'.format(p))
    Gandalf: None | None
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
    for assignment in assignments:
        for person in people:
            _LOG.debug('loading {} grade for {}'.format(assignment, person))
            path = assignment_path(basedir, assignment, person)
            gpath = _os_path.join(path, 'grade')
            try:
                g = _load_grade(_io.open(gpath, 'r', encoding=_ENCODING),
                                assignment, person)
            except IOError:
                continue
            #g.late = _os.stat(gpath).st_mtime > assignment.due
            g.late = _os_path.exists(_os_path.join(path, 'late'))
            npath = _os_path.join(path, 'notified')
            if _os_path.exists(npath):
                g.notified = newer(npath, gpath)
            else:
                g.notified = False
            yield g

def _load_grade(stream, assignment, person):
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
