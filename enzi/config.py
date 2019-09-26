import toml
import logging
import os
import io
import typing
from semver import VersionInfo as Version
from enzi.utils import realpath

logger = logging.getLogger(__name__)

# TODO: move to other pack


class DependencySource(object):
    def __init__(self, git_urls: str):
        if not git_urls:
            raise ValueError('git_urls must be str')
        self.git_urls: str = git_urls

    def __eq__(self, other):
        if isinstance(other, DependencySource):
            return self.git_urls == other.git_urls

    def __hash__(self):
        return hash(self.git_urls)

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
    def __init__(self, git_urls: str, rev_ver: typing.Union[str, Version]):
        self.git_urls = git_urls
        self.rev_ver = rev_ver  # revision or version

    def __str__(self):
        return 'Dependency { git_urls: %s, rev_ver: %s }' % (self.git_urls, self.rev_ver)
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
            version = Version.parse(self.version)
        if self.revision and self.version:
            raise ValueError(
                'Dependency cannot specify `commit` and `version` at the same time.')
        if self.path and self.url:
            raise ValueError(
                'Dependency cannot specify `path` and `url` at the same time.')
        git_urls = self.path if self.path else self.url
        rev_ver = self.revision if self.revision else self.version
        return Dependency(git_urls, rev_ver)
        # if self.version:
        # return Dependency()


class DependencyEntry(object):
    def __init__(self, name: str, source: DependencySource, revision=None, version=None):
        """
        @param name: str
        @param source: DependencySource
        @param revision: str | None
        @param version: semver.VersionInfo | None
        """
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

    def get_version(self):
        if self.revision:
            return DependencyVersion.Git(self.revision)
        else:
            raise RuntimeError('DependencyEntry.revision is None')

    @property
    def __keys(self):
        return (self.name, self.source, self.revision, self.version)

    def __eq__(self, other):
        if isinstance(other, DependencyRef):
            return self.__keys == other.__keys

    def __hash__(self):
        return hash((self.name, self.source, self.revision, self.version))


class DependencyRef:
    def __init__(self, dep_id: int):
        self.id: int = dep_id

    def __eq__(self, other):
        if isinstance(other, DependencyRef):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)


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
            self.ids[dep_id] = entry
            return dep_id


class LockedSource(object):
    def __init__(self, url_path: str):
        self.url_path: str = url_path

    def __str__(self):
        return "LockedSource({})".format(self.url_path)
    # TODO: use a more elegant way
    __repr__ = __str__


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
        return "LockedDependency{revision: %s, version: %s, \
            source: %s, dependencies: %s}" % (self.revision, self.version, self.source, self.dependencies)
    # TODO: use a more elegant way
    __repr__ = __str__

class Locked(object):
    """
    A Lock, contains all the resolved dependencies
    """
    def __init__(self, *, dependencies: typing.MutableMapping[str, LockedDependency]):
        self.dependencies = dependencies
    
    def __str__(self):
        return "Locked { %s }" % self.dependencies
    # TODO: use a more elegant way
    __repr__ = __str__

class Config(object):
    def __init__(self, config_file, from_str=False):
        conf = {}
        if from_str:
            conf = toml.loads(config_file)
        else:
            conf = toml.load(config_file)

        if not conf:
            logger.error('Config toml file is empty.')
            raise RuntimeError('Config toml file is empty.')

        self.directory = os.path.dirname(config_file)
        self.file_stat = os.stat(config_file)
        self.package = {}
        self.dependencies: typing.MutableMapping[str, Dependency] = {}
        self.filesets = {}
        self.targets = {}
        self.tools = {}
        self.is_local = (not 'provider' in conf)

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

        if 'dependencies' in conf:
            for dep, dep_conf in conf['dependencies'].items():
                dep_path = dep_conf['path']
                if 'path' in dep_conf and not os.path.isabs(dep_path):
                    dep_conf['path'] = realpath(dep_path)
                self.dependencies[dep] = RawDependency.from_config(
                    dep_conf).validate()

        # for dep in self.dependencies.values():
        #     print(dep.git_urls, dep.rev_ver)

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
    def from_str(config_str: str):
        return Config(config_str, from_str=True)
