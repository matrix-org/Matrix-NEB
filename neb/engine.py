"""Defines the interfaces for plugins."""
from collections import namedtuple
from . import NebError

import BaseHTTPServer
import json
import threading
import urllib

# Native.Extraction.Bot

Command = namedtuple("Command", 'cmd func summary help_list')


class Plugin(object):

    def open(self, url, content=None):
        print "[Plugin]url >>> %s  >>>> %s" % (url, content)
        response = urllib.urlopen(url, data=content)
        if response.code != 200:
            raise NebError("Request to %s failed: %s" % (url, response.code))
        return response.read()

    def get_commands(self):
        """Return human readable commands with descriptions.

        Returns:
            list[Command]
        """
        return []

    def get_webhook_key(self):
        """ Return the path to receive webhook events, or nothing if you don't
        require a webhook."""
        pass

    def on_receive_webhook(self, data, ip, headers):
        """Someone hit your webhook.

        Args:
            data(str): The request body
            ip(str): The source IP address
            headers: A dict of headers (via .get("headername"))
        Returns:
            A tuple of (response_body, http_status_code, header_dict) or None
            to return a 200 OK. Raise an exception to return a 500.
        """
        pass

    def sync(self, matrix, initial_sync):
        """Configure yourself from the initial sync and use the given matrix for requests.

        Args:
            matrix (neb.Matrix): The matrix object to make requests from.
            initial_sync (event): The result of GET /initialSync
        """
        pass

    def on_msg(self, event, body):
        """An m.room.message has been received which isn't a command.
        '"""
        pass

    def on_event(self, event, event_type):
        """A random event has come down the stream."""
        pass

    def _body(self, text):
        return {
            "msgtype": "m.text",
            "body": text
        }


class KeyValueStore(object):

    def __init__(self, config_loc, version="1"):
        self.config = {
            "version": version
        }
        self.config_loc = config_loc
        self._load()

    def _load(self):
        try:
            with open(self.config_loc, 'r') as f:
                self.config = json.loads(f.read())
        except:
            self._save()

    def _save(self):
        with open(self.config_loc, 'w') as f:
            f.write(json.dumps(self.config, indent=4))

    def has(self, key):
        return key in self.config

    def set(self, key, value, save=True):
        self.config[key] = value
        if save:
            self._save()

    def get(self, key):
        return self.config[key]
