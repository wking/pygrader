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

class Assignment (object):
    def __init__(self, name, points=1, weight=0, due=0, submittable=True):
        self.name = name
        self.points = points
        self.weight = weight
        self.due = due
        self.submittable = submittable

    def __str__(self):
        return '<{} {}>'.format(type(self).__name__, self.name)

    def __lt__(self, other):
        if self.due < other.due:
            return True
        elif other.due < self.due:
            return False
        return self.name < other.name
