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

from email import message_from_file as _message_from_file
from email.header import decode_header as _decode_header
from email.utils import formatdate as _formatdate
import hashlib as _hashlib
import locale as _locale
import mailbox as _mailbox
import os as _os
import os.path as _os_path
import sys as _sys
import time as _time

from pgp_mime import verify as _verify
from lxml import etree as _etree

from . import LOG as _LOG
from .color import standard_colors as _standard_colors
from .color import color_string as _color_string
from .email import construct_response as _construct_response
from .extract_mime import extract_mime as _extract_mime
from .extract_mime import message_time as _message_time
from .model.person import Person as _Person
from .storage import assignment_path as _assignment_path
from .storage import set_late as _set_late


def mailpipe(basedir, course, stream=None, mailbox=None, input_=None,
             output=None, max_late=0, respond=None, use_color=None,
             dry_run=False, **kwargs):
    """Run from procmail to sort incomming submissions

    For example, you can setup your ``.procmailrc`` like this::

      SHELL=/bin/sh
      DEFAULT=$MAIL
      MAILDIR=$HOME/mail
      DEFAULT=$MAILDIR/mbox
      LOGFILE=$MAILDIR/procmail.log
      #VERBOSE=yes
      PYGRADE_MAILPIPE="pg.py -d $HOME/grades/phys160"

      # Grab all incoming homeworks emails.  This rule eats matching emails
      # (i.e. no further procmail processing).
      :0
      * ^Subject:.*\[phys160-sub]
      | "$PYGRADE_MAILPIPE" mailpipe

    If you don't want procmail to eat the message, you can use the
    ``c`` flag (carbon copy) by starting your rule off with ``:0 c``.

    >>> from asyncore import loop
    >>> from io import StringIO
    >>> from pgp_mime.email import encodedMIMEText
    >>> from pygrader.test.course import StubCourse
    >>> from pygrader.test.client import MessageSender
    >>> from pygrader.test.server import SMTPServer

    Messages with unrecognized ``Return-Path``\s are silently dropped:

    >>> course = StubCourse()
    >>> def process(peer, mailfrom, rcpttos, data):
    ...     mailpipe(
    ...         basedir=course.basedir, course=course.course,
    ...         stream=StringIO(data), output=course.mailbox)
    >>> message = encodedMIMEText('The answer is 42.')
    >>> message['Message-ID'] = '<123.456@home.net>'
    >>> message['Return-Path'] = '<invalid.return.path@home.net>'
    >>> message['Received'] = (
    ...     'from smtp.home.net (smtp.home.net [123.456.123.456]) '
    ...     'by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF '
    ...     'for <wking@tremily.us>; Sun, 09 Oct 2011 11:50:46 -0400 (EDT)')
    >>> message['From'] = 'Billy B <bb@greyhavens.net>'
    >>> message['To'] = 'phys101 <phys101@tower.edu>'
    >>> message['Subject'] = 'assignment 1 submission'
    >>> messages = [message]
    >>> ms = MessageSender(address=('localhost', 1025), messages=messages)
    >>> loop()
    >>> course.print_tree()  # doctest: +REPORT_UDIFF
    course.conf

    If we add a valid ``Return-Path``, we get the expected delivery:

    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=1)
    >>> del message['Return-Path']
    >>> message['Return-Path'] = '<bb@greyhavens.net>'
    >>> ms = MessageSender(address=('localhost', 1025), messages=messages)
    >>> loop()
    >>> course.print_tree()  # doctest: +REPORT_UDIFF, +ELLIPSIS
    Bilbo_Baggins
    Bilbo_Baggins/Assignment_1
    Bilbo_Baggins/Assignment_1/mail
    Bilbo_Baggins/Assignment_1/mail/cur
    Bilbo_Baggins/Assignment_1/mail/new
    Bilbo_Baggins/Assignment_1/mail/new/...:2,S
    Bilbo_Baggins/Assignment_1/mail/tmp
    course.conf
    mail
    mail/cur
    mail/new
    mail/new/...
    mail/tmp

    The last ``Received`` is used to timestamp the message:

    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=1)
    >>> del message['Message-ID']
    >>> message['Message-ID'] = '<abc.def@home.net>'
    >>> del message['Received']
    >>> message['Received'] = (
    ...     'from smtp.mail.uu.edu (localhost.localdomain [127.0.0.1]) '
    ...     'by smtp.mail.uu.edu (Postfix) with SMTP id 68CB45C8453 '
    ...     'for <wking@tremily.us>; Mon, 10 Oct 2011 12:50:46 -0400 (EDT)')
    >>> message['Received'] = (
    ...     'from smtp.home.net (smtp.home.net [123.456.123.456]) '
    ...     'by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF '
    ...     'for <wking@tremily.us>; Mon, 09 Oct 2011 11:50:46 -0400 (EDT)')
    >>> messages = [message]
    >>> ms = MessageSender(address=('localhost', 1025), messages=messages)
    >>> loop()
    >>> course.print_tree()  # doctest: +REPORT_UDIFF, +ELLIPSIS
    Bilbo_Baggins
    Bilbo_Baggins/Assignment_1
    Bilbo_Baggins/Assignment_1/late
    Bilbo_Baggins/Assignment_1/mail
    Bilbo_Baggins/Assignment_1/mail/cur
    Bilbo_Baggins/Assignment_1/mail/new
    Bilbo_Baggins/Assignment_1/mail/new/...:2,S
    Bilbo_Baggins/Assignment_1/mail/new/...:2,S
    Bilbo_Baggins/Assignment_1/mail/tmp
    course.conf
    mail
    mail/cur
    mail/new
    mail/new/...
    mail/new/...
    mail/tmp

    You can send receipts to the acknowledge incoming messages, which
    includes warnings about dropped messages (except for messages
    without ``Return-Path`` and messages where the ``Return-Path``
    email belongs to multiple ``People``.  Both of these cases should
    only come from problems with pygrader configuration).

    Response to a successful submission:

    >>> def respond(message):
    ...     print('respond with:\\n{}'.format(message.as_string()))
    >>> def process(peer, mailfrom, rcpttos, data):
    ...     mailpipe(
    ...         basedir=course.basedir, course=course.course,
    ...         stream=StringIO(data), output=course.mailbox,
    ...         respond=respond)
    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=1)
    >>> del message['Message-ID']
    >>> message['Message-ID'] = '<hgi.jlk@home.net>'
    >>> messages = [message]
    >>> ms = MessageSender(address=('localhost', 1025), messages=messages)
    >>> loop()  # doctest: +REPORT_UDIFF, +ELLIPSIS
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
    We received your submission for Assignment 1 on Mon, 10 Oct 2011 16:50:46 -0000.
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
    From: Billy B <bb@greyhavens.net>
    To: phys101 <phys101@tower.edu>
    Subject: assignment 1 submission
    Return-Path: <bb@greyhavens.net>
    Received: from smtp.mail.uu.edu (localhost.localdomain [127.0.0.1]) by smtp.mail.uu.edu (Postfix) with SMTP id 68CB45C8453 for <wking@tremily.us>; Mon, 10 Oct 2011 12:50:46 -0400 (EDT)
    Received: from smtp.home.net (smtp.home.net [123.456.123.456]) by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF for <wking@tremily.us>; Mon, 09 Oct 2011 11:50:46 -0400 (EDT)
    Message-ID: <hgi.jlk@home.net>
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
    Version: GnuPG v2.0.17 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP SIGNATURE-----
    <BLANKLINE>
    --===============...==--

    Response to a submission on an unsubmittable assignment:

    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=1)
    >>> del message['Subject']
    >>> message['Subject'] = 'attendance 1 submission'
    >>> messages = [message]
    >>> ms = MessageSender(address=('localhost', 1025), messages=messages)
    >>> loop()  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/signed; protocol="application/pgp-signature"; micalg="pgp-sha1"; boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Bilbo Baggins <bb@shire.org>
    Subject: received invalid Attendance 1 submission
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
    We received your submission for Attendance 1, but you are not allowed
    to submit that assignment via email.
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
    From: Billy B <bb@greyhavens.net>
    To: phys101 <phys101@tower.edu>
    Return-Path: <bb@greyhavens.net>
    Received: from smtp.mail.uu.edu (localhost.localdomain [127.0.0.1]) by smtp.mail.uu.edu (Postfix) with SMTP id 68CB45C8453 for <wking@tremily.us>; Mon, 10 Oct 2011 12:50:46 -0400 (EDT)
    Received: from smtp.home.net (smtp.home.net [123.456.123.456]) by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF for <wking@tremily.us>; Mon, 09 Oct 2011 11:50:46 -0400 (EDT)
    Message-ID: <hgi.jlk@home.net>
    Subject: attendance 1 submission
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
    Version: GnuPG v2.0.17 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP SIGNATURE-----
    <BLANKLINE>
    --===============...==--

    Response to a bad subject:

    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=1)
    >>> del message['Subject']
    >>> message['Subject'] = 'need help for the first homework'
    >>> messages = [message]
    >>> ms = MessageSender(address=('localhost', 1025), messages=messages)
    >>> loop()  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/signed; protocol="application/pgp-signature"; micalg="pgp-sha1"; boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Bilbo Baggins <bb@shire.org>
    Subject: received 'need help for the first homework'
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
    We got an email from you with the following subject:
      'need help for the first homework'
    which does not match any submittable assignment name for
    phys101.
    Remember to use the full name for the assignment in the
    subject.  For example:
      Assignment 1 submission
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
    From: Billy B <bb@greyhavens.net>
    To: phys101 <phys101@tower.edu>
    Return-Path: <bb@greyhavens.net>
    Received: from smtp.mail.uu.edu (localhost.localdomain [127.0.0.1]) by smtp.mail.uu.edu (Postfix) with SMTP id 68CB45C8453 for <wking@tremily.us>; Mon, 10 Oct 2011 12:50:46 -0400 (EDT)
    Received: from smtp.home.net (smtp.home.net [123.456.123.456]) by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF for <wking@tremily.us>; Mon, 09 Oct 2011 11:50:46 -0400 (EDT)
    Message-ID: <hgi.jlk@home.net>
    Subject: need help for the first homework
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
    Version: GnuPG v2.0.17 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP SIGNATURE-----
    <BLANKLINE>
    --===============...==--

    >>> del message['Return-Path']
    >>> message['Return-Path'] = '<bb@greyhavens.net>'

    >>> course.cleanup()
    """
    if stream is None:
        stream = _sys.stdin
    for msg,person,assignment,time in _load_messages(
        course=course, stream=stream, mailbox=mailbox, input_=input_,
        output=output, respond=respond, use_color=use_color, dry_run=dry_run):
        assignment_path = _assignment_path(basedir, assignment, person)
        _save_local_message_copy(
            msg=msg, person=person, assignment_path=assignment_path,
            use_color=use_color, dry_run=dry_run)
        _extract_mime(message=msg, output=assignment_path, dry_run=dry_run)
        _check_late(
            basedir=basedir, assignment=assignment, person=person, time=time,
            max_late=max_late, use_color=use_color, dry_run=dry_run)

