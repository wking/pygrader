# Copyright

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
