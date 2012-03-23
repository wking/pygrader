# Copyright

"""List grading that still needs to be done.
"""

import os as _os
import os.path as _os_path


def mtime(path, walk_directories=True):
    if walk_directories and _os.path.isdir(path):
        time = mtime(path, walk_directories=False)
        for dirpath,dirnames,filenames in _os.walk(path):
            for filename in filenames:
                t = mtime(_os_path.join(dirpath, filename))
                time = max(time, t)
        return time
    stat = _os.stat(path)
    return stat.st_mtime

def newer(a, b):
    """Return ``True`` if ``a`` is newer than ``b``.
    """
    return mtime(a) > mtime(b)

def todo(basedir, source, target):
    """Yield ``source``\s in ``basedir`` with old/missing ``target``\s.
    """
    for dirpath,dirnames,filenames in _os.walk(basedir):
        names = dirnames + filenames
        if source in names:
            s = _os_path.join(dirpath, source)
            t = _os_path.join(dirpath, target)
            if target in names:
                if newer(s, t):
                    yield(s)
            else:
                yield s

def print_todo(basedir, source, target):
    """Print ``source``\s in ``basedir`` with old/missing ``target``\s.
    """
    for path in sorted(todo(basedir, source, target)):
        print(path)