def _load_messages(course, stream, mailbox=None, input_=None, output=None,
                   respond=None, use_color=None, dry_run=False):
    if mailbox is None:
        mbox = None
        messages = [(None,_message_from_file(stream))]
        if output is not None:
            ombox = _mailbox.Maildir(output, factory=None, create=True)
    elif mailbox == 'mbox':
        mbox = _mailbox.mbox(input_, factory=None, create=False)
        messages = mbox.items()
        if output is not None:
            ombox = _mailbox.mbox(output, factory=None, create=True)
    elif mailbox == 'maildir':
        mbox = _mailbox.Maildir(input_, factory=None, create=False)
        messages = mbox.items()
        if output is not None:
            ombox = _mailbox.Maildir(output, factory=None, create=True)
    else:
        raise ValueError(mailbox)
    for key,msg in messages:
        ret = _parse_message(
            course=course, msg=msg, respond=respond, use_color=use_color)
        if ret:
            if output is not None and dry_run is False:
                # move message from input mailbox to output mailbox
                ombox.add(msg)
                if mbox is not None:
                    del mbox[key]
            yield ret

def _parse_message(course, msg, respond=None, use_color=None):
    highlight,lowlight,good,bad = _standard_colors(use_color=use_color)
    mid = msg['Message-ID']
    sender = msg['Return-Path']  # RFC 822
    if sender is None:
        _LOG.debug(_color_string(
                string='no Return-Path in {}'.format(mid), color=lowlight))
        return None
    sender = sender[1:-1]  # strip wrapping '<' and '>'
    time = _message_time(message=msg, use_color=use_color)

    if respond:
        if time:
            time_str = _formatdate(time)
        else:
            time_str = 'unknown time'
        response_subject = 'received {} at {}'.format(mid, time_str)

    people = list(course.find_people(email=sender))
    if len(people) == 0:
        _LOG.warn(_color_string(
                string='no person found to match {}'.format(sender),
                color=bad))
        if respond:
            person = _Person(name=None, emails=[sender])
            response_text = (
                '{},\n\n'
                'Your email address is not registered with pygrader for\n'
                '{}.  If you feel it should be, contact your professor\n'
                'or TA.\n\n'
                'Yours,\n{}').format(
                sender, course.robot.alias())
            response_text = 'Address {} is not registered for {}.'.format(
                sender, course.name)
            response = _construct_response(
                author=course.robot, targets=[person],
                subject=response_subject, text=response_text, original=msg)
            respond(response)
        return None
    if len(people) > 1:
        _LOG.warn(_color_string(
                string='multiple people match {} ({})'.format(
                    sender, ', '.join(str(p) for p in people)),
                color=bad))
        return None
    person = people[0]

    if person.pgp_key:
        msg = _get_verified_message(msg, person.pgp_key, use_color=use_color)
        if msg is None:
            if respond:
                response_text = (
                    '{},\n\n'
                    'We received an email message from you without a valid\n'
                    'PGP signature.\n\n'
                    'Yours,\n{}').format(
                    person.alias(), course.robot.alias())
                response_text = 'Message not signed by {}.'.format(
                    person.pgp_key)
                response = _construct_response(
                    author=course.robot, targets=[person],
                    subject=response_subject, text=response_text, original=msg)
                respond(response)
            return None

    if msg['Subject'] is None:
        _LOG.warn(_color_string(
                string='no subject in {}'.format(mid), color=bad))
        if respond:
            response_text = (
                '{},\n\n'
                'We received an email message from you without a subject.\n\n'
                'Yours,\n{}').format(
                person.alias(), course.robot.alias())
            response = _construct_response(
                author=course.robot, targets=[person],
                subject=response_subject, text=response_text, original=msg)
            respond(response)
        return None
    parts = _decode_header(msg['Subject'])
    if len(parts) != 1:
        _LOG.warn(_color_string(
                string='multi-part header {}'.format(parts), color=bad))
        return None
    subject,encoding = parts[0]
    if encoding is None:
        encoding = 'ascii'
    _LOG.debug('decoded header {} -> {}'.format(parts[0], subject))

    subject = subject.lower().replace('#', '')
    for assignment in course.assignments:
        if _match_assignment(assignment, subject):
            break
    if not _match_assignment(assignment, subject):
        _LOG.warn(_color_string(
                string='no assignment found in {}'.format(repr(subject)),
                color=bad))
        if respond:
            response_subject = "received '{}'".format(subject)
            submittable_assignments = [
                a for a in course.assignments if a.submittable]
            if not submittable_assignments:
                hint = (
                    'In fact, there are no submittable assignments for\n'
                    'this course!\n')
            else:
                hint = (
                    'Remember to use the full name for the assignment in the\n'
                    'subject.  For example:\n'
                    '  {} submission\n\n').format(
                    submittable_assignments[0].name)
            response_text = (
                '{},\n\n'
                'We got an email from you with the following subject:\n'
                '  {}\n'
                'which does not match any submittable assignment name for\n'
                '{}.\n'
                '{}'
                'Yours,\n{}').format(
                person.alias(), repr(subject), course.name, hint,
                course.robot.alias())
            response = _construct_response(
                author=course.robot, targets=[person],
                subject=response_subject, text=response_text, original=msg)
            respond(response)
        return None

    if not assignment.submittable:
        response_subject = 'received invalid {} submission'.format(
            assignment.name)
        response_text = (
            '{},\n\n'
            'We received your submission for {}, but you are not allowed\n'
            'to submit that assignment via email.\n\n'
            'Yours,\n{}').format(
            person.alias(), assignment.name, course.robot.alias())
        response = _construct_response(
            author=course.robot, targets=[person],
            subject=response_subject, text=response_text, original=msg)
        respond(response)
        
    if respond:
        response_subject = 'received {} submission'.format(assignment.name)
        response_text = (
            '{},\n\n'
            'We received your submission for {} on {}.\n\n'
            'Yours,\n{}').format(
            person.alias(), assignment.name, time_str, course.robot.alias())
        response = _construct_response(
            author=course.robot, targets=[person],
            subject=response_subject, text=response_text, original=msg)
        respond(response)
    return (msg, person, assignment, time)

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

