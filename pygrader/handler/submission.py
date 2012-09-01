# Copyright

"""Assignment submission handler

Allow students to submit assignments via email (if
``Assignment.submittable`` is set).
"""

from email.utils import formatdate as _formatdate
import mailbox as _mailbox
import os as _os
import os.path as _os_path

from .. import LOG as _LOG
from ..color import color_string as _color_string
from ..color import standard_colors as _standard_colors
from ..extract_mime import extract_mime as _extract_mime
from ..extract_mime import message_time as _message_time
from ..storage import assignment_path as _assignment_path
from ..storage import set_late as _set_late
from . import respond as _respond


def run(basedir, course, original, message, person, subject,
        max_late=0, respond=None, use_color=None,
        dry_run=None):
    """
    >>> from pgp_mime.email import encodedMIMEText
    >>> from pygrader.test.course import StubCourse
    >>> course = StubCourse()
    >>> person = list(
    ...     course.course.find_people(email='bb@greyhavens.net'))[0]
    >>> message = encodedMIMEText('The answer is 42.')
    >>> message['Message-ID'] = '<123.456@home.net>'
    >>> message['Received'] = (
    ...     'from smtp.home.net (smtp.home.net [123.456.123.456]) '
    ...     'by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF '
    ...     'for <wking@tremily.us>; Sun, 09 Oct 2011 11:50:46 -0400 (EDT)')
    >>> subject = '[submit] assignment 1'
    >>> def respond(message):
    ...     print('respond with:\\n{}'.format(message.as_string()))
    >>> run(basedir=course.basedir, course=course.course, original=message,
    ...     message=message, person=person, subject=subject,
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
    Subject: received Assignment 1 submission
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
    We received your submission for Assignment 1 on ....
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
    time = _message_time(message=message, use_color=use_color)

    for assignment in course.assignments:
        if _match_assignment(assignment, subject):
            break
    if not _match_assignment(assignment, subject):
        response_subject = 'no assignment found in {!r}'.format(subject)
        if respond:
            submittable_assignments = [
                a for a in course.assignments if a.submittable]
            if not submittable_assignments:
                hint = (
                    'In fact, there are no submittable assignments for\n'
                    'this course!')
            else:
                hint = (
                    'Remember to use the full name for the assignment in the\n'
                    'subject.  For example:\n'
                    '  {} submission').format(
                    submittable_assignments[0].name)
            _respond(
                course=course, person=person, original=original,
                subject=response_subject, text=(
                    'We got an email from you with the following subject:\n'
                    '  {!r}\n'
                    'which does not match any submittable assignment name\n'
                    'for {}.\n'
                    '{}').format(subject, course.name, hint),
                respond=respond)
        raise ValueError(response_subject)

    if not assignment.submittable:
        response_subject = 'received invalid {} submission'.format(
            assignment.name)
        if respond:
            _respond(
                course=course, person=person, original=original,
                subject=response_subject, text=(
                    'We received your submission for {}, but you are not\n'
                    'allowed to submit that assignment via email.'
                    ).format(assignment.name),
                respond=respond)
        raise ValueError(response_subject)

    if respond:
        response_subject = 'received {} submission'.format(assignment.name)
        if time:
            time_str = 'on {}'.format(_formatdate(time))
        else:
            time_str = 'at an unknown time'
        _respond(
            course=course, person=person, original=original,
            subject=response_subject, text=(
                'We received your submission for {} {}.'
                ).format(assignment.name, time_str),
            respond=respond)

    assignment_path = _assignment_path(basedir, assignment, person)
    _save_local_message_copy(
        msg=message, person=person, assignment_path=assignment_path,
        use_color=use_color, dry_run=dry_run)
    _extract_mime(message=message, output=assignment_path, dry_run=dry_run)
    _check_late(
        basedir=basedir, assignment=assignment, person=person, time=time,
        max_late=max_late, use_color=use_color, dry_run=dry_run)

def _match_assignment(assignment, subject):
    return assignment.name.lower() in subject

def _save_local_message_copy(msg, person, assignment_path, use_color=None,
                             dry_run=False):
    highlight,lowlight,good,bad = _standard_colors(use_color=use_color)
    try:
        _os.makedirs(assignment_path)
    except OSError:
        pass
    mpath = _os_path.join(assignment_path, 'mail')
    try:
        mbox = _mailbox.Maildir(mpath, factory=None, create=not dry_run)
    except _mailbox.NoSuchMailboxError as e:
        _LOG.debug(_color_string(
                string='could not open mailbox at {}'.format(mpath),
                color=bad))
        mbox = None
        new_msg = True
    else:
        new_msg = True
        for other_msg in mbox:
            if other_msg['Message-ID'] == msg['Message-ID']:
                new_msg = False
                break
    if new_msg:
        _LOG.debug(_color_string(
                string='saving email from {} to {}'.format(
                    person, assignment_path), color=good))
        if mbox is not None and not dry_run:
            mdmsg = _mailbox.MaildirMessage(msg)
            mdmsg.add_flag('S')
            mbox.add(mdmsg)
            mbox.close()
    else:
        _LOG.debug(_color_string(
                string='already found {} in {}'.format(
                    msg['Message-ID'], mpath), color=good))

def _check_late(basedir, assignment, person, time, max_late=0, use_color=None,
                dry_run=False):
    highlight,lowlight,good,bad = _standard_colors(use_color=use_color)
    if time > assignment.due + max_late:
        dt = time - assignment.due
        _LOG.warn(_color_string(
                string='{} {} late by {} seconds ({} hours)'.format(
                    person.name, assignment.name, dt, dt/3600.),
                color=bad))
        if not dry_run:
            _set_late(basedir=basedir, assignment=assignment, person=person)
