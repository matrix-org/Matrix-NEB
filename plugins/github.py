# -*- coding: utf-8 -*-
from neb.engine import Plugin, Command, KeyValueStore, ThreadedServer

import BaseHTTPServer
import json

import logging

log = logging.getLogger(name=__name__)


class GithubPlugin(Plugin):
    """ Plugin for interacting with Github. Supports webhooks.

    New events:
        Type: neb.plugin.github.projects.tracking
        State: Yes
        Content: {
            projects: [projectName1, projectName2, ...]
        }

    Background operations:
        Listens on port 8500 (default; configurable in github.json) for incoming
        requests from github.
    """

    HELP = [
        "show-projects :: Display which projects this bot has been configured with.",
        "track-projects name,name2.name3 :: Track when commits are added to the named projects name, name2, name3.",
        "clear-tracking :: Clears tracked projects from this room."
    ]

    def __init__(self, config="github.json"):
        self.store = KeyValueStore(config)

        if not self.store.has("known_projects"):
            self.store.set("known_projects", ["FOO", "BAR"])

        if not self.store.has("server_port"):
            self.store.set("server_port", 8500)

        self.state = {
            # room_id : { projects: [projectName1, projectName2, ...] }
        }

        GithubWebServer.set_plugin(self)
        self.server = ThreadedServer(GithubWebServer,
                                     self.store.get("server_port"))
        self.server.daemon = True
        self.server.start()

    def get_commands(self):
        """Return human readable commands with descriptions.

        Returns:
            list[Command]
        """
        return [
            Command("github", self.github, "Perform commands on github.",
            GithubPlugin.HELP),
        ]

    def github(self, event, args):
        if len(args) == 1:
            return [self._body(x) for x in GithubPlugin.HELP]

        action = args[1]
        actions = {
            "show-projects": self._show_projects,
            "track-projects": self._track_projects,
            "clear-tracking": self._clear_tracking
        }

        try:
            return actions[action](event, args)
        except KeyError:
            return self._body("Unknown Github action: %s" % action)

    def on_receive_github_push(self, info):
        log.info("recv %s", info)

    def _show_projects(self, event, args):
        projects = self.store.get("known_projects")
        return [
            self._body("Available projects: %s" % json.dumps(projects)),
        ]

    def _track_projects(self, event, args):
        project_names_csv = ' '.join(args[2:]).upper().strip()
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
            "Commits for projects %s from will be displayed as they are commited." % (project_names)
        )

    def _clear_tracking(self, event, args):
        self._send_track_event(event["room_id"], [])
        return self._body(
            "Stopped tracking projects."
        )

    def _send_track_event(self, room_id, project_names):
        self.matrix.send_event(
            room_id,
            "neb.plugin.github.projects.tracking",
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
                    if state["type"] == "neb.plugin.github.projects.tracking":
                        self._set_track_event(state)
            except KeyError:
                pass

        print "Plugin: GitHub Sync state:"
        print json.dumps(self.state, indent=4)


class GithubWebServer(BaseHTTPServer.BaseHTTPRequestHandler):

    @classmethod
    def set_plugin(cls, plugin):
        cls.plugin = plugin

    def get_json_keys(j):
        return {
            "foo": "bar"
        }

    def do_POST(s):
        log.debug("GithubWebServer: %s from %s", s.requestline,
                  s.client_address)

        if s.headers['Content-Type'].startswith("application/json"):
            j = json.load(s.rfile)
            log.debug("Content: %s", j)

        s.send_response(200)
        s.send_header("Content-Length", 0)
        s.end_headers()



