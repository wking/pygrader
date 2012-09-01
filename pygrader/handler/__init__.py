# Copyright

"Define assorted handlers for use in :py:mod:`~pygrader.mailpipe`."

import pgp_mime as _pgp_mime


class InvalidMessage (ValueError):
    def __init__(self, message=None, error=None):
        super(InvalidMessage, self).__init__(error)
        self.message = message
        self.error = error


class UnsignedMessage (InvalidMessage):
    def __init__(self, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'unsigned message'
        super(UnsignedMessage, self).__init__(**kwargs)


class InvalidSubjectMessage (InvalidMessage):
    def __init__(self, subject=None, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'invalid subject {!r}'.format(subject)
        try:
            super(InvalidSubjectMessage, self).__init__(**kwargs)
        except TypeError:
            raise ValueError(kwargs)
        self.subject = subject


class Response (Exception):
    """Exception to bubble out email responses.

    Rather than sending email responses themselves, handlers should
    raise this exception.  The caller can catch it and mail the email
    (or take other appropriate action).
    """
    def __init__(self, message=None):
        super(Response, self).__init__()
        self.message = message
