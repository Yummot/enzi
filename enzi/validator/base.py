# -*- coding: utf-8 -*-

import logging
import os
import toml
import typing

from abc import ABCMeta, abstractmethod
from semver import VersionInfo as Version

from enzi.backend import KnownBackends
from enzi.ver import complete_version
from enzi.ver import VersionReq

ALLOW_BACKENDS = set(KnownBackends().allow_backends.keys())
ENZI_CONFIG_VERSIONS = {"0.1", "0.2", "0.3"}
CONFIG_CURRENT_VERSION = "0.2"

logger = logging.getLogger('xvalidator')

__all__ = [
    'ALLOW_BACKENDS', 'ENZI_CONFIG_VERSIONS', 'CONFIG_CURRENT_VERSION',
    'tools_section_line', 'ValidatorError', 'Validator', 'BaseTypeValidator',
    'StringValidator', 'BoolValidator', 'IntValidator', 'FloatValidator',
    'VersionValidator', 'VersionReqValidator', 'StringListValidator',
    'TypedMapValidator', 'PackageValidator', 'DependencyValidator',
    'DepsValidator',
]


def tools_section_line(line: str):
    """
    pretty print the line of a tools section
    """
    if not line:
        return line
    if line.startswith(('[[', 'name')):
        return line + '\n'

    return '\t{}\n'.format(line)


class ValidatorError(ValueError):
    """Base Validator Exception / Error."""

    def __init__(self, chained, msg):
        emsg = 'Error at `{}`: {}'.format(chained, msg)
        super(ValidatorError, self).__init__(emsg)
        self.chained = chained
        self.msg = msg
        logger.error(self)


class Validator(metaclass=ABCMeta):
    """
    Validator: Base class for validating Config
    """

    __slots__ = ('allows', 'key', 'val', 'parent', 'root')

    def __init__(self, *, key, val=None, allows=None, parent=None):
        from typing import Optional, Mapping, Any
        self.key: str = key
        if isinstance(val, toml.decoder.InlineTableDict):
            val = dict(val)
        self.val: typing.Any = val
        if parent and isinstance(parent, Validator):
            self.parent: Optional[Validator] = parent
        else:
            self.parent = None
        # allow keys to contain if None, this is a leaf in config
        # if it is a dict, K = key, V = Validator
        self.allows: Optional[Mapping[str, Validator]] = allows
        if self.parent is None:
            self.root = self
        else:
            self.root = parent.root

    def chain_keys(self):
        """
        get the full keys chain
        """
        if not self.parent:
            return [self.key]
        parent = self.parent
        keys = [self.key]
        while parent:
            keys.append(parent.key)
            parent = parent.parent

        return keys[::-1]

    def chain_keys_str(self):
        return '.'.join(self.chain_keys())

    def expect_kvs(self, *, emsg=None):
        if self.val is None:
            msg = 'this section should be specified' if emsg is None else emsg
            raise ValidatorError(self.chain_keys_str(), msg)
        elif type(self.val) != dict:
            msg = 'must be a key-value table' if emsg is None else emsg
            raise ValidatorError(self.chain_keys_str(), msg)

    @abstractmethod
    def validate(self):
        """
        prue virtual method for validating self.val
        """
        return None

    @staticmethod
    @abstractmethod
    def info():
        """
        return a help information for the expected value
        """
        return ''


