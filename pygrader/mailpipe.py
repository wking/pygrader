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

"Incoming email processing."

from __future__ import absolute_import

from email import message_from_file as _message_from_file
from email.header import decode_header as _decode_header
from email.mime.text import MIMEText as _MIMEText
from email.utils import parseaddr as _parseaddr
import mailbox as _mailbox
import re as _re
import sys as _sys

import pgp_mime as _pgp_mime
import pgp_mime.key as _pgp_mime_key

from . import LOG as _LOG
from .email import construct_email as _construct_email
from .email import construct_response as _construct_response
from .extract_mime import message_time as _message_time
from .model.person import Person as _Person

from .handler import InsecureMessage as _InsecureMessage
from .handler import InvalidAssignmentSubject as _InvalidAssignmentSubject
from .handler import InvalidMessage as _InvalidMessage
from .handler import InvalidStudentSubject as _InvalidStudentSubject
from .handler import InvalidSubjectMessage as _InvalidSubjectMessage
from .handler import PermissionViolationMessage as _PermissionViolationMessage
from .handler import Response as _Response
from .handler import UnsignedMessage as _UnsignedMessage
from .handler.get import run as _handle_get
from .handler.grade import run as _handle_grade
from .handler.grade import MissingGradeMessage as _MissingGradeMessage
from .handler.submission import run as _handle_submission
from .handler.submission import InvalidSubmission as _InvalidSubmission


_TAG_REGEXP = _re.compile('^.*\[([^]]*)\].*$')


