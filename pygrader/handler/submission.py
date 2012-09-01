# Copyright

"""Assignment submission handler

Allow students to submit assignments via email (if
``Assignment.submittable`` is set).
"""

from email.utils import formatdate as _formatdate
import mailbox as _mailbox
import os as _os
import os.path as _os_path

import pgp_mime as _pgp_mime

from .. import LOG as _LOG
from ..color import color_string as _color_string
from ..color import standard_colors as _standard_colors
from ..extract_mime import extract_mime as _extract_mime
from ..extract_mime import message_time as _message_time
from ..storage import assignment_path as _assignment_path
from ..storage import set_late as _set_late
from . import InvalidMessage as _InvalidMessage
from . import Response as _Response


class InvalidAssignment (_InvalidMessage):
    def __init__(self, assignment, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'Received invalid {} submission'.format(
                assignment.name)
        super(InvalidAssignment, self).__init__(**kwargs)
        self.assignment = assignment


def run(basedir, course, message, person, subject,
        max_late=0, use_color=None, dry_run=None, **kwargs):
    """
    >>> from pgp_mime.email import encodedMIMEText
    >>> from ..test.course import StubCourse
    >>> from . import Response
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
    >>> try:
    ...     run(basedir=course.basedir, course=course.course, message=message,
    ...         person=person, subject=subject, max_late=0)
    ... except Response as e:
    ...     print('respond with:')
    ...     print(e.message.as_string())
    ... # doctest: +ELLIPSIS, +REPORT_UDIFF
    respond with:
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Subject: Received Assignment 1 submission
    <BLANKLINE>
    We received your submission for Assignment 1 on ....

    >>> course.cleanup()
    """
    time = _message_time(message=message, use_color=use_color)
    assignment = _get_assignment(
        course=course, subject=subject, use_color=use_color)
    assignment_path = _assignment_path(basedir, assignment, person)
    _save_local_message_copy(
        msg=message, person=person, assignment_path=assignment_path,
        use_color=use_color, dry_run=dry_run)
    _extract_mime(message=message, output=assignment_path, dry_run=dry_run)
    _check_late(
        basedir=basedir, assignment=assignment, person=person, time=time,
        max_late=max_late, use_color=use_color, dry_run=dry_run)
    if time:
        time_str = 'on {}'.format(_formatdate(time))
    else:
        time_str = 'at an unknown time'
    message = _pgp_mime.encodedMIMEText((
            'We received your submission for {} {}.'
            ).format(
            assignment.name, time_str))
    message['Subject'] = 'Received {} submission'.format(assignment.name)
    raise _Response(message=message)

def _match_assignment(assignment, subject):
    return assignment.name.lower() in subject.lower()

def _get_assignment(course, subject, use_color):
    assignments = [a for a in course.assignments
                   if _match_assignment(a, subject)]
    if len(assignments) != 1:
        if len(assignments) == 0:
            response_subject = 'no assignment found in {!r}'.format(subject)
            error = (
                'does not match any submittable assignment name\n'
                'for {}.\n').format(course.name)
        else:
            response_subject = 'several assignments found in {!r}'.format(
                subject)
            error = (
                'matches several submittable assignment names\n'
                'for {}:  * {}\n').format(
                course.name,
                '\n  * '.join(a.name for a in assignments))
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
        message = _pgp_mime.encodedMIMEText((
                'We got an email from you with the following subject:\n'
                '  {!r}\n'
                'which {}.\n\n'
                '{}\n').format(subject, course.name, hint))
        message['Subject'] = response_subject
        raise _Response(
            message=message, exception=ValueError(response_subject))
    assignment = assignments[0]

    if not assignment.submittable:
        raise InvalidAssignment(assignment)
    return assignments[0]

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
