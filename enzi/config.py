# -*- coding: utf-8 -*-

import io
import logging
import os
import platform
import pprint
import toml
import typing
import copy as py_copy

from abc import ABCMeta, abstractmethod
from itertools import chain
from semver import VersionInfo as Version


from enzi.backend import KnownBackends
from enzi.utils import Launcher
from enzi.utils import realpath, toml_load, toml_loads
from enzi.ver import complete_version
from enzi.ver import VersionReq

__all__ = [
    'validate_git_repo', 'validate_dep_path',
    'DependencySource', 'DependencyVersion',
    'Dependency', 'RawDependency',
    'DependencyEntry', 'DependencyRef', 'DependencyTable',
    'LockedSource', 'LockedDependency', 'Locked',
    'ValidatorError', 'Validator', 'BaseTypeValidator',
    'StringValidator', 'IntValidator', 'BoolValidator',
    'FloatValidator', 'StringListValidator',
    'VersionValidator', 'VersionReqValidator',
    'PackageValidator', 'DependencyValidator', 'DepsValidator',
    'FilesetValidator', 'FilesetsValidator',
    'ToolParamsValidator', 'IESParamsValidator', 'IXSParamsValidator',
    'QuestaParamsValidator', 'VsimParamsValidator',
    'ToolValidator', 'ToolsValidator', 'TargetValidator', 'TargetsValidator',
    'EnziConfigValidator', 'PartialConfig', 'Config', 'RawConfig'
]


logger = logging.getLogger(__name__)

KNOWN_BACKENDS = set(KnownBackends().known_backends.keys())
ENZI_CONFIG_VERSIONS = {"0.1", "0.2"}
CONFIG_CURRENT_VERSION = "0.2"


def flat_git_records(item):
    name, records = item
    if len(records) == 1:
        record = list(records)[0]
        return (name, {'path': record})
    else:
        return (name, {'path': records})


def validate_git_repo(dep_name: str, git_url: str, test=False):
    try:
        Launcher('git', ['ls-remote', '-q', git_url]).run(no_log=test)
        return True
    except Exception as e:
        if test:
            return False
        fmt = 'validate_git_repo: {}(git_url:{}) is a not valid git repo'
        msg = fmt.format(dep_name, git_url)
        logger.error(msg)
        raise ValueError(msg) from e


def validate_dep_path(dep_name: str, dep_path: str):
    dep_path = realpath(dep_path)
    if os.path.isabs(dep_path):
        return dep_path
    else:
        msg = 'validate_dep_path: {}(dep_path:{}) must have a absolute path'.format(
            dep_name, dep_path)
        logger.error(msg)
        raise ValueError(msg)


def tools_section_line(line: str):
    """
    pretty print the line of a tools section
    """
    if not line:
        return line
    if line.startswith(('[[', 'name')):
        return line + '\n'

    return '\t{}\n'.format(line)


class DependencySource(object):
    def __init__(self, git_url: str, is_local: bool):
        if not git_url:
            raise ValueError('git_url must be str')
        self.git_url: str = git_url
        self.is_local: bool = is_local

    def __eq__(self, other):
        if isinstance(other, DependencySource):
            return self.git_url == other.git_url and self.is_local == other.is_local

    def __hash__(self):
        return hash((self.git_url, self.is_local))

    def is_git(self):
        return True


class DependencyVersion(object):
    def __init__(self, revision: str):
        self.revision: str = revision

    def __eq__(self, other):
        if isinstance(other, DependencyVersion):
            return self.revision == other.revision

    def __hash__(self):
        return hash(self.revision)

    @staticmethod
    def Git(revision: str):
        return DependencyVersion(revision)

    def is_git(self):
        return True


class Dependency(object):
    def __init__(self, git_url: str, rev_ver: VersionReq, use_version, is_local):
        self.git_url = git_url
        self.rev_ver = rev_ver  # revision or version
        self.use_version = use_version
        self.is_local = is_local

    def __str__(self, *, dep_name=None):
        if dep_name is None:
            return 'Dependency { git_url: %s, rev_ver: %s }' % (self.git_url, self.rev_ver)
        else:
            return 'Dependency(%s) { git_url: %s, rev_ver: %s }' % (str(dep_name), self.git_url, self.rev_ver)
    # TODO: use a more elegant way
    __repr__ = __str__


