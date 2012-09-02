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

import asyncore as _asyncore
import email as _email
import smtpd as _smptd
import socket as _socket

from .. import LOG as _LOG


class SMTPChannel (_smptd.SMTPChannel):
    def close(self):
        super(SMTPChannel, self).close()
        _LOG.debug('close {}'.format(self))
        self.smtp_server.channel_closed()


class SMTPServer (_smptd.SMTPServer):
    """An SMTP server for testing pygrader.

    >>> from asyncore import loop
    >>> from smtplib import SMTP
    >>> from pgp_mime.email import encodedMIMEText
    >>> from pygrader.test.client import MessageSender

    >>> def process(peer, mailfrom, rcpttos, data):
    ...     print('peer:     {}'.format(peer))
    ...     print('mailfrom: {}'.format(mailfrom))
    ...     print('rcpttos:  {}'.format(rcpttos))
    ...     print('message:')
    ...     print(data)
    >>> server = SMTPServer(
    ...     ('localhost', 1025), None, process=process, count=3)

    >>> message = encodedMIMEText('Ping')
    >>> message['From'] = 'a@example.com'
    >>> message['To'] = 'b@example.com, c@example.com'
    >>> message['Cc'] = 'd@example.com'
    >>> messages = [message, message, message]
    >>> ms = MessageSender(address=('localhost', 1025), messages=messages)
    >>> loop()  # doctest: +REPORT_UDIFF, +ELLIPSIS
    peer:     ('127.0.0.1', ...)
    mailfrom: a@example.com
    rcpttos:  ['b@example.com', 'c@example.com', 'd@example.com']
    message:
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    From: a@example.com
    To: b@example.com, c@example.com
    Cc: d@example.com
    <BLANKLINE>
    Ping
    peer:     ('127.0.0.1', ...)
    mailfrom: a@example.com
    rcpttos:  ['b@example.com', 'c@example.com', 'd@example.com']
    message:
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    From: a@example.com
    To: b@example.com, c@example.com
    Cc: d@example.com
    <BLANKLINE>
    Ping
    peer:     ('127.0.0.1', ...)
    mailfrom: a@example.com
    rcpttos:  ['b@example.com', 'c@example.com', 'd@example.com']
    message:
    Content-Type: text/plain; charset="us-ascii"
    MIME-Version: 1.0
    Content-Transfer-Encoding: 7bit
    Content-Disposition: inline
    From: a@example.com
    To: b@example.com, c@example.com
    Cc: d@example.com
    <BLANKLINE>
    Ping
    """
    channel_class = SMTPChannel

    def __init__(self, *args, **kwargs):
        self.count = kwargs.pop('count', None)
        self.process = kwargs.pop('process', None)
        self.channels_open = 0
        super(SMTPServer, self).__init__(*args, **kwargs)

    def log_info(self, message, type='info'):
        # TODO: type -> severity
        _LOG.info(message)

    def handle_accepted(self, conn, addr):
        if self.count <= 0:
            conn.close()
            return
        super(SMTPServer, self).handle_accepted(conn, addr)
        self.channels_open += 1

    def channel_closed(self):
        self.channels_open -= 1
        if self.channels_open == 0 and self.count <= 0:
            _LOG.debug('close {}'.format(self))
            self.close()

    def process_message(self, peer, mailfrom, rcpttos, data):
        if self.count is not None:
            self.count -= 1
            _LOG.debug('Count: {}'.format(self.count))
        _LOG.debug('receiving message from: {}'.format(peer))
        _LOG.debug('message addressed from: {}'.format(mailfrom))
        _LOG.debug('message addressed to  : {}'.format(rcpttos))
        _LOG.debug('message length        : {}'.format(len(data)))
        if self.process:
            self.process(peer, mailfrom, rcpttos, data)
        return
