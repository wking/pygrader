# Copright

import os as _os
import os.path as _os_path
import shutil as _shutil
import tempfile as _tempfile

from pygrader.storage import load_course as _load_course


COURSE_CONF = """
[course]
name: Physics 101
assignments: Attendance 1, Attendance 2, Attendance 3, Attendance 4,
  Attendance 5, Attendance 6, Attendance 7, Attendance 8, Attendance 9,
  Assignment 1, Assignment 2, Exam 1, Exam 2
robot: Robot101
professors: Gandalf
assistants: Sauron
students: Bilbo Baggins, Frodo Baggins, Aragorn

[Attendance 1]
points: 1
weight: 0.1/9
due: 2011-10-03

[Attendance 2]
points: 1
weight: 0.1/9
due: 2011-10-04

[Attendance 3]
points: 1
weight: 0.1/9
due: 2011-10-05

[Attendance 4]
points: 1
weight: 0.1/9
due: 2011-10-06

[Attendance 5]
points: 1
weight: 0.1/9
due: 2011-10-11

[Attendance 6]
points: 1
weight: 0.1/9
due: 2011-10-12

[Attendance 7]
points: 1
weight: 0.1/9
due: 2011-10-13

[Attendance 8]
points: 1
weight: 0.1/9
due: 2011-10-14

[Attendance 9]
points: 1
weight: 0.1/9
due: 2011-10-15

[Assignment 1]
points: 10
weight: 0.4/2
due: 2011-10-10
submittable: yes

[Assignment 2]
points: 1
weight: 0.4/2
due: 2011-10-17
submittable: yes

[Exam 1]
points: 10
weight: 0.4/2
due: 2011-10-10

[Exam 2]
points: 10
weight: 0.4/2
due: 2011-10-17

[Robot101]
nickname: phys-101 robot
emails: phys101@tower.edu
pgp-key: 4332B6E3

[Gandalf]
nickname: G-Man
emails: g@grey.edu
pgp-key: 0x0123456789ABCDEF

[Sauron]
nickname: Saury
emails: eye@tower.edu
pgp-key: 4332B6E3

[Bilbo Baggins]
nickname: Billy
emails: bb@shire.org, bb@greyhavens.net

[Frodo Baggins]
nickname: Frodo
emails: fb@shire.org

[Aragorn]
emails: a@awesome.gov
"""


class StubCourse (object):
    """Manage a course directory for testing.

    >>> course = StubCourse()
    >>> course.print_tree()
    course.conf
    >>> course.cleanup()
    """
    def __init__(self, load=True):
        self.basedir = _tempfile.mkdtemp(prefix='pygrader-tmp-')
        try:
            self.mailbox = _os_path.join(self.basedir, 'mail')
            course_conf = _os_path.join(self.basedir, 'course.conf')
            with open(course_conf, 'w') as f:
                f.write(COURSE_CONF)
            if load:
                self.course = _load_course(basedir=self.basedir)
        except Exception:
            self.cleanup()

    def cleanup(self):
        if self.basedir:
            _shutil.rmtree(self.basedir)
            self.basedir = None

    def tree(self):
        paths = []
        for dirpath,dirnames,filenames in _os.walk(self.basedir):
            for dirname in dirnames:
                paths.append(_os_path.join(dirpath, dirname))
            for filename in filenames:
                paths.append(_os_path.join(dirpath, filename))
        for i,path in enumerate(paths):
            paths[i] = _os_path.relpath(path, self.basedir)
        paths.sort()
        return paths

    def print_tree(self):
        for path in self.tree():
            print(path)
