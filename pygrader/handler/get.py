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

"""Handle information requests

Allow professors, TAs, and students to request grade information via email.
"""

from email.mime.message import MIMEMessage as _MIMEMessage
from email.mime.multipart import MIMEMultipart as _MIMEMultipart
import io as _io
import mailbox as _mailbox
import os.path as _os_path

import pgp_mime as _pgp_mime

from .. import LOG as _LOG
from ..email import construct_text_email as _construct_text_email
from ..email import construct_email as _construct_email
from ..extract_mime import message_time as _message_time
from ..storage import assignment_path as _assignment_path
from ..tabulate import tabulate as _tabulate
from ..template import _student_email as _student_email
from . import get_subject_assignment as _get_subject_assignment
from . import get_subject_student as _get_subject_student
from . import InvalidStudentSubject as _InvalidStudentSubject
from . import InvalidAssignmentSubject as _InvalidAssignmentSubject
from . import Response as _Response
from . import UnsignedMessage as _UnsignedMessage


def run(basedir, course, message, person, subject,
        trust_email_infrastructure=False, dry_run=False, **kwargs):
    """
    >>> from pgp_mime.email import encodedMIMEText
    >>> from ..model.grade import Grade
    >>> from ..test.course import StubCourse
    >>> from . import InvalidMessage, Response
    >>> course = StubCourse()
    >>> person = list(
    ...     course.course.find_people(email='bb@greyhavens.net'))[0]
    >>> message = encodedMIMEText('This text is not important.')
    >>> message['Message-ID'] = '<123.456@home.net>'
    >>> def process(**kwargs):
    ...     try:
    ...         run(**kwargs)
    ...     except Response as response:
    ...         print('respond with:')
    ...         print(response.message.as_string().replace('\\t', '  '))
    ...     except InvalidMessage as error:
    ...         print('{} error:'.format(type(error).__name__))
    ...         print(error)

    Unauthenticated messages are refused by default.

    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person, subject='[get]', max_late=0)
    UnsignedMessage error:
    unsigned message

    Although you can process them by setting the
    ``trust_email_infrastructure`` option.  This might not be too
    dangerous, since you're sending the email to the user's configured
    email address, not just replying blindly to the incoming email
    address.  With ``trust_email_infrastructure`` and missing user PGP
    keys, sysadmins on the intervening systems will be able to read
    our responses, possibly leaking grade information.  If leaking to
    sysadmins is considered unacceptable, you've can only email users
    who have registered PGP keys.

    Students without grades get a reasonable response.

    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person, subject='[get]', max_late=0,
    ...     trust_email_infrastructure=True)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Subject: No grades for Billy
    <BLANKLINE>
    We don't have any of your grades on file for this course.

    >>> message.authenticated = True
    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person, subject='[get]', max_late=0)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Subject: No grades for Billy
    <BLANKLINE>
    We don't have any of your grades on file for this course.

    Once we add a grade, they get details on all their grades for the
    course.

    >>> grade = Grade(
    ...     student=person,
    ...     assignment=course.course.assignment('Attendance 1'),
    ...     points=1)
    >>> course.course.grades.append(grade)
    >>> grade = Grade(
    ...     student=person,
    ...     assignment=course.course.assignment('Attendance 2'),
    ...     points=1)
    >>> course.course.grades.append(grade)
    >>> grade = Grade(
    ...     student=person,
    ...     assignment=course.course.assignment('Assignment 1'),
    ...     points=10, comment='Looks good.')
    >>> course.course.grades.append(grade)
    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person, subject='[get]', max_late=0)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Bilbo Baggins <bb@shire.org>
    Subject: Physics 101 grades
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    <BLANKLINE>
    Billy,
    <BLANKLINE>
    Grades:
      * Attendance 1:  1 out of 1 available points.
      * Attendance 2:  1 out of 1 available points.
      * Assignment 1:  10 out of 10 available points.
    <BLANKLINE>
    Comments:
    <BLANKLINE>
    Assignment 1
    <BLANKLINE>
    Looks good.
    <BLANKLINE>
    Yours,
    phys-101 robot
    --===============...==
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Description: OpenPGP digital signature
    Content-Type: application/pgp-signature; name="signature.asc"; charset="us-ascii"
    <BLANKLINE>
    -----BEGIN PGP SIGNATURE-----
    Version: GnuPG v2.0.19 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP SIGNATURE-----
    <BLANKLINE>
    --===============...==--

    Professors and TAs can request the grades for the whole course.

    >>> student = person
    >>> person = list(
    ...     course.course.find_people(email='eye@tower.edu'))[0]
    >>> person.pgp_key = None
    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person, subject='[get]', max_late=0)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Sauron <eye@tower.edu>
    Subject: All grades for Physics 101
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    <BLANKLINE>
    Student  Attendance 1  Attendance 2  Assignment 1
    Bilbo Baggins  1  1  10
    --
    Mean  1.00  1.00  10.00
    Std. Dev.  0.00  0.00  0.00
    <BLANKLINE>
    --===============...==
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Description: OpenPGP digital signature
    Content-Type: application/pgp-signature; name="signature.asc"; charset="us-ascii"
    <BLANKLINE>
    -----BEGIN PGP SIGNATURE-----
    Version: GnuPG v2.0.19 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP SIGNATURE-----
    <BLANKLINE>
    --===============...==--

    They can also request grades for a particular student.

    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person, subject='[get] {}'.format(student.name),
    ...     max_late=0)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Sauron <eye@tower.edu>
    Subject: Physics 101 grades for Bilbo Baggins
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    <BLANKLINE>
    Saury,
    <BLANKLINE>
    Grades:
      * Attendance 1:  1 out of 1 available points.
      * Attendance 2:  1 out of 1 available points.
      * Assignment 1:  10 out of 10 available points.
    <BLANKLINE>
    Comments:
    <BLANKLINE>
    Assignment 1
    <BLANKLINE>
    Looks good.
    <BLANKLINE>
    Yours,
    phys-101 robot
    --===============...==
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Description: OpenPGP digital signature
    Content-Type: application/pgp-signature; name="signature.asc"; charset="us-ascii"
    <BLANKLINE>
    -----BEGIN PGP SIGNATURE-----
    Version: GnuPG v2.0.19 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP SIGNATURE-----
    <BLANKLINE>
    --===============...==--

    They can also request every submission for a particular student on
    a particular assignment.  Lets give the student a submission email
    to see how that works.

    >>> from .submission import run as _handle_submission
    >>> submission = encodedMIMEText('The answer is 42.')
    >>> submission['Message-ID'] = '<789.abc@home.net>'
    >>> submission['Received'] = (
    ...     'from smtp.home.net (smtp.home.net [123.456.123.456]) '
    ...     'by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF '
    ...     'for <wking@tremily.us>; Sun, 09 Oct 2011 11:50:46 -0400 (EDT)')
    >>> try:
    ...     _handle_submission(
    ...         basedir=course.basedir, course=course.course,
    ...         message=submission, person=student,
    ...         subject='[submit] Assignment 1')
    ... except _Response:
    ...     pass

    Now lets request the submissions.

    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person,
    ...     subject='[get] {}, {}'.format(student.name, 'Assignment 1'),
    ...     max_late=0)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Sauron <eye@tower.edu>
    Subject: Physics 101 assignment submissions for Bilbo Baggins
    <BLANKLINE>
    --===============...==
    Content-Type: multipart/mixed; boundary="===============...=="
    MIME-Version: 1.0
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    <BLANKLINE>
    Physics 101 assignment submissions for Bilbo Baggins:
      * Assignment 1
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    <BLANKLINE>
    Assignment 1 grade: 10
    <BLANKLINE>
    Looks good.
    <BLANKLINE>
    --===============...==
    Content-Type: message/rfc822
    MIME-Version: 1.0
    <BLANKLINE>
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Message-ID: <789.abc@home.net>
    Received: from smtp.home.net (smtp.home.net [123.456.123.456]) by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF for <wking@tremily.us>; Sun, 09 Oct 2011 11:50:46 -0400 (EDT)
    <BLANKLINE>
    The answer is 42.
    --===============...==--
    --===============...==
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Description: OpenPGP digital signature
    Content-Type: application/pgp-signature; name="signature.asc"; charset="us-ascii"
    <BLANKLINE>
    -----BEGIN PGP SIGNATURE-----
    Version: GnuPG v2.0.19 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP SIGNATURE-----
    <BLANKLINE>
    --===============...==--

    >>> course.cleanup()
    """
    if trust_email_infrastructure:
        authenticated = True
    else:
        authenticated = (
            hasattr(message, 'authenticated') and message.authenticated)
    if not authenticated:
        raise _UnsignedMessage()
    if person.is_admin():
        email = _get_admin_email(
            basedir=basedir, course=course, person=person, subject=subject)
    elif 'students' in person.groups:
        email = _get_student_email(
            basedir=basedir, course=course, person=person)
    else:
        raise NotImplementedError(
            'strange groups {} for {}'.format(person.groups, person))
    raise _Response(message=email, complete=True)

