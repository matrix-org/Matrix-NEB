from neb import NebError
from neb.plugins import CommandNotFoundError
from neb.webhook import NebHookServer

import json
import logging as log


class Engine(object):
    """Orchestrates plugins and the matrix API/endpoints."""
    PREFIX = "!"

    def __init__(self, matrix_api):
        self.plugin_cls = {}
        self.plugins = {}
        self.matrix = matrix_api

    def setup(self):
        self.webhook = NebHookServer(8500)
        self.webhook.daemon = True
        self.webhook.start()

        # init the plugins
        for cls_name in self.plugin_cls:
            self.plugins[cls_name] = self.plugin_cls[cls_name](
                self.matrix,
                self.webhook
            )

        sync = self.matrix.initial_sync()
        log.debug("Notifying plugins of initial sync results")
        for plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            plugin.on_sync(sync)

            # see if this plugin needs a webhook
            if plugin.get_webhook_key():
                self.webhook.set_plugin(plugin.get_webhook_key(), plugin)

    def _help(self):
        body = (
            "Installed plugins: %s - Type '%shelp <plugin_name>' for more." %
            (self.plugins.keys(), Engine.PREFIX)
        )
        return [self.matrix._body(body)]

    def add_plugin(self, plugin):
        log.debug("add_plugin %s", plugin)
        if not plugin.name:
            raise NebError("No name for plugin %s" % plugin)

        self.plugin_cls[plugin.name] = plugin

    def parse_membership(self, event):
        log.info("Parsing membership: %s", event)
        if (event["state_key"] == self.matrix.config.user_id
                and event["content"]["membership"] == "invite"):
            user_id = event["user_id"]
            if user_id in self.matrix.config.admins:
                self.matrix.join_room(event["room_id"])
            else:
                log.info(
                    "Refusing invite, %s not in admin list. Event: %s",
                    user_id, event
                )

    def parse_msg(self, event):
        body = event["content"]["body"]
        if event["user_id"] == self.matrix.config.user_id:
            return
        if body.startswith(Engine.PREFIX):
            room = event["room_id"]
            try:
                segments = body.split()
                cmd = segments[0][1:]
                if cmd == "help":
                    if len(segments) == 2 and segments[1] in self.plugins:
                        # return help on a plugin
                        self.matrix.send_message(
                            room,
                            self.matrix._body(self.plugins[segments[1]].__doc__)
                        )
                    else:
                        # return generic help
                        for help_msg in self._help():
                            self.matrix.send_message(room, help_msg)
                elif cmd in self.plugins:
                    plugin = self.plugins[cmd]
                    responses = None

                    try:
                        responses = plugin.run(
                            event,
                            unicode(" ".join(body.split()[1:]).encode("utf8"))
                        )
                    except CommandNotFoundError as e:
                        self.matrix.send_message(
                            room,
                            self.matrix._body(str(e))
                        )

                    if responses:
                        log.debug("[Plugin-%s] Response => %s", cmd, responses)
                        if type(responses) == list:
                            for res in responses:
                                if type(res) in [str, unicode]:
                                    self.matrix.send_message(
                                        room,
                                        self.matrix._body(res)
                                    )
                                else:
                                    self.matrix.send_message(room, res)
                        elif type(responses) in [str, unicode]:
                            self.matrix.send_message(
                                room,
                                self.matrix._body(responses)
                            )
                        else:
                            self.matrix.send_message(room, responses)
            except NebError as ne:
                self.matrix.send_message(room, self.matrix._body(ne.as_str()))
            except Exception as e:
                log.exception(e)
                self.matrix.send_message(
                    room,
                    self.matrix._body("Fatal error when processing command.")
                )
        else:
            try:
                for p in self.plugins:
                    self.plugins[p].on_msg(event, body)
            except Exception as e:
                log.exception(e)

    def event_proc(self, event):
        etype = event["type"]
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
            url = self.matrix._url("/events", {"timeout": 30000, "from": end})
            j = self.matrix._open(url)
            end = j["end"]
            events = j["chunk"]
            log.debug("Received: %s", events)
            for event in events:
                self.event_proc(event)


class RoomContextStore(object):
    """Stores state events for rooms."""

    def __init__(self, event_types):
        """Init the store.

        Args:
            event_types(list<str>): The state event types to store.
        """
        self.state = {}
        self.types = event_types

    def init_from_sync(self, sync):
        for room in sync["rooms"]:
            # see if we know anything about these rooms
            room_id = room["room_id"]
            if room["membership"] != "join":
                continue

            self.state[room_id] = {}

            try:
                for state in room["state"]:
                    if state["type"] in self.types:
                        key = (state["type"], state["state_key"])
                        self.state[room_id][key] = state
            except KeyError:
                pass

        log.debug(json.dumps(self.state, indent=4))


class KeyValueStore(object):
    """A persistent JSON store."""

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
