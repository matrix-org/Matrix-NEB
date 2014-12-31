from __future__ import absolute_import
from neb.plugins import Plugin

import calendar
import datetime
import time
from dateutil import parser


class TimePlugin(Plugin):
    """Encodes and decodes timestamps.
    time encode <date> : Encode <date> as a unix timestamp.
    time decode <unix timestamp> : Decode the unix timestamp and return the date.
    """

    name="time"

    def cmd_encode(self, event, *args):
        """Encode a time. Multiple different formats are supported, e.g. YYYY-MM-DD HH:MM:SS 'time encode <date>'"""
        # use the body directly so spaces are handled correctly.
        date_str = event["content"]["body"][len("!time encode "):]
        
        if date_str.lower().strip() == "now":
            now = time.time()
            return "Parsed as %s\n%s" % (datetime.datetime.utcfromtimestamp(now), now)
        
        try:
            d = parser.parse(date_str)
            ts = calendar.timegm(d.timetuple())
            return "Parsed as %s\n%s" % (d.strftime("%Y-%m-%d %H:%M:%S"), ts)
        except ValueError:
            return "Failed to parse '%s'" % date_str

    def cmd_decode(self, event, timestamp):
        """Decode from a unix timestamp. 'time decode <timestamp>'"""
        is_millis = len(timestamp) > 10
        try:
            ts = int(timestamp)
            if is_millis:
                return datetime.datetime.utcfromtimestamp(ts/1000.0).strftime("%Y-%m-%d %H:%M:%S.%f")
            else:
                return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return "Failed to parse '%s'" % timestamp