def _get_student_email(basedir, course, person, student=None):
    if student is None:
        student = person
        targets = None
        _LOG.debug('construct student grade email about {} for {}'.format(
                student, student))
    else:
        targets = [person]
        _LOG.debug('construct student grade email about {} for {}'.format(
                student, person))
    emails = list(_student_email(
        basedir=basedir, author=course.robot, course=course,
        student=student, targets=targets, old=True))
    if len(emails) == 0:
        if targets is None:
            text = (
                "We don't have any of your grades on file for this course."
                )
        else:
            text = (
                "We don't have any grades for {} on file for this course."
                ).format(student.name)
        message = _pgp_mime.encodedMIMEText(text)
        message['Subject'] = 'No grades for {}'.format(student.alias())
        raise _Response(message=message, complete=True)
    elif len(emails) > 1:
        raise NotImplementedError(emails)
    email,callback = emails[0]
    # callback records notification, but don't bother here
    return email

def _get_student_submission_email(
    basedir, course, person, assignments, student):
    _LOG.debug('construct student submission email about {} {} for {}'.format(
            student, assignments, person))
    subject = '{} assignment submissions for {}'.format(
        course.name, student.name)
    text = '{}:\n  * {}\n'.format(
        subject, '\n  * '.join(a.name for a in assignments))
    message = _MIMEMultipart('mixed')
    message.attach(_pgp_mime.encodedMIMEText(text))
    for assignment in assignments:
        grade = course.grade(student=student, assignment=assignment)
        if grade is not None:
            text = '{} grade: {}\n'.format(assignment.name, grade.points)
            if grade.comment:
                text += '\n{}\n'.format(grade.comment)
            message.attach(_pgp_mime.encodedMIMEText(text))
        assignment_path = _assignment_path(basedir, assignment, student)
        mpath = _os_path.join(assignment_path, 'mail')
        try:
            mbox = _mailbox.Maildir(mpath, factory=None, create=False)
        except _mailbox.NoSuchMailboxError as e:
            pass
        else:
            messages = []
            for key,msg in mbox.items():
                subpath = mbox._lookup(key)
                if subpath.endswith('.gitignore'):
                    _LOG.debug('skipping non-message {}'.format(subpath))
                    continue
                messages.append(msg)
            messages.sort(key=_message_time)
            for msg in messages:
                message.attach(_MIMEMessage(msg))
    return _construct_email(
        author=course.robot, targets=[person], subject=subject,
        message=message)

def _get_admin_email(basedir, course, person, subject):
    try:
        student = _get_subject_student(course, subject)
    except _InvalidStudentSubject as error:
        if error.students:  # several students
            raise
        # no students
        _LOG.debug('construct course grades email for {}'.format(person))
        stream = _io.StringIO()
        _tabulate(
            course=course, statistics=True, stream=stream, use_color=False)
        text = stream.getvalue()
        email = _construct_text_email(
            author=course.robot, targets=[person],
            subject='All grades for {}'.format(course.name),
            text=text)
    else:  # a single student
        try:
            assignment = _get_subject_assignment(course, subject)
        except _InvalidAssignmentSubject as error:
            if error.assignments:  # several assignments
                email = _get_student_submission_email(
                    basedir=basedir, course=course, person=person,
                    student=student, assignments=error.assignments)
            else: # no assignments
                email = _get_student_email(
                    basedir=basedir, course=course, person=person,
                    student=student)
        else:  # a single assignment
            email = _get_student_submission_email(
                basedir=basedir, course=course, person=person, student=student,
                assignments=[assignment])
    return email
