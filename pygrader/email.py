# -*- coding: utf-8 -*-
# Copyright (C) 2011 W. Trevor King <wking@drexel.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from __future__ import absolute_import

from email.header import Header as _Header
from email.header import decode_header as _decode_header
import email.utils as _email_utils
import logging as _logging
import smtplib as _smtplib

import pgp_mime as _pgp_mime

from . import ENCODING as _ENCODING
from . import LOG as _LOG
from .color import standard_colors as _standard_colors
from .color import color_string as _color_string
from .color import write_color as _write_color
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

def send_emails(emails, smtp=None, use_color=None, debug_target=None,
                dry_run=False):
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
    >>> send_emails(emails, use_color=False, dry_run=True)
    ... # doctest: +REPORT_UDIFF, +NORMALIZE_WHITESPACE
    sending message to ['Moneypenny <mp@sis.gov.uk>', 'James Bond <007@sis.gov.uk>']...\tDRY-RUN
    SUCCESS: None
    sending message to ['M <m@sis.gov.uk>', 'James Bond <007@sis.gov.uk>']...\tDRY-RUN
    SUCCESS: None
    """
    local_smtp = smtp is None
    highlight,lowlight,good,bad = _standard_colors(use_color=use_color)
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
            _LOG.debug(_color_string(
                    '\n{}\n'.format(msg.as_string()), color=lowlight))
        _write_color('sending message to {}...'.format(targets),
                     color=highlight)
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
                _write_color('\tFAILED\n', bad)
                if callback:
                    callback(False)
                raise
            else:
                _write_color('\tOK\n', good)
                if callback:
                    callback(True)
        else:
            _write_color('\tDRY-RUN\n', good)
            if callback:
                callback(None)

def get_address(person, header=False):
    r"""
    >>> from pygrader.model.person import Person as Person
    >>> p = Person(name='Jack', emails=['a@b.net'])
    >>> get_address(p)
    'Jack <a@b.net>'

    Here's a simple unicode example.

    >>> p.name = '✉'
    >>> get_address(p)
    '✉ <a@b.net>'

    When you encode addresses that you intend to place in an email
    header, you should set the `header` option to `True`.  This
    encodes the name portion of the address without encoding the email
    portion.

    >>> get_address(p, header=True)
    '=?utf-8?b?4pyJ?= <a@b.net>'

    Note that the address is in the clear.  Without the `header`
    option you'd have to rely on something like:

    >>> from email.header import Header
    >>> Header(get_address(p), 'utf-8').encode()
    '=?utf-8?b?4pyJIDxhQGIubmV0Pg==?='

    This can cause trouble when your mailer tries to decode the name
    following :RFC:`2822`, which limits the locations in which encoded
    words may appear.
    """
    if header:
        encoding = _pgp_mime.guess_encoding(person.name)
        if encoding == 'us-ascii':
            name = person.name
        else:
            name = _Header(person.name, encoding).encode()
        return _email_utils.formataddr((name, person.emails[0]))
    return _email_utils.formataddr((person.name, person.emails[0]))

def construct_email(author, targets, subject, text, cc=None, sign=True):
    r"""Built a text/plain email using `Person` instances

    >>> from pygrader.model.person import Person as Person
    >>> author = Person(name='Джон Доу', emails=['jdoe@a.gov.ru'])
    >>> targets = [Person(name='Jill', emails=['c@d.net'])]
    >>> cc = [Person(name='H.D.', emails=['hd@wall.net'])]
    >>> msg = construct_email(author, targets, cc=cc,
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

    >>> msg = construct_email(author, targets, cc=cc,
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
    msg = _pgp_mime.encodedMIMEText(text)
    if sign and author.pgp_key:
        msg = _pgp_mime.sign(message=msg, sign_as=author.pgp_key)

    msg['Date'] = _email_utils.formatdate()
    msg['From'] = get_address(author, header=True)
    msg['Reply-to'] = msg['From']
    msg['To'] = ', '.join(
        get_address(target, header=True) for target in targets)
    if cc:
        msg['Cc'] = ', '.join(
            get_address(target, header=True) for target in cc)
    subject_encoding = _pgp_mime.guess_encoding(subject)
    if subject_encoding == 'us-ascii':
        msg['Subject'] = subject
    else:
        msg['Subject'] = _Header(subject, subject_encoding)

    return msg
