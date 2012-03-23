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

import logging as _logging

__version__ = '0.1'
ENCODING = 'utf-8'


LOG = _logging.getLogger('pygrade')
LOG.setLevel(_logging.ERROR)
LOG.addHandler(_logging.StreamHandler())
