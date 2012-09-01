# Copyright

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
from ..color import color_string as _color_string
from ..color import standard_colors as _standard_colors
from ..email import construct_email as _construct_email
from ..email import _construct_email as _raw_construct_email
from ..storage import assignment_path as _assignment_path
from ..tabulate import tabulate as _tabulate
from ..template import _student_email as _student_email
from . import respond as _respond


def run(basedir, course, original, message, person, subject,
        trust_email_infrastructure=False, respond=None,
        use_color=None, dry_run=False, **kwargs):
    """
    >>> from pgp_mime.email import encodedMIMEText
    >>> from pygrader.model.grade import Grade
    >>> from pygrader.test.course import StubCourse
    >>> course = StubCourse()
    >>> person = list(
    ...     course.course.find_people(email='bb@greyhavens.net'))[0]
    >>> message = encodedMIMEText('This text is not important.')
    >>> message['Message-ID'] = '<123.456@home.net>'
    >>> def respond(message):
    ...     print('respond with:\\n{}'.format(
    ...             message.as_string().replace('\\t', '  ')))

    Unauthenticated messages are refused by default.

    >>> run(basedir=course.basedir, course=course.course, original=message,
    ...     message=message, person=person, subject='[get]',
    ...     max_late=0, respond=respond)
    Traceback (most recent call last):
      ...
    ValueError: must request information in a signed email

    Although you can process them by setting the
    ``trust_email_infrastructure`` option.  This might not be too
    dangerous, since you're sending the email to the user's configured
    email address, not just replying blindly to the incoming email
    address.  With ``trust_email_infrastructure`` and missing user PGP
    keys, sysadmins on the intervening systems will be able to read
    our responses, possibly leaking grade information.  If leaking to
    sysadmins is considered unacceptable, you've can only email users
    who have registered PGP keys.

    >>> run(basedir=course.basedir, course=course.course, original=message,
    ...     message=message, person=person, subject='[get]',
    ...     max_late=0, trust_email_infrastructure=True, respond=respond)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    Traceback (most recent call last):
      ...
    ValueError: no grades for <Person Bilbo Baggins>

    Students without grades get a reasonable response.

    >>> message.authenticated = True
    >>> try:
    ...     run(basedir=course.basedir, course=course.course, original=message,
    ...         message=message, person=person, subject='[get]',
    ...         max_late=0, respond=respond)
    ... except ValueError as error:
    ...     print('\\ngot error: {}'.format(error))
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; protocol="application/pgp-signature"; micalg="pgp-sha1"; boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Bilbo Baggins <bb@shire.org>
    Subject: no grades for Billy
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
    Billy,
    <BLANKLINE>
    We don't have any of your grades on file for this course.
    <BLANKLINE>
    Yours,
    phys-101 robot
    --===============...==
    Content-Type: message/rfc822
    MIME-Version: 1.0
    <BLANKLINE>
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Message-ID: <123.456@home.net>
    <BLANKLINE>
    This text is not important.
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
    <BLANKLINE>
    got error: no grades for <Person Bilbo Baggins>

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
    >>> run(basedir=course.basedir, course=course.course, original=message,
    ...     message=message, person=person, subject='[get]',
    ...     max_late=0, respond=respond)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; protocol="application/pgp-signature"; micalg="pgp-sha1"; boundary="===============...=="
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
    >>> run(basedir=course.basedir, course=course.course, original=message,
    ...     message=message, person=person, subject='[get]',
    ...     max_late=0, respond=respond)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; protocol="application/pgp-signature"; micalg="pgp-sha1"; boundary="===============...=="
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

    >>> run(basedir=course.basedir, course=course.course, original=message,
    ...     message=message, person=person,
    ...     subject='[get] {}'.format(student.name),
    ...     max_late=0, respond=respond)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; protocol="application/pgp-signature"; micalg="pgp-sha1"; boundary="===============...=="
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
    >>> _handle_submission(
    ...     basedir=course.basedir, course=course.course, original=submission,
    ...     message=submission, person=student,
    ...     subject='[submit] Assignment 1')

    Now lets request the submissions.

    >>> run(basedir=course.basedir, course=course.course, original=message,
    ...     message=message, person=person,
    ...     subject='[get] {}, {}'.format(student.name, 'Assignment 1'),
    ...     max_late=0, respond=respond)
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: multipart/signed; protocol="application/pgp-signature"; micalg="pgp-sha1"; boundary="===============...=="
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
        authenticated = hasattr(message, 'authenticated') and message.authenticated
    if not authenticated:
        response_subject = 'must request information in a signed email'
        if respond:
            if person.pgp_key:
                hint = (
                    'Please resubmit your request in an OpenPGP-signed email\n'
                    'using your PGP key {}.').format(persion.pgp_key)
            else:
                hint = (
                    "We don't even have a PGP key on file for you.  Please talk\n"
                    'to your professor or TA about getting one set up.')
            _respond(
                course=course, person=person, original=original,
                subject=response_subject, text=(
                    'We got an email from you with the following subject:\n'
                    '  {!r}\n'
                    'but we cannot provide the information unless we know it\n'
                    'really was you who asked for it.\n\n'
                    '{}').format(subject, hint),
                respond=respond)
        raise ValueError(response_subject)
    if 'assistants' in person.groups or 'professors' in person.groups:
        email = _get_admin_email(
            basedir=basedir, course=course, original=original,
            person=person, subject=subject, respond=respond,
            use_color=None)
    elif 'students' in person.groups:
        email = _get_student_email(
            basedir=basedir, course=course, original=original,
            person=person, respond=respond, use_color=None)
    else:
        raise NotImplementedError(
            'strange groups {} for {}'.format(person.groups, person))
    if respond:
        respond(email)

def _get_student_email(basedir, course, original, person, student=None,
                       respond=None, use_color=None):
    if student is None:
        student = person
        targets = None
    else:
        targets = [person]
    emails = list(_student_email(
        basedir=basedir, author=course.robot, course=course,
        student=student, targets=targets, old=True))
    if len(emails) == 0:
        if respond:
            if targets:
                text = (
                    "We don't have any grades for {} on file for this course."
                    ).format(student.name)
            else:
                text = (
                    "We don't have any of your grades on file for this course.")
            _respond(
                course=course, person=person, original=original,
                subject='no grades for {}'.format(student.alias()), text=text,
                respond=respond)
        raise ValueError('no grades for {}'.format(student))
    elif len(emails) > 1:
        raise NotImplementedError(emails)
    email,callback = emails[0]
    # callback records notification, but don't bother here
    return email

def _get_student_submission_email(
    basedir, course, original, person, assignments, student,
    respond=None, use_color=None):
    subject = '{} assignment submissions for {}'.format(
        course.name, student.name)
    text = '{}:\n  * {}\n'.format(
        subject, '\n  * '.join(a.name for a in assignments))
    message = _MIMEMultipart('mixed')
    message.attach(_pgp_mime.encodedMIMEText(text))
    for assignment in assignments:
        grade = course.grade(student=student, assignment=assignment)
        if grade is not None:
            message.attach(_pgp_mime.encodedMIMEText(
                    '{} grade: {}\n\n{}\n'.format(
                        assignment.name, grade.points, grade.comment)))
        assignment_path = _assignment_path(basedir, assignment, student)
        mpath = _os_path.join(assignment_path, 'mail')
        try:
            mbox = _mailbox.Maildir(mpath, factory=None, create=False)
        except _mailbox.NoSuchMailboxError as e:
            pass
        else:
            for msg in mbox:
                message.attach(_MIMEMessage(msg))
    return _raw_construct_email(
        author=course.robot, targets=[person], subject=subject, message=message)

def _get_admin_email(basedir, course, original, person, subject, respond=None,
                     use_color=None):
    lsubject = subject.lower()
    students = [p for p in course.find_people()
                if p.name.lower() in lsubject]
    if len(students) == 0:
        stream = _io.StringIO()
        _tabulate(course=course, statistics=True, stream=stream)
        text = stream.getvalue()
        email = _construct_email(
            author=course.robot, targets=[person],
            subject='All grades for {}'.format(course.name),
            text=text)
    elif len(students) == 1:
        student = students[0]
        assignments = [a for a in course.assignments
                       if a.name.lower() in lsubject]
        if len(assignments) == 0:
            email = _get_student_email(
                basedir=basedir, course=course, original=original,
                person=person, student=student, respond=respond,
                use_color=None)
        else:
            email = _get_student_submission_email(
                basedir=basedir, course=course, original=original,
                person=person, student=student, assignments=assignments,
                use_color=None)
    else:
        if respond:
            _respond(
                course=course, person=person, original=original,
                subject='subject matches multiple students',
                text=(
                    'We got an email from you with the following subject:\n'
                    '  {!r}\n'
                    'but it matches several students:\n'
                    '  * {}').format(
                    subject, '\n  * '.join(s.name for s in students)),
                respond=respond)
        raise ValueError(
            'subject {!r} matches multiple students {}'.format(
            subject, students))
    return email
