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

from .. import LOG as _LOG


class Course (object):
    def __init__(self, name=None, assignments=None, people=None, grades=None,
                 robot=None):
        self.name = name
        if assignments is None:
            assignments = []
        self.assignments = sorted(assignments)
        if people is None:
            people = []
        self.people = sorted(people)
        if grades is None:
            grades = []
        self.grades = sorted(grades)
        self.robot = robot

    def assignment(self, name):
        for assignment in self.assignments:
            if assignment.name == name:
                return assignment
        raise ValueError(name)

    def active_assignments(self):
        return sorted(set(grade.assignment for grade in self.grades))

    def active_groups(self):
        groups = set()
        for person in self.people:
            groups.update(person.groups)
        return sorted(groups)

    def find_people(self, name=None, email=None, group=None):
        """Yield ``Person``\s that match ``name``, ``email``, and ``group``

        The value of ``None`` matches any person.

        >>> from pygrader.model.person import Person
        >>> c = Course(people=[
        ...     Person(name='Bilbo Baggins',
        ...            emails=['bb@shire.org', 'bb@greyhavens.net'],
        ...            aliases=['Billy'],
        ...            groups=['students', 'assistants']),
        ...     Person(name='Frodo Baggins',
        ...            emails=['fb@shire.org'],
        ...            groups=['students']),
        ...     ])
        >>> for person in c.find_people(name='Bilbo Baggins'):
        ...     print(person)
        <Person Bilbo Baggins>
        >>> for person in c.find_people(name='Billy'):
        ...     print(person)
        <Person Bilbo Baggins>
        >>> for person in c.find_people(email='bb@greyhavens.net'):
        ...     print(person)
        <Person Bilbo Baggins>
        >>> for person in c.find_people(group='assistants'):
        ...     print(person)
        <Person Bilbo Baggins>
        >>> for person in c.find_people(group='students'):
        ...     print(person)
        <Person Bilbo Baggins>
        <Person Frodo Baggins>
        """
        for person in self.people:
            name_match = (person.name == name or
                          (person.aliases and name in person.aliases))
            email_match = email in person.emails
            group_match = group in person.groups
            matched = True
            for (key,kmatched) in [(name, name_match),
                                   (email, email_match),
                                   (group, group_match),
                                   ]:
                if key is not None and not kmatched:
                    matched = False
                    break
            if matched:
                yield person

    def person(self, **kwargs):
        people = list(self.find_people(**kwargs))
        assert len(people) == 1, '{} -> {}'.format(kwargs, people)
        return people[0]

    def grade(self, student, assignment):
        """Return the ``Grade`` that matches ``Student`` and ``Assignment``

        >>> from pygrader.model.assignment import Assignment
        >>> from pygrader.model.grade import Grade
        >>> from pygrader.model.person import Person
        >>> p = Person(name='Bilbo Baggins')
        >>> a = Assignment(name='Exam 1')
        >>> g = Grade(student=p, assignment=a, points=10)
        >>> c = Course(assignments=[a], people=[p], grades=[g])
        >>> print(c.grade(student=p, assignment=a))
        <Grade Bilbo Baggins:Exam 1>
        """
        for grade in self.grades:
            if grade.student == student and grade.assignment == assignment:
                return grade
        raise ValueError((student, assignment))

    def total(self, student):
        total = 0
        for assignment in self.assignments:
            try:
                grade = self.grade(student=student, assignment=assignment)
            except ValueError:
                continue
            total += float(grade.points)/assignment.points * assignment.weight
        return total
