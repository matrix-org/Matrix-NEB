# Notes:
# matrix_endpoint
#   listen_for(["event.type", "event.type"])
# web_hook_server
#   register_hook("name", cb_fn)
# matrix_api
#   send_event(foo, bar)
#   send_message(foo, bar)

import inspect
import json
import re
import shlex

import logging as log


def admin_only(fn):
    def wrapped(*args, **kwargs):
        matrix = args[0].matrix
        event = args[1]
        if event["user_id"] not in matrix.config.admins:
            return "Sorry, only %s can do that." % json.dumps(matrix.config.admins)
        result = fn(*args, **kwargs)
        return result
    return wrapped


class CommandNotFoundError(Exception):
    pass


class PluginInterface(object):

    def __init__(self, matrix_api, matrix_endpoint, web_hook_server):
        self.matrix = matrix_api
        self.endpoint = matrix_endpoint

    def run(self, event, arg_str):
        pass

    def on_sync(self, response):
        pass

    def on_event(self, event, etype):
        pass

    def on_msg(self, event, body):
        pass

    def get_webhook_key(self):
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


class Plugin(PluginInterface):

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

    # =========================

    def run(self, event, arg_str):
        args_array = shlex.split(arg_str.encode("utf8"))
        if len(args_array) == 0:
            raise CommandNotFoundError(self.__doc__)

        # Structure is cmd_foo_bar_baz for "!foo bar baz"
        # This starts by assuming a no-arg cmd then getting progressively
        # more general until no args remain (in which case there isn't a match)
        for index, arg in enumerate(args_array):
            possible_method = "cmd_" + "_".join(args_array[:(len(args_array) - index)])
            if hasattr(self, possible_method):
                method = getattr(self, possible_method)
                remaining_args = [event] + args_array[len(args_array) - index:]

                # function params prefixed with "opt_" should be None if they
                # are not specified. This makes cmd definitions a lot nicer for
                # plugins rather than a generic arg array or no optional extras
                fn_param_names = inspect.getargspec(method)[0][1:]  # remove self
                if len(fn_param_names) > len(remaining_args):
                    # pad out the ones at the END marked "opt_" with None
                    for i in reversed(fn_param_names):
                        if i.startswith("opt_"):
                            remaining_args.append(None)
                        else:
                            break

                try:
                    if remaining_args:
                        return method(*remaining_args)
                    else:
                        return method()
                except TypeError as e:
                    log.exception(e)
                    raise CommandNotFoundError(method.__doc__)

        raise CommandNotFoundError("Unknown command")


