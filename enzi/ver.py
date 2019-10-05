# -*- coding: utf-8 -*-
import enum
import logging
import re
import semver
import typing

logger = logging.getLogger(__name__)

PREFIX_REGEX = re.compile(
    r"""
    ^(?P<prefix0>(>=|<=|>|<|~|^))\s*(?P<req0>(.+?))
    ,?
    (\s*(?P<prefix1>(>=|<=|>|<|~|^))\s*(?P<req1>(.+?)))?$
    """, re.X)

VERSION_REGEX = re.compile(
    r"""
        ^
        (?P<major>(?:0|[1-9][0-9]*))
        \.
        (?P<minor>(?:0|[1-9][0-9]*))
        \.
        (?P<patch>(?:0|[1-9][0-9]*))
        (\-(?P<prerelease>
            (?:0|[1-9A-Za-z-][0-9A-Za-z-]*)
            (\.(?:0|[1-9A-Za-z-][0-9A-Za-z-]*))*
        ))?
        (\+(?P<build>
            [0-9A-Za-z-]+
            (\.[0-9A-Za-z-]+)*
        ))?
        $
        """, re.VERBOSE)


@enum.unique
class ReqOp(enum.Enum):
    Exact = 0
    Gt = 1  # >
    Ge = 2  # >=
    Lt = 3  # <
    Le = 4  # <=
    Tilde = 5  # ~
    Caret = 6  # ^
    # Note: currently no wildcard ReqOp is supported.
    # WildcardMajor = 7
    # WildcardMinor = 8
    # WildcardPatch = 9
    # def From(prefix_str: str):


# map the requests operations string into ReqOp
_REQ_OP_DICT = {
    ">": ReqOp.Gt,
    ">=": ReqOp.Ge,
    "<": ReqOp.Lt,
    "<=": ReqOp.Le,
    "~": ReqOp.Tilde,
    "^": ReqOp.Caret,
}


def into_req_op(op_str: str):
    if not op_str in _REQ_OP_DICT:
        raise ValueError("{} is not a valid version request operation".format(op_str))
    return _REQ_OP_DICT[op_str]


def match_reqs(reqs_str: str):
    """
    Match the requests string. 
    Extract the request operations and the possible version string
    """
    reqs = PREFIX_REGEX.match(reqs_str)
    reqs_dict = reqs.groupdict()
    
    if not reqs_dict['prefix0']:
        try:
            return semver.parse(reqs['req0'])
        except Exception:
            msg = "{} is not a valid version request string".format(reqs_str)
            logger.error(msg)
            raise ValueError(msg) from None


    # filter the non-exists groups
    f = filter(lambda x: x[1], reqs_dict.items())
    d = dict(f)

    ret = {}

    p = into_req_op(d['prefix0'])
    v = semver.parse(d['req0'])
    ret[p] = v
    
    # extra request operation
    if 'prefix1' in d:
        p = into_req_op(d['prefix1'])
        v = semver.parse(d['req1'])
        ret[p] = v

    return ret


class Predicate(object):
    def __init__(self, op, major, minor=None, patch=None, prerelease=None, build=None):
        self.op: ReqOp = op
        self.major: int = major
        self.minor: typing.Optional[int] = minor
        self.patch: typing.Optional[int] = patch
        self.pre: typing.Optional[str] = prerelease

    @staticmethod
    def loads_with_op(op, v_dict: dict):
        """
        Load from a dict which may contain version parts with ReqOp
        """
        return Predicate(op, **v_dict)

    def __str__(self):
        _vars = vars(self)
        return "Predicate{}".format(_vars)


class VerReqVaildator(object):
    """
    VerReqVaildator: Vaildate a version request string
    """
    # Multiple version requirements can be separated with a comma,
    # e.g., >= 1.2, < 1.5
    def __init__(self, input_str: str):
        self.input = input_str

    def validate(self):
        """
        return a list of Predicates after validating.
        """
        ret = []
        matched = match_reqs(self.input)
        for op, ver_dict in matched.items():
            p = Predicate.loads_with_op(op, ver_dict)
            ret.append(p)
        return ret

class VersionReq(object):
    """
    verisonReq containing a list of predicates that can apply to find a matched version
    """

    def __init__(self, op, major, minor=None, patch=None, pre=None):
        self.op: ReqOp = op
        self.major: int = major
        self.minor: typing.Optional[int] = minor
        self.patch: typing.Optional[int] = patch
        self.pre: typing.Optional[str] = pre

# v = semver.VersionInfo.parse('0.1.0-alpha+build1')
# print(type(v.prerelease))
# print(type(v.build))
# vor = VerReqVaildator('>= 1.1.0, <= 1.1.8')
# ps = vor.validate()
# test1 = PREFIX_REGEX.match('>= 1.1.0')
# test2 = PREFIX_REGEX.match('>= 1.1.0, <= 1.1.8')
# print(test1.groupdict())
# print(test2.groupdict())
# print(match_reqs('aaaaaa'))
