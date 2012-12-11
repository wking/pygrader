#!/usr/bin/env python3
#
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

"""Manage grades from the command line
"""

import configparser as _configparser
from email.mime.text import MIMEText as _MIMEText
import email.utils as _email_utils
import inspect as _inspect
import logging as _logging
import logging.handlers as _logging_handlers
import os.path as _os_path
import sys as _sys

import pgp_mime as _pgp_mime

import pygrader as _pygrader
from pygrader import __version__
from pygrader import LOG as _LOG
from pygrader import color as _color
from pygrader.email import test_smtp as _test_smtp
from pygrader.email import Responder as _Responder
from pygrader.mailpipe import mailpipe as _mailpipe
from pygrader.storage import initialize as _initialize
from pygrader.storage import load_course as _load_course
from pygrader.tabulate import tabulate as _tabulate
from pygrader.template import assignment_email as _assignment_email
from pygrader.template import course_email as _course_email
from pygrader.template import student_email as _student_email
from pygrader.todo import print_todo as _todo


if __name__ == '__main__':
    from argparse import ArgumentParser as _ArgumentParser

    parser = _ArgumentParser(description=__doc__)
    parser.add_argument(
        '-v', '--version', action='version',
        version='%(prog)s {}'.format(_pgp_mime.__version__))
    parser.add_argument(
        '-d', '--base-dir', dest='basedir', default='.',
        help='Base directory containing grade data')
    parser.add_argument(
        '-e', '--encoding', dest='encoding', default='utf-8',
        help=('Override the default file encoding selection '
              '(useful when running from procmail)'))
    parser.add_argument(
        '-c', '--color', default=False, action='store_const', const=True,
        help='Color printed output with ANSI escape sequences')
    parser.add_argument(
        '-V', '--verbose', default=0, action='count',
        help='Increase verbosity')
    parser.add_argument(
        '-s', '--syslog', default=False, action='store_const', const=True,
        help='Log to syslog (rather than stderr)')
    subparsers = parser.add_subparsers(title='commands')

    smtp_parser = subparsers.add_parser(
        'smtp', help=_test_smtp.__doc__.splitlines()[0])
    smtp_parser.set_defaults(func=_test_smtp)
    smtp_parser.add_argument(
        '-a', '--author',
        help='Your address (email author)')
    smtp_parser.add_argument(
        '-t', '--target', dest='targets', action='append',
        help='Address for the email recipient')

    initialize_parser = subparsers.add_parser(
        'initialize', help=_initialize.__doc__.splitlines()[0])
    initialize_parser.set_defaults(func=_initialize)
    initialize_parser.add_argument(
        '-D', '--dry-run', default=False, action='store_const', const=True,
        help="Don't actually send emails, create files, etc.")

    tabulate_parser = subparsers.add_parser(
        'tabulate', help=_tabulate.__doc__.splitlines()[0])
    tabulate_parser.set_defaults(func=_tabulate)
    tabulate_parser.add_argument(
        '-s', '--statistics', default=False, action='store_const', const=True,
        help='Calculate mean and standard deviation for each assignment')

    email_parser = subparsers.add_parser(
        'email', help='Send emails containing grade information')
    email_parser.add_argument(
        '-D', '--dry-run', default=False, action='store_const', const=True,
        help="Don't actually send emails, create files, etc.")
    email_parser.add_argument(
        '-a', '--author',
        help='Your name (email author), defaults to course robot')
    email_parser.add_argument(
        '--cc', action='append', help='People to carbon copy')
    email_subparsers = email_parser.add_subparsers(title='type')
    assignment_parser = email_subparsers.add_parser(
        'assignment', help=_assignment_email.__doc__.splitlines()[0])
    assignment_parser.set_defaults(func=_assignment_email)
    assignment_parser.add_argument(
        'assignment', help='Name of the target assignment')
    student_parser = email_subparsers.add_parser(
        'student', help=_student_email.__doc__.splitlines()[0])
    student_parser.set_defaults(func=_student_email)
    student_parser.add_argument(
        '-o', '--old', default=False, action='store_const', const=True,
        help='Include already-notified information in emails')
    student_parser.add_argument(
        '-s', '--student', dest='student',
        help='Explicitly select the student to notify (instead of everyone)')
    course_parser = email_subparsers.add_parser(
        'course', help=_course_email.__doc__.splitlines()[0])
    course_parser.set_defaults(func=_course_email)
    course_parser.add_argument(
        '-t', '--target', dest='targets', action='append',
        help='Name, alias, or group for the email recipient(s)')

    mailpipe_parser = subparsers.add_parser(
        'mailpipe', help=_mailpipe.__doc__.splitlines()[0])
    mailpipe_parser.set_defaults(func=_mailpipe)
    mailpipe_parser.add_argument(
        '-D', '--dry-run', default=False, action='store_const', const=True,
        help="Don't actually send emails, create files, etc.")
    mailpipe_parser.add_argument(
        '-m', '--mailbox', choices=['maildir', 'mbox'],
        help=('Instead of piping a message in via stdout, you can also read '
              'directly from a mailbox.  This option specifies the format of '
              'your target mailbox.'))
    mailpipe_parser.add_argument(
        '-i', '--input', dest='input_', metavar='INPUT',
        help='Path to the mailbox containing messages to be processed')
    mailpipe_parser.add_argument(
        '-o', '--output',
        help=('Path to the mailbox that will recieve successfully processed '
              'messages.  If not given, successfully processed messages will '
              'be left in the input mailbox'))
    mailpipe_parser.add_argument(
        '-l', '--max-late', default=0, type=float,
        help=('Grace period in seconds before an incoming assignment is '
              'actually marked as late'))
    mailpipe_parser.add_argument(
        '-r', '--respond', default=False, action='store_const', const=True,
        help=('Send automatic response emails to acknowledge incoming '
              'messages.'))
    mailpipe_parser.add_argument(
        '-t', '--trust-email-infrastructure',
        default=False, action='store_const', const=True,
        help=('Send automatic response emails even if the target has not '
              'registered a PGP key.'))
    mailpipe_parser.add_argument(
        '-c', '--continue-after-invalid-message',
        default=False, action='store_const', const=True,
        help=('Send responses to invalid messages and continue processing '
              'further emails (default is to die with an error message).'))

    todo_parser = subparsers.add_parser(
        'todo', help=_todo.__doc__.splitlines()[0])
    todo_parser.set_defaults(func=_todo)
    todo_parser.add_argument(
        'source', help='Name of source file/directory')
    todo_parser.add_argument(
        'target', help='Name of target file/directory')


