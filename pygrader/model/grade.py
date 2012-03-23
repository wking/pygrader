# Copyright

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
