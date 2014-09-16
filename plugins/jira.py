from neb.engine import Plugin, Command

import requests

class JiraPlugin(Plugin):

    def get_commands(self):
        """Return human readable commands with descriptions.
        
        Returns:
            list[Command]
        """
        return [
            Command("jira", self.jira, "Perform commands on Matrix JIRA.", [
            "server-info - Retrieve server information."
            ]),
        ]
    
    def jira(self, event, args):
        action = args[1]
        actions = {
            "server-info": self._server_info
        }

        return actions[action](event, args)
            
    def _server_info(self, event, args):
        return self._body("Boo")
    
    def sync(self, matrix, initial_sync):
        pass
            
                
