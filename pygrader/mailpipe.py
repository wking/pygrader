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
import mailbox as _mailbox
import re as _re
import sys as _sys

from pgp_mime import verify as _verify
from lxml import etree as _etree

from . import LOG as _LOG
from .color import color_string as _color_string
from .color import standard_colors as _standard_colors
from .model.person import Person as _Person

from .handler import respond as _respond
from .handler.submission import run as _handle_submission


_TAG_REGEXP = _re.compile('^.*\[([^]]*)\].*$')


def mailpipe(basedir, course, stream=None, mailbox=None, input_=None,
             output=None, max_late=0, handlers={
        'submit': _handle_submission,
        }, respond=None, use_color=None,
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
      * ^Subject:.*\[phys160:submit]
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
    >>> message['Subject'] = '[submit] assignment 1'
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
    email belongs to multiple ``People``.  The former should only
    occur with malicious emails, and the latter with improper pygrader
    configurations).

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
    Subject: [submit] assignment 1
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
    Version: GnuPG v2.0.19 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP SIGNATURE-----
    <BLANKLINE>
    --===============...==--

    Response to a submission on an unsubmittable assignment:

    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=1)
    >>> del message['Subject']
    >>> message['Subject'] = '[submit] attendance 1'
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
    We received your submission for Attendance 1, but you are not
    allowed to submit that assignment via email.
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
    Subject: [submit] attendance 1
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
    Subject: no tag in 'need help for the first homework'
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
    We received an email message from you without
    subject tags.
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
    Version: GnuPG v2.0.19 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP SIGNATURE-----
    <BLANKLINE>
    --===============...==--

    Response to a missing subject:

    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=1)
    >>> del message['Subject']
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
    Subject: no subject in <hgi.jlk@home.net>
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
    We received an email message from you without a subject.
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

    Response to an insecure message from a person with a PGP key:

    >>> student = course.course.person(email='bb@greyhavens.net')
    >>> student.pgp_key = '4332B6E3'
    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=1)
    >>> del message['Subject']
    >>> messages = [message]
    >>> ms = MessageSender(address=('localhost', 1025), messages=messages)
    >>> loop()  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/encrypted; protocol="application/pgp-encrypted"; micalg="pgp-sha1"; boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Bilbo Baggins <bb@shire.org>
    Subject: unsigned message <hgi.jlk@home.net>
    <BLANKLINE>
    --===============...==
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Type: application/pgp-encrypted; charset="us-ascii"
    <BLANKLINE>
    Version: 1
    <BLANKLINE>
    --===============...==
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Description: OpenPGP encrypted message
    Content-Type: application/octet-stream; name="encrypted.asc"; charset="us-ascii"
    <BLANKLINE>
    -----BEGIN PGP MESSAGE-----
    Version: GnuPG v2.0.19 (GNU/Linux)
    <BLANKLINE>
    ...
    -----END PGP MESSAGE-----
    <BLANKLINE>
    --===============...==--

    Response to a message from an unregistered person:

    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=1)
    >>> del message['Return-Path']
    >>> message['Return-Path'] = '<invalid.return.path@home.net>'
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
    To: "invalid.return.path@home.net" <invalid.return.path@home.net>
    Subject: unregistered address invalid.return.path@home.net
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
    invalid.return.path@home.net,
    <BLANKLINE>
    Your email address is not registered with pygrader for
    Physics 101.  If you feel it should be, contact your professor
    or TA.
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
    Received: from smtp.mail.uu.edu (localhost.localdomain [127.0.0.1]) by smtp.mail.uu.edu (Postfix) with SMTP id 68CB45C8453 for <wking@tremily.us>; Mon, 10 Oct 2011 12:50:46 -0400 (EDT)
    Received: from smtp.home.net (smtp.home.net [123.456.123.456]) by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF for <wking@tremily.us>; Mon, 09 Oct 2011 11:50:46 -0400 (EDT)
    Message-ID: <hgi.jlk@home.net>
    Return-Path: <invalid.return.path@home.net>
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
    highlight,lowlight,good,bad = _standard_colors(use_color=use_color)
    if stream is None:
        stream = _sys.stdin
    for original,message,person,subject,target in _load_messages(
        course=course, stream=stream, mailbox=mailbox, input_=input_,
        output=output, respond=respond, use_color=use_color, dry_run=dry_run):
        handler = _get_handler(
            course=course, handlers=handlers, message=message, person=person,
            subject=subject, target=target)
        try:
            handler(
                basedir=basedir, course=course, original=original,
                message=message, person=person, subject=subject,
                max_late=max_late, respond=respond,
                use_color=use_color, dry_run=dry_run)
        except ValueError as error:
            _LOG.warn(_color_string(string=str(error), color=bad))

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
            course=course, message=msg, respond=respond, use_color=use_color)
        if ret:
            if output is not None and dry_run is False:
                # move message from input mailbox to output mailbox
                ombox.add(msg)
                if mbox is not None:
                    del mbox[key]
            yield ret

