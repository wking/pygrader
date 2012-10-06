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

import io as _io

from jinja2 import Template

from . import LOG as _LOG
from .email import construct_text_email as _construct_text_email
from .email import send_emails as _send_emails
from .storage import set_notified as _set_notified
from .tabulate import tabulate as _tabulate


ASSIGNMENT_TEMPLATE = Template("""
{{ grade.student.alias() }},

You got {{ grade.points }} out of {{ grade.assignment.points }} available points on {{ grade.assignment.name }}.
{% if grade.comment %}
{{ grade.comment }}
{% endif %}
Yours,
{{ author.alias() }}
""".strip())
#{{ grade.comment|wordwrap }}

STUDENT_TEMPLATE = Template("""
{{ target }},

Grades:
{%- for grade in grades %}
  * {{ grade.assignment.name }}:\t{{ grade.points }} out of {{ grade.assignment.points }} available points.
{%- endfor %}

Comments:
{%- for grade in grades -%}{% if grade.comment %}

{{ grade.assignment.name }}

{{ grade.comment }}
{%- endif %}{% endfor %}

Yours,
{{ author.alias() }}
""".strip())

COURSE_TEMPLATE = Template("""
{{ target }},

Here are the (tab delimited) course grades to date:

{{ table }}
The available points (and weights) for each assignment are:
{%- for assignment in course.active_assignments() %}
  * {{ assignment.name }}:\t{{ assignment.points }}\t{{ assignment.weight }}
{%- endfor %}

Yours,
{{ author.alias() }}
""".strip())


class NotifiedCallback (object):
    """A callback for marking notifications with `_send_emails`
    """
    def __init__(self, basedir, grades):
        self.basedir = basedir
        self.grades = grades

    def __call__(self, success):
        if success:
            for grade in self.grades:
                _set_notified(basedir=self.basedir, grade=grade)


def join_with_and(strings):
    """Join a list of strings.

    >>> join_with_and(['a','b','c'])
    'a, b, and c'
    >>> join_with_and(['a','b'])
    'a and b'
    >>> join_with_and(['a'])
    'a'
    """
    ret = [strings[0]]
    for i,s in enumerate(strings[1:]):
        if len(strings) > 2:
            ret.append(', ')
        else:
            ret.append(' ')
        if i == len(strings)-2:
            ret.append('and ')
        ret.append(s)
    return ''.join(ret)

def assignment_email(basedir, author, course, assignment, student=None,
                     cc=None, smtp=None, debug_target=None, dry_run=False):
    """Send each student an email with their grade on `assignment`
    """
    _send_emails(
        emails=_assignment_email(
            basedir=basedir, author=author, course=course,
            assignment=assignment, student=student, cc=cc),
        smtp=smtp, debug_target=debug_target, dry_run=dry_run)

def _assignment_email(basedir, author, course, assignment, student=None,
                      cc=None):
    """Iterate through composed assignment `Message`\s
    """
    if student:
        students = [student]
    else:
        students = course.people
    for student in students:
        try:
            grade = course.grade(student=student, assignment=assignment)
        except ValueError:
            continue
        if grade.notified:
            continue
        yield (construct_assignment_email(author=author, grade=grade, cc=cc),
               NotifiedCallback(basedir=basedir, grades=[grade]))

def construct_assignment_email(author, grade, cc=None):
    """Construct a `Message` notfiying a student of `grade`

    >>> from pygrader.model.person import Person
    >>> from pygrader.model.assignment import Assignment
    >>> from pygrader.model.grade import Grade
    >>> author = Person(name='Jack', emails=['a@b.net'])
    >>> student = Person(name='Jill', emails=['c@d.net'])
    >>> assignment = Assignment(name='Exam 1', points=3)
    >>> grade = Grade(student=student, assignment=assignment, points=2)
    >>> msg = construct_assignment_email(author=author, grade=grade)
    >>> print(msg.as_string())  # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Date: ...
    From: Jack <a@b.net>
    Reply-to: Jack <a@b.net>
    To: Jill <c@d.net>
    Subject: Your Exam 1 grade
    <BLANKLINE>
    Jill,
    <BLANKLINE>
    You got 2 out of 3 available points on Exam 1.
    <BLANKLINE>
    Yours,
    Jack

    >>> grade.comment = ('Some comment bla bla bla.').strip()
    >>> msg = construct_assignment_email(author=author, grade=grade)
    >>> print(msg.as_string())  # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Date: ...
    From: Jack <a@b.net>
    Reply-to: Jack <a@b.net>
    To: Jill <c@d.net>
    Subject: Your Exam 1 grade
    <BLANKLINE>
    Jill,
    <BLANKLINE>
    You got 2 out of 3 available points on Exam 1.
    <BLANKLINE>
    Some comment bla bla bla.
    <BLANKLINE>
    Yours,
    Jack
    """
    return _construct_text_email(
        author=author, targets=[grade.student], cc=cc,
        subject='Your {} grade'.format(grade.assignment.name),
        text=ASSIGNMENT_TEMPLATE.render(author=author, grade=grade))

