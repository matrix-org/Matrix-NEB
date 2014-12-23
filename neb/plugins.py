# TODO:
# Add @admin_only decorator; execute_cmd needs Context
# Add @help decorator; self.cmd_help {} for NebPlugin?


class NebPlugin(object):

    def __init__(self):
        self.cmds = {}

    def execute_cmd(self, args_array):
        if len(args_array) == 0 or args_array[0] not in self.cmds:
            raise Exception("Unknown command.")

        return self.cmds[args_array[0]](args_array[1:])
        
        
class Plugin(NebPlugin):
    
    def execute_cmd(self, args_array):
        if len(args_array) == 0:
            raise Exception("Empty array")
            
        # Structure is cmd_foo_bar_baz for "!foo bar baz"
        # This starts by assuming a no-arg cmd then getting progressively
        # more general until no args remain (in which case there isn't a match)
        for index, arg in enumerate(args_array):
            possible_method = "cmd_" + "_".join(args_array[:(len(args_array) - index)])
            if hasattr(self, possible_method):
                method = getattr(self, possible_method)
                remaining_args = args_array[len(args_array) - index:]
                if remaining_args:
                    return method(remaining_args)
                else:
                    return method()
        
        raise Exception("Unknown command")
        
        
class FooPlugin(Plugin):

    def cmd_jira_create(self, name):
        print "jira create %s" % name
        
    def cmd_jira_create_oldstyle(self, old):
        print "jira create oldstyle %s" % old
        
    def cmd_jira(self, *args):
        print "jira"
        
    def cmd_jira_version(self):
        print "jira version"
        

class BarPlugin(NebPlugin):

    def __init__(self):
        self.cmds = {
            "make": self.make,
            "do": self.do
        }
        
    def make(self, args):
        print "make %s" % args
        
    def do(self, args):
        print "do %s" % args
                    
class TopLevel(object):

    def __init__(self):
        self.plugins = {
            "bar": BarPlugin(),
            "foo": FooPlugin()
        }
        
    def execute_cmd(self, args_array):
        if len(args_array) == 0:
            raise Exception("Empty array")
            
        if args_array[0] in self.plugins:
            return self.plugins[args_array[0]].execute_cmd(args_array[1:])
            
        raise Exception("Unknown plugin")
        
