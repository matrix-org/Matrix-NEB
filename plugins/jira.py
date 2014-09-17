from neb.engine import Plugin, Command, KeyValueStore

import json
import requests


class JiraPlugin(Plugin):

    def __init__(self, config="jira.json"):
        self.store = KeyValueStore(config)

        if not self.store.has("url"):
            url = raw_input("JIRA URL: ").strip()
            self.store.set("url", url)

    def get_commands(self):
        """Return human readable commands with descriptions.

        Returns:
            list[Command]
        """
        return [
            Command("jira", self.jira, "Perform commands on a JIRA platform.", [
            "server-info - Retrieve server information."
            ]),
        ]

    def jira(self, event, args):
        if len(args) == 1:
            return self._body("Perform commands on a JIRA platform.")

        action = args[1]
        actions = {
            "server-info": self._server_info
        }

        return actions[action](event, args)

    def _server_info(self, event, args):
        url = self._url("/rest/api/2/serverInfo")
        response = json.loads(requests.get(url).text)

        info = "%s : version %s : build %s" % (response["serverTitle"],
               response["version"], response["buildNumber"])

        return self._body(info)

    def sync(self, matrix, initial_sync):
        pass

    def _url(self, path):
        return self.store.get("url") + path


