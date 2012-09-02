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

"""Extract message parts with a given MIME type from a mailbox.
"""

from __future__ import absolute_import

import email.utils as _email_utils
import hashlib as _hashlib
import mailbox as _mailbox
import os as _os
import os.path as _os_path
import time as _time

from . import LOG as _LOG


def message_time(message):
    """Get the Unix time when ``message`` was received.

    >>> from email.utils import formatdate
    >>> from pgp_mime.email import encodedMIMEText
    >>> msg = encodedMIMEText('Ping!')
    >>> msg['Received'] = (
    ...     'from smtp.home.net (smtp.home.net [123.456.123.456]) '
    ...     'by smtp.mail.uu.edu (Postfix) with ESMTP id 5BA225C83EF '
    ...     'for <wking@tremily.us>; Sun, 09 Oct 2011 11:50:46 -0400 (EDT)')
    >>> time = message_time(msg)
    >>> time
    1318175446.0
    >>> formatdate(time)
    'Sun, 09 Oct 2011 15:50:46 -0000'
    """
    received = message['Received']  # RFC 822
    if received is None:
        mid = message['Message-ID']
        _LOG.debug('no Received in {}'.format(mid))
        return None
    date = received.split(';', 1)[1]
    return _time.mktime(_email_utils.parsedate(date))

def extract_mime(message, mime_type=None, output='.', dry_run=False):
    _LOG.debug('parsing {}'.format(message['Subject']))
    time = message_time(message=message)
    for part in message.walk():
        fname = part.get_filename()
        if not fname:
            continue  # don't extract parts without filenames
        ffname = _os_path.join(output, fname)  # full file name
        ctype = part.get_content_type()
        if mime_type is None or ctype == mime_type:
            contents = part.get_payload(decode=True)
            count = 0
            base_ffname = ffname
            is_copy = False
            while _os_path.exists(ffname):
                old = _hashlib.sha1(open(ffname, 'rb').read())
                new = _hashlib.sha1(contents)
                if old.digest() == new.digest():
                    is_copy = True
                    break
                count += 1
                ffname = '{}.{}'.format(base_ffname, count)
            if is_copy:
                _LOG.debug('{} already extracted as {}'.format(fname, ffname))
                continue
            _LOG.debug('extract {} to {}'.format(fname, ffname))
            if not dry_run:
                with open(ffname, 'wb') as f:
                    f.write(contents)
                if time is not None:
                    _os.utime(ffname, (time, time))
