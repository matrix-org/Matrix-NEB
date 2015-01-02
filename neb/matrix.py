#!/usr/bin/env python
import json
import re
import urllib
import urllib2
from urllib2 import Request

from neb import NebError


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

    def __init__(self, config):
        self.config = config

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
        url = self._url(
            "/rooms/%s/%s/%s" % (
                urllib.quote(room_id),
                urllib.quote(state_path),
                urllib.quote(event_type)
            )
        )
        return self._open(url, content, as_PUT=state)

    def join_room(self, room_id):
        url = self._url("/join/%s" % urllib.quote(room_id))
        self._open(url, {})

    def invite_user(self, room_id, user_id):
        log.debug("Inviting %s to %s", user_id, room_id)
        url = self._url("/rooms/%s/invite" % urllib.quote(room_id))
        return self._open(url, {"user_id": user_id})

    def _body(self, text):
        return {
            "msgtype": "m.text",
            "body": text
        }

    def _rich_body(self, html):
        return {
            "body": re.sub('<[^<]+?>', '', html),
            "msgtype": "m.text",
            "format": "org.matrix.custom.html",
            "formatted_body": html
        }
