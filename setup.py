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

"Manage a course's grade database with email-based communication."

from distutils.core import setup as _setup
import os.path as _os_path

from pygrader import __version__


_this_dir = _os_path.dirname(__file__)

_setup(
    name='pygrader',
    version=__version__,
    maintainer='W. Trevor King',
    maintainer_email='wking@tremily.us',
    url='http://blog.tremily.us/posts/pygrader/',
    download_url='http://git.tremily.us/?p=pygrader.git;a=snapshot;h=v{};sf=tgz'.format(__version__),
    license = 'GNU General Public License (GPL)',
    platforms = ['all'],
    description = __doc__,
    long_description=open(_os_path.join(_this_dir, 'README'), 'r').read(),
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Education',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Topic :: Communications :: Email',
        'Topic :: Database',
        'Topic :: Education',
        ],
    scripts = ['bin/pg.py'],
    packages = [
        'pygrader', 'pygrader.handler', 'pygrader.model', 'pygrader.test'],
    provides = [
        'pygrader', 'pygrader.handler', 'pygrader.model', 'pygrader.test'],
    )
