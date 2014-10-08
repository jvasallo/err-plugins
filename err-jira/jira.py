from errbot import BotPlugin, botcmd

import requests

class Jira(BotPlugin):
    """Plugin to run salt commands on hosts"""

    def get_configuration_template(self):
        """ configuration entries """
        config = {
            'api_url': None,
            'api_user': None,
            'api_pass': None,
            'domain': None,
        }
        return config

    @botcmd(split_args_with=' ')
    def jira(self, msg, args):
        """<ticket>

        Returns the subject of the ticket along with a link to it.
        """

        ticket = args.pop(0)
        if ticket == '':
            yield 'ticket must be passed'
            return

        username = self.config['api_user']
        password = self.config['api_pass']
        api_url = self.config['api_url']
        domain = self.config['domain']

        url = '%s/issue/%s' % (api_url, ticket)
        url_display = '%s/browse/%s' % (domain, ticket)
        req = requests.get(url, auth=(username, password))

        if req.status_code == requests.codes.ok:
            data = req.json()

            response = '{0} created on {1} by {2} ({4}) - {3}'.format(
                                data['fields']['summary'],
                                data['fields']['created'],
                                data['fields']['reporter']['displayName'],
                                url_display,
                                data['fields']['status']['name'])
        else:
            response = 'Issue {0} not found.'.format(ticket)

        yield response
