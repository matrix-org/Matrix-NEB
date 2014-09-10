N E Bot
=======

This is a generic client bot for Matrix which supports plugins.

Setup
=====
First time:

    python neb.py -r <username> -u <home server url>
  
Subsequent times:

    python neb.py -c <config location>
    
Create a room and invite NEB to it, and then type ``!help`` for a list of valid commands.


Plugins
=======

Tumblr
------
 - Support via Tumblr API v1
 - TODO: v2 support, using JSON not XML. Proper image support. Get entire state from rooms. Support extra options as described in help.

RSS Feeds
---------
 - WIP

Digg
----
 - WIP

Reddit
------
 - WIP
