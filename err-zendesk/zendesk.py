from errbot import BotPlugin, botcmd

import requests

class Zendesk(BotPlugin):
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

    @botcmd(split_args_with=" ")
    def zendesk(self, msg, args):
        """<id>

        Returns the subject of the ticket along with a link to it.
        """

        ticket = args.pop(0)
        if ticket == '':
            yield "id required"
            return

        username = self.config['api_user']
        password = self.config['api_pass']
        api_url = self.config['api_url']
        domain = self.config['domain']

        url = '{0}/tickets/{1}.json'.format(api_url, ticket)
        display_url = '{0}/tickets/{1}'.format(domain, ticket)
        req = requests.get(url, auth=(username, password))

        if req.status_code == requests.codes.ok:

            data = req.json()
            user = self._get_name_by_id(data['ticket']['assignee_id'])
            response = '{0} created on {1} by {2} ({4}) - {3}'.format(
                                    data['ticket']['subject'],
                                    data['ticket']['created_at'],
                                    user,
                                    display_url,
                                    data['ticket']['status'])
        else:
            response = 'Id {0} not found.'.format(ticket)

        yield response

    def _get_name_by_id(self, id):

        username = self.config['api_user']
        password = self.config['api_pass']
        api_url = self.config['api_url']

        url = '{0}/users/{1}.json'.format(api_url, id)
        req = requests.get(url, auth=(username, password))
        data = req.json()
        return data['user']['name']
        
