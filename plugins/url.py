from neb.engine import Plugin, Command

import urllib


class UrlPlugin(Plugin):

    def get_commands(self):
        """Return human readable commands with descriptions.

        Returns:
            list[Command]
        """
        return [
            Command("urlencode", self.encode, "URL encode some text.", []),
            Command("urldecode", self.decode, "URL decode some text.", [])
        ]

    def encode(self, event, args):
        content = ' '.join(args[1:])
        return self._body(urllib.quote(content))

    def decode(self, event, args):
        content = ' '.join(args[1:])
        return self._body(urllib.unquote(content))

    def _error(self, value):
        return self._body("Cannot convert %s" % (value))

    def sync(self, matrix, initial_sync):
        pass

