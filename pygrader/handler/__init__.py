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

"Define assorted handlers for use in :py:mod:`~pygrader.mailpipe`."

import pgp_mime as _pgp_mime


class InvalidMessage (ValueError):
    def __init__(self, message=None, error=None):
        super(InvalidMessage, self).__init__(error)
        self.message = message
        self.error = error

    def message_id(self):
        """Return a short string identifying the invalid message.
        """
        if self.message is None:
            return None
        subject = self.message['Subject']
        if subject is not None:
            return repr(subject)
        message_id = self.message['Message-ID']
        if message_id is not None:
            return message_id
        return None


class PermissionViolationMessage (InvalidMessage):
    def __init__(self, person=None, allowed_groups=None, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'action not permitted'
        super(PermissionViolationMessage, self).__init__(**kwargs)
        self.person = person
        self.allowed_groups = allowed_groups


class InsecureMessage (InvalidMessage):
    def __init__(self, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'insecure message'
        super(InsecureMessage, self).__init__(**kwargs)


class UnsignedMessage (InsecureMessage):
    def __init__(self, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'unsigned message'
        super(UnsignedMessage, self).__init__(**kwargs)


class InvalidSubjectMessage (InvalidMessage):
    def __init__(self, subject=None, **kwargs):
        if 'error' not in kwargs:
            kwargs['error'] = 'invalid subject {!r}'.format(subject)
        super(InvalidSubjectMessage, self).__init__(**kwargs)
        self.subject = subject


class InvalidStudentSubject (InvalidSubjectMessage):
    def __init__(self, students=None, **kwargs):
        if 'error' not in kwargs:
            if students:
                kwargs['error'] = 'Subject matches multiple students'
            else:
                kwargs['error'] = "Subject doesn't match any student"
        super(InvalidStudentSubject, self).__init__(**kwargs)
        self.students = students


class InvalidAssignmentSubject (InvalidSubjectMessage):
    def __init__(self, assignments=None, **kwargs):
        if 'error' not in kwargs:
            if assignments:
                kwargs['error'] = 'Subject matches multiple assignments'
            else:
                kwargs['error'] = "Subject doesn't match any assignment"
        super(InvalidAssignmentSubject, self).__init__(**kwargs)
        self.assignments = assignments


class Response (Exception):
    """Exception to bubble out email responses.

    Rather than sending email responses themselves, handlers should
    raise this exception.  The caller can catch it and mail the email
    (or take other appropriate action).
    """
    def __init__(self, message=None, complete=False):
        super(Response, self).__init__()
        self.message = message
        self.complete = complete


def get_subject_student(course, subject):
    lsubject = subject.lower()
    students = [p for p in course.find_people()
                if p.name.lower() in lsubject]
    if len(students) == 1:
        return students[0]
    raise InvalidStudentSubject(students=students, subject=subject)

def get_subject_assignment(course, subject):
    lsubject = subject.lower()
    assignments = [a for a in course.assignments
                   if a.name.lower() in lsubject]
    if len(assignments) == 1:
        return assignments[0]
    raise InvalidAssignmentSubject(assignments=assignments, subject=subject)
