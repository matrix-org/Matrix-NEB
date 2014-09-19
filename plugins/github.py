# -*- coding: utf-8 -*-
from neb.engine import Plugin, Command, KeyValueStore

from flask import Flask
from flask import request

from hashlib import sha1
import hmac
import json
import threading

import logging

log = logging.getLogger(name=__name__)


class GithubPlugin(Plugin):
    """ Plugin for interacting with Github. Supports webhooks.

    New events:
        Type: org.matrix.neb.plugin.github.projects.tracking
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
            self.store.set("known_projects", [])

        if not self.store.has("server_port"):
            self.store.set("server_port", 8500)

        if not self.store.has("secret_token"):
            self.store.set("secret_token", "")

        self.state = {
            # room_id : { projects: [projectName1, projectName2, ...] }
        }

        self.server = GithubWebServer(
            self,
            self.store.get("server_port"),
            self.store.get("secret_token")
        )
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

        # TODO: make this configurable
        if event["user_id"] not in self.matrix.config.admins:
            return self._body("Sorry, only %s can do that." % json.dumps(self.matrix.config.admins))

        try:
            return actions[action](event, args)
        except KeyError:
            return self._body("Unknown Github action: %s" % action)

    def on_receive_github_push(self, info):
        log.info("recv %s", info)

        # add the project if we didn't know about it before
        if info["repo"] not in self.store.get("known_projects"):
            log.info("Added new repo: %s", info["repo"])
            projects = self.store.get("known_projects")
            projects.append(info["repo"])
            self.store.set("known_projects", projects)



        # form the template:
        # [<repo>] <username> pushed <num> commits to <branch>: <git.io link>
        # 1<=3 of <branch name> <short hash> <full username>: <comment>
        push_message = "[%s] %s pushed to %s: %s  - %s" % (
            info["repo"],
            info["commit_username"],
            info["branch"],
            info["commit_msg"],
            info["commit_link"]
        )

        # send messages to all rooms registered with this project.
        for (room_id, room_info) in self.state.iteritems():
            try:
                if info["repo"] in room_info["projects"]:
                    self.matrix.send_message(room_id, self._body(push_message))
            except KeyError:
                pass

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
            "org.matrix.neb.plugin.github.projects.tracking",
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
        if event_type == "org.matrix.neb.plugin.github.projects.tracking":
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
                    if state["type"] == "org.matrix.neb.plugin.github.projects.tracking":
                        self._set_track_event(state)
            except KeyError:
                pass

        print "Plugin: GitHub Sync state:"
        print json.dumps(self.state, indent=4)


app = Flask("GithubWebServer")


class GithubWebServer(threading.Thread):

    def __init__(self, plugin, port, token=None):
        super(GithubWebServer, self).__init__()
        self.plugin = plugin
        self.port = port
        self.secret_token = token

        app.add_url_rule('/neb/github', '/neb/github', self.do_POST, methods=["POST"])

    def notify_plugin(self, content):
        self.plugin.on_receive_github_push(content)

    def run(self):
        log.info("Running GithubWebServer")
        app.run(host="0.0.0.0", port=self.port)

    def do_POST(self):
        log.debug("GithubWebServer: Incoming request from %s",
                  request.remote_addr)

        j = request.get_json()

        if self.secret_token:
            token_sha1 = request.headers.get('X-Hub-Signature')
            payload_body = request.data
            calc = hmac.new(str(self.secret_token), payload_body, sha1)
            calc_sha1 = "sha1=" + calc.hexdigest()
            if token_sha1 != calc_sha1:
                log.warn("GithubWebServer: FAILED SECRET TOKEN AUTH. IP=%s",
                         request.remote_addr)
                return ("", 403, {})

        repo_name = j["repository"]["full_name"]
        branch = j["ref"].split('/')[-1]
        commit_msg = j["head_commit"]["message"]
        commit_name = j["head_commit"]["committer"]["name"]

        commit_uname = None
        try:
            commit_uname = j["head_commit"]["committer"]["username"]
        except KeyError:
            # possible if they haven't tied up with a github account
            commit_uname = commit_name

        commit_link = j["head_commit"]["url"]
        # short hash please
        short_hash = commit_link.split('/')[-1][0:8]
        commit_link = '/'.join(commit_link.split('/')[0:-1]) + "/" + short_hash

        self.notify_plugin({
            "branch": branch,
            "repo": repo_name,
            "commit_msg": commit_msg,
            "commit_username": commit_uname,
            "commit_name": commit_name,
            "commit_link": commit_link,
            "commit_hash": short_hash
        })
        return ("", 200, {})


