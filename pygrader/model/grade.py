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

class Grade (object):
    def __init__(self, student, assignment, points, comment=None,
                 late=False, notified=False):
        self.student = student
        self.assignment = assignment
        self.points = points
        self.comment = comment
        self.late = late
        self.notified = notified

    def __str__(self):
        return '<{} {}:{}>'.format(
            type(self).__name__, self.student.name, self.assignment.name)

    def __lt__(self, other):
        if self.student < other.student:
            return True
        elif other.student < self.student:
            return False
        return self.assignment < other.assignment
