# Copyright

class Assignment (object):
    def __init__(self, name, points=1, weight=0, due=0):
        self.name = name
        self.points = points
        self.weight = weight
        self.due = due

    def __str__(self):
        return '<{} {}>'.format(type(self).__name__, self.name)

    def __lt__(self, other):
        if self.due < other.due:
            return True
        elif other.due < self.due:
            return False
        return self.name < other.name
