# -*- coding: utf-8 -*-
from jinja2 import Template
import json
from matrix_client.api import MatrixRequestError
from neb.engine import KeyValueStore, RoomContextStore
from neb.plugins import Plugin, admin_only
from Queue import PriorityQueue
from threading import Thread


import time
import logging as log
import random

queue = PriorityQueue()


class PrometheusPlugin(Plugin):
    """Plugin for interacting with Prometheus.
    """
    name = "prometheus"

    #Webhooks:
        #    /neb/prometheus
    TYPE_TRACK = "org.matrix.neb.plugin.prometheus.projects.tracking"
    TYPE_COLOR = "org.matrix.neb.plugin.prometheus.projects.color"

    TRACKING = ["track", "tracking"]

    def __init__(self, *args, **kwargs):
        super(PrometheusPlugin, self).__init__(*args, **kwargs)
        self.store = KeyValueStore("prometheus.json")
        self.rooms = RoomContextStore(
            [PrometheusPlugin.TYPE_TRACK]
        )
        self.queue_counter = 1L
        self.consumer = MessageConsumer(self.matrix)
        self.consumer.daemon = True
        self.consumer.start()

    def on_receive_message(self, info):
        log.info("recv %s", info)
        template = Template(self.store.get("message_template"))
        for alert in info["alert"]:
            for room_id in self.rooms.get_room_ids():
                log.debug("queued message for room " + room_id + " at " + str(self.queue_counter) + ": %s", alert)
                queue.put((self.queue_counter, room_id, template.render(alert)))

    def cmd_show(self, event, action):
        """Plugin to report prometheus alerts, the message temlate is represented in prometheus.json
        change when the prometheus message interface is changed.
        """
        pass

    @admin_only
    def cmd_track(self, event, *args):
        pass

    def _send_track_event(self, room_id, project_names):
        pass

    def _get_tracking(self, room_id):
        pass

    def on_event(self, event, event_type):
        self.rooms.update(event)

    def on_sync(self, sync):
        log.debug("Plugin: Prometheus sync state:")
        self.rooms.init_from_sync(sync)

    def get_webhook_key(self):
        return "prometheus"

    def on_receive_webhook(self, url, data, ip, headers):
        json_data = json.loads(data)
        self.on_receive_message(json_data)


class MessageConsumer(Thread):
    INITIAL_TIMEOUT = 5
    TIMEOUT_INCREMENT = 5
    MAX_TIMEOUT = 60 * 5

    def __init__(self, matrix):
        super(MessageConsumer, self).__init__()
        self.matrix = matrix

    def run(self):
        timeout = self.INITIAL_TIMEOUT

        log.debug("Starting consumer thread")
        while True:
            priority, room_id, message = queue.get()
            log.debug("Popped message for room " + room_id + " at position " + str(priority) + ": %s", message)
            try:
                self.send_message(room_id, message)
                timeout = self.INITIAL_TIMEOUT
            except Exception as e:
                log.debug("Failed to send message: %s", e)
                queue.put((priority, room_id, message))

                time.sleep(timeout)
                timeout += self.TIMEOUT_INCREMENT
                if timeout > self.MAX_TIMEOUT:
                    timeout = self.MAX_TIMEOUT

    def send_message(self, room_id, message):
        try:
            self.matrix.send_message_event(
                    room_id,
                    "m.room.message",
                    self.matrix.get_html_body(message, msgtype="m.notice"),
            )
        except KeyError:
            log.error(KeyError)
        except MatrixRequestError as e:
            if 400 <= e.code < 500:
                log.error("Matrix ignored message %s", e)
            else:
                raise
