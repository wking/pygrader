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

import asynchat as _asynchat
import socket as _socket

from pgp_mime import email as _email

from .. import LOG as _LOG


class MessageSender (_asynchat.async_chat):
    """A SMTP message sender using ``asyncore``.

    To test ``PygraderServer``, it's useful to have a message-sender
    that also uses ``asyncore``.  This avoids the need to use
    multithreaded tests.
    """
    def __init__(self, address, messages):
        super(MessageSender, self).__init__()
        self.address = address
        self.messages = messages
        self.create_socket(_socket.AF_INET, _socket.SOCK_STREAM)
        self.connect(address)
        self.intro = None
        self.ilines = []
        self.ibuffer = []
        self.set_terminator(b'\r\n')
        if self.messages:
            self.callback = (self.send_message, [], {})
        else:
            self.callback = (self.quit_callback, [], {})
        self.send_command('ehlo [127.0.0.1]')

    def log_info(self, message, type='info'):
        # TODO: type -> severity
        _LOG.info(message)

    def send_command(self, command, clear_command_list=True):
        if clear_command_list:
            self.commands = [command]
            self.responses = []
        _LOG.debug('push: {}'.format(command))
        self.push(bytes(command + '\r\n', 'ascii'))

    def send_commands(self, commands):
        self.commands = commands
        self.responses = []
        for command in self.commands:
            self.send_command(command=command, clear_command_list=False)

    def collect_incoming_data(self, data):
        self.ibuffer.append(data)

    def found_terminator(self):
        ibuffer = b''.join(self.ibuffer)
        self.ibuffer = []
        self.ilines.append(ibuffer)
        if len(self.ilines[-1]) >= 4 and self.ilines[-1][3] == ord(b' '):
            response = self.ilines
            self.ilines = []
            self.handle_response(response)

    def handle_response(self, response):
        _LOG.debug('handle response: {}'.format(response))
        code = int(response[-1][:3])
        if not self.intro:
            self.intro = (code, response)
        else:
            self.responses.append((code, response))
        if len(self.responses) == len(self.commands):
            if self.callback:
                callback,args,kwargs = self.callback
                self.callback = None
                commands = self.commands
                self.commands = []
                responses = self.responses
                self.responses = []
                _LOG.debug('callback: ({}, {})'.format(callback, list(zip(commands, responses))))
                callback(commands, responses, *args, **kwargs)
            else:
                self.close()

    def close_callback(self, commands, responses):
        _LOG.debug(commands)
        _LOG.debug(responses)
        self.close()

    def quit_callback(self, commands, responses):
        self.send_command('quit')
        self.callback = (self.close_callback, [], {})

    def send_message(self, commands, responses):
        message = self.messages.pop(0)
        if self.messages:
            self.callback = (self.send_message, [], {})
        else:
            self.callback = (self.quit_callback, [], {})
        sources = list(_email.email_sources(message))
        commands = [
            'mail FROM:<{}>'.format(sources[0][1])
            ]
        for name,address in _email.email_targets(message):
            commands.append('rcpt TO:<{}>'.format(address))
        commands.extend([
                'DATA',
                message.as_string() + '\r\n.',
                ])
        self.send_commands(commands=commands)