class RawDependency(object):
    def __init__(self, path=None, url=None, revision=None, version=None):
        self.path: typing.Optional[str] = path
        self.url: typing.Optional[str] = url
        self.revision: typing.Optional[str] = revision
        self.version: typing.Optional[str] = version

    @staticmethod
    def from_config(config):
        path: typing.Optional[str] = config.get('path')
        url: typing.Optional[str] = config.get('url')
        revision: typing.Optional[str] = config.get('commit')
        version: typing.Optional[str] = config.get('version')
        return RawDependency(path=path, url=url, revision=revision, version=version)

    def validate(self):
        version = self.version
        if version:
            version = VersionReq.parse(self.version)
        if self.revision and self.version:
            raise ValueError(
                'Dependency cannot specify `commit` and `version` at the same time.')
        if self.path and self.url:
            raise ValueError(
                'Dependency cannot specify `path` and `url` at the same time.')
        git_url = self.path if self.path else self.url

        if self.path:
            git_url = self.path
            is_local = True
        else:
            git_url = self.url
            is_local = False

        if self.revision:
            rev_ver = self.revision
            use_version = False
        else:
            rev_ver = version
            use_version = True

        return Dependency(git_url, rev_ver, use_version, is_local)
        # if self.version:
        # return Dependency()


class DependencyEntry(object):
    def __init__(self, name: str, source: DependencySource, revision=None, version=None):
        """
        :param name: str
        :param source: DependencySource
        :param revision: str | None
        :param version: semver.VersionInfo | None
        """
        # help detect if this DependencyEntry is originally local repo
        self.is_local = source.is_local
        self.name: str = name
        self.source: DependencySource = source
        if revision is None or type(revision) == str:
            self.revision: typing.Optional[str] = revision
        else:
            raise RuntimeError('DependencyEntry.revision must be str or None')
        if version is None or isinstance(version, Version):
            self.version: typing.Optional[Version] = version
        else:
            raise RuntimeError(
                'DependencyEntry.version must be semver.VersionInfo or None')

    def dump_vars(self):
        vs = py_copy.deepcopy(vars(self))
        vs['source'] = self.source.git_url
        return vs

    def get_version(self):
        if self.revision:
            return DependencyVersion.Git(self.revision)
        else:
            raise RuntimeError('DependencyEntry.revision is None')

    @property
    def __keys(self):
        return (self.name, self.source, self.revision, self.version)

    def __eq__(self, other):
        if isinstance(other, DependencyEntry):
            return self.__keys == other.__keys

    def __hash__(self):
        return hash((self.name, self.source, self.revision, self.version))


class DependencyRef(object):
    def __init__(self, dep_id: int):
        self.id: int = dep_id

    def __eq__(self, other):
        if isinstance(other, DependencyRef):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

    def __gt__(self, other):
        if isinstance(other, DependencyRef):
            return self.id > other.id

    def __lt__(self, other):
        if isinstance(other, DependencyRef):
            return self.id < other.id

    def __repr__(self):
        return 'DependencyRef({})'.format(self.id)


class DependencyTable(object):
    def __init__(self):
        self.list: typing.List[DependencyEntry] = []  # list[DependencyEntry]
        # <K=DependencyEntry, V=DependencyRef>
        self.ids: typing.MutableMapping[DependencyEntry, DependencyRef] = {}

    def add(self, entry: DependencyEntry):
        if entry in self.ids:
            return self.ids[entry]
        else:
            dep_id = DependencyRef(len(self.list))
            self.list.append(entry)
            self.ids[entry] = dep_id
            return dep_id

    def is_empty(self):
        return len(self.list) == 0


class LockedSource(object):
    def __init__(self, url_path: str):
        self.url_path: str = url_path

    def __str__(self):
        return self.url_path
    # TODO: use a more elegant way

    def __repr__(self):
        return "LockedSource({})".format(self.url_path)


class LockedDependency(object):
    """
    Locked dependency
    package the selected version and source of a locked dependency
    """

    def __init__(self, *, revision: typing.Optional[str], version: typing.Optional[str], source: LockedSource, dependencies: typing.Set[str]):
        self.revision = revision
        self.version = version
        self.source = source
        self.dependencies = dependencies

    def __str__(self):
        return "LockedDependency{{revision: \"{}\", version: \"{}\", \
source: \"{}\", dependencies: {}}}".format(self.revision, self.version, self.source, self.dependencies)
    # TODO: use a more elegant way
    __repr__ = __str__


