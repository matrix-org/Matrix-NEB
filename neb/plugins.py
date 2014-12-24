# Notes:
# matrix_endpoint
#   listen_for(["event.type", "event.type"])
# web_hook_server
#   register_hook("name", cb_fn)
# matrix_api
#   send_event(foo, bar)
#   send_message(foo, bar)

import inspect
import re
import shlex
import urllib


def admin_only(fn):
    def wrapped(*args, **kwargs):
        print "admin only check -> %s" % args[0].matrix_api
        result = fn(*args, **kwargs)
        return result
    return wrapped


class CommandNotFoundError(Exception):
    pass


class PluginInterface(object):

    def __init__(self, matrix_api, matrix_endpoint, web_hook_server):
        self.matrix_api = matrix_api
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

    def open(self, url, content=None):
        log.debug("[Plugin]url >>> %s  >>>> %s" % (url, content))
        response = urllib.urlopen(url, data=content)
        if response.code != 200:
            raise NebError("Request to %s failed: %s" % (url, response.code))
        return response.read()

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
                    print e
                    raise CommandNotFoundError(method.__doc__)
        
        raise CommandNotFoundError("Unknown command")


class TopLevel(object):

    def __init__(self):
        web_hook = None
        matrix_api = None
        endpoint = None
        self.plugins = {
            "foo": FooPlugin(matrix_api, endpoint, web_hook),
            "boo": FooPlugin(matrix_api, endpoint, web_hook)
        }
        
    def run(self, arg_str):
        arg_tokens = arg_str.split()
        plugin_name = arg_tokens[0]
            
        if plugin_name in self.plugins:
            return self.plugins[plugin_name].run(" ".join(arg_tokens[1:]))
            
        raise CommandNotFoundError("Unknown plugin")
        
