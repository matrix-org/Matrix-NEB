# -*- coding: utf-8 -*-
"""Devoted to services which use web hooks. Plugins are identified via the
path being hit, which then delegates to the plugin to process.
"""
from flask import Flask
from flask import request
import threading

import logging as log

app = Flask("NebHookServer")


class NebHookServer(threading.Thread):

    def __init__(self, port):
        super(NebHookServer, self).__init__()
        self.port = port
        self.plugin_mappings = {
        #    plugin_key : plugin_instance
        }

        app.add_url_rule('/neb/<path:service>', '/neb/<path:service>',
                         self.do_POST, methods=["POST"])

    def set_plugin(self, key, plugin):
        log.info("Registering plugin %s for webhook on /neb/%s" % (plugin, key))
        self.plugin_mappings[key] = plugin

    def do_POST(self, service=""):
        log.debug("NebHookServer: Plugin=%s : Incoming request from %s",
                  service, request.remote_addr)
        if service.split("/")[0] not in self.plugin_mappings:
            return ("", 404, {})

        plugin = self.plugin_mappings[service.split("/")[0]]

        try:
            # tuple (body, status_code, headers)
            response = plugin.on_receive_webhook(
                request.url,
                request.get_data(),
                request.remote_addr,
                request.headers
            )
            if response:
                return response
            return ("", 200, {})
        except Exception as e:
            log.exception(e)
            return ("", 500, {})

    def notify_plugin(self, content):
        self.plugin.on_receive_github_push(content)

    def run(self):
        log.info("Running NebHookServer")
        app.run(host="0.0.0.0", port=self.port)