def _parse_message(course, message, respond=None, use_color=None):
    """Parse an incoming email and respond if neccessary.

    Return ``(msg, person, assignment, time)`` on successful parsing.
    Return ``None`` on failure.
    """
    highlight,lowlight,good,bad = _standard_colors(use_color=use_color)
    original = message
    try:
        person = _get_message_person(
            course=course, message=message, original=original,
            respond=respond, use_color=use_color)
        if person.pgp_key:
            message = _get_decoded_message(
                course=course, message=message, original=original, person=person,
                respond=respond, use_color=use_color)
        subject = _get_message_subject(
            course=course, message=message, original=original, person=person,
            respond=respond, use_color=use_color)
        target = _get_message_target(
            course=course, message=message, original=original, person=person,
            subject=subject, respond=respond, use_color=use_color)
    except ValueError as error:
        _LOG.debug(_color_string(string=str(error), color=bad))
        return None
    return (original, message, person, subject, target)

def _get_message_person(course, message, original, respond=None,
                        use_color=None):
    mid = message['Message-ID']
    sender = message['Return-Path']  # RFC 822
    if sender is None:
        raise ValueError('no Return-Path in {}'.format(mid))
    sender = sender[1:-1]  # strip wrapping '<' and '>'
    people = list(course.find_people(email=sender))
    if len(people) == 0:
        if respond:
            person = _Person(name=sender, emails=[sender])
            response_subject = 'unregistered address {}'.format(sender)
            _respond(
                course=course, person=person, original=original,
                subject=response_subject, text=(
                    'Your email address is not registered with pygrader for\n'
                    '{}.  If you feel it should be, contact your professor\n'
                    'or TA.').format(course.name),
                respond=respond)
        raise ValueError('no person found to match {}'.format(sender))
    if len(people) > 1:
        raise ValueError('multiple people match {} ({})'.format(
                sender, ', '.join(str(p) for p in people)))
    return people[0]

def _get_decoded_message(course, message, original, person,
                         respond=None, use_color=None):
    message = _get_verified_message(
        message, person.pgp_key, use_color=use_color)
    if message is None:
        if respond:
            mid = original['Message-ID']
            response_subject = 'unsigned message {}'.format(mid)
            _respond(
                course=course, person=person, original=original,
                subject=response_subject, text=(
                    'We received an email message from you without a valid\n'
                    'PGP signature.'),
                respond=respond)
        raise ValueError('unsigned message from {}'.format(person.alias()))
    return message