def student_email(basedir, author, course, student=None, cc=None, old=False,
                  smtp=None, debug_target=None, dry_run=False):
    """Send each student an email with their grade to date
    """
    _send_emails(
        emails=_student_email(
            basedir=basedir, author=author, course=course, student=student,
            cc=cc, old=old),
        smtp=smtp, debug_target=debug_target, dry_run=dry_run)

def _student_email(basedir, author, course, student=None, targets=None, cc=None, old=False):
    """Iterate through composed student `Message`\s
    """
    if student:
        students = [student]
    else:
        students = course.people
    for student in students:
        grades = [g for g in course.grades if g.student == student]
        if not old:
            grades = [g for g in grades if not g.notified]
        if not grades:
            continue
        yield (construct_student_email(
                author=author, course=course, grades=grades, targets=targets,
                cc=cc),
               NotifiedCallback(basedir=basedir, grades=grades))

def construct_student_email(author, course, grades, targets=None, cc=None):
    """Construct a `Message` notfiying a student of `grade`

    >>> from pygrader.model.person import Person
    >>> from pygrader.model.assignment import Assignment
    >>> from pygrader.model.course import Course
    >>> from pygrader.model.grade import Grade
    >>> course = Course(name='Physics 101')
    >>> author = Person(name='Jack', emails=['a@b.net'])
    >>> student = Person(name='Jill', emails=['c@d.net'])
    >>> grades = []
    >>> for name,points in [('Homework 1', 3), ('Exam 1', 10)]:
    ...     assignment = Assignment(name=name, points=points)
    ...     grade = Grade(
    ...         student=student, assignment=assignment,
    ...         points=int(points/2.0))
    ...     grades.append(grade)
    >>> msg = construct_student_email(
    ...     author=author, course=course, grades=grades)
    >>> print(msg.as_string().replace('\\t', '  '))
    ... # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Date: ...
    From: Jack <a@b.net>
    Reply-to: Jack <a@b.net>
    To: Jill <c@d.net>
    Subject: Physics 101 grades
    <BLANKLINE>
    Jill,
    <BLANKLINE>
    Grades:
      * Exam 1:  5 out of 10 available points.
      * Homework 1:  1 out of 3 available points.
    <BLANKLINE>
    Comments:
    <BLANKLINE>
    Yours,
    Jack

    >>> grades[0].comment = ('Bla bla bla.  '*20).strip()
    >>> grades[1].comment = ('Hello world')
    >>> msg = construct_student_email(
    ...     author=author, course=course, grades=grades)
    >>> print(msg.as_string().replace('\\t', '  '))
    ... # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Date: ...
    From: Jack <a@b.net>
    Reply-to: Jack <a@b.net>
    To: Jill <c@d.net>
    Subject: Physics 101 grades
    <BLANKLINE>
    Jill,
    <BLANKLINE>
    Grades:
      * Exam 1:  5 out of 10 available points.
      * Homework 1:  1 out of 3 available points.
    <BLANKLINE>
    Comments:
    <BLANKLINE>
    Exam 1
    <BLANKLINE>
    Hello world
    <BLANKLINE>
    Homework 1
    <BLANKLINE>
    Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.  Bla bla bla.
    <BLANKLINE>
    Yours,
    Jack

    >>> grades[0].comment = 'Work harder!'
    >>> grades[1].comment = None
    >>> msg = construct_student_email(
    ...     author=author, course=course, grades=grades)
    >>> print(msg.as_string().replace('\\t', '  '))
    ... # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Date: ...
    From: Jack <a@b.net>
    Reply-to: Jack <a@b.net>
    To: Jill <c@d.net>
    Subject: Physics 101 grades
    <BLANKLINE>
    Jill,
    <BLANKLINE>
    Grades:
      * Exam 1:  5 out of 10 available points.
      * Homework 1:  1 out of 3 available points.
    <BLANKLINE>
    Comments:
    <BLANKLINE>
    Homework 1
    <BLANKLINE>
    Work harder!
    <BLANKLINE>
    Yours,
    Jack

    You can also send the student grades to alternative targets:

    >>> prof = Person(name='H.D.', emails=['hd@wall.net'])
    >>> msg = construct_student_email(
    ...     author=author, course=course, grades=grades, targets=[prof])
    >>> print(msg.as_string().replace('\\t', '  '))
    ... # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Date: ...
    From: Jack <a@b.net>
    Reply-to: Jack <a@b.net>
    To: "H.D." <hd@wall.net>
    Subject: Physics 101 grades for Jill
    <BLANKLINE>
    H.D.,
    <BLANKLINE>
    Grades:
      * Exam 1:  5 out of 10 available points.
      * Homework 1:  1 out of 3 available points.
    <BLANKLINE>
    Comments:
    <BLANKLINE>
    Homework 1
    <BLANKLINE>
    Work harder!
    <BLANKLINE>
    Yours,
    Jack
    """
    students = set(g.student for g in grades)
    assert len(students) == 1, students
    student = students.pop()
    subject = '{} grades'.format(course.name)
    if not targets:
        targets = [student]
    else:
        subject += ' for {}'.format(student.name)
    target = join_with_and([t.alias() for t in targets])
    return _construct_text_email(
        author=author, targets=targets, cc=cc, subject=subject,
        text=STUDENT_TEMPLATE.render(
            author=author, target=target, grades=sorted(grades)))

