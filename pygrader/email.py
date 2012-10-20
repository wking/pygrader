# -*- coding: utf-8 -*-
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

from __future__ import absolute_import

from email.header import Header as _Header
from email.header import decode_header as _decode_header
from email.mime.message import MIMEMessage as _MIMEMessage
from email.mime.multipart import MIMEMultipart as _MIMEMultipart
import email.utils as _email_utils
import logging as _logging
import smtplib as _smtplib

import pgp_mime as _pgp_mime

from . import ENCODING as _ENCODING
from . import LOG as _LOG
from .model.person import Person as _Person


def test_smtp(smtp, author, targets, msg=None):
    """Test the SMTP connection by sending a message to `target`
    """
    if msg is None:
        msg = _pgp_mime.encodedMIMEText('Success!')
        msg['Date'] = _email_utils.formatdate()
        msg['From'] = author
        msg['Reply-to'] = msg['From']
        msg['To'] = ', '.join(targets)
        msg['Subject'] = 'Testing pygrader SMTP connection'
    _LOG.info('send test message to SMTP server')
    smtp.send_message(msg=msg)
test_smtp.__test__ = False  # not a test for nose

def send_emails(emails, smtp=None, debug_target=None, dry_run=False):
    """Iterate through `emails` and mail them off one-by-one

    >>> from email.mime.text import MIMEText
    >>> from sys import stdout
    >>> emails = []
    >>> for target in ['Moneypenny <mp@sis.gov.uk>', 'M <m@sis.gov.uk>']:
    ...     msg = MIMEText('howdy!', 'plain', 'us-ascii')
    ...     msg['From'] = 'John Doe <jdoe@a.gov.ru>'
    ...     msg['To'] = target
    ...     msg['Bcc'] = 'James Bond <007@sis.gov.uk>'
    ...     emails.append(
    ...         (msg,
    ...          lambda status: stdout.write('SUCCESS: {}\\n'.format(status))))
    >>> send_emails(emails, dry_run=True)
    ... # doctest: +REPORT_UDIFF, +NORMALIZE_WHITESPACE
    SUCCESS: None
    SUCCESS: None
    """
    local_smtp = smtp is None
    for msg,callback in emails:
        sources = [
            _email_utils.formataddr(a) for a in _pgp_mime.email_sources(msg)]
        author = sources[0]
        targets = [
            _email_utils.formataddr(a) for a in _pgp_mime.email_targets(msg)]
        _pgp_mime.strip_bcc(msg)
        if _LOG.level <= _logging.DEBUG:
            # TODO: remove convert_content_transfer_encoding?
            #if msg.get('content-transfer-encoding', None) == 'base64':
            #    convert_content_transfer_encoding(msg, '8bit')
            _LOG.debug('\n{}\n'.format(msg.as_string()))
        _LOG.info('sending message to {}...'.format(targets))
        if not dry_run:
            try:
                if local_smtp:
                    smtp = _smtplib.SMTP('localhost')
                if debug_target:
                    targets = [debug_target]
                smtp.sendmail(author, targets, msg.as_string())
                if local_smtp:
                    smtp.quit()
            except:
                _LOG.warning('failed to send message to {}'.format(targets))
                if callback:
                    callback(False)
                raise
            else:
                _LOG.info('sent message to {}'.format(targets))
                if callback:
                    callback(True)
        else:
            _LOG.info('dry run, so no message sent to {}'.format(targets))
            if callback:
                callback(None)


class Responder (object):
    def __init__(self, *args, **kwargs):
        self.args = args
        if kwargs is None:
            kwargs = {}
        self.kwargs = kwargs

    def __call__(self, message):
        send_emails([(message, None)], *self.args, **self.kwargs)


def get_address(person):
    r"""
    >>> from pygrader.model.person import Person as Person
    >>> p = Person(name='Jack', emails=['a@b.net'])
    >>> get_address(p)
    'Jack <a@b.net>'

    Here's a simple unicode example.  The name portion of the address
    is encoded following RFC 2047.

    >>> p.name = '✉'
    >>> get_address(p)
    '=?utf-8?b?4pyJ?= <a@b.net>'

    Note that the address is in the clear.  Otherwise you can have
    trouble when your mailer tries to decode the name following
    :RFC:`2822`, which limits the locations in which encoded words may
    appear.
    """
    encoding = _pgp_mime.guess_encoding(person.name)
    return _email_utils.formataddr(
        (person.name, person.emails[0]), charset=encoding)

