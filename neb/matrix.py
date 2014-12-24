#!/usr/bin/env python
import json
import shlex
import time
import urllib
import urllib2
from urllib2 import Request

from neb import NebError
from neb.plugins import CommandNotFoundError
from neb.webhook import NebHookServer

import logging as log


class MatrixConfig(object):
    URL = "url"
    USR = "user"
    TOK = "token"
    ADM = "admins"

    def __init__(self, hs_url, user_id, access_token, admins):
        self.user_id = user_id
        self.token = access_token
        self.base_url = hs_url
        self.admins = admins

    @classmethod
    def to_file(cls, config, f):
        f.write(json.dumps({
            MatrixConfig.URL: config.base_url,
            MatrixConfig.TOK: config.token,
            MatrixConfig.USR: config.user_id,
            MatrixConfig.ADM: config.admins
        }, indent=4))

    @classmethod
    def from_file(cls, f):
        j = json.load(f)
        return MatrixConfig(
            hs_url=j[MatrixConfig.URL],
            user_id=j[MatrixConfig.USR],
            access_token=j[MatrixConfig.TOK],
            admins=j[MatrixConfig.ADM]
        )


class PutRequest(Request):

    def get_method(self):
        return "PUT"


class Matrix(object):
    PREFIX = "!"

    def __init__(self, config):
        self.config = config
        self.plugin_cls = {}
        self.plugins = {}

    def _url(self, path, query={}, with_token=True):
        url = self.config.base_url + path
        if with_token:
            query["access_token"] = self.config.token
        if query:
            return url + "?" + urllib.urlencode(query)
        return url

    def _open(self, url, content=None, as_PUT=False, redact=False):
        if not redact:
            log.debug("open url >>> %s  >>>> %s", url, content)
        req = url
        if content and as_PUT:
            log.debug("Sending as a PUT")
            req = PutRequest(url)

        if content is not None:
            content = json.dumps(content)

        try:
            response = urllib2.urlopen(req, data=content)
            if response.code != 200:
                try:
                    res_content = response.read().encode("UTF-8")
                except:
                    res_content = None
                raise NebError(response.code, res_content)
            return json.loads(response.read())
        except urllib2.HTTPError as e:
            raise NebError(e.getcode(), e.read())

    def register(self):
        url = self._url("/register", with_token=False)
        content = {
            "user": self.config.user_id,
            "type": "m.login.password",
            "password": self.config.password
        }
        return self._open(url, content, redact=True)

    def initial_sync(self):
        url = self._url("/initialSync", {"limit": 1})
        return self._open(url)

    def create_room(self, alias):
        url = self._url("/createRoom")
        log.debug("create_room %s   %s", alias, type(alias))
        content = {
            "room_alias_name": alias
        }
        log.debug("create_room >>>> %s", content)
        return self._open(url, content)

    def send_message(self, room_id, content):
        return self.send_event(room_id, "m.room.message", content, state=False)

    def send_event(self, room_id, event_type, content, state=False):
        state_path = "state" if state else "send"
        url = self._url("/rooms/%s/%s/%s" % (urllib.quote(room_id), state_path, event_type))
        return self._open(url, content, as_PUT=state)

    def join_room(self, room_id):
        url = self._url("/join/%s" % urllib.quote(room_id))
        self._open(url, {})

    def invite_user(self, room_id, user_id):
        log.debug("Inviting %s to %s", user_id, room_id)
        url = self._url("/rooms/%s/invite" % urllib.quote(room_id))
        return self._open(url, {"user_id": user_id})

    def add_plugin(self, plugin):
        log.debug("add_plugin %s", plugin)
        if not plugin.name:
            raise NebError("No name for plugin %s" % plugin)
            
        self.plugin_cls[plugin.name] = plugin

    def setup(self):
        self.webhook = NebHookServer(8500)
        self.webhook.daemon = True
        self.webhook.start()
        
        # init the plugins
        for cls_name in self.plugin_cls:
            self.plugins[cls_name] = self.plugin_cls[cls_name](self, None, self.webhook)

        sync = self.initial_sync()
        log.debug("Notifying plugins of initial sync results")
        for plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            plugin.on_sync(sync)

            # see if this plugin needs a webhook
            if plugin.get_webhook_key():
                self.webhook.set_plugin(plugin.get_webhook_key(), plugin)

    def _help(self):
        body = ("Installed plugins: %s - Type '%shelp <plugin_name>' for more." % 
            (self.plugins.keys(), Matrix.PREFIX))
        return [self._body(body)]

    def _body(self, text):
        return {
            "msgtype": "m.text",
            "body": text
        }

    def parse_membership(self, event):
        log.info("Parsing membership: %s", event)
        if event["state_key"] == self.config.user_id and event["content"]["membership"] == "invite":
            user_id = event["user_id"]
            if user_id in self.config.admins:
                self.join_room(event["room_id"])
            else:
                log.info("Refusing invite, %s not in admin list. Event: %s", user_id, event)

    def parse_msg(self, event):
        body = event["content"]["body"]
        if event["user_id"] == self.config.user_id:
            return
        if body.startswith(Matrix.PREFIX):
            room = event["room_id"]
            try:
                segments = body.split()
                cmd = segments[0][1:]
                if cmd == "help":
                    if len(segments) == 2 and segments[1] in self.plugins:
                        # return help on a plugin
                        self.send_message(
                            room, 
                            self._body(self.plugins[segments[1]].__doc__)
                        )
                    else:
                        # return generic help
                        for help_msg in self._help():
                            self.send_message(room, help_msg)
                elif cmd in self.plugins:
                    plugin = self.plugins[cmd]
                    responses = None
                    
                    try:
                        responses = plugin.run(event, unicode(" ".join(body.split()[1:]).encode("utf8")))
                    except CommandNotFoundError as e:
                        self.send_message(room, self._body(str(e)))
                        
                    if responses:
                        log.debug("[Plugin-%s] Response => %s", cmd, responses)
                        if type(responses) == list:
                            for res in responses:
                                if type(res) in [str, unicode]:
                                    self.send_message(room, self._body(res))
                                else:
                                    self.send_message(room, res)
                        elif type(responses) in [str, unicode]:
                            self.send_message(room, self._body(responses))
                        else:
                            self.send_message(room, responses)
            except NebError as ne:
                self.send_message(room, self._body(ne.as_str()))
            except Exception as e:
                log.exception(e)
                self.send_message(room, self._body("Fatal error when processing command."))
        elif body.lower() == "neb?":
            self.send_message(
                event["room_id"],
                self._body("N E Bot v0.1.0 - Type !help to begin. Type !help <command> for help on a command."))
        else:
            try:
                for p in self.plugins:
                    self.plugins[p].on_msg(event, body)
            except Exception as e:
                log.exception(e)

    def event_proc(self, event):
        etype =  event["type"]
        switch = {
            "m.room.member": self.parse_membership,
            "m.room.message": self.parse_msg
        }
        try:
            switch[etype](event)
        except KeyError:
            try:
                for p in self.plugins:
                    self.plugins[p].on_event(event, etype)
            except Exception as e:
                log.exception(e)
        except Exception as e:
            log.error("Couldn't process event: %s", e)

    def event_loop(self):
        end = "END"
        while True:
            url = self._url("/events", {"timeout": 30000, "from": end})
            j= self._open(url)
            end = j["end"]
            events = j["chunk"]
            log.debug("Received: %s", events)
            for event in events:
                self.event_proc(event)
