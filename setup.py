# Copyright

"Manage a course's grade database with email-based communication."

from distutils.core import setup as _setup
import os.path as _os_path

from pygrader import __version__


_this_dir = _os_path.dirname(__file__)

_setup(
    name='pygrader',
    version=__version__,
    maintainer='W. Trevor King',
    maintainer_email='wking@drexel.edu',
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
        'Topic :: Communications :: Email',
        'Topic :: Database',
        'Topic :: Education',
        ],
    scripts = ['bin/pg.py'],
    packages = ['pygrader', 'pygrade.model'],
    provides = ['pygrader', 'pygrade.model'],
    )