def construct_email(author, targets, subject, message, cc=None):
    if author.pgp_key:
        signers = [author.pgp_key]
    else:
        signers = []
    recipients = [p.pgp_key for p in targets if p.pgp_key]
    encrypt = True
    for person in targets:
        if not person.pgp_key:
            encrypt = False  # cannot encrypt to every recipient
            break
    if cc:
        recipients.extend([p.pgp_key for p in cc if p.pgp_key])
        for person in cc:
            if not person.pgp_key:
                encrypt = False
                break
    if not recipients:
        encrypt = False  # noone to encrypt to
    if signers and encrypt:
        if author.pgp_key not in recipients:
            recipients.append(author.pgp_key)
        message = _pgp_mime.sign_and_encrypt(
            message=message, signers=signers, recipients=recipients,
            always_trust=True)
    elif signers:
        message = _pgp_mime.sign(message=message, signers=signers)
    elif encrypt:
        message = _pgp_mime.encrypt(message=message, recipients=recipients)

    message['Date'] = _email_utils.formatdate()
    message['From'] = get_address(author)
    message['Reply-to'] = message['From']
    message['To'] = ', '.join(
        get_address(target) for target in targets)
    if cc:
        message['Cc'] = ', '.join(
            get_address(target) for target in cc)
    subject_encoding = _pgp_mime.guess_encoding(subject)
    if subject_encoding == 'us-ascii':
        message['Subject'] = subject
    else:
        message['Subject'] = _Header(subject, subject_encoding)

    return message

def construct_text_email(author, targets, subject, text, cc=None):
    r"""Build a text/plain email using `Person` instances

    >>> from pygrader.model.person import Person as Person
    >>> author = Person(name='Джон Доу', emails=['jdoe@a.gov.ru'])
    >>> targets = [Person(name='Jill', emails=['c@d.net'])]
    >>> cc = [Person(name='H.D.', emails=['hd@wall.net'])]
    >>> msg = construct_text_email(author, targets, cc=cc,
    ...     subject='Once upon a time', text='Bla bla bla...')
    >>> print(msg.as_string())  # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Date: ...
    From: =?utf-8?b?0JTQttC+0L0g0JTQvtGD?= <jdoe@a.gov.ru>
    Reply-to: =?utf-8?b?0JTQttC+0L0g0JTQvtGD?= <jdoe@a.gov.ru>
    To: Jill <c@d.net>
    Cc: "H.D." <hd@wall.net>
    Subject: Once upon a time
    <BLANKLINE>
    Bla bla bla...

    With unicode text:

    >>> msg = construct_text_email(author, targets, cc=cc,
    ...     subject='Once upon a time', text='Funky ✉.')
    >>> print(msg.as_string())  # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: text/plain; charset="utf-8"
    MIME-Version: 1.0
    Content-Transfer-Encoding: base64
    Content-Disposition: inline
    Date: ...
    From: =?utf-8?b?0JTQttC+0L0g0JTQvtGD?= <jdoe@a.gov.ru>
    Reply-to: =?utf-8?b?0JTQttC+0L0g0JTQvtGD?= <jdoe@a.gov.ru>
    To: Jill <c@d.net>
    Cc: "H.D." <hd@wall.net>
    Subject: Once upon a time
    <BLANKLINE>
    RnVua3kg4pyJLg==
    <BLANKLINE>
    """
    message = _pgp_mime.encodedMIMEText(text)
    return construct_email(
        author=author, targets=targets, subject=subject, message=message,
        cc=cc)

def construct_response(author, targets, subject, text, original, cc=None):
    r"""Build a multipart/mixed response email using `Person` instances

    >>> from pygrader.model.person import Person as Person
    >>> student = Person(name='Джон Доу', emails=['jdoe@a.gov.ru'])
    >>> assistant = Person(name='Jill', emails=['c@d.net'])
    >>> cc = [assistant]
    >>> msg = construct_text_email(author=student, targets=[assistant],
    ...     subject='Assignment 1 submission', text='Bla bla bla...')
    >>> rsp = construct_response(author=assistant, targets=[student],
    ...     subject='Received assignment 1 submission', text='3 hours late',
    ...     original=msg)
    >>> print(rsp.as_string())  # doctest: +REPORT_UDIFF, +ELLIPSIS
    Content-Type: multipart/mixed; boundary="===============...=="
    MIME-Version: 1.0
    Date: ...
    From: Jill <c@d.net>
    Reply-to: Jill <c@d.net>
    To: =?utf-8?b?0JTQttC+0L0g0JTQvtGD?= <jdoe@a.gov.ru>
    Subject: Received assignment 1 submission
    <BLANKLINE>
    --===============...==
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    <BLANKLINE>
    3 hours late
    --===============...==
    Content-Type: message/rfc822
    MIME-Version: 1.0
    <BLANKLINE>
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    Date: ...
    From: =?utf-8?b?0JTQttC+0L0g0JTQvtGD?= <jdoe@a.gov.ru>
    Reply-to: =?utf-8?b?0JTQttC+0L0g0JTQvtGD?= <jdoe@a.gov.ru>
    To: Jill <c@d.net>
    Subject: Assignment 1 submission
    <BLANKLINE>
    Bla bla bla...
    --===============...==--
    """
    message = _MIMEMultipart('mixed')
    message.attach(_pgp_mime.encodedMIMEText(text))
    message.attach(_MIMEMessage(original))
    return construct_email(
        author=author, targets=targets, subject=subject, message=message,
        cc=cc)