class BaseTypeValidator(Validator):
    """ base type validator base class"""
    __slots__ = ('val', 'T', 'emsg')

    def __init__(self, *, key, val, parent=None, T=None, emsg=None):
        super(BaseTypeValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.T = T
        default_emsg = 'type must be {}'.format(T.__class__.__name__)
        self.emsg = emsg if emsg else default_emsg

    def validate(self):
        if not (type(self.val) == self.T or isinstance(self.val, self.T)):
            raise ValidatorError(self.chain_keys_str(), self.emsg)
        return self.val


class StringValidator(BaseTypeValidator):
    """Validator for a string"""
    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        emsg = 'type must be string'
        super(StringValidator, self).__init__(
            key=key, val=val, parent=parent, T=str, emsg=emsg)
        self.val: str

    @staticmethod
    def info():
        return '<string>'


class BoolValidator(BaseTypeValidator):
    """Validator for a string"""
    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(BoolValidator, self).__init__(
            key=key, val=val, parent=parent, T=bool)
        self.val: bool

    @staticmethod
    def info():
        return '<bool>'


class IntValidator(BaseTypeValidator):
    """Validator for a bool"""
    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(IntValidator, self).__init__(
            key=key, val=val, parent=parent, T=int)
        self.val: int

    @staticmethod
    def info():
        return '<int>'


class FloatValidator(BaseTypeValidator):
    """Validator for a float"""
    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(FloatValidator, self).__init__(
            key=key, val=val, parent=parent, T=float)
        self.val: float

    @staticmethod
    def info():
        return '<float>'


class VersionValidator(Validator):
    """Validator for a semver version"""
    __slots__ = ('val',)

    def __init__(self, *, key, val, parent=None):
        super(VersionValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.val: Version

    def validate(self):
        if not isinstance(self.val, (Version, str)):
            msg = '"{}" must be a semver version string'.format(self.val)
            raise ValidatorError(self.chain_keys_str(), msg)

        if type(self.val) == str:
            val, _ = complete_version(self.val)
        else:
            return self.val

        try:
            Version.parse(val)
        except Exception:
            msg = '{} is not a valid semver version'.format(self.val)
            raise ValidatorError(self.chain_keys_str(), msg) from None

        return self.val

    @staticmethod
    def info():
        return '<semver version string>'


class VersionReqValidator(Validator):
    """Validator for a semver version"""
    __slots__ = ('val',)

    def __init__(self, *, key, val, parent=None):
        super(VersionReqValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.val: Version

    def validate(self):
        if not isinstance(self.val, (VersionReq, str)):
            msg = '"{}" must be a semver version request string'.format(
                self.val)
            raise ValidatorError(self.chain_keys_str(), msg)

        if type(self.val) == VersionReq:
            return self.val

        try:
            VersionReq.parse(self.val)
        except Exception:
            fmt = '{} is not a valid semver version request string'
            msg = fmt.format(self.val)
            raise ValidatorError(self.chain_keys_str(), msg) from None

        return self.val

    @staticmethod
    def info():
        return '<semver version request string>'


class StringListValidator(Validator):
    """Validator for a string list/vector/array"""
    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(StringListValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.val: typing.List[str]

    def validate(self):
        if not isinstance(self.val, list):
            msg = 'value({}) must be a string list'.format(self.val)
            raise ValidatorError(self.chain_keys_str(), msg)
        pred = all(map(lambda x: isinstance(x, str), self.val))

        if not pred:
            msg = 'all value must be string'
            raise ValidatorError(self.chain_keys_str(), msg)

        return self.val

    @staticmethod
    def info():
        return '<array<string>>'


class TypedMapValidator(Validator):
    """
    A base Validator for validating Typed Mapping<K=str, V=Any>
    e.g. { 'name' : str, 'inttype'=str, 'data'=int }
    """

    def __init__(self, *, key, val, parent=None, must={}, optional={}):
        """
        :param key: The key of this mapping
        :param val: The value of this mapping
        :param parent: The parent of this key
        :param must: the mandatory keys of this mapping and the corresponding validator
        :param optional: the optional keys of this mapping and the corresponding validator
        """
        (check, must) = TypedMapValidator.check_validator_dict(must)
        if not check:
            msg = 'param:must: must be a dict<k=str, V=subclass<Validator>>'
            raise ValidatorError(
                TypedMapValidator.__construct_keys(parent, key), msg)
        (check, optional) = TypedMapValidator.check_validator_dict(optional)
        if not check:
            msg = 'param:optional: must be a dict<k=str, V=subclass<Validator>>'
            raise ValidatorError(
                TypedMapValidator.__construct_keys(parent, key), msg)

        allow = {**must, **optional}
        super(TypedMapValidator, self).__init__(
            key=key,
            val=val,
            allows=allow,
            parent=parent
        )
        self.must = must  # <K=str,V=Validator>
        self.optional = optional  # <K=str,V=Validator>
        self._mset = set(must.keys())
        self._oset = set(optional.keys())
        self._aset = set(self.allows.keys())
        self.val: typing.Mapping[str, typing.Any]

    @staticmethod
    def __construct_keys(parent, this_key):
        if parent is None:
            return str(this_key)
        else:
            parent.chain_keys_str() + '.' + str(this_key)

    @staticmethod
    def check_validator_dict(vdict):
        if vdict is None:
            return (True, {})
        elif type(vdict) == dict:
            if not vdict:
                return (True, vdict)

            def f(x): return type(x[0]) == str and issubclass(x[1], Validator)
            ret = any(map(f, vdict.items()))
            return (ret, vdict)
        else:
            return (False, vdict)

    def check_missing_keys(self):
        if self.val is None:
            return

        self.expect_kvs()
        kset = set(self.val.keys())
        missing = self._mset - kset

        if missing:
            msg = 'missing keys: {}'.format(missing)
            raise ValidatorError(self.chain_keys_str(), msg)

    def check_unknown_keys(self):
        if self.val is None:
            return

        self.expect_kvs()
        kset = set(self.val.keys())
        unknown = kset - self._aset

        if unknown:
            msg = 'unknown keys: {}'.format(unknown)
            raise ValidatorError(self.chain_keys_str(), msg)

    def check_must_only(self):
        self.check_missing_keys()
        self.check_unknown_keys()

        for key, V in self.must.items():
            val = self.val.get(key)
            validator = V(key=key, val=val, parent=self)
            self.val[key] = validator.validate()

    def check_optional(self, check_unknown=True):
        if check_unknown:
            self.check_unknown_keys()
        kset = set(self.val.keys())
        options = self._oset & kset

        if options:
            for option in options:
                val = self.val.get(option)
                V = self.optional[option]
                validator = V(key=option, val=val, parent=self)
                self.val[option] = validator.validate()

    def validate(self):
        if self.must:
            self.check_must_only()
        if self.optional:
            self.check_optional()

        return self.val


class PackageValidator(TypedMapValidator):
    """Validator for a package section"""

    __slots__ = ('val', )
    __allow__ = {
        'name': StringValidator,
        'version': VersionValidator,
        'authors': StringListValidator
    }

    def __init__(self, *, key, val, parent=None):
        from typing import Any, Mapping
        super(PackageValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            must=PackageValidator.__allow__
        )
        self.val: typing.Mapping[str, typing.Any]

    @staticmethod
    def info():
        return {
            'name': StringValidator.info(),
            'version': VersionValidator.info(),
            'authors': StringListValidator.info()
        }


class DependencyValidator(Validator):
    """Validator for a single dependency section"""

    __slots__ = ('val', )
    __allow__ = {
        'path': StringValidator,
        'url': StringValidator,
        'version': VersionReqValidator,
        'commit': StringValidator,
    }
    opt_path_url = {'path', 'url'}
    opt_rev_ver = {'commit', 'version'}

    def __init__(self, *, key, val, parent=None):
        from typing import Any, Mapping
        super(DependencyValidator, self).__init__(
            key=key, val=val, allows=DependencyValidator.__allow__, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        pre_valid = self.val is None or (
            type(self.val) == dict and not self.val)
        if pre_valid:
            msg = 'missing keys (path/url) and (commit/version)'
            raise ValidatorError(self.chain_keys_str(), msg)

        self.expect_kvs()

        kset = set(self.val.keys())
        aset = set(self.__allow__.keys())
        git_url_t = self.opt_path_url & kset
        rev_or_ver = self.opt_rev_ver & kset
        unknown = kset - aset

        if not git_url_t:
            msg = 'no path or url is provided'
            raise ValidatorError(self.chain_keys_str(), msg)

        if git_url_t == self.opt_path_url:
            msg = 'path and url cannot be the specified at the same time'
            raise ValidatorError(self.chain_keys_str(), msg)

        if not rev_or_ver:
            msg = 'no commit or version is specified'
            raise ValidatorError(self.chain_keys_str(), msg)

        if rev_or_ver == self.opt_rev_ver:
            msg = 'commit and version cannot be the specified at the same time'
            raise ValidatorError(self.chain_keys_str(), msg)

        if unknown:
            msg = 'unknown keys: {}'.format(unknown)
            raise ValidatorError(self.chain_keys_str(), msg)

        for key, V in self.__allow__.items():
            if not key in kset:
                continue
            val = self.val[key]
            validator = V(key=key, val=val, parent=self)
            self.val[key] = validator.validate()

        return self.val

    @staticmethod
    def info():
        c = StringValidator.info()
        v = VersionReqValidator.info()
        info = '{}/{}'.format(c, v)
        return {
            'path/url': StringValidator.info(),
            'commit/version': info,
        }


class DepsValidator(Validator):
    """Validator for the whole dependencies section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        # this specified each dependency Validator
        super(DepsValidator, self).__init__(key=key, val=val, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        if self.val is None:
            return self.val

        self.expect_kvs()

        for k, v in self.val.items():
            validator = DependencyValidator(key=k, val=v, parent=self)
            self.val[k] = validator.validate()

        return self.val

    @staticmethod
    def info():
        return {
            'dep0': DependencyValidator.info(),
            'dep1': DependencyValidator.info(),
        }
