# -*- coding: utf-8 -*-
import requests


class MatrixHttpApi(object):
    """Contains all raw Matrix HTTP Client-Server API calls.

    Usage:
        matrix = MatrixApi("https://matrix.org", token="foobar")
        response = matrix.initial_sync()
        response = matrix.send_message("!roomid:matrix.org", "Hello!")

    For room and sync handling, consider using MatrixClient.
    """

    def __init__(self, base_url, token=None):
        self.url = base_url
        self.token = token

    def initial_sync(self):
        pass

