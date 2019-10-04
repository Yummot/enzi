# -*- coding: utf-8 -*-

import semver
import re



class VersionReq(object):
    """
    verisonReq containing a list of predicates that can apply to find a matched version
    """
    def __init__(self, req_str: str):
        self.req_str: str = req_str