def _get_verified_message(message, pgp_key, use_color=None):
    """

    >>> from pgp_mime import sign, encodedMIMEText

    The student composes a message...

    >>> message = encodedMIMEText('1.23 joules')

    ... and signs it (with the pgp-mime test key).

    >>> signed = sign(message, signers=['pgp-mime-test'])

    As it is being delivered, the message picks up extra headers.

    >>> signed['Message-ID'] = '<01234567@home.net>'
    >>> signed['Received'] = 'from smtp.mail.uu.edu ...'
    >>> signed['Received'] = 'from smtp.home.net ...'

    We check that the message is signed, and that it is signed by the
    appropriate key.

    >>> our_message = _get_verified_message(signed, pgp_key='4332B6E3')
    >>> print(our_message.as_string())  # doctest: +REPORT_UDIFF
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Message-ID: <01234567@home.net>
    Received: from smtp.mail.uu.edu ...
    Received: from smtp.home.net ...
    <BLANKLINE>
    1.23 joules

    If it is signed, but not by the right key, we get ``None``.

    >>> print(_get_verified_message(signed, pgp_key='01234567'))
    None

    If it is not signed at all, we get ``None``.

    >>> print(_get_verified_message(message, pgp_key='4332B6E3'))
    None
    """
    highlight,lowlight,good,bad = _standard_colors(use_color=use_color)
    mid = message['message-id']
    try:
        decrypted,verified,result = _verify(message=message)
    except (ValueError, AssertionError):
        _LOG.warn(_color_string(
                string='could not verify {} (not signed?)'.format(mid),
                color=bad))
        return None
    _LOG.info(_color_string(str(result, 'utf-8'), color=lowlight))
    tree = _etree.fromstring(result.replace(b'\x00', b''))
    match = None
    for signature in tree.findall('.//signature'):
        for fingerprint in signature.iterchildren('fpr'):
            if fingerprint.text.endswith(pgp_key):
                match = signature
                break
    if match is None:
        _LOG.warn(_color_string(
                string='{} is not signed by the expected key'.format(mid),
                color=bad))
        return None
    if not verified:
        sumhex = list(signature.iterchildren('summary'))[0].get('value')
        summary = int(sumhex, 16)
        if summary != 0:
            _LOG.warn(_color_string(
                    string='{} has an unverified signature'.format(mid),
                    color=bad))
            return None
        # otherwise, we may have an untrusted key.  We'll count that
        # as verified here, because the caller is explicity looking
        # for signatures by this fingerprint.
    for k,v in message.items(): # copy over useful headers
        if k.lower() not in ['content-type',
                             'mime-version',
                             'content-disposition',
                             ]:
            decrypted[k] = v
    return decrypted
