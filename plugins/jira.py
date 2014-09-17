from neb.engine import Plugin, Command, KeyValueStore

import getpass
import json
import re
import requests

import logging

log = logging.getLogger(name=__name__)


class JiraPlugin(Plugin):
    """ Plugin for interacting with JIRA.

    New events:
        Type: neb.plugin.jira.issues.display
        State: Yes
        Content: {
            display: [projectKey1, projectKey2, ...]
        }
    """

    def __init__(self, config="jira.json"):
        self.store = KeyValueStore(config)

        if not self.store.has("url"):
            url = raw_input("JIRA URL: ").strip()
            self.store.set("url", url)

        if not self.store.has("user") or not self.store.has("pass"):
            user = raw_input("(%s) JIRA Username: " % self.store.get("url")).strip()
            pw = getpass.getpass("(%s) JIRA Password: " % self.store.get("url")).strip()
            self.store.set("user", user)
            self.store.set("pass", pw)

        self.state = {
            # room_id : { display: [projectKey1, projectKey2, ...] }
        }

        self.auth = (self.store.get("user"), self.store.get("pass"))
        self.regex = re.compile(r"\b(([A-Za-z]+)-\d+)\b")

    def get_commands(self):
        """Return human readable commands with descriptions.

        Returns:
            list[Command]
        """
        return [
            Command("jira", self.jira, "Perform commands on a JIRA platform.", [
            "server-info :: Retrieve server information.",
            "track-issues AAA,BBB,CCC :: Display information about bugs which have " +
            "the project key AAA, BBB or CCC.",
            "clear-issues :: Stops tracking all issues."
            ]),
        ]

    def jira(self, event, args):
        if len(args) == 1:
            return self._body("Perform commands on a JIRA platform.")

        action = args[1]
        actions = {
            "server-info": self._server_info,
            "track-issues": self._track_issues,
            "clear-issues": self._clear_issues
        }

        try:
            return actions[action](event, args)
        except KeyError:
            return self._body("Unknown JIRA action: %s" % action)

    def _clear_issues(self, event, args):
        self.matrix.send_event(
            event["room_id"],
            "neb.plugin.jira.issues.display",
            {
                "display": []
            },
            state=True
        )

        url = self.store.get("url")
        return self._body(
            "Stopped tracking project keys from %s." % (url)
        )

    def _track_issues(self, event, args):
        project_keys_csv = ' '.join(args[2:]).upper().strip()
        project_keys = [a.strip() for a in project_keys_csv.split(',')]
        if not project_keys_csv:
            try:
                return self._body("Currently tracking %s" % self.state[event["room_id"]]["display"])
            except KeyError:
                return self._body("Not tracking any projects currently.")

        for key in project_keys:
            if not re.match("[A-Z][A-Z_0-9]+", key):
                return self._body("Key %s isn't a valid project key." % key)

        self.matrix.send_event(
            event["room_id"],
            "neb.plugin.jira.issues.display",
            {
                "display": project_keys
            },
            state=True
        )

        url = self.store.get("url")
        return self._body(
            "Issues for projects %s from %s will be displayed as they are mentioned." % (project_keys, url)
        )

    def _server_info(self, event, args):
        url = self._url("/rest/api/2/serverInfo")
        response = json.loads(requests.get(url).text)

        info = "%s : version %s : build %s" % (response["serverTitle"],
               response["version"], response["buildNumber"])

        return self._body(info)

    def on_msg(self, event, body):
        room_id = event["room_id"]
        body = body.upper()
        groups = self.regex.findall(body)
        if not groups:
            return

        projects = []
        try:
            projects = self.state[room_id]["display"]
        except KeyError:
            return

        for (key, project) in groups:
            if project in projects:
                try:
                    issue_info = self._get_issue_info(key)
                    self.matrix.send_message(event["room_id"], self._body(issue_info))
                except Exception as e:
                    log.exception(e)

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
                        issues = state["content"]["display"]
                        if type(issues) == list:
                            self.state[room_id]["display"] = issues
                        else:
                            self.state[room_id]["display"] = []
            except KeyError:
                pass

        print "Plugin: JIRA Sync state:"
        print json.dumps(self.state, indent=4)

    def _get_issue_info(self, issue_key):
        url = self._url("/rest/api/2/issue/%s" % issue_key)
        response = json.loads(requests.get(url, auth=self.auth).text)
        link = "%s/browse/%s" % (self.store.get("url"), issue_key)
        desc = response["fields"]["summary"]
        status = response["fields"]["status"]["name"]
        priority = response["fields"]["priority"]["name"]
        reporter = response["fields"]["reporter"]["displayName"]
        assignee = ""
        if response["fields"]["assignee"]:
            assignee = response["fields"]["assignee"]["displayName"]

        info = "%s : %s [%s,%s,reporter=%s,assignee=%s]" % (link, desc, status,
               priority, reporter, assignee)
        return info

    def _url(self, path):
        return self.store.get("url") + path


