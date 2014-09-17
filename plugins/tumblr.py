from neb.engine import Plugin, Command, KeyValueStore
from neb import NebError

from pytumblr import TumblrRestClient

from xml.dom import minidom
import json
import threading
import urllib
import sys

import logging

log = logging.getLogger(name=__name__)


class TumblrPlugin(Plugin):
    """ Plugin for trawling Tumblr's API.

    New events:
      Type: neb.plugin.tumblr.username
      State: Yes
      Content: { username: foo }

      Type: neb.plugin.tumblr.position
      State: Yes
      Content: { unixts: 1234 }
    """

    def __init__(self, config="tumblr.json"):
        self.config = KeyValueStore(config)

        self._check_keys()

        self.client = TumblrRestClient(
            self.config.get("consumer_key"),
            self.config.get("secret_key"),
            self.config.get("oauth_token"),
            self.config.get("token_secret"),
        )

        # set from initial sync
        self.state = {
            "rooms": {},
            "usernames": {}
        }

    def get_info(self, username):
        info = self._get(username=username)
        return self._get(room_id=info["room_id"])

    def _get(self, room_id=None, username=None):
        if not room_id and not username:
            return None
        if room_id and room_id in self.state["rooms"]:
            return self.state["rooms"][room_id]
        if username and username in self.state["usernames"]:
            return self.state["usernames"][username]

    def map_room(self, room, username, position=0, clobber=False):
        updated = False
        if clobber:
            self.state["usernames"][username] = {
                "room_id": room
            }
            self.state["rooms"][room] = {
                "position": position,
                "username": username
            }
            updated = True
        elif room not in self.state["rooms"] or username not in self.state["usernames"]:
            updated = self.map_room(room, username, position=0, clobber=True)

        return updated

    def _check_keys(self):
        keylist = [
            ("consumer_key", "Tumblr API v2 Consumer Key: "),
            ("secret_key", "Tumblr API v2 Secret Key: "),
            ("oauth_token", "Tumblr API v2 OAuth Token: "),
            ("token_secret", "Tumblr API v2 Token Secret: "),
        ]
        for (key, desc) in keylist:
            if not self.config.has(key):
                val = raw_input(desc).strip()
                self.config.set(key, val)

    def get_commands(self):
        return [
            Command("follow", self.follow, "Follow username.tumblr.com", [
                "follow <username> <opts>: Follow username.tumblr.com with the specified options. ",
                "Options include:",
                "  '--upload-images' : Re-upload images from Tumblr to the HS.",
                "  '--secret' : Keeps this between us, and don't make a public room for this. Read-only.",
                 "  '--social' : The created room will be private, but you will have permission to invite people and send messages."
            ])
        ]

    def sync(self, matrix, sync):
        self.matrix = matrix
        log.debug("Handling initial sync results")
        for room in sync["rooms"]:
            # see if we know anything about these rooms
            room_id = room["room_id"]
            if room["membership"] != "join":
                continue
            username = None
            position = None
            try:
                for state in room["state"]:
                    if state["type"] == "neb.plugin.tumblr.username":
                        username = state["content"]["username"]
                    elif state["type"] == "neb.plugin.tumblr.position":
                        position = state["content"]["unixts"]
            except KeyError:
                log.warn("No state info found for %s", room_id)

            if username and position:
                log.info("Syncing state for room %s (%s)", room_id, username)

                self.map_room(
                    username=username,
                    room=room_id,
                    clobber=True,
                    position=position
                )
            elif username:
                if self.map_room(
                    username=username,
                    room=room_id,
                    clobber=False
                ):
                    log.info("Synced new state for %s (%s) as don't have it.", room_id, username)
                else:
                    log.info("Synced existing state for %s (%s)", room_id, username)

            print "Plugin: Tumblr Sync state:"
            print json.dumps(self.state, indent=4)

    def follow(self, event, args):
        username = args[1]
        log.info("Follow request for %s", username)

        room_info = self._get(username=username)
        if room_info:
            room_id = room_info["room_id"]
            log.debug("Username %s to %s found in cache.", username, room_id)
            try:
                self.matrix.invite_user(room_id, event["user_id"])
                return [self._body("Invited to existing room.")]
            except NebError as e:
                return [self._body(e.as_str())]


        log.debug("Creating new room for %s", username)
        try:
            room_info = self.matrix.create_room(username)
        except NebError as e:
            return [self._body(e.as_str())]
        room_id = room_info["room_id"]
        log.debug("Created new room %s for username %s", room_id, username)

        user = event["user_id"]
        self.matrix.invite_user(room_id, user)
        self.map_room(username=username, room=room_id)
        log.debug("Invited %s to room %s. Reason: They issued a follow.", user, room_id)

        # setup state in room
        self.matrix.send_event(room_id, "neb.plugin.tumblr.username", {
            "username": username
        }, state=True)
        self.update_pos(room_id, 0)


        responses = [
            self._body("Sent invite for room.")
        ]

        # TODO: Asyncly populate this.
        posts = self.get_posts(user=username)

        rate_limited = False
        rate_limit_sleep_dur = 1
        for post in posts["entries"]:
            messages = self.to_messages(posts["entries"], event_type="matrix")
            for msg in messages:
                try:
                    self.matrix.send_message(room_id, msg)
                except NebError as e:
                    if e.code == 429:
                        log.warn("Rate limited on request. Bailing.")
                        rate_limited = True
                        rate_limit_sleep_dur = json.loads(e.msg)["retry_after_ms"]
                        break
            if rate_limited:
                break

        # FIXME : Do something about this.
        threading._sleep(1 + (rate_limit_sleep_dur/1000))

        current_pos = self.get_info(username=username)["position"]
        new_pos = posts["position"]
        if current_pos != new_pos:
            log.debug("Updating position for room %s from %s to %s", room_id, current_pos, new_pos)
            self.map_room(room=room_id, username=username, position=new_pos, clobber=True)
            self.update_pos(room_id, new_pos)

        return responses

    def update_pos(self, room_id, pos):
        self.matrix.send_event(room_id, "neb.plugin.tumblr.position", {
            "unixts": pos
        }, state=True)


    def get_xml(self, username):
        url = "http://%s.tumblr.com/api/read" % username
        r = self.open(url)
        try:
            return r.encode("UTF-8")
        except:
            return r

    def get_posts(self, user=None, offset=0):
        log.debug("get_posts %s offset=%s", user, offset)

        if not user:
            return None

        xml_text = self.get_xml(user)

        doc = minidom.parseString(xml_text)
        posts = doc.getElementsByTagName("post")
        log.debug("Parsed XML: found %s posts for %s.", len(posts), user)
        entries = []
        current_pos = self.get_info(username=user)["position"]
        new_pos = current_pos
        log.debug("%s old pos = %s", user, current_pos)
        for p in posts:
            ts = p.attributes["unix-timestamp"].value
            if ts <= current_pos:
                continue
            if ts > new_pos:
                new_pos = ts
            url = p.attributes["url-with-slug"].value
            content = ""
            try:
                # TODO: We should just scan the entire post for things ending in file extensions we know we can send.
                # tumblr is too inconsistent to give pics! Some have <photo-url>, some are <regular-body>
                body = p.getElementsByTagName("regular-body")[0]
                content = body.childNodes[0].data
            except Exception as e:
                print "Can't get regular-body for post: %s" % url

            try:
                photo_urls = p.getElementsByTagName("photo-url")
                for u in photo_urls:
                    entries.append({"url":u.firstChild.nodeValue, "content":u.firstChild.nodeValue, "ts":ts})
            except Exception as e:
                print "Can't get photo-url for post: %s : %s" % (url, e)

            entries.append({"url":url, "content": content, "ts": ts})

        return {
            "entries": entries,
            "position": new_pos
        }

    def to_messages(self, posts, event_type):
        if event_type == "matrix":
            entries = []
            for post in posts:
                if post["url"].endswith("250.jpg") or post["url"].endswith("250.gif") or post["url"].endswith("250.jpeg"):
                    entries.append({
                           "msgtype": "m.image",
                           "body": post["url"],
                           "url": post["url"]
                    })
                else:
                    entries.append({
                        "msgtype": "m.text",
                        "body": post["url"],
                        "unixts": post["ts"]
                    })
            return entries
        else:
            raise Exception("Unknown event_type %s" % event_type)

