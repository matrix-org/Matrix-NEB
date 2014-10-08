# -*- coding: utf-8 -*-
from neb.engine import Plugin, Command, KeyValueStore

from hashlib import sha1
import hmac
import json

import logging

log = logging.getLogger(name=__name__)


class JenkinsPlugin(Plugin):
    """ Plugin for receiving Jenkins notifications via the Notification Plugin.
    https://wiki.jenkins-ci.org/display/JENKINS/Notification+Plugin

    Supports webhooks.

    New events:
        Type: org.matrix.neb.plugin.jenkins.projects.tracking
        State: Yes
        Content: {
            projects: [projectName1, projectName2, ...]
        }

    Webhooks:
        /neb/jenkins
    """

    HELP = [
        "show-projects :: Display which projects this bot has been configured with.",
        "track-projects name,name2.name3 :: Track Jenkins notifications for named projects name, name2, name3.",
        "clear-tracking :: Clears tracked projects from this room."
    ]

    def __init__(self, config="jenkins.json"):
        self.store = KeyValueStore(config)

        if not self.store.has("known_projects"):
            self.store.set("known_projects", [])

        if not self.store.has("secret_token"):
            self.store.set("secret_token", "")

        self.state = {
            # room_id : { projects: [projectName1, projectName2, ...] }
        }

    def get_commands(self):
        """Return human readable commands with descriptions.

        Returns:
            list[Command]
        """
        return [
            Command("jenkins", self.jenkins, "Listen for Jenkins notifications.",
            JenkinsPlugin.HELP),
        ]

    def jenkins(self, event, args):
        if len(args) == 1:
            return [self._body(x) for x in JenkinsPlugin.HELP]

        action = args[1]
        actions = {
            "show-projects": self._show_projects,
            "track-projects": self._track_projects,
            "clear-tracking": self._clear_tracking
        }

        # TODO: make this configurable
        if event["user_id"] not in self.matrix.config.admins:
            return self._body("Sorry, only %s can do that." % json.dumps(self.matrix.config.admins))

        try:
            return actions[action](event, args)
        except KeyError:
            return self._body("Unknown Jenkins action: %s" % action)

    def _show_projects(self, event, args):
        projects = self.store.get("known_projects")
        return [
            self._body("Available projects: %s" % json.dumps(projects)),
        ]

    def _track_projects(self, event, args):
        project_names_csv = ' '.join(args[2:]).strip()
        project_names = [a.strip() for a in project_names_csv.split(',')]
        if not project_names_csv:
            try:
                return self._body("Currently tracking %s" %
                json.dumps(self.state[event["room_id"]]["projects"]))
            except KeyError:
                return self._body("Not tracking any projects currently.")

        for key in project_names:
            if not key in self.store.get("known_projects"):
                return self._body("Unknown project name: %s." % key)

        self._send_track_event(event["room_id"], project_names)

        return self._body(
            "Jenkins notifications for projects %s will be displayed." % (project_names)
        )

    def _clear_tracking(self, event, args):
        self._send_track_event(event["room_id"], [])
        return self._body(
            "Stopped tracking projects."
        )

    def _send_track_event(self, room_id, project_names):
        self.matrix.send_event(
            room_id,
            "org.matrix.neb.plugin.jenkins.projects.tracking",
            {
                "projects": project_names
            },
            state=True
        )

    def _set_track_event(self, event):
        room_id = event["room_id"]
        projects = event["content"]["projects"]

        if room_id not in self.state:
            self.state[room_id] = {}

        if type(projects) == list:
            self.state[room_id]["projects"] = projects
        else:
            self.state[room_id]["projects"] = []

    def on_event(self, event, event_type):
        if event_type == "org.matrix.neb.plugin.jenkins.projects.tracking":
            self._set_track_event(event)

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
                    if state["type"] == "org.matrix.neb.plugin.jenkins.projects.tracking":
                        self._set_track_event(state)
            except KeyError:
                pass

        print "Plugin: Jenkins Sync state:"
        print json.dumps(self.state, indent=4)

    def get_webhook_key(self):
        return "jenkins"

    def on_receive_webhook(self, url, data, ip, headers):
        # data is of the form:
        # {
        #   "name":"Synapse",
        #   "url":"job/Synapse/",
        #   "build": {
        #     "full_url":"http://localhost:9009/job/Synapse/8/",
        #     "number":8,
        #     "phase":"FINALIZED",
        #     "status":"SUCCESS",
        #     "url":"job/Synapse/8/",
        #     "scm": {
        #        "url":"git@github.com:matrix-org/synapse.git",
        #        "branch":"origin/develop",
        #        "commit":"72aef114ab1201f5a5cd734220c9ec738c4e2910"
        #      },
        #     "artifacts":{}
        #    }
        # }
        log.info("URL: %s", url)
        log.info("Data: %s", data)
        log.info("Headers: %s", headers)