from matrix_client.api import MatrixRequestError
from neb import NebError
from neb.plugins import CommandNotFoundError
from neb.webhook import NebHookServer

import json
import logging as log
import pprint


class Engine(object):
    """Orchestrates plugins and the matrix API/endpoints."""
    PREFIX = "!"

    def __init__(self, matrix_api, config):
        self.plugin_cls = {}
        self.plugins = {}
        self.config = config
        self.matrix = matrix_api
        self.sync_token = None  # set later by initial sync

    def setup(self):
        self.webhook = NebHookServer(8500)
        self.webhook.daemon = True
        self.webhook.start()

        # init the plugins
        for cls_name in self.plugin_cls:
            self.plugins[cls_name] = self.plugin_cls[cls_name](
                self.matrix,
                self.config,
                self.webhook
            )

        sync = self.matrix.sync(timeout_ms=30000, since=self.sync_token)
        self.parse_sync(sync, initial_sync=True)
        log.debug("Notifying plugins of initial sync results")
        for plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            plugin.on_sync(sync)

            # see if this plugin needs a webhook
            if plugin.get_webhook_key():
                self.webhook.set_plugin(plugin.get_webhook_key(), plugin)

    def _help(self):
        return (
            "Installed plugins: %s - Type '%shelp <plugin_name>' for more." %
            (self.plugins.keys(), Engine.PREFIX)
        )

    def add_plugin(self, plugin):
        log.debug("add_plugin %s", plugin)
        if not plugin.name:
            raise NebError("No name for plugin %s" % plugin)

        self.plugin_cls[plugin.name] = plugin

    def parse_membership(self, event):
        log.info("Parsing membership: %s", event)
        if (event["state_key"] == self.config.user_id
                and event["content"]["membership"] == "invite"):
            user_id = event["sender"]
            if user_id in self.config.admins:
                self.matrix.join_room(event["room_id"])
            else:
                log.info(
                    "Refusing invite, %s not in admin list. Event: %s",
                    user_id, event
                )

    def parse_msg(self, event):
        body = event["content"]["body"]
        if (event["sender"] == self.config.user_id or
                event["content"]["msgtype"] == "m.notice"):
            return
        if body.startswith(Engine.PREFIX):
            room = event["room_id"]  # room_id added by us
            try:
                segments = body.split()
                cmd = segments[0][1:]
                if self.config.case_insensitive:
                    cmd = cmd.lower()

                if cmd == "help":
                    if len(segments) == 2 and segments[1] in self.plugins:
                        # return help on a plugin
                        self.matrix.send_message(
                            room,
                            self.plugins[segments[1]].__doc__,
                            msgtype="m.notice"
                        )
                    else:
                        # return generic help
                        self.matrix.send_message(room, self._help(), msgtype="m.notice")
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
                            str(e),
                            msgtype="m.notice"
                        )
                    except MatrixRequestError as ex:
                        self.matrix.send_message(
                            room,
                            "Problem making request: (%s) %s" % (ex.code, ex.content),
                            msgtype="m.notice"
                        )

                    if responses:
                        log.debug("[Plugin-%s] Response => %s", cmd, responses)
                        if type(responses) == list:
                            for res in responses:
                                if type(res) in [str, unicode]:
                                    self.matrix.send_message(
                                        room,
                                        res,
                                        msgtype="m.notice"
                                    )
                                else:
                                    self.matrix.send_message_event(
                                        room, "m.room.message", res
                                    )
                        elif type(responses) in [str, unicode]:
                            self.matrix.send_message(
                                room,
                                responses,
                                msgtype="m.notice"
                            )
                        else:
                            self.matrix.send_message_event(
                                room, "m.room.message", responses
                            )
            except NebError as ne:
                self.matrix.send_message(room, ne.as_str(), msgtype="m.notice")
            except Exception as e:
                log.exception(e)
                self.matrix.send_message(
                    room,
                    "Fatal error when processing command.",
                    msgtype="m.notice"
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
        while True:
            j = self.matrix.sync(timeout_ms=30000, since=self.sync_token)
            self.parse_sync(j)

    def parse_sync(self, sync_result, initial_sync=False):
        self.sync_token = sync_result["next_batch"]  # for when we start syncing

        # check invited rooms
        rooms = sync_result["rooms"]["invite"]
        for room_id in rooms:
            events = rooms[room_id]["invite_state"]["events"]
            self.process_events(events, room_id)

        # return early if we're performing an initial sync (ie: don't parse joined rooms, just drop the state)
        if initial_sync:
            return

        # check joined rooms
        rooms = sync_result["rooms"]["join"]
        for room_id in rooms:
            events = rooms[room_id]["timeline"]["events"]
            self.process_events(events, room_id)

    def process_events(self, events, room_id):
        for event in events:
            event["room_id"] = room_id
            self.event_proc(event)


class RoomContextStore(object):
    """Stores state events for rooms."""

    def __init__(self, event_types, content_only=True):
        """Init the store.

        Args:
            event_types(list<str>): The state event types to store.
            content_only(bool): True to only store the content for state events.
        """
        self.state = {}
        self.types = event_types
        self.content_only = content_only

    def get_content(self, room_id, event_type, key=""):
        if self.content_only:
            return self.state[room_id][(event_type, key)]
        else:
            return self.state[room_id][(event_type, key)]["content"]

    def get_room_ids(self):
        return self.state.keys()

    def update(self, event):
        try:
            room_id = event["room_id"]
            etype = event["type"]
            if etype in self.types:
                if room_id not in self.state:
                    self.state[room_id] = {}
                key = (etype, event["state_key"])

                s = event
                if self.content_only:
                    s = event["content"]

                self.state[room_id][key] = s
        except KeyError:
            pass

    def init_from_sync(self, sync):
        for room_id in sync["rooms"]["join"]:
            # see if we know anything about these rooms
            room = sync["rooms"]["join"][room_id]

            self.state[room_id] = {}

            try:
                for state in room["state"]["events"]:
                    if state["type"] in self.types:
                        key = (state["type"], state["state_key"])

                        s = state
                        if self.content_only:
                            s = state["content"]

                        self.state[room_id][key] = s
            except KeyError:
                pass

        log.debug(pprint.pformat(self.state))


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
