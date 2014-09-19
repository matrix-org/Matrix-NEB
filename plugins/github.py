# -*- coding: utf-8 -*-
from neb.engine import Plugin, Command, KeyValueStore

import json


class GithubPlugin(Plugin):

    HELP = [
        "show-projects :: Display which projects this bot has been configured with.",
        "track-projects name,name2.name3 :: Track when commits are added to the named projects name, name2, name3.",
        "clear-tracking :: Clears tracked projects from this room."
    ]

    def __init__(self, config="github.json"):
        self.store = KeyValueStore(config)

        if not self.store.has("known_projects"):
            self.store.set("known_projects", ["FOO", "BAR"])

        self.state = {
            # room_id : { projects: [projectName1, projectName2, ...] }
        }

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
                return self._body("Currently tracking %s" % json.dumps(self.state[event["room_id"]]["projects"]))
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

