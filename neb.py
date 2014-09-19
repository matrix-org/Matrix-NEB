#!/usr/bin/env python
import argparse
import getpass
import json

from neb.matrix import Matrix, MatrixConfig
from plugins.tumblr import TumblrPlugin
from plugins.b64 import Base64Plugin
from plugins.guess_number import GuessNumberPlugin
from plugins.jira import JiraPlugin
from plugins.url import UrlPlugin
from plugins.github import GithubPlugin

import logging
import sys

logging.basicConfig(level=6)
log = logging.getLogger(name=__name__)

# TODO:
# - Allow multiple users in one NEB process. Particularly important when rate limiting kicks in. Plugins already
#   support this because they just operate on the matrix instance given to them.
# - Async requests in plugins PREASE
# - Make setting up accounts less confusing.
# - Add utility plugins in neb package to do things like "invite x to room y"?
# - Add other plugins as tests of plugin architecture (e.g. anagrams, dictionary lookup, etc)

# Tumblr specific:
# - Use JSON not XML. Consider using api v2 (though requires oauth key annoyingly)
# - Send actual images, not just links!!! Implement ALL THE CONFIG OPTIONS.
# - Tumblr config needs a private_rooms key for people who duplicate public #channels so they don't clash.


def generate_config(url, username, password):
    config = MatrixConfig(
            hs_url=url,
            user_id=username,
            access_token=None,
            password=password,
            admins=[]
    )
    m = Matrix(config)

    log.info("Registering user %s", username)
    response = m.register()
    config.user_id = response["user_id"]
    config.token = response["access_token"]

    fname = raw_input("Enter name of config file: ")
    log.info("Saving config to %s", fname)
    save_config(fname, config)
    return config


def save_config(loc, config):
    with open(loc, 'w') as f:
        MatrixConfig.to_file(config, f)


def load_config(loc):
    with open(loc, 'r') as f:
        return MatrixConfig.from_file(f)


def main(config):
    matrix = Matrix(config)

    log.debug("Setting up plugins...")
    plugins = [
    #    TumblrPlugin(),
        Base64Plugin(),
    #    GuessNumberPlugin(),
        JiraPlugin(),
        UrlPlugin(),
        GithubPlugin(),
    ]

    for plugin in plugins:
        matrix.add_plugin(plugin)

    matrix.setup()

    try:
        log.info("Listening for incoming events.")
        matrix.event_loop()

    except Exception as e:
        log.error("Ruh roh: %s", e)

    log.info("Terminating.")


if __name__ == '__main__':
    a = argparse.ArgumentParser("Runs NEB. See plugins for commands.")
    a.add_argument("-c", "--config", help="The config to read from.", dest="config")
    a.add_argument("-u", "--url", help="The home server url up to the version path e.g. localhost/_matrix/client/api/v1", dest="url")
    a.add_argument("-r", "--register", help="Register a new account as the specified username.", dest="register")
    args = a.parse_args()

    config = None
    if args.config:
        log.info("Loading config from %s", args.config)
        config = load_config(args.config)
    elif args.register and args.url:
        log.info("Creating config for user %s on home server %s", args.register, args.url)
        password = "_"
        password2 = "__"
        while password != password2:
            password = getpass.getpass("Enter a password for this new account: ")
            password2 = getpass.getpass("Reconfirm the password: ")

        config = generate_config(args.url, args.register, password)
    else:
        a.print_help()
        print "You probably want to run something like 'python neb.py -r neb -u \"http://localhost:8008/_matrix/client/api/v1\"'"
        print "After you make a config file, you probably want to run 'python neb.py -c CONFIG_NAME'"

    if config:
        main(config)