class Locked(object):
    """
    A Lock, contains all the resolved dependencies
    """

    def __init__(self, *, dependencies: typing.MutableMapping[str, LockedDependency], config_path=None, config_mtime=None):
        self.dependencies = dependencies
        # the last modified time of Enzi.toml
        self.config_path: typing.Optional[str] = config_path
        self.config_mtime: typing.Optional[int] = config_mtime
        self.cache = {}

    def __str__(self):
        pstr = pprint.pformat(vars(self))
        return "Locked { %s }" % pstr
    # TODO: use a more elegant way
    __repr__ = __str__

    def add_cache(self, name, data):
        """
        Add a cache section's sub section to lock file.
        If name exists, overwrite with new data.
        """
        self.cache[name] = data

    def remove_cache(self, name):
        """
        remove a cache section's sub section in lock file
        """
        self.cache.pop(name, None)

    def cache_dumps(self):
        # TODO: add more useful cache info in lock file
        d = {}
        if 'git' in self.cache:
            d['git'] = self.git_cache_dumps()

        return d

    def git_cache_dumps(self):
        """
        dump locked's git cache to a dict: typing.MutableMapping[str, str]
        """
        if 'git' in self.cache:
            git_cache = self.cache['git']
            ret = dict(map(flat_git_records, git_cache.items()))
            return ret
        else:
            return {}

    def dep_dumps(self):
        """
        dump locked's deps to a dict: typing.MutableMapping[str, str]
        """
        d = {}
        d['dependencies'] = {}
        deps = d['dependencies']
        for dep_name, dep in self.dependencies.items():
            # deps[dep_name] =
            dep_var = {
                "source": str(dep.source),
                "revision": dep.revision,
                "version": str(dep.version),
                "dependencies": dep.dependencies
            }
            deps[dep_name] = dep_var
        return d

    def dumps(self):
        """
        dump locked's deps to a dict: typing.MutableMapping[str, str]
        """
        d = {}

        config = {
            'path': self.config_path,
            'mtime': self.config_mtime,
        }
        d['metadata'] = {}
        d['metadata']['config'] = config

        d['dependencies'] = self.dep_dumps()['dependencies']
        d['cache'] = self.cache_dumps()

        return d

    @staticmethod
    def loads(config: dict):
        """
        load a Locked from a given dict
        """
        locked = Locked(dependencies={})
        metadata = config['metadata']
        meta_config = metadata['config']
        locked.config_path = meta_config['path']
        locked.config_mtime = int(meta_config['mtime'])
        for dep_name, dep in config['dependencies'].items():
            locked_dep = LockedDependency(
                revision=dep.get('revision'),
                version=dep.get('version'),
                source=LockedSource(dep.get('source')),
                dependencies=set(dep.get('dependencies', []))
            )
            locked.dependencies[dep_name] = locked_dep

        if 'cache' in config and 'git' in config['cache']:
            git_records = config['cache']['git']
            for name, paths in git_records.items():
                paths = paths['path']
                if type(paths) == list:
                    git_records[name] = set(paths)
                else:
                    # TODO: code review
                    git_records[name] = set([paths, ])
            locked.cache = config['cache']
            return locked
        else:
            return locked

    @staticmethod
    def load(config_path: typing.Union[str, bytes]):
        """
        load a Locked from a given path of a lock file
        """
        data = toml_load(config_path)
        return Locked.loads(data)


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


class PackageValidator(Validator):
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
            key=key, val=val, allows=PackageValidator.__allow__, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        self.expect_kvs()

        aset = set(self.__allow__.keys())
        kset = set(self.val.keys())
        missing = aset - kset
        unknown = kset - aset

        if missing:
            msg = 'missing keys: {}'.format(missing)
            raise ValidatorError(self.chain_keys_str(), msg)

        if unknown:
            msg = 'unknown keys: {}'.format(unknown)
            raise ValidatorError(self.chain_keys_str(), msg)

        for key, V in self.__allow__.items():
            val = self.val[key]
            validator = V(key=key, val=val, parent=self)
            self.val[key] = validator.validate()

        return self.val

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


