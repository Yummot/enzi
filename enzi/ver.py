# -*- coding: utf-8 -*-

"""
A semver patch module to support VersionReq schematic.
This patch is based on rust semver library https://crates.io/crates/semver
e.g. : '>=1.1.0", "^1.1.0", "<1.1.0", "~1.1.0". 
"""


import enum
import logging
import re
import semver
import typing

from semver import VersionInfo

__all__ = [
    'PREFIX_REGEX', 'VERSION_REGEX',
    'complete_version', 'Predicate', 'VersionReq'
]

logger = logging.getLogger(__name__)

PREFIX_REGEX = re.compile(
    r"""
    ^(?P<prefix>(>=|<=|>|<|=|~|\^))?\s*(?P<ver>(.+))$
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


# _nat_cmp from semver https://github.com/k-bx/python-semver
# this is a backup to make sure change to semver api does not affect this module
def _cmp(a, b):
    if a > b:
        return 1
    elif a < b:
        return -1
    else:
        return 0


def _nat_cmp(a, b):
    def convert(text):
        return int(text) if re.match('^[0-9]+$', text) else text

    def split_key(key):
        return [convert(c) for c in key.split('.')]

    def cmp_prerelease_tag(a, b):
        if isinstance(a, int) and isinstance(b, int):
            return _cmp(a, b)
        elif isinstance(a, int):
            return -1
        elif isinstance(b, int):
            return 1
        else:
            return _cmp(a, b)

    a, b = a or '', b or ''
    a_parts, b_parts = split_key(a), split_key(b)
    for sub_a, sub_b in zip(a_parts, b_parts):
        cmp_result = cmp_prerelease_tag(sub_a, sub_b)
        if cmp_result != 0:
            return cmp_result
    else:
        return _cmp(len(a), len(b))


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

    def __str__(self):
        if self == ReqOp.Exact:
            return "="
        elif self == ReqOp.Gt:
            return ">"
        elif self == ReqOp.Ge:
            return ">="
        elif self == ReqOp.Lt:
            return "<"
        elif self == ReqOp.Le:
            return "<="
        elif self == ReqOp.Tilde:
            return "~"
        elif self == ReqOp.Caret:
            return "^"


# map the requests operations string into ReqOp
_REQ_OP_DICT = {
    "=": ReqOp.Exact,
    ">": ReqOp.Gt,
    ">=": ReqOp.Ge,
    "<": ReqOp.Lt,
    "<=": ReqOp.Le,
    "~": ReqOp.Tilde,
    "^": ReqOp.Caret,  # is compatible
}


def into_req_op(op_str: str):
    if not op_str in _REQ_OP_DICT:
        raise ValueError(
            "{} is not a valid version request operation".format(op_str))
    return _REQ_OP_DICT[op_str]


def complete_version(s: str):
    """
    Complete the Version to meet x.y.z-*+* format requirements of semver.VersionInfo
    """
    s = s.strip()
    count_dot = s.count('.')
    if count_dot == 0:
        return (s + '.0.0', 2)
    elif count_dot == 1:
        return (s + '.0', 1)
    else:
        return (s, 0)


def match_reqs(reqs_str: str):
    """
    Match the requests string. 
    Extract the request operations and the possible version string.
    """
    if not reqs_str:
        raise ValueError("input string is empty.")
    if ',' in reqs_str:
        reqs_map = map(str.strip, reqs_str.split(','))
        reqs = list(reqs_map)
        # test invalid
        test = map(lambda x: not x, reqs)
        if any(test):
            msg = "{} is not a valid version request string".format(reqs_str)
            logger.error(msg)
            raise ValueError(msg) from None
    else:
        reqs = [reqs_str]

    ret = []
    for req in reqs:
        matched = PREFIX_REGEX.match(req)
        gdict = matched.groupdict()
        # if gdict['prefix'] is None:
        try:
            pre = gdict['ver']
            completed, ccnt = complete_version(pre)
            ver = semver.parse(completed)
            if ccnt == 1:
                ver['patch'] = None
            if ccnt == 2:
                ver['minor'] = None
                ver['patch'] = None
        except Exception:
            msg = "{} is not a valid version request string".format(req)
            logger.error(msg)
            raise ValueError(msg) from None
        if gdict['prefix'] is None:
            op = ReqOp.Caret
        else:
            op = into_req_op(gdict['prefix'])
        ret.append((op, ver))

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
        Load from a dict which may contain version parts with ReqOp.
        """
        return Predicate(op, **v_dict)

    @staticmethod
    def exact(version: semver.VersionInfo):
        """
        construct an Predicate with an exact Version.
        """
        op = ReqOp.Exact
        return Predicate(
            op=op,
            major=version.major,
            minor=version.minor,
            patch=version.patch,
            prerelease=version.pre
        )

    def matches(self, ver: VersionInfo):
        if self.op == ReqOp.Exact:
            return self.is_exact(ver)
        elif self.op == ReqOp.Gt:
            return self.is_greater(ver)
        elif self.op == ReqOp.Ge:
            return self.is_exact(ver) or self.is_greater(ver)
        elif self.op == ReqOp.Lt:
            return not self.is_exact(ver) and not self.is_greater(ver)
        elif self.op == ReqOp.Le:
            return not self.is_greater(ver)
        elif self.op == ReqOp.Tilde:
            return self.matches_tilde(ver)
        elif self.op == ReqOp.Caret:
            return self.is_compatible(ver)

    def is_exact(self, ver: VersionInfo):
        if self.major != ver.major:
            return False

        if self.minor is None:
            return True
        elif self.minor != ver.minor:
            return False

        if self.patch is None:
            return True
        elif self.patch != ver.patch:
            return False

        if self.pre != ver.prerelease:
            return False

        return True

    def is_greater(self, ver: VersionInfo):
        """
        check if ver is greater than this VersionReq constraint
        """
        if self.major != ver.major:
            return ver.major > self.major

        if self.minor is None:
            return False
        elif self.minor != ver.minor:
            return ver.minor > self.minor

        if self.patch is None:
            return False
        elif self.patch != ver.patch:
            return ver.patch > self.patch

        if self.pre:
            left = not ver.prerelease
            return left or _nat_cmp(ver.prerelease, self.pre) == 1

        return False

    def matches_tilde(self, ver: VersionInfo):
        # see https://www.npmjs.org/doc/misc/semver.html for behavior
        if self.minor is None:
            return self.major == ver.major
        else:
            minor = self.minor

        if self.patch is None:
            return self.major == ver.major and minor == ver.minor
        else:
            patch = self.patch
            major_match = self.major == ver.major
            minor_match = minor == ver.minor
            patch_and_pre = (ver.patch > patch or (
                ver.patch == patch and self.pre_is_compatible(ver)))
            ret = major_match and minor_match and patch_and_pre
            return ret

    def is_compatible(self, ver: VersionInfo):
        # see https://www.npmjs.org/doc/misc/semver.html for behavior
        if self.major != ver.major:
            return False

        if self.minor is None:
            return self.major == ver.major
        else:
            minor = self.minor

        if self.patch is None:
            if self.major == 0:
                return ver.minor == minor
            else:
                return ver.minor >= minor
        else:
            patch = self.patch
            if self.major == 0:
                if minor == 0:
                    patch_match = ver.patch == patch
                    patch_and_pre = patch_match and self.pre_is_compatible(ver)
                    return ver.minor == minor and patch_and_pre
                else:
                    patch_gt = ver.patch > patch
                    patch_match = ver.patch == patch
                    pcompatible = self.pre_is_compatible(ver)
                    patch_and_pre = patch_gt or (patch_match and pcompatible)
                    return ver.minor == minor and patch_and_pre
            else:
                minor_gt = ver.minor > minor
                minor_match = ver.minor == minor
                patch_match = ver.patch == patch
                patch_gt = ver.patch > patch
                pcompatible = self.pre_is_compatible(ver)
                patch_and_pre = patch_gt or (patch_match and pcompatible)
                return minor_gt or (minor_match and patch_and_pre)

    def pre_tag_is_compatible(self, ver: VersionInfo):
        # https://docs.npmjs.com/misc/semver#prerelease-tags
        not_prerelease = (ver.prerelease is None)
        major_match = self.major == ver.major
        minor_match = self.minor == ver.minor
        patch_match = self.patch == ver.patch
        has_pre = (not self.pre is None)
        ret = not_prerelease or (
            major_match and minor_match and minor_match and patch_match and has_pre)
        return ret

    def pre_is_compatible(self, ver: VersionInfo):
        is_empty = not ver.prerelease
        return is_empty or _nat_cmp(ver.prerelease, self.pre) != -1

    def _vars(self):
        return vars(self)

    def _build_ver_str(self):
        """
        build a version string
        """
        tmajor = str(self.major)
        str_buf = [tmajor]
        if self.minor is None:
            return str(tmajor)
        str_buf.append('.{}'.format(self.minor))

        if self.patch is None:
            return ''.join(str_buf)
        str_buf.append('.{}'.format(self.patch))

        if self.pre is None:
            return ''.join(str_buf)
        str_buf.append('-{}'.format(self.pre))

        return ''.join(str_buf)

    def __str__(self):
        tmp = self._build_ver_str()
        if self.op == ReqOp.Caret or self.op == ReqOp.Tilde:
            return str(self.op) + tmp
        else:
            return str(self.op) + " " + tmp

    def __repr__(self):
        _vars = vars(self)
        return "Predicate{}".format(_vars)

    def __eq__(self, other):
        if not isinstance(other, Predicate):
            raise ValueError(
                'try to compare Predicate with non-Predicate class')

        return self._vars() == other._vars()

    def __tuple__(self):
        return (
            self.op,
            self.major,
            self.minor,
            self.patch,
            self.pre
        )

    def __hash__(self):
        h = self.__tuple__()
        return hash(h)


class VerReqValidator(object):
    """
    VerReqValidator: Vaildate a version request string.
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
        for op, ver_dict in matched:
            p = Predicate.loads_with_op(op, ver_dict)
            ret.append(p)
        return ret


class VersionReq(object):
    """
    verisonReq containing a list of predicates that can apply to find a matched version.
    """

    def __init__(self, predicates: typing.List[Predicate]):
        self.predicates: typing.List[Predicate] = predicates

    @staticmethod
    def any():
        """
        create a VersionReq that any version will match against it.
        """
        return VersionReq([])

    @staticmethod
    def parse(ver_req: str):
        """
        take a version and return a VersionReq that contains corresponding requirements.
        """
        ver_req = ver_req.strip()
        validator = VerReqValidator(ver_req)
        preds = validator.validate()
        return VersionReq(preds)

    @staticmethod
    def exact(version: semver.VersionInfo):
        """
        construct a VersionReq with one exact Version constraint.
        """
        return VersionReq([Predicate.exact(version)])

    def matches(self, version: semver.VersionInfo):
        if type(version) == str:
            version = semver.VersionInfo.parse(version)

        if not isinstance(version, semver.VersionInfo):
            fmt = 'version must be string or semver.VersionInfo, not {}'
            msg = fmt.format(version.__class__.__name__)
            logger.error(msg)
            raise ValueError(msg)

        if not self.predicates:
            return True

        all_match = all(map(lambda p: p.matches(version), self.predicates))
        any_compatible = any(
            map(lambda p: p.pre_tag_is_compatible(version), self.predicates))

        return all_match and any_compatible

    def _vars(self):
        return vars(self)

    def __str__(self):
        str_preds = list(map(lambda p: p.__str__(), self.predicates))
        return ', '.join(str_preds)

    def __repr__(self):
        _vars = self._vars()
        str_preds = map(lambda p: p.__repr__(), _vars['predicates'])
        _vars['predicates'] = list(str_preds)
        return "VersionReq<{}>{}".format(hex(id(self)), _vars)

    def __eq__(self, other):
        if not isinstance(other, VersionReq):
            raise ValueError(
                'try to compare VersionReq with non-VersionReq class')

        return self.predicates == other.predicates

    def __hash__(self):
        return hash(tuple(self.predicates))


# v = semver.VersionInfo.parse('0.1.0-alpha+build1')
# print(type(v.major))
# print(type(v.build))
# vor = VerReqValidator('>= 1.1.0, <= 1.1.8')
# ps = vor.validate()
# test1 = PREFIX_REGEX.match('>= 1.1.0')
# test2 = PREFIX_REGEX.match('>= 1.1.0, <= 1.1.8')
# print(test1.groupdict())
# print(test2.groupdict())
# print(match_reqs('aaaaaa'))
# print(_nat_cmp('build1.2', 'build1.0'))
# print(VersionReq.parse('>= 1.1.0, <= 1.1.8'))
# print(VersionReq.parse('^ 1.1.0,~ 1.1.8'))
# print(VersionReq.parse('1.1.0'))
