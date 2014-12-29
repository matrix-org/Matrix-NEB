# -*- coding: utf-8 -*-
from neb.plugins import Plugin, admin_only
from neb.engine import KeyValueStore

import json
import urlparse

import logging as log


class JenkinsPlugin(Plugin):
    """ Plugin for receiving Jenkins notifications via the Notification Plugin.
    jenkins show projects : Display which projects this bot recognises.
    jenkins show track|tracking : Display which projects this bot is tracking.
    jenkins track project1 project2 ... : Track Jenkins notifications for the named projects.
    jenkins stop track|tracking : Stop tracking Jenkins notifications.
    """
    name = "jenkins"

    # https://wiki.jenkins-ci.org/display/JENKINS/Notification+Plugin

    #New events:
    #    Type: org.matrix.neb.plugin.jenkins.projects.tracking
    #    State: Yes
    #    Content: {
    #        projects: [projectName1, projectName2, ...]
    #    }

    #Webhooks:
    #    /neb/jenkins

    TRACKING = ["track", "tracking"]
    TYPE_TRACK = "org.matrix.neb.plugin.jenkins.projects.tracking"

    def __init__(self, *args, **kwargs):
        super(JenkinsPlugin, self).__init__(*args, **kwargs)
        self.store = KeyValueStore("jenkins.json")

        if not self.store.has("known_projects"):
            self.store.set("known_projects", [])

        if not self.store.has("secret_token"):
            self.store.set("secret_token", "")

        self.state = {
            # room_id : { projects: [projectName1, projectName2, ...] }
        }

        self.failed_builds = {
            # projectName:branch: { commit:x }
        }

    def cmd_show(self, event, action):
        """Show information on projects or projects being tracked.
        Show which projects are being tracked. 'jenkins show tracking'
        Show which proejcts are recognised so they could be tracked. 'jenkins show projects'
        """
        if action in self.TRACKING:
            return self._get_tracking(event["room_id"])
        elif action == "projects":
            projects = self.store.get("known_projects")
            return [
                self._body("Available projects: %s" % json.dumps(projects)),
            ]
        else:
            return "Invalid arg '%s'.\n %s" % (action, self.cmd_show.__doc__)

    @admin_only
    def cmd_track(self, event, *args):
        """Track projects. 'jenkins track Foo "bar with spaces"'"""
        if len(args) == 0:
            return self._get_tracking(event["room_id"])

        for project in args:
            if not project in self.store.get("known_projects"):
                return self._body("Unknown project name: %s." % project)

        self._send_track_event(event["room_id"], args)

        return self._body(
            "Jenkins notifications for projects %s will be displayed when they fail." % (args)
        )

    @admin_only
    def cmd_stop(self, event, action):
        """Stop tracking projects. 'jenkins stop tracking'"""
        if action in self.TRACKING:
            self._send_track_event(event["room_id"], [])
            return "Stopped tracking projects."
        else:
            return "Invalid arg '%s'.\n %s" % (action, self.cmd_stop.__doc__)

    def _get_tracking(self, room_id):
        try:
            return self._body("Currently tracking %s" %
            json.dumps(self.state[room_id]["projects"]))
        except KeyError:
            return self._body("Not tracking any projects currently.")

    def _send_track_event(self, room_id, project_names):
        self.matrix.send_event(
            room_id,
            self.TYPE_TRACK,
            {
                "projects": project_names
            },
            state=True
        )

    def send_message_to_repos(self, repo, push_message):
        # send messages to all rooms registered with this project.
        for (room_id, room_info) in self.state.iteritems():
            try:
                if repo in room_info["projects"]:
                    self.matrix.send_message(
                        room_id,
                        self._rich_body(push_message)
                    )
            except KeyError:
                pass

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
        if event_type == self.TYPE_TRACK:
            self._set_track_event(event)

    def on_sync(self, sync):
        for room in sync["rooms"]:
            # see if we know anything about these rooms
            room_id = room["room_id"]
            if room["membership"] != "join":
                continue

            self.state[room_id] = {}

            try:
                for state in room["state"]:
                    if state["type"] == self.TYPE_TRACK:
                        self._set_track_event(state)
            except KeyError:
                pass

        log.debug("Plugin: Jenkins Sync state:")
        log.debug(json.dumps(self.state, indent=4))

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

        j = json.loads(data)
        name = j["name"]

        query_dict = urlparse.parse_qs(urlparse.urlparse(url).query)
        if "secret" in query_dict and self.store.get("secret_token"):
            # The jenkins Notification plugin does not support any sort of
            # "execute this code on this json object before you send" so we can't
            # send across HMAC SHA1s like with github :( so a secret token will
            # have to do.
            secrets = query_dict["secret"]
            if len(secrets) > 1:
                log.warn("Jenkins webhook: FAILED SECRET TOKEN AUTH. Too many secrets. IP=%s",
                         ip)
                return ("", 403, {})
            elif secrets[0] != self.store.get("secret_token"):
                log.warn("Jenkins webhook: FAILED SECRET TOKEN AUTH. Mismatch. IP=%s",
                         ip)
                return ("", 403, {})
            else:
                log.info("Jenkins webhook: Secret verified.")


        # add the project if we didn't know about it before
        if name not in self.store.get("known_projects"):
            log.info("Added new job: %s", name)
            projects = self.store.get("known_projects")
            projects.append(name)
            self.store.set("known_projects", projects)

        status = j["build"]["status"]
        branch = None
        commit = None
        git_url = None
        jenkins_url = None
        info = ""
        try:
            branch = j["build"]["scm"]["branch"]
            commit = j["build"]["scm"]["commit"]
            git_url = j["build"]["scm"]["url"]
            jenkins_url = j["build"]["full_url"]
            # try to format the git url nicely
            if (git_url.startswith("git@github.com") and
                    git_url.endswith(".git")):
                # git@github.com:matrix-org/synapse.git
                org_and_repo = git_url.split(":")[1][:-4]
                commit = "https://github.com/%s/commit/%s" % (org_and_repo, commit)


            info = "%s commit %s - %s" % (branch, commit, jenkins_url)
        except KeyError:
            pass

        fail_key = "%s:%s" % (name, branch)

        if status.upper() != "SUCCESS":
            # complain
            msg = '<font color="red">[%s] <b>%s - %s</b></font>' % (
                name,
                status,
                info
            )

            if fail_key in self.failed_builds:
                info = "%s failing since commit %s - %s" % (branch, self.failed_builds[fail_key]["commit"], jenkins_url)
                msg = '<font color="red">[%s] <b>%s - %s</b></font>' % (
                    name,
                    status,
                    info
                )
            else:  # add it to the list
                self.failed_builds[fail_key] = {
                    "commit": commit
                }

            self.send_message_to_repos(name, msg)
        else:
            # do we need to prod people?
            if fail_key in self.failed_builds:
                info = "%s commit %s" % (branch, commit)
                msg = '<font color="green">[%s] <b>%s - %s</b></font>' % (
                    name,
                    status,
                    info
                )
                self.send_message_to_repos(name, msg)
                self.failed_builds.pop(fail_key)


