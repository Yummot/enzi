# -*- coding: utf-8 -*-

import io
import logging
import os
import pprint
import toml
import typing
import copy as py_copy

from semver import VersionInfo as Version

from enzi.utils import Launcher
from enzi.utils import realpath, toml_load, toml_loads
from enzi.ver import VersionReq

logger = logging.getLogger(__name__)

def flat_git_records(item):
    name, records = item
    if len(records) == 1:
        record = list(records)[0]
        return (name, {'path': record})
    else:
        return (name, {'path': records})

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

    def __str__(self):
        return 'Dependency { git_url: %s, rev_ver: %s }' % (self.git_url, self.rev_ver)
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
            # TODO: allow version as a version compare string
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


def validate_git_repo(dep_name: str, git_url: str, test=False):
    try:
        Launcher('git', ['ls-remote', '-q', git_url]).run()
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

# TODO: seperate Config, using a new Config class for fileset_only usage
class Config(object):
    def __init__(self, config_file, from_str=False, base_path=None, is_local=True, *, fileset_only=False):
        conf = {}
        if from_str:
            conf = toml_loads(config_file)
        else:
            conf = toml_load(config_file)

        if not conf:
            logger.error('Config toml file is empty.')
            raise RuntimeError('Config toml file is empty.')

        self.directory = base_path if from_str else os.path.dirname(
            config_file)
        if from_str:
            self.state = None
        else:
            self.file_stat = os.stat(config_file)
        self.package = {}
        self.dependencies: typing.MutableMapping[str, Dependency] = {}
        self.filesets = {}
        self.targets = {}
        self.tools = {}
        self.is_local: bool = is_local
        self.remote_repo = (not 'provider' in conf)  # remote provider
        if self.remote_repo:
            self.is_local = False  # makrsure remote is not marked as local

        logger.debug('Config:__init__: directory = {}'.format(self.directory))

        if 'package' in conf:
            if not 'name' in conf['package']:
                raise RuntimeError('package with no name is not allowed.')
            self.package = conf['package']
            self.name = self.package['name']
        else:
            raise RuntimeError(
                'package info must specify in Config toml file.')

        if not 'filesets' in conf:
            raise RuntimeError('At least one fileset must be specified.')
        for k, v in conf['filesets'].items():
            fileset = {}
            if 'files' in v:
                fileset['files'] = v['files']
            # if 'dependencies' in v:
            #     fileset['dependencies'] = v['dependencies']
            self.filesets[k] = fileset

        if fileset_only:
            return

        if 'dependencies' in conf:
            for dep, dep_conf in conf['dependencies'].items():
                # TODO: make sure the existence of the path of each dependency
                # TODO: add function to resolve abs dependency's path
                dep_path = dep_conf['path']
                if 'path' in dep_conf and not os.path.isabs(dep_path):
                    dep_conf['path'] = validate_dep_path(dep, dep_path)
                self.dependencies[dep] = RawDependency.from_config(
                    dep_conf).validate()

        # validate dependencies
        for dep_name, dep in self.dependencies.items():
            validate_git_repo(dep_name, dep.git_url)

        # for dep in self.dependencies.values():
        #     print(dep.git_url, dep.rev_ver)

        # targets configs
        for target, values in conf.get('targets', {}).items():
            if not 'default_tool' in values:
                raise RuntimeError(
                    'default_tool must be set for targets.{}'.format(target))
            if not 'toplevel' in values:
                raise RuntimeError(
                    'toplevel must be set for targets.{}'.format(target))
            if not 'filesets' in values:
                raise RuntimeError(
                    'filesets must be set for targets.{}'.format(target))
            self.targets[target] = {
                'default_tool': values['default_tool'],
                'toplevel': values['toplevel'],
                'filesets': values['filesets'],
            }
        # tools configs
        for idx, tool in enumerate(conf.get('tools', {})):
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

    @staticmethod
    def from_str(config_str: str, base_path, is_local: bool, *, fileset_only=False):
        logger.debug(
            'Config: construct from a given str with given base_path {}'.format(base_path))
        return Config(config_str, from_str=True, base_path=base_path, is_local=is_local, fileset_only=fileset_only)
