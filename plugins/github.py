# -*- coding: utf-8 -*-
from neb.engine import KeyValueStore
from neb.plugins import Plugin, admin_only

from hashlib import sha1
import hmac
import json

import logging as log


class GithubPlugin(Plugin):
    """Plugin for interacting with Github.
    github show projects : Show which github projects this bot recognises.
    github show track|tracking : Show which projects are being tracked.
    github track "owner/repo" "owner/repo" : Track the given projects.
    github stop track|tracking : Stop tracking github projects.
    """
    name = "github"
    #New events:
    #    Type: org.matrix.neb.plugin.github.projects.tracking
    #    State: Yes
    #    Content: {
    #        projects: [projectName1, projectName2, ...]
    #    }

    #Webhooks:
    #    /neb/github
    TYPE_TRACK = "org.matrix.neb.plugin.github.projects.tracking"
    TYPE_COLOR = "org.matrix.neb.plugin.github.projects.color"

    TRACKING = ["track", "tracking"]

    def __init__(self, *args, **kwargs):
        super(GithubPlugin, self).__init__(*args, **kwargs)
        self.store = KeyValueStore("github.json")

        if not self.store.has("known_projects"):
            self.store.set("known_projects", [])

        if not self.store.has("secret_token"):
            self.store.set("secret_token", "")

        self.state = {
            # room_id : { projects: [projectName1, projectName2, ...] }
        }

    def on_receive_github_push(self, info):
        log.info("recv %s", info)

        # add the project if we didn't know about it before
        if info["repo"] not in self.store.get("known_projects"):
            log.info("Added new repo: %s", info["repo"])
            projects = self.store.get("known_projects")
            projects.append(info["repo"])
            self.store.set("known_projects", projects)

        push_message = ""

        if info["type"] == "delete":
            push_message = '[%s] %s <font color="red"><b>deleted</font> %s</b>' % (
                info["repo"],
                info["commit_username"],
                info["branch"]
            )
        elif info["type"] == "commit":
            # form the template:
            # [<repo>] <username> pushed <num> commits to <branch>: <git.io link>
            # 1<=3 of <branch name> <short hash> <full username>: <comment>
            if info["num_commits"] == 1:
                push_message = "[%s] %s pushed to <b>%s</b>: %s  - %s" % (
                    info["repo"],
                    info["commit_username"],
                    info["branch"],
                    info["commit_msg"],
                    info["commit_link"]
                )
            else:
                summary = ""
                max_commits = 3
                count = 0
                for c in info["commits_summary"]:
                    if count == max_commits:
                        break
                    summary += "\n%s: %s" % (c["author"], c["summary"])
                    count += 1

                push_message = "[%s] %s pushed %s commits to <b>%s</b>: %s %s" % (
                    info["repo"],
                    info["commit_username"],
                    info["num_commits"],
                    info["branch"],
                    info["commit_link"],
                    summary
                )
        else:
            log.warn("Unknown push type. %s", info["type"])
            return

        self.send_message_to_repos(info["repo"], push_message)

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

    def cmd_show(self, event, action):
        """Show information on projects or projects being tracked.
        Show which projects are being tracked. 'github show tracking'
        Show which proejcts are recognised so they could be tracked. 'github show projects'
        """
        if action == "projects":
            projects = self.store.get("known_projects")
            return "Available projects: %s" % json.dumps(projects)
        elif action in self.TRACKING:
            return self._get_tracking(event["room_id"])
        else:
            return self.cmd_show.__doc__

    @admin_only
    def cmd_track(self, event, *args):
        if len(args) == 0:
            return self._get_tracking(event["room_id"])

        for project in args:
            if not project in self.store.get("known_projects"):
                return "Unknown project name: %s." % project

        self._send_track_event(event["room_id"], args)

        return "Commits for projects %s will be displayed as they are commited." % (args,)

    @admin_only
    def cmd_stop(self, event, action):
        """Stop tracking projects. 'github stop tracking'"""
        if action in self.TRACKING:
            self._send_track_event(event["room_id"], [])
            return "Stopped tracking projects."
        else:
            return self.cmd_stop.__doc__

    def xcmd_color(self, event, repo, branch, color):
        """"Set the color of notifications for a project and branch. The color must be hex or an HTML 4 named color.
        'github color project branch color' e.g. github color bob/repo develop #0000ff
        """

        if not repo in self.store.get("known_projects"):
            return self._body("Unknown github repo: %s" % repo)

        # basic color validation
        valid = False
        color = color.strip().lower()
        if color in ["white","silver","gray","black","red","maroon","yellow","olive","lime","green","aqua","teal","blue","navy","fuchsia","purple"]:
            valid = True
        else:
            test_color = color
            if color[0] == '#':
                test_color = color[1:]
            try:
                color_int = int(test_color, 16)
                valid = color_int <= 0xFFFFFF
                color = "#%06x" % color_int
            except:
                return self._body("Color should be like '#112233', '0x112233' or 'green'")

        if not valid:
            return self._body("Color should be like '#112233', '0x112233' or 'green'")

        return self._body("Not yet implemented. Valid. Repo=%s Branch=%s Color=%s" % (repo, branch, color))

 #       color_list = self.store.get("project_colors")
 #       color_list

 #       self._send_color_event(event["room_id"], repo, branch, color)

    def _send_color_event(self, room_id, repo, branch, color):
        self.matrix.send_event(
            room_id,
            self.TYPE_COLOR,
            {
                "projects": project_names
            },
            state=True
        )

    def _send_track_event(self, room_id, project_names):
        self.matrix.send_event(
            room_id,
            self.TYPE_TRACK,
            {
                "projects": project_names
            },
            state=True
        )

    def _get_tracking(self, room_id):
        try:
            return "Currently tracking %s" % json.dumps(self.state[room_id]["projects"])
        except KeyError:
            return "Not tracking any projects currently."

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

    def get_webhook_key(self):
        return "github"

    def on_receive_pull_request(self, data):
        action = data["action"]
        pull_req_num = data["number"]
        repo_name = data["repository"]["full_name"]
        pr = data["pull_request"]
        pr_url = pr["html_url"]
        pr_state = pr["state"]
        pr_title = pr["title"]

        user = data["sender"]["login"]

        msg = "[%s] %s %s <b>pull request #%s</b>: %s [%s] - %s" % (
            repo_name,
            user,
            action,
            pull_req_num,
            pr_title,
            pr_state,
            pr_url
        )

        self.send_message_to_repos(repo_name, msg)

    def on_receive_create(self, data):
        if data["ref_type"] != "branch":
            return  # only echo branch creations for now.

        branch_name = data["ref"]
        user = data["sender"]["login"]
        repo_name = data["repository"]["full_name"]

        msg = '[%s] %s <font color="green">created</font> a new branch: <b>%s</b>' % (
            repo_name,
            user,
            branch_name
        )

        self.send_message_to_repos(repo_name, msg)

    def on_receive_ping(self, data):
        repo_name = data["repository"]["full_name"]
        # add the project if we didn't know about it before
        if repo_name not in self.store.get("known_projects"):
            log.info("Added new repo: %s", repo_name)
            projects = self.store.get("known_projects")
            projects.append(repo_name)
            self.store.set("known_projects", projects)

    def on_receive_comment(self, data):
        repo_name = data["repository"]["full_name"]
        issue = data["issue"]
        comment = data["comment"]
        is_pull_request = "pull_request" in issue
        if not is_pull_request:
            return  # don't bother displaying issue comments

        pr_title = issue["title"]
        pr_num = issue["number"]
        comment_url = comment["html_url"]
        username = comment["user"]["login"]

        msg = "[%s] %s commented on <b>pull request #%s</b>: %s - %s" % (
            repo_name,
            username,
            pr_num,
            pr_title,
            comment_url
        )
        self.send_message_to_repos(repo_name, msg)


    def on_receive_issue(self, data):
        action = data["action"]
        repo_name = data["repository"]["full_name"]
        issue = data["issue"]
        title = issue["title"]
        issue_num = issue["number"]
        url = issue["html_url"]

        user = data["sender"]["login"]

        if action == "assigned":
            try:
                assignee = data["assignee"]["login"]
                msg = "[%s] %s assigned issue #%s to %s: %s - %s" % (
                    repo_name,
                    user,
                    issue_num,
                    assignee,
                    title,
                    url
                )
                self.send_message_to_repos(repo_name, msg)
                return
            except:
                pass


        msg = "[%s] %s %s issue #%s: %s - %s" % (
            repo_name,
            user,
            action,
            issue_num,
            title,
            url
        )

        self.send_message_to_repos(repo_name, msg)


    def on_receive_webhook(self, url, data, ip, headers):
        if self.store.get("secret_token"):
            token_sha1 = headers.get('X-Hub-Signature')
            payload_body = data
            calc = hmac.new(str(self.store.get("secret_token")), payload_body,
                            sha1)
            calc_sha1 = "sha1=" + calc.hexdigest()
            if token_sha1 != calc_sha1:
                log.warn("GithubWebServer: FAILED SECRET TOKEN AUTH. IP=%s",
                         ip)
                return ("", 403, {})

        event_type = headers.get('X-GitHub-Event')
        if event_type == "pull_request":
            self.on_receive_pull_request(json.loads(data))
            return
        elif event_type == "issues":
            self.on_receive_issue(json.loads(data))
            return
        elif event_type == "create":
            self.on_receive_create(json.loads(data))
            return
        elif event_type == "ping":
            self.on_receive_ping(json.loads(data))
            return
        elif event_type == "issue_comment":  # INCLUDES PR COMMENTS!!!
            self.on_receive_comment(json.loads(data))
            return

        j = json.loads(data)
        repo_name = j["repository"]["full_name"]
        # strip 'refs/heads' from 'refs/heads/branch_name'
        branch = '/'.join(j["ref"].split('/')[2:])

        commit_msg = ""
        commit_name = ""
        commit_link = ""
        short_hash = ""
        push_type = "commit"

        if j["head_commit"]:
            commit_msg = j["head_commit"]["message"]
            commit_name = j["head_commit"]["committer"]["name"]
            commit_link = j["head_commit"]["url"]
            # short hash please
            short_hash = commit_link.split('/')[-1][0:8]
            commit_link = '/'.join(commit_link.split('/')[0:-1]) + "/" + short_hash
        elif j["deleted"]:
            # looks like this branch was deleted, no commit and deleted=true
            commit_name = j["pusher"]["name"]
            push_type = "delete"

        commit_uname = None
        try:
            commit_uname = j["head_commit"]["committer"]["username"]
        except Exception:
            # possible if they haven't tied up with a github account
            commit_uname = commit_name

        # look for multiple commits
        num_commits = 1
        commits_summary = []
        if "commits" in j and len(j["commits"]) > 1:
            num_commits = len(j["commits"])
            for c in j["commits"]:
                cname = None
                try:
                    cname = c["author"]["username"]
                except:
                    cname = c["author"]["name"]
                commits_summary.append({
                    "author": cname,
                    "summary": c["message"]
                })


        self.on_receive_github_push({
            "branch": branch,
            "repo": repo_name,
            "commit_msg": commit_msg,
            "commit_username": commit_uname,
            "commit_name": commit_name,
            "commit_link": commit_link,
            "commit_hash": short_hash,
            "type": push_type,
            "num_commits": num_commits,
            "commits_summary": commits_summary
        })

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

        log.debug("Plugin: GitHub Sync state:")
        log.debug(json.dumps(self.state, indent=4))


