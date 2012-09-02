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
from ..color import GOOD_DEBUG as _GOOD_DEBUG
from ..extract_mime import extract_mime as _extract_mime
from ..extract_mime import message_time as _message_time
from ..storage import assignment_path as _assignment_path
from ..storage import set_late as _set_late
from . import get_subject_assignment as _get_subject_assignment
from . import InvalidMessage as _InvalidMessage
from . import Response as _Response


class InvalidSubmission (_InvalidMessage):
    def __init__(self, assignment=None, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'invalid submission'
        super(InvalidSubmission, self).__init__(**kwargs)
        self.assignment = assignment


def run(basedir, course, message, person, subject, max_late=0, dry_run=None,
        **kwargs):
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
    time = _message_time(message=message)
    assignment = _get_assignment(course=course, subject=subject)
    assignment_path = _assignment_path(basedir, assignment, person)
    _save_local_message_copy(
        msg=message, person=person, assignment_path=assignment_path,
        dry_run=dry_run)
    _extract_mime(message=message, output=assignment_path, dry_run=dry_run)
    _check_late(
        basedir=basedir, assignment=assignment, person=person, time=time,
        max_late=max_late, dry_run=dry_run)
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

def _get_assignment(course, subject):
    assignment = _get_subject_assignment(course, subject)
    if not assignment.submittable:
        raise InvalidSubmission(assignment=assignment)
    return assignment

def _save_local_message_copy(msg, person, assignment_path, dry_run=False):
    try:
        _os.makedirs(assignment_path)
    except OSError:
        pass
    mpath = _os_path.join(assignment_path, 'mail')
    try:
        mbox = _mailbox.Maildir(mpath, factory=None, create=not dry_run)
    except _mailbox.NoSuchMailboxError as e:
        _LOG.warn('could not open mailbox at {}'.format(mpath))
        mbox = None
        new_msg = True
    else:
        new_msg = True
        for other_msg in mbox:
            if other_msg['Message-ID'] == msg['Message-ID']:
                new_msg = False
                break
    if new_msg:
        _LOG.log(_GOOD_DEBUG, 'saving email from {} to {}'.format(
                person, assignment_path))
        if mbox is not None and not dry_run:
            mdmsg = _mailbox.MaildirMessage(msg)
            mdmsg.add_flag('S')
            mbox.add(mdmsg)
            mbox.close()
    else:
        _LOG.log(_GOOD_DEBUG, 'already found {} in {}'.format(
                    msg['Message-ID'], mpath))

def _check_late(basedir, assignment, person, time, max_late=0, dry_run=False):
    if time > assignment.due + max_late:
        dt = time - assignment.due
        _LOG.warning('{} {} late by {} seconds ({} hours)'.format(
            person.name, assignment.name, dt, dt/3600.))
        if not dry_run:
            _set_late(basedir=basedir, assignment=assignment, person=person)
