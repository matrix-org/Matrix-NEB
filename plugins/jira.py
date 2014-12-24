from neb.engine import Plugin, Command, KeyValueStore

import getpass
import json
import re
import requests

import logging as log


class JiraPlugin(Plugin):
    """ Plugin for interacting with JIRA.

    New events:
        Type: org.matrix.neb.plugin.jira.issues.display
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

        self.help_msgs = [
            "server-info :: Retrieve server information.",
            "track-issues AAA,BBB,CCC :: Display information about bugs which have " +
            "the project key AAA, BBB or CCC.",
            "clear-issues :: Stops tracking all issues."
        ]

    def get_commands(self):
        """Return human readable commands with descriptions.

        Returns:
            list[Command]
        """
        return [
            Command("jira", self.jira, "Perform commands on a JIRA platform.",
                    self.help_msgs),
        ]

    def jira(self, event, args):
        if len(args) == 1:
            return [self._body(x) for x in self.help_msgs]

        action = args[1]
        actions = {
            "server-info": self._server_info,
            "track-issues": self._track_issues,
            "clear-issues": self._clear_issues
        }

        # TODO: make this configurable
        if event["user_id"] not in self.matrix.config.admins:
            return self._body("Sorry, only %s can do that." % json.dumps(self.matrix.config.admins))

        try:
            return actions[action](event, args)
        except KeyError:
            return self._body("Unknown JIRA action: %s" % action)

    def _clear_issues(self, event, args):
        self.matrix.send_event(
            event["room_id"],
            "org.matrix.neb.plugin.jira.issues.display",
            {
                "display": []
            },
            state=True
        )
        self._send_display_event(event["room_id"], [])

        url = self.store.get("url")
        return self._body(
            "Stopped tracking project keys from %s." % (url)
        )

    def _track_issues(self, event, args):
        project_keys_csv = ' '.join(args[2:]).upper().strip()
        project_keys = [a.strip() for a in project_keys_csv.split(',')]
        if not project_keys_csv:
            try:
                return self._body("Currently tracking %s" % json.dumps(self.state[event["room_id"]]["display"]))
            except KeyError:
                return self._body("Not tracking any projects currently.")

        for key in project_keys:
            if not re.match("[A-Z][A-Z_0-9]+", key):
                return self._body("Key %s isn't a valid project key." % key)

        self._send_display_event(event["room_id"], project_keys)


        url = self.store.get("url")
        return self._body(
            "Issues for projects %s from %s will be displayed as they are mentioned/edited." % (project_keys, url)
        )

    def _send_display_event(self, room_id, project_keys):
        self.matrix.send_event(
            room_id,
            "org.matrix.neb.plugin.jira.issues.display",
            {
                "display": project_keys
            },
            state=True
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
                    if issue_info:
                        self.matrix.send_message(
                            event["room_id"],
                            self._body(issue_info)
                        )
                except Exception as e:
                    log.exception(e)

    def on_event(self, event, event_type):
        if event_type == "org.matrix.neb.plugin.jira.issues.display":
            self._set_display_event(event)

    def on_receive_jira_push(self, info):
        log.debug("on_recv %s", info)
        project = self.regex.match(info["key"]).groups()[1]

        # form the message
        link = "%s/browse/%s" % (self.store.get("url"), info["key"])
        push_message = "%s %s %s - %s %s" % (info["user"], info["action"],
                       info["key"], info["summary"], link)

        # send messages to all rooms registered with this project.
        for (room_id, room_info) in self.state.iteritems():
            try:
                if project in room_info["display"]:
                    self.matrix.send_message(room_id, self._body(push_message))
            except KeyError:
                pass

    def _set_display_event(self, event):
        room_id = event["room_id"]
        issues = event["content"]["display"]

        if room_id not in self.state:
            self.state[room_id] = {}

        if type(issues) == list:
            self.state[room_id]["display"] = issues
        else:
            self.state[room_id]["display"] = []

    def on_sync(self, matrix, sync):
        self.matrix = matrix

        for room in sync["rooms"]:
            # see if we know anything about these rooms
            room_id = room["room_id"]
            if room["membership"] != "join":
                continue

            self.state[room_id] = {}

            try:
                for state in room["state"]:
                    if state["type"] == "org.matrix.neb.plugin.jira.issues.display":
                        self._set_display_event(state)
            except KeyError:
                pass

        log.debug("Plugin: JIRA Sync state:")
        log.debug(json.dumps(self.state, indent=4))

    def _get_issue_info(self, issue_key):
        url = self._url("/rest/api/2/issue/%s" % issue_key)
        res = requests.get(url, auth=self.auth)
        if res.status_code != 200:
            return

        response = json.loads(res.text)
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

    def get_webhook_key(self):
        return "jira"

    def on_receive_webhook(self, url, data, ip, headers):
        j = json.loads(data)

        info = self.get_webhook_json_keys(j)
        self.on_receive_jira_push(info)

    def get_webhook_json_keys(self, j):
        key = j['issue']['key']
        user = j['user']['name']
        self_key = j['issue']['self']
        summary = self.get_webhook_summary(j)
        action = ""

        if j['webhookEvent'] == "jira:issue_updated":
            action = "updated"
        elif j['webhookEvent'] == "jira:issue_deleted":
            action = "deleted"
        elif j['webhookEvent'] == "jira:issue_created":
            action = "created"

        return {
            "key": key,
            "user": user,
            "summary": summary,
            "self": self_key,
            "action": action
        }

    def get_webhook_summary(self, j):
        summary = j['issue']['fields']['summary']
        priority = j['issue']['fields']['priority']['name']
        status = j['issue']['fields']['status']['name']

        if "resolution" in j['issue']['fields'] \
            and j['issue']['fields']['resolution'] is not None:
            status = "%s (%s)" \
                % (status, j['issue']['fields']['resolution']['name'])

        return "%s [%s, %s]" \
            % (summary, priority, status)
