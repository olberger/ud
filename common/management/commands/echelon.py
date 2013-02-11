# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Copyright (C) 2013 Luca Filipozzi <lfilipoz@debian.org>

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from common.models import User

import optparse
import email
import email.mime.text
import email.utils
import pyme.constants.sigsum
import pyme.core
import smtplib
import sys
import time

class Command(BaseCommand):
    help = 'Watches for email activity from Debian Developers.'
    option_list = BaseCommand.option_list + (
        optparse.make_option('--dryrun',
            action='store_true',
            default=False,
            help='do not commit changes'
        ),
    )

    def handle(self, *args, **options):
        self.options = options
        try:
            message = email.message_from_file(sys.stdin)
            user = None
            key = ''
            val = '[%s]' % ( time.strftime("%a, %d %b %Y %H:%M:%S",time.gmtime(time.time())) )
            try: # to determine user from signature
                (fingerprint, ignore) = self.verify_message(message)
                user = self.verify_fingerprint(fingerprint)
                key = 'activityPGP'
                val += ' "%s" ' % (fingerprint)
            except:
                pass
            try: # to determine user from headers
                user = self.verify_address(message)
                key = 'activityFrom'
                val += ' "%s" ' % (message.get('From'))
            except:
                pass
            if user:
                val += ' "%s" "%s"' % (message.get('X-Mailing-List'), message.get('Message-ID'))
                if self.options['dryrun']:
                    sys.stdout.write('%s: %s\n' % (key, val))
                else:
                    user.update(key, val)
        except Exception as err:
            raise CommandError(err)

    def verify_message(self, message):
        if message.get('Reply-To'):
            (x,y) = email.utils.parseaddr(message.get('Reply-To'))
            if not y:
                raise Exception('malformed message: bad Reply-To header')
        elif message.get('From'):
            (x,y) = email.utils.parseaddr(message.get('From'))
            if not y:
                raise Exception('malformed message: bad From header')
        ctx = pyme.core.Context()
        if message.get_content_type() == 'text/plain':
            try: # normal signature (clearsign or sign & armor)
                plaintext = pyme.core.Data() # output
                signature = pyme.core.Data(message.get_payload())
                ctx.op_verify(signature, None, plaintext)
                plaintext.seek(0,0)
            except Exception as err:
                raise Exception('malformed text/plain message')
            commands = plaintext.read().splitlines()
        elif message.get_content_type() == 'multipart/signed':
            try: # detached signature
                signedtxt = pyme.core.Data(message.get_payload(0).as_string())
                signature = pyme.core.Data(message.get_payload(1).as_string())
                ctx.op_verify(signature, signedtxt, None)
            except:
                raise Exception('malformed multipart/signed message')
            commands = message.get_payload(0).get_payload(decode=True).splitlines()
        else:
            raise Exception('malformed message: unsupported content-type')
        result = ctx.op_verify_result()
        if len(result.signatures) == 0:
            raise Exception('malformed message: too few signatures')
        if len(result.signatures) >= 2:
            raise Exception('malformed message: too many signatures')
        if result.signatures[0].status != 0:
            raise Exception('invalid signature')
        return (result.signatures[0].fpr, commands)

    def verify_fingerprint(self, fingerprint):
        result = User.objects.filter(keyFingerPrint=fingerprint)
        if len(result) == 0:
            raise Exception('too few user objects found')
        if len(result) >= 2:
            raise Exception('too many user objects found')
        return result[0]

    def verify_address(self, message):
        emailForwards = set()
        uids = set()
        if message.get('From'):
            (x,y) = email.utils.parseaddr(message.get('From'))
            if y:
                emailForwards.add(y)
                if y.endswith('@debian.org'):
                    uids.add(y.split('@')[0])
        result = User.objects.filter(Q(uid__in=uids)|Q(emailForward__in=emailForwards))
        if len(result) == 0:
            raise Exception('too few user objects found')
        if len(result) >= 2:
            raise Exception('too many user objects found')
        return result[0]

# vim: set ts=4 sw=4 et ai si sta:
