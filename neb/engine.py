"""Defines the interfaces for plugins."""
from collections import namedtuple
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
    
    
    def sync(self, matrix, initial_sync):
        """Configure yourself from the initial sync and use the given matrix for requests.
        
        Args:
            matrix (neb.Matrix): The matrix object to make requests from.
            initial_sync (event): The result of GET /initialSync
        """
        pass
        
    def _body(self, text):
        return { 
            "msgtype": "m.text",
            "body": text
        }
    