def course_email(basedir, author, course, targets, assignment=None,
                 student=None, cc=None, smtp=None, debug_target=None,
                 dry_run=False):
    """Send the professor an email with all student grades to date
    """
    _send_emails(
        emails=_course_email(
            basedir=basedir, author=author, course=course, targets=targets,
            assignment=assignment, student=student, cc=cc),
        smtp=smtp, debug_target=debug_target, dry_run=dry_run)

def _course_email(basedir, author, course, targets, assignment=None,
                  student=None, cc=None):
    """Iterate through composed course `Message`\s
    """
    yield (construct_course_email(
            author=author, course=course, targets=targets, cc=cc),
           None)

def construct_course_email(author, course, targets, cc=None):
    """Construct a `Message` notfiying a professor of all grades to date

    >>> from pygrader.model.person import Person
    >>> from pygrader.model.assignment import Assignment
    >>> from pygrader.model.grade import Grade
    >>> from pygrader.model.course import Course
    >>> author = Person(name='Jack', emails=['a@b.net'])
    >>> student = Person(name='Jill', emails=['c@d.net'])
    >>> prof = Person(name='H.D.', emails=['hd@wall.net'])
    >>> grades = []
    >>> for name,points in [('Homework 1', 3), ('Exam 1', 10)]:
    ...     assignment = Assignment(name=name, points=points, weight=0.5)
    ...     grade = Grade(
    ...         student=student, assignment=assignment,
    ...         points=int(points/2.0))
    ...     grades.append(grade)
    >>> assignments = [g.assignment for g in grades]
    >>> course = Course(
    ...     assignments=assignments, people=[student], grades=grades)
    >>> msg = construct_course_email(
    ...     author=author, course=course, targets=[prof])
    >>> print(msg.as_string().replace('\\t', '  '))
    ... # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Date: ...
    From: Jack <a@b.net>
    Reply-to: Jack <a@b.net>
    To: "H.D." <hd@wall.net>
    Subject: Course grades
    <BLANKLINE>
    H.D.,
    <BLANKLINE>
    Here are the (tab delimited) course grades to date:
    <BLANKLINE>
    Student  Exam 1  Homework 1  Total
    Jill  5  1  0.416...
    --
    Mean  5.00  1.00  0.416...
    Std. Dev.  0.00  0.00  0.0
    <BLANKLINE>
    The available points (and weights) for each assignment are:
      * Exam 1:  10  0.5
      * Homework 1:  3  0.5
    <BLANKLINE>
    Yours,
    Jack
    """
    target = join_with_and([t.alias() for t in targets])
    table = _io.StringIO()
    _tabulate(course=course, statistics=True, stream=table, use_color=False)
    return _construct_text_email(
        author=author, targets=targets, cc=cc,
        subject='Course grades',
        text=COURSE_TEMPLATE.render(
            author=author, course=course, target=target,
            table=table.getvalue()))
