#!/usr/bin/env python
import json


class MatrixConfig(object):
    URL = "url"
    USR = "user"
    TOK = "token"
    ADM = "admins"
    CIS = "case_insensitive"

    def __init__(self, hs_url, user_id, access_token, admins, case_insensitive):
        self.user_id = user_id
        self.token = access_token
        self.base_url = hs_url
        self.admins = admins
        self.case_insensitive = case_insensitive

    @classmethod
    def to_file(cls, config, f):
        f.write(json.dumps({
            MatrixConfig.URL: config.base_url,
            MatrixConfig.TOK: config.token,
            MatrixConfig.USR: config.user_id,
            MatrixConfig.ADM: config.admins,
            MatrixConfig.CIS: config.case_insensitive
        }, indent=4))

    @classmethod
    def from_file(cls, f):
        j = json.load(f)
        return MatrixConfig(
            hs_url=j[MatrixConfig.URL],
            user_id=j[MatrixConfig.USR],
            access_token=j[MatrixConfig.TOK],
            admins=j[MatrixConfig.ADM],
            case_insensitive=j[MatrixConfig.CIS] if MatrixConfig.CIS in j else False
        )
