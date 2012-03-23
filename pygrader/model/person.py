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

class Person (object):
    def __init__(self, name, emails=None, pgp_key=None, aliases=None,
                 groups=None):
        self.name = name
        self.emails = emails
        self.pgp_key = pgp_key
        if not aliases:
            aliases = [self.name]
        self.aliases = aliases
        self.groups = groups

    def __str__(self):
        return '<{} {}>'.format(type(self).__name__, self.name)

    def __lt__(self, other):
        return self.name < other.name

    def alias(self):
        """Return a good alias for direct address
        """
        try:
            return self.aliases[0]
        except KeyError:
            return self.name