def _get_message_subject(course, message, original, person,
                         respond=None, use_color=None):
    """
    >>> from email.header import Header
    >>> from pgp_mime.email import encodedMIMEText
    >>> message = encodedMIMEText('The answer is 42.')
    >>> message['Message-ID'] = 'msg-id'
    >>> _get_message_subject(
    ...     course=None, message=message, original=message, person=None)
    Traceback (most recent call last):
      ...
    ValueError: no subject in msg-id
    >>> del message['Subject']
    >>> subject = Header('unicode part', 'utf-8')
    >>> subject.append('-ascii part', 'ascii')
    >>> message['Subject'] = subject.encode()
    >>> _get_message_subject(
    ...     course=None, message=message, original=message, person=None)
    'unicode part-ascii part'
    >>> del message['Subject']
    >>> message['Subject'] = 'clean subject'
    >>> _get_message_subject(
    ...     course=None, message=message, original=message, person=None)
    'clean subject'
    """
    if message['Subject'] is None:
        mid = message['Message-ID']
        response_subject = 'no subject in {}'.format(mid)
        if respond:
            _respond(
                course=course, person=person, original=original,
                subject=response_subject, text=(
                    'We received an email message from you without a subject.'
                    ),
                respond=respond)
        raise ValueError(response_subject)

    parts = _decode_header(message['Subject'])
    part_strings = []
    for string,encoding in parts:
        if encoding is None:
            encoding = 'ascii'
        if not isinstance(string, str):
            string = str(string, encoding)
        part_strings.append(string)
    subject = ''.join(part_strings)
    _LOG.debug('decoded header {} -> {}'.format(parts[0], subject))
    return subject.lower().replace('#', '')

def _get_message_target(course, message, original, person, subject,
                        respond=None, use_color=None):
    """
    >>> _get_message_target(course=None, message=None, original=None,
    ...     person=None, subject='no tag')
    Traceback (most recent call last):
      ...
    ValueError: no tag in 'no tag'
    >>> _get_message_target(course=None, message=None, original=None,
    ...     person=None, subject='[] empty tag')
    Traceback (most recent call last):
      ...
    ValueError: empty tag in '[] empty tag'
    >>> _get_message_target(course=None, message=None, original=None,
    ...     person=None, subject='[abc] empty tag')
    'abc'
    >>> _get_message_target(course=None, message=None, original=None,
    ...     person=None, subject='[phys160:abc] empty tag')
    'abc'
    """
    match = _TAG_REGEXP.match(subject)
    if match is None:
        response_subject = 'no tag in {!r}'.format(subject)
        if respond:
            _respond(
                course=course, person=person, original=original,
                subject=response_subject, text=(
                        'We received an email message from you without\n'
                        'subject tags.'),
                respond=respond)
        raise ValueError(response_subject)
    tag = match.group(1)
    if tag == '':
        response_subject = 'empty tag in {!r}'.format(subject)
        if respond:
            _respond(
                course=course, person=person, original=original,
                subject=response_subject, text=(
                        'We received an email message from you with empty\n'
                        'subject tags.'),
                respond=respond)
        raise ValueError(response_subject)    
    target = tag.rsplit(':', 1)[-1]
    _LOG.debug('extracted target {} -> {}'.format(subject, target))
    return target

def _get_handler(course, handlers, message, person, subject, target,
                 respond=None, use_color=None):
    try:
        handler = handlers[target]
    except KeyError: 
        response_subject = 'no handler for {}'.format(target)
        highlight,lowlight,good,bad = _standard_colors(use_color=use_color)
        _LOG.debug(_color_string(string=response_subject, color=bad))
        if respond:
            targets = sorted(handlers.keys())
            if not targets:
                hint = (
                    'In fact, there are no available handlers for this\n'
                    'course!\n')
            else:
                hint = (
                    'Perhaps you meant to use one of the following:\n'
                    '  {}\n\n').format('\n  '.join(targets))
            _respond(
                course=course, person=person, original=original,
                subject=response_subject, text=(
                    'We got an email from you with the following subject:\n'
                    '  {!r}\n'
                    'which does not match any submittable handler name for\n'
                    '{}.\n'
                    '{}').format(repr(subject), course.name, hint),
                respond=respond)
        return None
    return handler

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

    >>> signed.authenticated
    Traceback (most recent call last):
      ...
    AttributeError: 'MIMEMultipart' object has no attribute 'authenticated'
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
    >>> our_message.authenticated
    True

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
    decrypted.authenticated = True
    return decrypted