class NoReturnPath (_InvalidMessage):
    def __init__(self, address, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'no Return-Path'
        super(NoReturnPath, self).__init__(**kwargs)


class UnregisteredAddress (_InvalidMessage):
    def __init__(self, address, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'unregistered address {}'.format(address)
        super(UnregisteredAddress, self).__init__(**kwargs)
        self.address = address


class AmbiguousAddress (_InvalidMessage):
    def __init__(self, address, people, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'ambiguous address {}'.format(address)
        super(AmbiguousAddress, self).__init__(**kwargs)
        self.address = address
        self.people = people


class WrongSignatureMessage (_InsecureMessage):
    def __init__(self, pgp_key=None, signatures=None, fingerprints=None,
                 decrypted=None, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'not signed by the expected key'
        super(WrongSignatureMessage, self).__init__(**kwargs)
        self.pgp_key = pgp_key
        self.signatures = signatures
        self.fingerprints = fingerprints
        self.decrypted = decrypted


class UnverifiedSignatureMessage (_InsecureMessage):
    def __init__(self, signature=None, decrypted=None, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'unverified signature'
        super(UnverifiedSignatureMessage, self).__init__(**kwargs)
        self.signature = signature
        self.decrypted = decrypted


class SubjectlessMessage (_InvalidSubjectMessage):
    def __init__(self, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'no subject'
        super(SubjectlessMessage, self).__init__(**kwargs)


class InvalidHandlerMessage (_InvalidSubjectMessage):
    def __init__(self, target=None, handlers=None, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'no handler for {!r}'.format(target)
        super(InvalidHandlerMessage, self).__init__(**kwargs)
        self.target = target
        self.handlers = handlers


def mailpipe(basedir, course, stream=None, mailbox=None, input_=None,
             output=None, continue_after_invalid_message=False, max_late=0,
             trust_email_infrastructure=False,
             handlers={
        'get': _handle_get,
        'grade': _handle_grade,
        'submit': _handle_submission,
        }, respond=None, dry_run=False, **kwargs):
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

    >>> from io import StringIO
    >>> from pgp_mime.email import encodedMIMEText
    >>> from .handler import InvalidMessage, Response
    >>> from .test.course import StubCourse

    >>> course = StubCourse()
    >>> def respond(message):
    ...     print('respond with:\\n{}'.format(message.as_string()))
    >>> def process(message):
    ...     mailpipe(
    ...         basedir=course.basedir, course=course.course,
    ...         stream=StringIO(message.as_string()),
    ...         output=course.mailbox,
    ...         continue_after_invalid_message=True,
    ...         respond=respond)
    >>> message = encodedMIMEText('The answer is 42.')
    >>> message['Message-ID'] = '<123.456@home.net>'
    >>> message['Received'] = (
    ...     'from smtp.home.net (smtp.home.net [123.456.123.456]) '
    ...     'by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF '
    ...     'for <wking@tremily.us>; Sun, 09 Oct 2011 11:50:46 -0400 (EDT)')
    >>> message['From'] = 'Billy B <bb@greyhavens.net>'
    >>> message['To'] = 'phys101 <phys101@tower.edu>'
    >>> message['Subject'] = '[submit] assignment 1'

    Messages with unrecognized ``Return-Path``\s are silently dropped:

    >>> process(message)  # doctest: +REPORT_UDIFF, +ELLIPSIS
    >>> course.print_tree()  # doctest: +REPORT_UDIFF, +ELLIPSIS
    course.conf
    mail
    mail/cur
    mail/new
    mail/tmp

    Response to a message from an unregistered person:

    >>> message['Return-Path'] = '<invalid.return.path@home.net>'
    >>> process(message)  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
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
    <BLANKLINE>
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
    From: Billy B <bb@greyhavens.net>
    To: phys101 <phys101@tower.edu>
    Subject: [submit] assignment 1
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

    If we add a valid ``Return-Path``, we get the expected delivery:

    >>> del message['Return-Path']
    >>> message['Return-Path'] = '<bb@greyhavens.net>'
    >>> process(message)  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Bilbo Baggins <bb@shire.org>
    Subject: Received Assignment 1 submission
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Disposition: inline
    Content-Transfer-Encoding: 7bit
    <BLANKLINE>
    Billy,
    <BLANKLINE>
    We received your submission for Assignment 1 on Sun, 09 Oct 2011 15:50:46 -0000.
    <BLANKLINE>
    Yours,
    phys-101 robot
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
    >>> process(message)  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Bilbo Baggins <bb@shire.org>
    Subject: Received Assignment 1 submission
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Disposition: inline
    Content-Transfer-Encoding: 7bit
    <BLANKLINE>
    Billy,
    <BLANKLINE>
    We received your submission for Assignment 1 on Mon, 10 Oct 2011 16:50:46 -0000.
    <BLANKLINE>
    Yours,
    phys-101 robot
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

    >>> del message['Message-ID']
    >>> message['Message-ID'] = '<hgi.jlk@home.net>'
    >>> process(message)  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Bilbo Baggins <bb@shire.org>
    Subject: Received Assignment 1 submission
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Disposition: inline
    Content-Transfer-Encoding: 7bit
    <BLANKLINE>
    Billy,
    <BLANKLINE>
    We received your submission for Assignment 1 on Mon, 10 Oct 2011 16:50:46 -0000.
    <BLANKLINE>
    Yours,
    phys-101 robot
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

    Response to a submission on an unsubmittable assignment:

    >>> del message['Subject']
    >>> message['Subject'] = '[submit] attendance 1'
    >>> process(message)  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
    MIME-Version: 1.0
    Content-Disposition: inline
    Date: ...
    From: Robot101 <phys101@tower.edu>
    Reply-to: Robot101 <phys101@tower.edu>
    To: Bilbo Baggins <bb@shire.org>
    Subject: Received invalid Attendance 1 submission
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
    <BLANKLINE>
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

    >>> del message['Subject']
    >>> message['Subject'] = 'need help for the first homework'
    >>> process(message)  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
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
    We received an email message from you with an invalid
    subject.
    <BLANKLINE>
    Yours,
    phys-101 robot
    <BLANKLINE>
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

    >>> del message['Subject']
    >>> process(message)  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/signed; ...protocol="application/pgp-signature"; ...boundary="===============...=="
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
    <BLANKLINE>
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
    >>> del message['Subject']
    >>> process(message)  # doctest: +REPORT_UDIFF, +ELLIPSIS
    respond with:
    Content-Type: multipart/encrypted; ...protocol="application/pgp-encrypted"; ...boundary="===============...=="
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

    >>> course.cleanup()
    """
    if stream is None:
        stream = _sys.stdin
    for original,message,person,subject,target in _load_messages(
        course=course, stream=stream, mailbox=mailbox, input_=input_,
        output=output, dry_run=dry_run,
        continue_after_invalid_message=continue_after_invalid_message,
        trust_email_infrastructure=trust_email_infrastructure,
        respond=respond):
        try:
            handler = _get_handler(handlers=handlers, target=target)
            _LOG.debug('handling {}'.format(target))
            handler(
                basedir=basedir, course=course, message=message,
                person=person, subject=subject,
                max_late=max_late,
                trust_email_infrastructure=trust_email_infrastructure,
                dry_run=dry_run)
        except _InvalidMessage as error:
            error.course = course
            error.message = original
            for attribute,value in [('person', person),
                                    ('subject', subject),
                                    ('target', target)]:
                if (value is not None and
                    getattr(error, attribute, None) is None):
                    setattr(error, attribute, value)
            _LOG.warn('invalid message {}'.format(error.message_id()))
            if not continue_after_invalid_message:
                raise
            _LOG.warn('{}'.format(error))
            if respond:
                response = _get_error_response(error)
                respond(response)
        except _Response as response:
            if respond:
                msg = response.message
                if not response.complete:
                    author = course.robot
                    target = person
                    msg = response.message
                    if isinstance(response.message, _MIMEText):
                        # Manipulate body (based on pgp_mime.append_text)
                        original_encoding = msg.get_charset().input_charset
                        original_payload = str(
                            msg.get_payload(decode=True), original_encoding)
                        new_payload = (
                            '{},\n\n'
                            '{}\n\n'
                            'Yours,\n'
                            '{}\n').format(
                            target.alias(), original_payload, author.alias())
                        new_encoding = _pgp_mime.guess_encoding(new_payload)
                        if msg.get('content-transfer-encoding', None):
                            # clear CTE so set_payload will set it properly
                            del msg['content-transfer-encoding']
                        msg.set_payload(new_payload, new_encoding)
                    subject = msg['Subject']
                    assert subject is not None, msg
                    del msg['Subject']
                    msg = _construct_email(
                        author=author, targets=[person], subject=subject,
                        message=msg)
                respond(msg)

def _load_messages(course, stream, mailbox=None, input_=None, output=None,
                   continue_after_invalid_message=False,
                   trust_email_infrastructure=False, respond=None,
                   dry_run=False):
    if mailbox is None:
        _LOG.debug('loading message from {}'.format(stream))
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
        messages = []
        for key,msg in mbox.items():
            subpath = mbox._lookup(key)
            if subpath.endswith('.gitignore'):
                _LOG.debug('skipping non-message {}'.format(subpath))
                continue
            messages.append((key, msg))
        if output is not None:
            ombox = _mailbox.Maildir(output, factory=None, create=True)
    else:
        raise ValueError(mailbox)
    messages.sort(key=_get_message_time)
    for key,msg in messages:
        try:
            ret = _parse_message(
                course=course, message=msg,
                trust_email_infrastructure=trust_email_infrastructure)
        except _InvalidMessage as error:
            error.message = msg
            _LOG.warn('invalid message {}'.format(error.message_id()))
            if not continue_after_invalid_message:
                raise
            _LOG.warn('{}'.format(error))
            if respond:
                response = _get_error_response(error)
                if response is not None:
                    respond(response)
            continue
        if output is not None and dry_run is False:
            # move message from input mailbox to output mailbox
            ombox.add(msg)
            if mbox is not None:
                del mbox[key]
        yield ret

def _parse_message(course, message, trust_email_infrastructure=False):
    """Parse an incoming email and respond if neccessary.

    Return ``(msg, person, assignment, time)`` on successful parsing.
    Return ``None`` on failure.
    """
    original = message
    person = subject = target = None
    try:
        person = _get_message_person(course=course, message=message)
        if person.pgp_key:
            _LOG.debug('verify message is from {}'.format(person))
            try:
                message = _get_verified_message(message, person.pgp_key)
            except _UnsignedMessage as error:
                if trust_email_infrastructure:
                    _LOG.warn('{}'.format(error))
                else:
                    raise
        subject = _get_message_subject(message=message)
        target = _get_message_target(subject=subject)
    except _InvalidMessage as error:
        error.course = course
        error.message = original
        for attribute,value in [('person', person),
                                ('subject', subject),
                                ('target', target)]:
            if (value is not None and
                getattr(error, attribute, None) is None):
                setattr(error, attribute, value)
        raise
    return (original, message, person, subject, target)

def _get_message_person(course, message, trust_admin_from=True):
    """Get the `Person` that sent the message.

    We use 'Return-Path' (envelope from) instead of the message's From
    header, because it's more consistent and harder to fake.  However,
    there may be times when you *want* to send a message in somebody
    elses name.

    For example, if a student submitted an assignment from an
    unexpected address, you might add that address to their entry in
    your course config, and then bounce the message back into
    pygrader.  In this case, the From header will still be the
    student, but the 'Return-Path' will be you.  With
    `trust_admin_from` (on by default), messages who's 'Return-Path'
    matches a professor or TA will have their 'From' line used to find
    the final person responsible for the message.

    >>> from pygrader.model.course import Course
    >>> from pygrader.model.person import Person
    >>> from pgp_mime import encodedMIMEText

    >>> course = Course(people=[
    ...     Person(
    ...         name='Gandalf', emails=['g@grey.edu'], groups=['professors']),
    ...     Person(name='Bilbo', emails=['bb@shire.org']),
    ...     ])
    >>> message = encodedMIMEText('testing')
    >>> message['Return-Path'] = '<g@grey.edu>'
    >>> message['From'] = 'Bill <bb@shire.org>'
    >>> message['Message-ID'] = '<123.456@home.net>'

    >>> person = _get_message_person(course=course, message=message)
    >>> print(person)
    <Person Bilbo>

    >>> person = _get_message_person(
    ...     course=course, message=message, trust_admin_from=False)
    >>> print(person)
    <Person Gandalf>
    """
    sender = message['return-path']  # RFC 822
    if sender is None:
        raise NoReturnPath(message)
    sender = sender[1:-1]  # strip wrapping '<' and '>'
    people = list(course.find_people(email=sender))
    if len(people) == 0:
        raise UnregisteredAddress(message=message, address=sender)
    if len(people) > 1:
        raise AmbiguousAddress(message=message, address=sender, people=people)
    person = people[0]
    if trust_admin_from and person.is_admin():
        mid = message['message-id']
        from_headers = message.get_all('from')
        if len(from_headers) == 0:
            _LOG.debug("no 'From' headers in {}".format(mid))
        elif len(from_headers) > 1:
            _LOG.debug("multiple 'From' headers in {}".format(mid))
        else:
            name,address = _parseaddr(from_headers[0])
            people = list(course.find_people(email=address))
            if len(people) == 0:
                _LOG.debug("'From' address {} is unregistered".format(address))
            if len(people) > 1:
                _LOG.debug("'From' address {} is ambiguous".format(address))
            _LOG.debug('message from {} treated as being from {}'.format(
                    person, people[0]))
            person = people[0]
    _LOG.debug('message from {}'.format(person))
    return person

def _get_message_subject(message):
    """
    >>> from email.header import Header
    >>> from pgp_mime.email import encodedMIMEText
    >>> message = encodedMIMEText('The answer is 42.')
    >>> message['Message-ID'] = 'msg-id'
    >>> _get_message_subject(message=message)
    Traceback (most recent call last):
      ...
    pygrader.mailpipe.SubjectlessMessage: no subject
    >>> del message['Subject']
    >>> subject = Header('unicode part', 'utf-8')
    >>> subject.append('-ascii part', 'ascii')
    >>> message['Subject'] = subject.encode()
    >>> _get_message_subject(message=message)
    'unicode part -ascii part'
    >>> del message['Subject']
    >>> message['Subject'] = 'clean subject'
    >>> _get_message_subject(message=message)
    'clean subject'
    """
    if message['Subject'] is None:
        raise SubjectlessMessage(subject=None, message=message)

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

def _get_message_target(subject):
    """
    >>> _get_message_target(subject='no tag')
    Traceback (most recent call last):
      ...
    pygrader.handler.InvalidSubjectMessage: no tag in 'no tag'
    >>> _get_message_target(subject='[] empty tag')
    Traceback (most recent call last):
      ...
    pygrader.handler.InvalidSubjectMessage: empty tag in '[] empty tag'
    >>> _get_message_target(subject='[abc] empty tag')
    'abc'
    >>> _get_message_target(subject='[phys160:abc] empty tag')
    'abc'
    """
    match = _TAG_REGEXP.match(subject)
    if match is None:
        raise _InvalidSubjectMessage(
            subject=subject, error='no tag in {!r}'.format(subject))
    tag = match.group(1)
    if tag == '':
        raise _InvalidSubjectMessage(
            subject=subject, error='empty tag in {!r}'.format(subject))
    target = tag.rsplit(':', 1)[-1]
    _LOG.debug('extracted target {} -> {}'.format(subject, target))
    return target

def _get_handler(handlers, target):
    try:
        handler = handlers[target]
    except KeyError as error:
        raise InvalidHandlerMessage(
            target=target, handlers=handlers) from error
    return handler

def _get_verified_message(message, pgp_key):
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

    If it is signed, but not by the right key, we get an error.

    >>> print(_get_verified_message(signed, pgp_key='01234567'))
    Traceback (most recent call last):
      ...
    pygrader.mailpipe.WrongSignatureMessage: not signed by the expected key

    If it is not signed at all, we get another error.

    >>> print(_get_verified_message(message, pgp_key='4332B6E3'))
    Traceback (most recent call last):
      ...
    pygrader.handler.UnsignedMessage: unsigned message
    """
    mid = message['message-id']
    try:
        decrypted,verified,signatures = _pgp_mime.verify(message=message)
    except (ValueError, AssertionError) as error:
        raise _UnsignedMessage(message=message) from error
    for signature in signatures:
        _LOG.debug(signature.dumps())
    match = None
    fingerprints = dict((s.fingerprint, s) for s in signatures)
    for s in signatures:
        for key in _pgp_mime_key.lookup_keys([s.fingerprint]):
            if key.subkeys[0].fingerprint != s.fingerprint:
                # the signature was made with a subkey.  Add the primary.
                fingerprints[key.subkeys[0].fingerprint] = s
    if pgp_key.startswith('0x'):
        key_tail = pgp_key[len('0x'):]
    else:
        key_tail = pgp_key
    matches = [fingerprints[f] for f in fingerprints.keys()
               if f.endswith(key_tail)]
    if len(matches) == 0:
        raise WrongSignatureMessage(
            message=message, pgp_key=pgp_key, signatures=signatures,
            fingerprints=fingerprints, decrypted=decrypted)
    signature = matches[0]
    if not verified:
        problems = [k for k,v in signature.summary.items() if v]
        for good in ['green', 'valid']:
            if good in problems:
                problems.remove(good)
        if problems:
            raise UnverifiedSignatureMessage(
                message=message, signature=signature, decrypted=decrypted)
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

def _get_error_response(error):
    author = error.course.robot
    target = getattr(error, 'person', None)
    subject = str(error)
    if isinstance(error, _InvalidSubmission):
        subject = 'Received invalid {} submission'.format(
            error.assignment.name)
        text = (
            'We received your submission for {}, but you are not\n'
            'allowed to submit that assignment via email.'
            ).format(error.assignment.name)
    elif isinstance(error, _MissingGradeMessage):
        subject = 'No grade in {!r}'.format(error.subject)
        text = (
            'Your grade submission did not include a text/plain\n'
            'part containing the new grade and comment.'
            )
    elif isinstance(error, InvalidHandlerMessage):
        targets = sorted(error.handlers.keys())
        if not targets:
            hint = (
                'In fact, there are no available handlers for this\n'
                'course!')
        else:
            hint = (
                'Perhaps you meant to use one of the following:\n'
                '  {}').format('\n  '.join(targets))
        text = (
            'We received an email from you with the following subject:\n'
            '  {!r}\n'
            'which does not match any submittable handler name for\n'
            '{}.\n'
            '{}').format(error.subject, error.course.name, hint)
    elif isinstance(error, SubjectlessMessage):
        subject = 'no subject in {}'.format(error.message['Message-ID'])
        text = 'We received an email message from you without a subject.'
    elif isinstance(error, AmbiguousAddress):
        text = (
            'Multiple people match {} ({})'.format(
                error.address, ', '.join(p.name for p in error.people)))
    elif isinstance(error, UnregisteredAddress):
        target = _Person(name=error.address, emails=[error.address])
        text = (
            'Your email address is not registered with pygrader for\n'
            '{}.  If you feel it should be, contact your professor\n'
            'or TA.').format(error.course.name)
    elif isinstance(error, NoReturnPath):
        return
    elif isinstance(error, _InvalidAssignmentSubject):
        if error.assignments:
            hint = (
                'but it matches several assignments:\n'
                '  * {}').format('\n  * '.join(
                    a.name for a in error.assignments))
        else:
            # prefer a submittable example assignment
            assignments = [
                a for a in error.course.assignments if a.submittable]
            assignments += error.course.assignments  # but fall back to any one
            hint = (
                'Remember to use the full name for the assignment in the\n'
                'subject.  For example:\n'
                '  {} submission').format(assignments[0].name)
        text = (
            'We received an email from you with the following subject:\n'
            '  {!r}\n{}').format(error.subject, hint)
    elif isinstance(error, _InvalidStudentSubject):
        text = (
            'We received an email from you with the following subject:\n'
            '  {!r}\n'
            'but it matches several students:\n'
            '  * {}').format(
            error.subject, '\n  * '.join(s.name for s in error.students))
    elif isinstance(error, _InvalidSubjectMessage):
        text = (
            'We received an email message from you with an invalid\n'
            'subject.')
    elif isinstance(error, _UnsignedMessage):
        subject = 'unsigned message {}'.format(error.message['Message-ID'])
        text = (
            'We received an email message from you without a PGP\n'
            'signature.'
            )
    elif isinstance(error, WrongSignatureMessage):
        lines = [
            'We received an email message from you without a valid',
            'PGP signature.  We were expecting a signature by',
            '{}, but got signatures by:'.format(error.person.pgp_key),
            ]
        lines.extend(['  {}'.format(s.fingerprint) for s in error.signatures])
        text = '\n'.join(lines)
    elif isinstance(error, UnverifiedSignatureMessage):
        text = (
            'We received an email message from you with an unverified\n'
            'signature:\n\n'
            '{}\n\n'
            'If this is the key you intended to use, contact your\n'
            'professor or TA.'
            ).format(error.signature.dumps(prefix='  '))
    elif isinstance(error, _PermissionViolationMessage):
        text = (
            'We received an email from you with the following subject:\n'
            '  {!r}\n'
            "but you can't do that unless you belong to one of the\n"
            'following groups:\n'
            '  * {}').format(
            error.subject, '\n  * '.join(error.allowed_groups))
    elif isinstance(error, _InvalidMessage):
        text = (
            'We received an email from you with the following subject:\n'
            '  {!r}\n'
            'but the message was invalid:\n'
            '  {}').format(error.subject, error)
    else:
        raise NotImplementedError((type(error), error))
    if target is None:
        raise NotImplementedError((type(error), error))
    return _construct_response(
        author=author,
        targets=[target],
        subject=subject,
        text=(
            '{},\n\n'
            '{}\n\n'
            'Yours,\n'
            '{}\n'.format(target.alias(), text, author.alias())),
        original=error.message)

def _get_message_time(key_message):
    "Key function for sorting mailbox (key,message) tuples."
    key,message = key_message
    return _message_time(message)
