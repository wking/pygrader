# Copyright

import logging as _logging

__version__ = '0.1'
ENCODING = 'utf-8'


LOG = _logging.getLogger('pygrade')
LOG.setLevel(_logging.ERROR)
LOG.addHandler(_logging.StreamHandler())