#    p.add_option('-t', '--template', default=None)

    args = parser.parse_args()

    if not hasattr(args, 'func'):
        # no command selected; print help and die
        parser.print_help()
        _sys.exit(0)

    if args.verbose:
        _LOG.setLevel(max(_logging.DEBUG, _LOG.level - 10*args.verbose))
        _pgp_mime.LOG.setLevel(_LOG.level)
    if args.syslog:
        syslog = _logging_handlers.SysLogHandler(address="/dev/log")
        syslog.setFormatter(_logging.Formatter('%(name)s: %(message)s'))
        for handler in list(_LOG.handlers):
            _LOG.removeHandler(handler)
        _LOG.addHandler(syslog)
        for handler in list(_pgp_mime.LOG.handlers):
            _pgp_mime.LOG.removeHandler(handler)
        _pgp_mime.LOG.addHandler(syslog)
    _color.USE_COLOR = args.color

    _pygrader.ENCODING = args.encoding

    config = _configparser.ConfigParser()
    config.read([
            _os_path.expanduser(_os_path.join('~', '.config', 'smtplib.conf')),
            ], encoding=_pygrader.ENCODING)

    func_args = _inspect.getargspec(args.func).args
    kwargs = {}

    if 'basedir' in func_args:
        kwargs['basedir'] = args.basedir

    if 'course' in func_args:
        course = _load_course(basedir=args.basedir)
        active_groups = course.active_groups()
        kwargs['course'] = course
        if hasattr(args, 'assignment'):
            kwargs['assignment'] = course.assignment(name=args.assignment)
        if hasattr(args, 'cc') and args.cc:
            kwargs['cc'] = [course.person(name=cc) for cc in args.cc]
        for attr in ['author', 'student']:
            if hasattr(args, attr):
                name = getattr(args, attr)
                if name is None and attr == 'author':
                    kwargs[attr] = course.robot
                else:
                    kwargs[attr] = course.person(name=name)
        for attr in ['targets']:
            if hasattr(args, attr):
                people = getattr(args, attr)
                if people is None:
                    people = ['professors']  # for the course email
                kwargs[attr] = []
                for person in people:
                    if person in active_groups:
                        kwargs[attr].extend(course.find_people(group=person))
                    else:
                        kwargs[attr].extend(course.find_people(name=person))
        for attr in ['dry_run', 'mailbox', 'output', 'input_', 'max_late',
                     'old', 'statistics', 'trust_email_infrastructure',
                     'continue_after_invalid_message']:
            if hasattr(args, attr):
                kwargs[attr] = getattr(args, attr)
    elif args.func == _test_smtp:
        for attr in ['author', 'targets']:
            if hasattr(args, attr):
                kwargs[attr] = getattr(args, attr)
    elif args.func == _todo:
        for attr in ['source', 'target']:
            if hasattr(args, attr):
                kwargs[attr] = getattr(args, attr)

    if 'use_color' in func_args:
        kwargs['use_color'] = args.color

    if ('smtp' in func_args and
        not kwargs.get('dry_run', False) and
        'smtp' in config.sections()):
        params = _pgp_mime.get_smtp_params(config)
        kwargs['smtp'] = _pgp_mime.get_smtp(*params)
        del params

    if hasattr(args, 'respond') and getattr(args, 'respond'):
        kwargs['respond'] = _Responder(
            smtp=kwargs.get('smtp', None),
            dry_run=kwargs.get('dry_run', False))

    _LOG.debug('execute {} with {}'.format(args.func, kwargs))
    try:
        ret = args.func(**kwargs)
    finally:
        smtp = kwargs.get('smtp', None)
        if smtp:
            _LOG.info('disconnect from SMTP server')
            smtp.quit()
    if ret is None:
        ret = 0
    _sys.exit(ret)