class FilesetValidator(Validator):
    """Validator for a single fileset section"""

    __slots__ = ('val', )
    __allow__ = {
        "files": StringListValidator
    }

    def __init__(self, *, key, val, parent=None):
        # this specified each dependency Validator

        super(FilesetValidator, self).__init__(
            key=key, val=val, allows=FilesetValidator.__allow__, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        self.expect_kvs()

        kset = set(self.val.keys())
        aset = set(self.__allow__.keys())
        missing = aset - kset
        unknown = kset - aset

        if missing:
            msg = 'missing keys: {}'.format(missing)
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

        if 'files' in self.val:
            files = self.val['files']
            # no empty file name strings is allowed
            for f in files:
                if not f:
                    msg = 'contains an empty string'
                    raise ValidatorError(self.chain_keys_str(), msg)
            # all files' paths must be relative
            for f in files:
                if os.path.isabs(f):
                    msg = 'file: "{}" must be a relative path'.format(f)
                    raise ValidatorError(self.chain_keys_str(), msg)
                # files must be inside the package
                if f.startswith('..'):
                    msg = 'file: "{}" is oustside this package'.format(f)
                    raise ValidatorError(self.chain_keys_str(), msg)

        return self.val

    @staticmethod
    def info():
        return {
            'files': StringListValidator.info(),
        }


class FilesetsValidator(Validator):
    """Validator for the whole filsets section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        # this specified each dependency Validator
        super(FilesetsValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        msg = 'At least one fileset must be specified.'
        self.expect_kvs(emsg=msg)

        for k, v in self.val.items():
            validator = FilesetValidator(key=k, val=v, parent=self)
            self.val[k] = validator.validate()

        return self.val

    @staticmethod
    def info():
        return {
            'f0': FilesetValidator.info(),
            'f1': FilesetValidator.info(),
        }


class ToolParamsValidator(Validator):
    """Validator for A tool's params section"""

    __slots__ = ('val', 'params')
    __allow__ = {}

    def __init__(self, *, key, val, parent=None, extras=None):
        if extras:
            if type(extras) == dict:
                logger.debug('ToolParamsValidator: filtered extras')
                f = filter(lambda x: issubclass(
                    x[1], Validator), extras.items())
                z = chain(ToolParamsValidator.__allow__.items(), f)
                self.params = dict(z)
            else:
                logger.warning(
                    'ToolParamsValidator: Ingore non-dict type extras')
        else:
            self.params = ToolParamsValidator.__allow__
            logger.debug('ToolParamsValidator: No extras')
        super(ToolParamsValidator, self).__init__(
            key=key, val=val, allows=self.params, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        if self.val is None:
            return self.val

        self.expect_kvs()

        kset = set(self.val.keys())
        aset = set(self.params.keys())
        unknown = kset - aset

        if unknown:
            msg = 'unknown keys: {}'.format(unknown)
            raise ValidatorError(self.chain_keys_str(), msg)

        for key, V in self.params.items():
            if not key in kset:
                continue
            val = self.val[key]
            validator = V(key=key, val=val, parent=self)
            self.val[key] = validator.validate()

        return self.val

    @staticmethod
    def info():
        """
        ToolParamsValidator is just a base class, so not details info
        """
        return {}


class IESParamsValidator(ToolParamsValidator):
    """Validator for A IES tool's params section"""

    __slots__ = ('val', )
    __extras__ = {
        'link_libs': StringListValidator,
        'gen_waves': BoolValidator,
        'vlog_opts': StringListValidator,
        'vhdl_opts': StringListValidator,
        'vlog_defines': StringListValidator,
        'vhdl_defines': StringListValidator,
        'elab_opts': StringListValidator,
        'sim_opts': StringListValidator,
        'compile_log': StringValidator,
        'elaborate_log': StringValidator,
        'simulate_log': StringValidator
    }

    def __init__(self, *, key, val, parent=None):

        super(IESParamsValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            extras=IESParamsValidator.__extras__
        )
        self.val: typing.Mapping[str, typing.Any]

    @staticmethod
    def info():
        base = ToolParamsValidator.info()
        extras = {
            'link_libs': StringListValidator.info(),
            'gen_waves': BoolValidator.info(),
            'vlog_opts': StringListValidator.info(),
            'vhdl_opts': StringListValidator.info(),
            'vlog_defines': StringListValidator.info(),
            'vhdl_defines': StringListValidator.info(),
            'elab_opts': StringListValidator.info(),
            'sim_opts': StringListValidator.info(),
            'compile_log': StringValidator.info(),
            'elaborate_log': StringValidator.info(),
            'simulate_log': StringValidator.info()
        }
        return {**base, **extras}


class IXSParamsValidator(IESParamsValidator):
    """
    Validator for A IXS tool's params section.
    Warning: IXS backend is not available now.
    """

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(IXSParamsValidator, self).__init__(
            key=key,
            val=val,
            parent=parent
        )
        msg = 'Currently, the IXS tool section is just a placeholder'
        logging.getLogger('IXSParamsValidator').warning(msg)
        # logger.warning(msg)


class QuestaParamsValidator(ToolParamsValidator):
    """Validator for A Questa tool's params section"""

    __slots__ = ('val', )
    __extras__ = {
        'link_libs': StringListValidator,
        'gen_waves': BoolValidator,
        'vlog_opts': StringListValidator,
        'vhdl_opts': StringListValidator,
        'vlog_defines': StringListValidator,
        'vhdl_defines': StringListValidator,
        'elab_opts': StringListValidator,
        'sim_opts': StringListValidator,
        'compile_log': StringValidator,
        'elaborate_log': StringValidator,
        'simulate_log': StringValidator
    }

    def __init__(self, *, key, val, parent=None):

        super(QuestaParamsValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            extras=QuestaParamsValidator.__extras__
        )
        self.val: typing.Mapping[str, typing.Any]

    @staticmethod
    def info():
        base = ToolParamsValidator.info()
        extras = {
            'link_libs': StringListValidator.info(),
            'gen_waves': BoolValidator.info(),
            'vlog_opts': StringListValidator.info(),
            'vhdl_opts': StringListValidator.info(),
            'vlog_defines': StringListValidator.info(),
            'vhdl_defines': StringListValidator.info(),
            'elab_opts': StringListValidator.info(),
            'sim_opts': StringListValidator.info(),
            'compile_log': StringValidator.info(),
            'elaborate_log': StringValidator.info(),
            'simulate_log': StringValidator.info()
        }
        return {**base, **extras}


class VsimParamsValidator(QuestaParamsValidator):
    """Validator for A Vsim(Modelsim/Questasim) tool's params section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(VsimParamsValidator, self).__init__(
            key=key,
            val=val,
            parent=parent
        )


# tools' parms validator name-validator mapping
TPARAMS_VALIDATOR_MAP = {
    'ies': IESParamsValidator,
    'ixs': IXSParamsValidator,
    'questa': QuestaParamsValidator,
    'vsim': VsimParamsValidator
}


class ToolValidator(Validator):
    """validator for a single tool section"""

    __slots__ = ('val', )
    __allow__ = {
        'name': StringValidator,
        'params': ToolParamsValidator
    }
    __must__ = {'name'}
    __options__ = { 'params' }

    def __init__(self, *, key, val, parent=None):

        super(ToolValidator, self).__init__(
            key=key,
            val=val,
            allows=ToolValidator.__allow__,
            parent=parent
        )
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        self.expect_kvs()

        kset = set(self.val.keys())
        aset = set(self.__allow__.keys())
        missing = ToolValidator.__must__ - kset
        unknown = kset - aset

        if missing:
            msg = 'missing keys: {}'.format(missing)
            raise ValidatorError(self.chain_keys_str(), msg)

        if unknown:
            msg = 'unknown keys: {}'.format(unknown)
            raise ValidatorError(self.chain_keys_str(), msg)

        val = self.val['name']
        name = StringValidator(key='name', val=val, parent=self).validate()
        tool_name = name.lower()
        self.val['name'] = tool_name

        if not (tool_name in KNOWN_BACKENDS or tool_name == 'ixs'):
            msg = 'unknown backend: `{}`'.format(tool_name)
            raise ValidatorError(self.chain_keys_str(), msg)

        params_validator = TPARAMS_VALIDATOR_MAP[tool_name]

        if not 'params' in self.val:
            return self.val

        params = self.val['params']
        self.val['params'] = params_validator(
            key='params', val=params, parent=self).validate()

        return self.val

    @staticmethod
    def info(*, tool_name=None):
        tool_name = tool_name.lower() if type(tool_name) == str else tool_name
        if tool_name is None or not tool_name in TPARAMS_VALIDATOR_MAP:
            return {
                'name': 'questa',
                'params': QuestaParamsValidator.info()
            }

        return {
            'name': tool_name,
            'params': TPARAMS_VALIDATOR_MAP[tool_name].info()
        }


class ToolsValidator(Validator):
    """Validator for the whole tools section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        # this specified each dependency Validator
        super(ToolsValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        if self.val is None:
            return self.val

        if type(self.val) != list:
            msg = 'must be an array of tool'
            raise ValidatorError(self.chain_keys_str(), msg)

        for idx, tool in enumerate(self.val):
            validator = ToolValidator(key=str(idx), val=tool, parent=self)
            self.val[idx] = validator.validate()

        return self.val

    @staticmethod
    def info():
        tool0 = ToolValidator.info()
        tool1 = ToolValidator.info()
        tool1['name'] += ' '
        return [tool0, tool1]


class TargetValidator(Validator):
    """validator for a single target section"""

    __slots__ = ('val', )
    __allow__ = {
        'default_tool': StringValidator,
        'toplevel': StringValidator,
        'filesets': StringListValidator
    }

    def __init__(self, *, key, val, parent=None):
        super(TargetValidator, self).__init__(
            key=key,
            val=val,
            allows=TargetValidator.__allow__,
            parent=parent
        )
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        self.expect_kvs()

        kset = set(self.val.keys())
        aset = set(self.__allow__.keys())
        missing = aset - kset
        unknown = kset - aset

        if missing:
            msg = 'missing keys: {}'.format(missing)
            raise ValidatorError(self.chain_keys_str(), msg)

        if unknown:
            msg = 'unknown keys: {}'.format(unknown)
            raise ValidatorError(self.chain_keys_str(), msg)

        for key, V in self.__allow__.items():
            val = self.val[key]
            validator = V(key=key, val=val, parent=self)
            self.val[key] = validator.validate()

        return self.val

    @staticmethod
    def info():
        return {
            'default_tool': StringValidator.info(),
            'toplevel': StringValidator.info(),
            'filesets': StringListValidator.info()
        }


class TargetsValidator(Validator):
    """Validator for the whole tools section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        # this specified each dependency Validator
        super(TargetsValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        if self.val is None:
            return self.val

        self.expect_kvs()

        for k, v in self.val.items():
            validator = TargetValidator(key=k, val=v, parent=self)
            self.val[k] = validator.validate()

        return self.val

    @staticmethod
    def info():
        return {
            'sim': TargetValidator.info(),
            'run': TargetValidator.info(),
        }


class EnziConfigValidator(Validator):
    """
    Validator for "Enzi.toml"
    """

    __slots__ = ('config_path', 'val')
    __must__ = {'enzi_version', 'package', 'filesets'}
    __options__ = {'dependencies', 'target', 'tools'}
    __allow__ = {
        'enzi_version': StringValidator,
        'package': PackageValidator,
        'dependencies': DepsValidator,
        'filesets': FilesetsValidator,
        'targets': TargetsValidator,
        'tools': ToolsValidator
    }
    BASE_ESTRING = 'Enzi exits on error: '

    BASE_FILE_TARGET_COMMENT = '''
# Optional targets section, use when you want Enzi to execute some targets.
# Here is the key-values hint.
'''

    HEADER_COMMENT = '''
# Cheatsheet for an Enzi Configuration File, also known as `Enzi.toml`.
'''

    ENZI_VERSION_COMMENT = '''
# Enzi configuration file version
# Mandatory enzi configuration file version section, must be specified.
'''
    PACKAGE_COMMENT = '''
# This enzi project/package information:
# Mandatory package section, must be specified.
# All the keys listed bellow need to be specified.
# No additional keys are allowed.
'''
    FILESETS_COMMENT = '''
# Filesets for this enzi project/package
# At least one fileset must be provided.
'''

    TARGETS_COMMENT = '''
# Targets for this enzi project/package
# Optional Dependencies Section, use when you want to run a target.
# One or more targets can be specified, see Enzi supported targets for more details.
'''

    DEPS_COMMENT = '''
# Dependencies for this enzi project/package:
# Optional Dependencies Section, use when this Enzi package has dependencies.
# A dependency must have a `path` or `url` key, but not have them the same time.
# A dependency must have a `commit` or `path` key, but not have them the same time.
# (WARNING) if using the path key in a dependency section, it must be a absolute path.
'''

    TOOLS_COMMENT = '''
# Tools configuration for this enzi project/package:
# Optional Dependencies Section, use when you want to provide extra parameters for a tool.
# All parameters in a single tool param section are optional. You don\'t have to provide all parameters.
# This section is just a reminder of all the available tools and their available optional parameters.
# Also, You don\'t have to include tools section, if you don\'t need to specify the parameters of any tools.
'''

    def __init__(self, val, config_path=None, *, git_url=None):
        
        # construct a readable EnziConfigValidator.key
        if git_url and config_path:
            cur_system = platform.system()
            is_windows = (cur_system == 'Windows')
            basename = os.path.basename(config_path)
            if not is_windows:
                raw_key = os.path.join(git_url, basename)
            else:
                raw_key = os.path.join(git_url, basename)
                first_slash = git_url.find('/')
                first_backslash = git_url.find('\\')
                if first_slash != -1 and first_backslash != -1:
                    raw_key = raw_key.replace('/', '\\')
        else:
            raw_key = config_path
        key = '<%s>' % raw_key

        super(EnziConfigValidator, self).__init__(
            key=key,
            val=val,
            allows=EnziConfigValidator.__allow__,
        )
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        self.expect_kvs()

        aset = set(self.__allow__.keys())
        kset = set(self.val.keys())
        missing = self.__must__ - kset
        unknown = kset - aset
        options = kset & self.__options__

        if missing:
            msg = 'missing keys: {}'.format(missing)
            raise ValidatorError(self.chain_keys_str(), msg)

        if unknown:
            msg = 'unknown keys: {}'.format(unknown)
            raise ValidatorError(self.chain_keys_str(), msg)

        for key in self.__must__:
            V = self.__allow__[key]
            val = self.val[key]
            validator = V(key=key, val=val, parent=self)
            self.val[key] = validator.validate()

        for key in options:
            V = self.__allow__[key]
            val = self.val[key]
            validator = V(key=key, val=val, parent=self)
            self.val[key] = validator.validate()

        # check `enzi_version`
        enzi_version = self.val['enzi_version']
        if not enzi_version in ENZI_CONFIG_VERSIONS:
            _v = StringValidator(key='enzi_version',
                                 val=enzi_version, parent=self)
            msg = 'unknown enzi_version: {}'.format(enzi_version)
            raise ValidatorError(_v.chain_keys_str(), msg)

        # check self dependency
        if 'dependencies' in self.val:
            package_name = self.val['package']['name']
            if package_name in self.val['dependencies']:
                fmt = 'Possible self dependency for package: {} at {}'
                msg = fmt.format(package_name, self.key)
                logger.error(msg)
                raise SystemExit(EnziConfigValidator.BASE_ESTRING + msg)
        return self.val

    def expect_kvs(self, *, emsg=None):
        if self.val is None:
            msg = 'Empty Enzi configuration file' if emsg is None else emsg
            raise ValidatorError(self.chain_keys_str(), msg)
        elif type(self.val) != dict:
            msg = 'must be a key-value table' if emsg is None else emsg
            raise ValidatorError(self.chain_keys_str(), msg)

    @staticmethod
    def base_dict(package_name, authors=None):
        """generate a minimal Enzi.toml's dict with given information"""
        d = {}
        d['enzi_version'] = CONFIG_CURRENT_VERSION

        package = {'name': str(package_name), 'version': '0.1.0'}
        if authors is None:
            authors = []
        elif type(authors) == str:
            authors = [authors]
        elif type(authors) == list:
            authors = StringListValidator(
                key='authors', val=authors).validate()
        else:
            raise ValueError('authors must be a string or a string list')
        package['authors'] = authors
        d['package'] = package

        d['filesets'] = {'src': {'files': []}}

        return d

    @staticmethod
    def base_file(package_name, authors=None):
        """generate a minimal Enzi.toml's content StringIO with given information"""
        import toml
        d = EnziConfigValidator.base_dict(package_name, authors)
        sio = io.StringIO()
        sio.write(toml.dumps(d))

        sio.write(EnziConfigValidator.BASE_FILE_TARGET_COMMENT)
        targets = TargetsValidator.info()
        dtargets = {'targets': targets}
        targets_lines = toml.dumps(dtargets).splitlines()
        mlines = map(lambda x: '# {}\n'.format(x), targets_lines)
        sio.writelines(mlines)
        return sio

    @staticmethod
    def info():
        out = io.StringIO()

        out.write(EnziConfigValidator.HEADER_COMMENT)

        out.write(EnziConfigValidator.ENZI_VERSION_COMMENT)
        ev = {'enzi_version': '|'.join(ENZI_CONFIG_VERSIONS)}
        toml.dump(ev, out)

        out.write(EnziConfigValidator.PACKAGE_COMMENT)
        pack = {'package': PackageValidator.info()}
        toml.dump(pack, out)

        out.write(EnziConfigValidator.DEPS_COMMENT)
        deps = {'dependencies': DepsValidator.info()}
        toml.dump(deps, out)

        out.write(EnziConfigValidator.FILESETS_COMMENT)
        filesets = {'filesets': FilesetsValidator.info()}
        toml.dump(filesets, out)

        out.write(EnziConfigValidator.TARGETS_COMMENT)
        targets = {'targets': TargetsValidator.info()}
        toml.dump(targets, out)

        out.write(EnziConfigValidator.TOOLS_COMMENT)

        def fn(tool_name):
            tool = {'tools': [ToolValidator.info(tool_name=tool_name)]}
            lines = toml.dumps(tool).splitlines()

            toolinfo = list(map(tools_section_line, lines))
            out.writelines(toolinfo)
            out.write('\n')

        m = map(fn, TPARAMS_VALIDATOR_MAP.keys())
        _ = list(m)

        return out


class PartialConfig(object):
    """
    A partial config which only contains section 'package', 'dependencies', 'filesets'.
    Tools section is optional in PartialConfig
    """
    __slots__ = ('path', 'package', 'name', 'filesets',
                 'is_local', 'tools', 'file_stat')

    def __init__(self, config, config_path, is_local=True, *, from_str=False, include_tools=False):
        self.path = config_path
        self.package = config.get('package')
        self.name = self.package.get('name')
        self.is_local = is_local

        # preparation for provider section
        if 'provider' in config:
            self.is_local = False  # make sure remote is not marked as local

        msg = 'PartialConfig:__init__: config path = {}'.format(self.path)
        logger.debug(msg)

        # extract filesets
        self.filesets = config.get('filesets')

        # get file stat
        if from_str:
            self.file_stat = None
        else:
            self.file_stat = os.stat(self.path)

        # optional tools section
        self.tools = config.get('tools')

    def into(self):
        """Convert PartialConfig into Config"""
        config = {
            'package': self.package,
            'filesets': self.filesets,
            'tools': self.tools
        }
        ret = Config(config, self.path, self.is_local, from_str=True)
        ret.file_stat = self.file_stat
        return ret

    def get_flat_fileset(self):
        class Files:
            def __init__(self):
                self.files = []
            def add_files(self, x):
                self.files = self.files + x['files']
        files = Files()
        m = map(files.add_files, self.filesets.values())
        _ = list(m)
        return { 'files': files.files }

def check_exists(path, base_path=None):
    """check the existence of a path"""
    if base_path:
        path = os.path.join(base_path, path)
    return os.path.exists(path)

class Config(object):
    """
    A completed configuration file
    """

    def __init__(self, config, config_path, is_local=True, *, from_str=False):
        self.path = config_path
        self.package = config.get('package')
        self.name = self.package.get('name')
        self.is_local = is_local

        # preparation for provider section
        if 'provider' in config:
            self.is_local = False  # make sure remote is not marked as local

        msg = 'PartialConfig:__init__: config path = {}'.format(self.path)
        logger.debug(msg)

        # extract filesets
        self.filesets = config.get('filesets')

        # get file stat
        if from_str:
            self.file_stat = None
        else:
            self.file_stat = os.stat(self.path)

        # extract dependencies
        self.dependencies = {}
        if 'dependencies' in config:
            for dep, dep_conf in config.get('dependencies').items():
                # TODO: add function to resolve abs dependency's path
                dep_path = dep_conf['path']
                if 'path' in dep_conf and not os.path.isabs(dep_path):
                    dep_conf['path'] = validate_dep_path(dep, dep_path)
                validated = RawDependency.from_config(dep_conf).validate()
                self.dependencies[dep] = validated

        # validate dependencies
        for dep_name, dep in self.dependencies.items():
            validate_git_repo(dep_name, dep.git_url)

        # targets configs
        self.targets = {}
        if 'targets' in config:
            self.targets = config.get('targets')

        # tools configs
        self.tools = {}
        self._raw_tools = None
        tools_config = config.get('tools')
        if tools_config:
            self._raw_tools = tools_config
            for idx, tool in enumerate(tools_config):
                if not 'name' in tool:
                    raise RuntimeError(
                        'tool must be set for tools<{}>'.format(idx))
                self.tools[tool['name']] = {}
                self.tools[tool['name']]['params'] = tool.get('params', {})

    def debug_str(self):
        str_buf = ['Config: {']
        m = vars(self)
        for k, v in m.items():
            str_buf.append('\t%s: %s' % (k, v))
        str_buf.append('}')
        return '\n'.join(str_buf)
    
    def check_filesets(self):
        dirname = os.path.dirname(self.path)
        fmt = 'Filesets.{}\'s files: {} not found'
        
        checker = lambda x: check_exists(x, dirname)

        for fsname, fs in self.filesets.items():
            files = fs['files']
            if files:
                exists_f = filter(checker, files)
                fset = set(files)
                eset = set(exists_f)
                non_exists = fset - eset
                if non_exists:
                    msg = fmt.format(fsname, non_exists)
                    logger.error(msg)
                    raise ValueError(msg)

    def get_flat_fileset(self):
        class Files:
            def __init__(self):
                self.files = []
            def add_files(self, x):
                self.files = self.files + x['files']
        files = Files()
        m = map(files.add_files, self.filesets.values())
        _ = list(m)
        return { 'files': files.files }

    def into(self):
        """ Returns self for duck type compatibility"""
        return self

    def content(self):
        """ retun a StringIO with the string content of this Config"""
        out = io.StringIO()
        d = {'enzi_version': CONFIG_CURRENT_VERSION }
        d['package'] = self.package
        d['filesets'] = self.filesets
        
        if self.dependencies:
            d['dependencies'] = self.dependencies
        if self.targets:
            d['targets'] = self.targets

        toml.dump(d, out)
        tools = self._raw_tools
        
        if not tools:
            return out

        out.write('\n')

        def fn(tool):
            tool = {'tools': [tool]}
            lines = toml.dumps(tool).splitlines()

            toolinfo = list(map(tools_section_line, lines))
            out.writelines(toolinfo)
            out.write('\n')
        
        m = map(fn, tools)
        _ = list(m)

        return out

class RawConfig(object):
    """
    A raw configuration file ready to validate.
    After calling validate member function a Config/PartialConfig will be generated
    """
    __slots__ = ('conf', 'is_local', 'config_path',
                 'validator', 'fileset_only', 'from_str', 'git_url')

    def __init__(self, config_file, from_str=False, base_path=None, is_local=True, *, git_url=None, fileset_only=False):
        if from_str:
            conf = toml_loads(config_file)
        else:
            conf = toml_load(config_file)

        if from_str:
            self.config_path = os.path.join(base_path, 'Enzi.toml')
        else:
            self.config_path = config_file

        if not conf:
            logger.error('Config toml file is empty.')
            raise RuntimeError('Config toml file is empty.')

        self.git_url = git_url
        self.conf = conf
        self.from_str = from_str
        self.is_local = is_local
        self.fileset_only = fileset_only
        self.validator = EnziConfigValidator(conf, self.config_path, git_url=git_url)

    def validate(self):
        """
        validate this raw config, return PartialConfig/Config
        """
        validated = self.validator.validate()
        if self.fileset_only:
            # TODO: In future version, make use of include_tools
            return PartialConfig(validated, self.config_path, self.is_local, from_str=self.from_str, include_tools=False)
        else:
            return Config(validated, self.config_path, self.is_local, from_str=self.from_str)
