from neb.engine import Plugin, Command

import base64

class Base64Plugin(Plugin):

    def get_commands(self):
        """Return human readable commands with descriptions.
        
        Returns:
            list[Command]
        """
        return [
            Command("b64encode", self.encode, "Encode as base64.", []),
            Command("b64decode", self.decode, "Decode from base64.", [])
        ]
    
    def encode(self, event, args):
        content = ' '.join(args[1:])
        return self._body(base64.b64encode(content))
        
    def decode(self, event, args):
        content = ' '.join(args[1:])
        return self._body(base64.b64decode(content))
            
    def _error(self, value):
        return self._body("Cannot convert %s" % (value))
    
    
    def sync(self, matrix, initial_sync):
        pass
            
                