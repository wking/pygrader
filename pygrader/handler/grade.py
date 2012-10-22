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

"""Handle grade assignment

Allow professors and TAs to assign grades via email.
"""

import io as _io
import mailbox as _mailbox
import os.path as _os_path

import pgp_mime as _pgp_mime

from .. import LOG as _LOG
from ..email import construct_text_email as _construct_text_email
from ..extract_mime import message_time as _message_time
from ..model.grade import Grade as _Grade
from ..storage import load_grade as _load_grade
from ..storage import parse_grade as _parse_grade
from ..storage import save_grade as _save_grade
from . import InvalidMessage as _InvalidMessage
from . import get_subject_assignment as _get_subject_assignment
from . import get_subject_student as _get_subject_student
from . import PermissionViolationMessage as _PermissionViolationMessage
from . import Response as _Response
from . import UnsignedMessage as _UnsignedMessage


class MissingGradeMessage (_InvalidMessage):
    def __init__(self, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'missing grade'
        super(MissingGradeMessage, self).__init__(**kwargs)


def run(basedir, course, message, person, subject,
        trust_email_infrastructure=False, dry_run=False, **kwargs):
    """
    >>> from pgp_mime.email import encodedMIMEText
    >>> from ..test.course import StubCourse
    >>> from . import InvalidMessage, Response
    >>> course = StubCourse()
    >>> person = list(
    ...     course.course.find_people(email='eye@tower.edu'))[0]
    >>> message = encodedMIMEText('10')
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

    Message authentication is handled identically to the ``get`` module.

    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person, subject='[grade]')
    UnsignedMessage error:
    unsigned message

    Students are denied access:

    >>> student = list(
    ...     course.course.find_people(email='bb@greyhavens.net'))[0]
    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=student, subject='[grade]',
    ...     trust_email_infrastructure=True)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    PermissionViolationMessage error:
    action not permitted

    >>> person.pgp_key = None  # so we have plain-text to doctest
    >>> assignment = course.course.assignments[0]
    >>> message.authenticated = True
    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person, subject='[grade] {}, {}'.format(student.name, assignment.name))
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Sauron <eye@tower.edu>
    Subject: Set Bilbo Baggins grade on Attendance 1 to 10.0
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    <BLANKLINE>
    Set comment to:
    <BLANKLINE>
    None
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

    >>> message = encodedMIMEText('9\\n\\nUnits!')
    >>> message['Message-ID'] = '<123.456@home.net>'
    >>> message.authenticated = True
    >>> process(
    ...     basedir=course.basedir, course=course.course, message=message,
    ...     person=person, subject='[grade] {}, {}'.format(student.name, assignment.name))
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Sauron <eye@tower.edu>
    Subject: Set Bilbo Baggins grade on Attendance 1 to 9.0
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    <BLANKLINE>
    Set comment to:
    <BLANKLINE>
    Units!
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

    >>> course.cleanup()
    """
    if trust_email_infrastructure:
        authenticated = True
    else:
        authenticated = (
            hasattr(message, 'authenticated') and message.authenticated)
    if not authenticated:
        raise _UnsignedMessage()
    if not person.is_admin():
        raise _PermissionViolationMessage(
            person=person, allowed_groups=person.admin_groups)
    student = _get_subject_student(course=course, subject=subject)
    assignment = _get_subject_assignment(course=course, subject=subject)
    grade = _get_grade(
        basedir=basedir, message=message, assignment=assignment,
        student=student)
    _LOG.info('set {} grade on {} to {}'.format(
            student, assignment, grade.points))
    if not dry_run:
        _save_grade(basedir=basedir, grade=grade)
    response = _construct_text_email(
        author=course.robot, targets=[person],
        subject='Set {} grade on {} to {}'.format(
            student.name, assignment.name, grade.points),
        text='Set comment to:\n\n{}\n'.format(grade.comment))
    raise _Response(message=response, complete=True)

def _get_grade(basedir, message, assignment, student):
    text = None
    for part in message.walk():
        if part.get_content_type() == 'text/plain':
            charset = part.get_charset()
            if charset is None:
                encoding = 'ascii'
            else:
                encoding = charset.input_charset
            text = str(part.get_payload(decode=True), encoding)
    if text is None:
        raise _MissingGradeMessage(message=message)
    stream = _io.StringIO(text)
    new_grade = _parse_grade(
        stream=stream, assignment=assignment, person=student)
    try:
        old_grade = _load_grade(
            basedir=basedir, assignment=assignment, person=student)
    except IOError as error:
        _LOG.warn(str(error))
        old_grade = _Grade(student=student, assignment=assignment, points=0)
    old_grade.points = new_grade.points
    old_grade.comment = new_grade.comment
    return old_grade
