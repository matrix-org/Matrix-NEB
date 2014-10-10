N E Bot
=======

This is a generic client bot for Matrix which supports plugins.

Setup
=====
First time (you'll be prompted where to store the generated config file):

    python neb.py -r <username> -u <home server url>
  
Subsequent times:

    python neb.py -c <config location>
    
Create a room and invite NEB to it, and then type ``!help`` for a list of valid commands.


Plugins
=======

Github
------
 - Processes webhook requests and send messages to interested rooms.
 - Supports secret token HMAC authentication.
 - Supported events: ``push``, ``create``, ``ping``, ``pull_request``
 
Jenkins
-------
 - Sends build failure messages to interested rooms.
 - Support via the Notification plugin.
 - Supports shared secret authentication.

JIRA
----
 - Processes webhook requests and sends messages to interested rooms.
 - Resolves JIRA issue IDs into one-line summaries as they are mentioned by other people.

Guess Number
------------
 - Basic guess-the-number game.

URL
---
 - Provides URL encoding/decoding.

B64
---
 - Provides base64 encoding/decoding.

Tumblr
------
 - Sends tumblr posts for Tumblr users to interested rooms.
 - Unstable, WIP.
