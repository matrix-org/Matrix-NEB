from neb.engine import Plugin, Command, KeyValueStore

import base64
import getpass
import json
import requests


class JiraPlugin(Plugin):
    """ Plugin for interacting with JIRA.

    New events:
        Type: neb.plugin.jira.issues.display
        State: Yes
        Content: {
            display: true|false
        }
    """

    def __init__(self, config="jira.json"):
        self.store = KeyValueStore(config)

        if not self.store.has("url"):
            url = raw_input("JIRA URL: ").strip()
            self.store.set("url", url)

        if not self.store.has("basic_auth"):
            user = raw_input("(%s) JIRA Username: " % self.store.get("url")).strip()
            pw = getpass.getpass("(%s) JIRA Password: " % self.store.get("url")).strip()
            basic = base64.encodestring('%s:%s' % (user, pw)).strip()
            self.store.set("basic_auth", basic)

        self.state = {
            # room_id : { display: true|false }
        }

    def get_commands(self):
        """Return human readable commands with descriptions.

        Returns:
            list[Command]
        """
        return [
            Command("jira", self.jira, "Perform commands on a JIRA platform.", [
            "server-info :: Retrieve server information.",
            "issues on|off :: Toggle information about an issue as other people mention them."
            ]),
        ]

    def jira(self, event, args):
        if len(args) == 1:
            return self._body("Perform commands on a JIRA platform.")

        action = args[1]
        actions = {
            "server-info": self._server_info,
            "issues": self._issues
        }

        try:
            return actions[action](event, args)
        except KeyError:
            return self._body("Unknown JIRA action: %s" % action)

    def _issues(self, event, args):
        if len(args) < 3 or args[2].lower() not in ["on", "off"]:
            return self._body("Bad 'issues' value. Must be 'on' or 'off'.")

        value = args[2].lower() == "on"

        self.matrix.send_event(
            event["room_id"],
            "neb.plugin.jira.issues.display",
            {
                "display": value
            },
            state=True
        )

        url = self.store.get("url")
        if value:
            return self._body(
                "Issues for %s will be displayed as they are mentioned." % url
            )
        else:
            return self._body(
                "Issues for %s will NOT be displayed as they are mentioned." %
                url
            )

    def _server_info(self, event, args):
        url = self._url("/rest/api/2/serverInfo")
        response = json.loads(requests.get(url).text)

        info = "%s : version %s : build %s" % (response["serverTitle"],
               response["version"], response["buildNumber"])

        return self._body(info)

    def on_msg(self, event, body):
        # TODO generic please
        if "SYWEB-" in body:
            pass

    def sync(self, matrix, sync):
        self.matrix = matrix

        for room in sync["rooms"]:
            # see if we know anything about these rooms
            room_id = room["room_id"]
            if room["membership"] != "join":
                continue

            self.state[room_id] = {}

            try:
                for state in room["state"]:
                    if state["type"] == "neb.plugin.jira.issues.display":
                        should_display = state["content"]["display"]
                        if type(should_display) != bool:
                            should_display = False
                        self.state[room_id]["display"] = should_display
            except KeyError:
                pass

        print "Plugin: JIRA Sync state:"
        print json.dumps(self.state, indent=4)

    def _url(self, path):
        return self.store.get("url") + path


