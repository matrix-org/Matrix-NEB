#!/usr/bin/env python
import argparse
import getpass
import json

from neb.matrix import Matrix, MatrixConfig
from plugins.tumblr import TumblrPlugin
from plugins.b64 import Base64Plugin
from plugins.guess_number import GuessNumberPlugin
from plugins.jenkins import JenkinsPlugin
from plugins.jira import JiraPlugin
from plugins.url import UrlPlugin
from plugins.github import GithubPlugin

import logging
import time

log = logging.getLogger(name=__name__)

# TODO:
# - Allow multiple users in one NEB process. Particularly important when rate limiting kicks in. Plugins already
#   support this because they just operate on the matrix instance given to them.
# - Async requests in plugins PREASE
# - Add utility plugins in neb package to do things like "invite x to room y"?
# - Add other plugins as tests of plugin architecture (e.g. anagrams, dictionary lookup, etc)

# Tumblr specific:
# - Use JSON not XML. Consider using api v2 (though requires oauth key annoyingly)
# - Send actual images, not just links!!! Implement ALL THE CONFIG OPTIONS.
# - Tumblr config needs a private_rooms key for people who duplicate public #channels so they don't clash.


def generate_config(url, username, token, config_loc):
    config = MatrixConfig(
            hs_url=url,
            user_id=username,
            access_token=token,
            admins=[]
    )
    save_config(config_loc, config)
    return config


def save_config(loc, config):
    with open(loc, 'w') as f:
        MatrixConfig.to_file(config, f)


def load_config(loc):
    try:
        with open(loc, 'r') as f:
            return MatrixConfig.from_file(f)
    except:
        pass


def configure_logging(logfile):
    log_format = "%(asctime)s %(levelname)s: %(message)s"
    if logfile:
        logging.basicConfig(
            filename=args.log,
            level=logging.DEBUG,
            format=log_format
        )
        # also log to console
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        formatter = logging.Formatter(log_format)
        console.setFormatter(formatter)
        logging.getLogger('').addHandler(console)
    else:
        logging.basicConfig(
            level=6,
            format=log_format
        )


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
        JenkinsPlugin(),
    ]

    for plugin in plugins:
        matrix.add_plugin(plugin)

    matrix.setup()

    while True:
        try:
            log.info("Listening for incoming events.")
            matrix.event_loop()
        except Exception as e:
            log.error("Ruh roh: %s", e)
        time.sleep(5)

    log.info("Terminating.")


if __name__ == '__main__':
    a = argparse.ArgumentParser("Runs NEB. See plugins for commands.")
    a.add_argument(
        "-c", "--config", dest="config",
        help="The config to create or read from."
    )
    a.add_argument(
        "-l", "--log-file", dest="log",
        help="Log to this file."
    )
    args = a.parse_args()

    configure_logging(args.log)

    config = None
    if args.config:
        log.info("Loading config from %s", args.config)
        config = load_config(args.config)
        if not config:
            log.info("Setting up for an existing account.")
            print "Config file could not be loaded."
            print "NEB works with an existing Matrix account. Please set up an account for NEB if you haven't already.'"
            print "The config for this account will be saved to '%s'" % args.config
            hsurl = raw_input("Home server URL (e.g. http://localhost:8008): ").strip()
            if hsurl.endswith("/"):
                hsurl = hsurl[:-1]
            hsurl = hsurl + "/_matrix/client/api/v1" # v1 compatibility
            username = raw_input("Full user ID (e.g. @user:domain): ").strip()
            token = raw_input("Access token: ").strip()
            config = generate_config(hsurl, username, token, args.config)
    else:
        a.print_help()
        print "You probably want to run 'python neb.py -c neb.config'"

    if config:
        main(config)



