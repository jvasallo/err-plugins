from errbot import BotPlugin, botcmd
from optparse import OptionParser

import sys
import pepper
import json
import urllib
import urllib2
import shlex

class Salt(BotPlugin):
    """Plugin to run salt commands on hosts"""

    def get_configuration_template(self):
        """ configuration entries """
        config = {
            'paste_api_url': None,
            'api_url': None,
            'api_user': None,
            'api_pass': None,
            'api_auth': None,
        }
        return config

    def paste_code(self, code):
        ''' Post the output to pastebin '''
        request = urllib2.Request(
            self.config['paste_api_url'],
            urllib.urlencode([('content', code)]),
        )
        response = urllib2.urlopen(request)
        return response.read()[1:-1]

    @botcmd
    def salt(self, msg, args):
        ''' executes a salt command on systems
            example:
            !salt log*.local cmd.run 'cat /etc/hosts'
            !salt log*.local test.ping
        '''
        parser = OptionParser()
        (options, args) = parser.parse_args(shlex.split(args))

        if len(args) < 2:
            response = '2 parameters required. see !help salt'
            self.send(msg.getFrom(), response, message_type=msg.getType())
            return

        targets = args.pop(0)
        action = args.pop(0)

        api = pepper.Pepper(self.config['api_url'], debug_http=False)
        auth = api.login(self.config['api_user'], self.config['api_pass'], self.config['api_auth'])
        ret = api.local(targets, action, arg=args, kwarg=None, expr_form='pcre')
        results = json.dumps(ret, sort_keys=True, indent=4)
        self.send(msg.getFrom(), results, message_type=msg.getType())
