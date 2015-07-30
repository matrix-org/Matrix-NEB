from neb.engine import KeyValueStore, RoomContextStore
from neb.plugins import Plugin, admin_only

import getpass
import json
import re
import requests

import logging as log


class JiraPlugin(Plugin):
    """ Plugin for interacting with JIRA.
    jira version : Display version information for this platform.
    jira track <project> <project2> ... : Track multiple projects
    jira expand <project> <project2> ... : Expand issue IDs for the given projects with issue information.
    jira stop track|tracking : Stops tracking for all projects.
    jira stop expand|expansion|expanding : Stop expanding jira issues.
    jira show track|tracking : Show which projects are being tracked.
    jira show expansion|expand|expanding : Show which project keys will result in issue expansion.
    jira create <project> <priority> <title> <desc> : Create a new JIRA issue.
    jira comment <issue-id> <comment> : Comment on a JIRA issue.
    """
    name = "jira"

    TRACK = ["track", "tracking"]
    EXPAND = ["expansion", "expand", "expanding"]

    # New events:
    #    Type: org.matrix.neb.plugin.jira.issues.tracking / expanding
    #    State: Yes
    #    Content: {
    #        projects: [projectKey1, projectKey2, ...]
    #    }
    TYPE_TRACK = "org.matrix.neb.plugin.jira.issues.tracking"
    TYPE_EXPAND = "org.matrix.neb.plugin.jira.issues.expanding"

    def __init__(self, *args, **kwargs):
        super(JiraPlugin, self).__init__(*args, **kwargs)
        self.store = KeyValueStore("jira.json")
        self.rooms = RoomContextStore(
            [JiraPlugin.TYPE_TRACK, JiraPlugin.TYPE_EXPAND]
        )

        if not self.store.has("url"):
            url = raw_input("JIRA URL: ").strip()
            self.store.set("url", url)

        if not self.store.has("user") or not self.store.has("pass"):
            user = raw_input("(%s) JIRA Username: " % self.store.get("url")).strip()
            pw = getpass.getpass("(%s) JIRA Password: " % self.store.get("url")).strip()
            self.store.set("user", user)
            self.store.set("pass", pw)

        self.auth = (self.store.get("user"), self.store.get("pass"))
        self.regex = re.compile(r"\b(([A-Za-z]+)-\d+)\b")

    @admin_only
    def cmd_stop(self, event, action):
        """ Clear project keys from tracking/expanding.
        Stop tracking projects. 'jira stop tracking'
        Stop expanding projects. 'jira stop expanding'
        """
        if action in self.TRACK:
            self._send_state(JiraPlugin.TYPE_TRACK, event["room_id"], [])
            url = self.store.get("url")
            return "Stopped tracking project keys from %s." % (url)
        elif action in self.EXPAND:
            self._send_state(JiraPlugin.TYPE_EXPAND, event["room_id"], [])
            url = self.store.get("url")
            return "Stopped expanding project keys from %s." % (url)
        else:
            return "Invalid arg '%s'.\n %s" % (action, self.cmd_stop.__doc__)

    @admin_only
    def cmd_track(self, event, *args):
        """Track project keys. 'jira track FOO BAR'"""
        if not args:
            return self._get_tracking(event["room_id"])

        args = [k.upper() for k in args]
        for key in args:
            if re.search("[^A-Z]", key):  # something not A-Z
                return "Key %s isn't a valid project key." % key

        self._send_state(JiraPlugin.TYPE_TRACK, event["room_id"], args)

        url = self.store.get("url")
        return "Issues for projects %s from %s will be displayed as they are updated." % (args, url)

    @admin_only
    def cmd_expand(self, event, *args):
        """Expand issues when mentioned for the given project keys. 'jira expand FOO BAR'"""
        if not args:
            return self._get_expanding(event["room_id"])

        args = [k.upper() for k in args]
        for key in args:
            if re.search("[^A-Z]", key):  # something not A-Z
                return "Key %s isn't a valid project key." % key

        self._send_state(JiraPlugin.TYPE_EXPAND, event["room_id"], args)

        url = self.store.get("url")
        return "Issues for projects %s from %s will be expanded as they are mentioned." % (args, url)

    @admin_only
    def cmd_create(self, event, *args):
        """Create a new issue. Format: 'create <project> <priority(optional;default 3)> <title> <desc(optional)>'
        E.g. 'create syn p1 This is the title without quote marks'
        'create syn p1 "Title here" "desc here"
        """
        if not args or len(args) < 2:
            return self.cmd_create.__doc__
        project = args[0]
        priority = 3
        others = args[1:]
        if re.match("[Pp][0-9]", args[1]):
            if len(args) < 3:  # priority without title
                return self.cmd_create.__doc__
            try:
                priority = int(args[1][1:])
                others = args[2:]
            except ValueError:
                return self.cmd_create.__doc__
        elif re.match("[Pp][0-9]", args[0]):
            priority = int(args[0][1:])
            project = args[1]
            others = args[2:]
        # others must contain a title, may contain a description. If it contains
        # a description, it MUST be in [1] and be longer than 1 word.
        title = ' '.join(others)
        desc = ""
        try:
            possible_desc = others[1]
            if ' ' in possible_desc:
                desc = possible_desc
                title = others[0]
        except:
            pass

        return self._create_issue(
            event["user_id"], project, priority, title, desc
        )

    @admin_only
    def cmd_comment(self, event, *args):
        """Comment on an issue. Format: 'comment <key> <comment text>'
        E.g. 'comment syn-56 A comment goes here'
        """
        if not args or len(args) < 2:
            return self.cmd_comment.__doc__
        key = args[0].upper()
        text = ' '.join(args[1:])
        return self._comment_issue(event["user_id"], key, text)

    def cmd_version(self, event):
        """Display version information for the configured JIRA platform. 'jira version'"""
        url = self._url("/rest/api/2/serverInfo")
        response = json.loads(requests.get(url).text)

        info = "%s : version %s : build %s" % (response["serverTitle"],
               response["version"], response["buildNumber"])

        return info

    def cmd_show(self, event, action):
        """Show which project keys are being tracked/expanded.
        Show which project keys are being expanded. 'jira show expanding'
        Show which project keys are being tracked. 'jira show tracking'
        """
        action = action.lower()
        if action in self.TRACK:
            return self._get_tracking(event["room_id"])
        elif action in self.EXPAND:
            return self._get_expanding(event["room_id"])

    def _get_tracking(self, room_id):
        try:
            return ("Currently tracking %s" %
                json.dumps(
                    self.rooms.get_content(
                        room_id,
                        JiraPlugin.TYPE_TRACK
                    )["projects"]
                )
            )
        except KeyError:
            return "Not tracking any projects currently."

    def _get_expanding(self, room_id):
        try:
            return ("Currently expanding %s" %
                json.dumps(
                    self.rooms.get_content(
                        room_id,
                        JiraPlugin.TYPE_EXPAND
                    )["projects"]
                )
            )
        except KeyError:
            return "Not expanding any projects currently."

    def _send_state(self, etype, room_id, project_keys):
        self.matrix.send_state_event(
            room_id,
            etype,
            {
                "projects": project_keys
            }
        )

    def on_msg(self, event, body):
        room_id = event["room_id"]
        body = body.upper()
        groups = self.regex.findall(body)
        if not groups:
            return

        projects = []
        try:
            projects = self.rooms.get_content(
                    room_id, JiraPlugin.TYPE_EXPAND
                )["projects"]
        except KeyError:
            return

        for (key, project) in groups:
            if project in projects:
                try:
                    issue_info = self._get_issue_info(key)
                    if issue_info:
                        self.matrix.send_message(
                            event["room_id"],
                            issue_info,
                            msgtype="m.notice"
                        )
                except Exception as e:
                    log.exception(e)

    def on_event(self, event, event_type):
        self.rooms.update(event)

    def on_receive_jira_push(self, info):
        log.debug("on_recv %s", info)
        project = self.regex.match(info["key"]).groups()[1]

        # form the message
        link = self._linkify(info["key"])
        push_message = "%s %s <b>%s</b> - %s %s" % (info["user"], info["action"],
                       info["key"], info["summary"], link)

        # send messages to all rooms registered with this project.
        for room_id in self.rooms.get_room_ids():
            try:
                content = self.rooms.get_content(room_id, JiraPlugin.TYPE_TRACK)
                if project in content["projects"]:
                    self.matrix.send_message_event(
                        room_id,
                        "m.room.message",
                        self.matrix.get_html_body(push_message, msgtype="m.notice")
                    )
            except KeyError:
                pass

    def on_sync(self, sync):
        log.debug("Plugin: JIRA sync state:")
        self.rooms.init_from_sync(sync)

    def _get_issue_info(self, issue_key):
        url = self._url("/rest/api/2/issue/%s" % issue_key)
        res = requests.get(url, auth=self.auth)
        if res.status_code != 200:
            return

        response = json.loads(res.text)
        link = self._linkify(issue_key)
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

    def _create_issue(self, user_id, project, priority, title, desc=""):
        if priority < 1:
            priority = 1
        if priority > 5:
            priority = 5
        desc = "Submitted by %s\n%s" % (user_id, desc)

        fields = {}
        fields["priority"] = {
            "name": ("P%s" % priority)
        }
        fields["project"] = {
            "key": project.upper().strip()
        }
        fields["issuetype"] = {
            "name": "Bug"
        }
        fields["summary"] = title
        fields["description"] = desc

        info = {
            "fields": fields
        }

        url = self._url("/rest/api/2/issue")
        res = requests.post(url, auth=self.auth, data=json.dumps(info), headers={
            "Content-Type": "application/json"
        })

        if res.status_code < 200 or res.status_code >= 300:
            err = "Failed: HTTP %s - %s" % (res.status_code, res.text)
            log.error(err)
            return err

        response = json.loads(res.text)
        issue_key = response["key"]
        link = self._linkify(issue_key)

        return "Created issue: %s" % link

    def _comment_issue(self, user_id, key, text):
        text = "By %s: %s" % (user_id, text)
        info = {
            "body": text
        }

        url = self._url("/rest/api/2/issue/%s/comment" % key)
        res = requests.post(url, auth=self.auth, data=json.dumps(info), headers={
            "Content-Type": "application/json"
        })

        if res.status_code < 200 or res.status_code >= 300:
            err = "Failed: HTTP %s - %s" % (res.status_code, res.text)
            log.error(err)
            return err
        link = self._linkify(key)
        return "Commented on issue %s" % link

    def _linkify(self, key):
        return "%s/browse/%s" % (self.store.get("url"), key)

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
