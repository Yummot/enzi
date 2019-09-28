# -*- coding: utf-8 -*-

import crypt
import logging
import os
import pprint
import toml
import typing
import copy as py_copy

import enzi.project_manager
from enzi import config
from enzi.backend import KnownBackends
from enzi.config import Config as EnziConfig
from enzi.config import DependencyRef, DependencySource
from enzi.config import DependencyVersion, DependencyEntry, DependencyTable
from enzi.git import Git, GitVersions, TreeEntry
from enzi.utils import realpath, PathBuf, try_parse_semver

logger = logging.getLogger(__name__)


def opts2str(opts):
    if type(opts) == list:
        return ' '.join(opts)
    else:
        return str(opts)


class Enzi(object):
    supported_targets = ['build', 'sim', 'run', 'program_device']
    __default_config__ = 'Enzi.toml'

    def __init__(self, work_dir='.', config_name='Enzi.toml'):
        self.work_dir = realpath(work_dir)
        self.build_dir = self.work_dir + '/build'
        work_root_config = os.path.join(self.work_dir, config_name)
        if os.path.exists(work_root_config):
            config = EnziConfig(work_root_config)
            self.config = config
        else:
            raise RuntimeError('No Enzi.toml in this directory.')

        self.config_mtime = self.config.file_stat.st_mtime
        # targets is a reference for self.config.targets for convenience.
        self.targets = config.targets
        self.is_local = config.is_local

        # TODO: currently the dependencies field in a fileset of config.filesets is just an placeholder.
        self.filesets = config.filesets
        self.package = config.package
        # self.dependencies = config.dependencies
        self.dependencies = DependencyTable()
        self.work_name = py_copy.copy(self.package['name'])
        self.tools = config.tools
        self.known_backends = KnownBackends()
        self.backend_conf_generator = BackendConfigGen(self.known_backends)

        # database
        self.database_path: PathBuf = PathBuf(self.work_dir).join('database')
        self.git_db_records: typing.MutableMapping[str,
                                                   typing.MutableSet[str]] = {}

        # check if we need update database
        potential_lock_file = os.path.join(self.work_dir, 'Enzi.lock')
        if os.path.exists(potential_lock_file) and self.database_path.exits():
            self.need_update = False
        elif os.path.exists(potential_lock_file) and not self.database_path.exits():
            if self.config.dependencies:
                logger.warning(
                    'Enzi: no database directory found, but there is a Enzi.lock file. Creating a new database.')
            self.need_update = True
        else:
            self.need_update = None

    def init(self):
        """
        Initialize the Enzi object, resolve dependencies and etc.
        """
        from enzi.lock import LockLoader
        if self.need_update is None:
            update = False
        else:
            update = self.need_update

        # Currently, we only create and load lock file if the project has dependencies
        # TODO: add more usefull data in lock file
        if self.config.dependencies:
            logger.debug(
                'Enzi:init: this project has dependencies, launching LockLoader')
            locked = LockLoader(self, self.work_dir).load(update)

            if locked.cache and 'git' in locked.cache:
                self.git_db_records = locked.cache['git']

            dep_msg = pprint.pformat(locked.dumps())
            cache_msg = pprint.pformat(locked.cache)
            logger.debug('Enzi:init: locked deps:\n{}'.format(dep_msg))
            logger.debug('Enzi:init: locked caches:\n{}'.format(cache_msg))
        else:
            logger.debug('Enzi:init: this project has no dependencies')

    @property
    def silence_mode(self):
        if hasattr(self, '_silence_mode'):
            return self._silence_mode
        else:
            setattr(self, '_silence_mode', False)
            return False

    @silence_mode.setter
    def silence_mode(self, value):
        if not isinstance(value, bool):
            raise ValueError('silence_mode must be boolean')
        if hasattr(self, '_silence_mode'):
            self._silence_mode = value
        else:
            setattr(self, '_silence_mode', value)

    def load_dependency(self, name, dep: config.Dependency, econfig: EnziConfig):
        if not isinstance(dep, config.Dependency):
            raise ValueError('dep must be an instance of config.Dependency')
        logger.debug('Loading dependency {} for {} with {}'.format(
            name, econfig.name, dep.git_url))
        src = config.DependencySource(dep.git_url, dep.is_local)
        dep_ref = self.dependencies.add(DependencyEntry(name, src))
        logger.debug('load_dependency: loaded(ref_id={}) {}'.format(
            dep_ref, self.dependencies.list[dep_ref.id].dump_vars()))
        # if dep_ref.id == 2:
        #     logger.debug('load_dependency: ppploaded(ref_id={}) {}'.format(
        #         1, self.dependencies.list[1].dump_vars()))
        #     logger.debug('load_dependency: ppptest = {}'.format(
        #         self.dependencies.list[dep_ref.id] == self.dependencies.list[1]))
        #     logger.debug('load_dependency: ppptest = {}'.format(
        #         hash(self.dependencies.list[dep_ref.id]) == hash(self.dependencies.list[1])))
        return dep_ref

    def dependecy(self, dep: DependencyRef) -> DependencyEntry:
        return self.dependencies.list[dep.id]

    def dependency_name(self, dep: DependencyRef) -> str:
        return self.dependencies.list[dep.id].name

    def dependency_source(self, dep: DependencyRef) -> DependencySource:
        # TODO: Code review
        return self.dependencies.list[dep.id].source

    def check_target_availability(self, target_name):
        if not target_name in self.supported_targets:
            raise RuntimeError(
                '{} in not in current supprot targets'.format(target_name))
        if not target_name in self.targets:
            raise RuntimeError('{} in not in targets'.format(target_name))

    def run_target(self, target_name, filelist=None, tool_name=None):
        self.check_target_availability(target_name)

        backend = self.get_backend(
            target_name, tool_name=tool_name, filelist=filelist)
        self.configure(target_name, backend)
        self.excute(target_name, backend)

    def configure(self, target_name, backend):
        self.check_target_availability(target_name)
        getattr(backend, 'configure')()

    def excute(self, target_name, backend):
        self.check_target_availability(target_name)

        # backend = self.get_backend(target_name)
        getattr(backend, target_name)()

    def get_backend(self, target_name, **kwargs):
        if target_name in self.targets:
            target = self.targets[target_name]
            target_toplevel = target.get('toplevel', '')
            target_fileset = []
            if not 'filelist' in kwargs:
                target_fileset = self.gen_target_fileset(target_name)
            else:
                target_fileset = kwargs['filelist']

            tool_name = str(target['default_tool'])
            if 'tool_name' in kwargs and kwargs['tool_name']:
                tool_name = str(kwargs['tool_name'])

            tool_config = self.tools.get(tool_name, {})
            tool_config['silence_mode'] = self.silence_mode
            tool_config['name'] = self.package['name']

            if not os.path.exists(self.build_dir):
                logger.info('Create a build directory.')
                os.makedirs(self.build_dir)

            backend_config = self.backend_conf_generator.get(
                tool_name=tool_name,
                tool_config=tool_config,
                work_name=self.work_name,
                work_root=self.build_dir,
                toplevel=target_toplevel,
                fileset=target_fileset
            )

            if tool_name == 'vsim':
                logger.warning(
                    'Treat Vsim tool request as using questa simulator')
                tool_name = 'questa'

            backend = self.known_backends.get(
                tool_name, backend_config, self.build_dir)
            return backend
        else:
            raise RuntimeError('{} in not in targets'.format(target_name))

    def abs_fileset(self, fileset):
        ret = py_copy.copy(fileset)
        return ret

    def gen_target_fileset(self, target_name):
        self.check_target_availability(target_name)

        _files = []
        # _deps = []
        for fileset_name in self.targets[target_name]['filesets']:
            fileset = self.filesets.get(
                fileset_name, {'files': [], })
            _files = _files + fileset.get('files', [])
            # _deps = _deps + fileset.get('dependencies', [])
        # return {'files': _files, 'dependencies': _deps}
        return {'files': _files, }

    # def update_target_fileset(self, target_name, new_fileset):
    #     if not target_name in self.targets:
    #         raise KeyError('{} in not in targets'.format(target_name))

    #     self.targets[target_name]['filesets'] = new_fileset if isinstance(
    #         new_fileset, list) else []


class EnziIO(object):
    def __init__(self, enzi: Enzi):
        self.enzi = enzi

    def dep_versions(self, dep_id):
        dep = self.enzi.dependecy(dep_id)
        git_url = dep.source.git_url
        dep_git = self.git_database(dep.name, git_url)
        return self.git_versions(dep_git)

    def git_database(self, name, git_url) -> Git:
        # url_hash = crypt.crypt(git_url, crypt.METHOD_SHA256)[:16]
        # logger.debug("EnziIO: {}, {}".format(type(name), type(url_hash)))
        # logger.debug("EnziIO: {}, {}".format(name, url_hash))
        # db_name = name + '-' + url_hash
        # TODO: change git database name format
        db_name = name
        # TODO: cache db_dir in Enzi
        db_dir: PathBuf = self.enzi.database_path.join(
            'git').join('db').join(db_name)
        os.makedirs(db_dir.path, exist_ok=True)
        git = Git(db_dir.path, self)

        logger.debug("EnziIO:git_database: new git_db at {}, origin: {}".format(
            db_dir.path, git_url))

        git_db_records = self.enzi.git_db_records
        if name in git_db_records:
            git_db_records[name].add(db_dir.path)
        else:
            git_db_records[name] = set([db_dir.path])

        if not db_dir.join("config").exits():
            git.spawn_with(lambda x: x.arg('init').arg('--bare'))
            git.spawn_with(lambda x: x.arg('remote').arg('add')
                           .arg('origin').arg(git_url))
            git.fetch('origin')
            return git
        else:
            db_mtime = os.stat(db_dir.join('FETCH_HEAD').path).st_mtime
            if self.enzi.config_mtime < db_mtime:
                logger.debug('skip update of {}'.format(db_dir.path))
                return git
            git.fetch('origin')
            return git

    def git_versions(self, git: Git) -> GitVersions:
        dep_refs = git.list_refs()
        dep_revs = git.list_revs()

        rev_ids = set(dep_revs)

        # get tags and branches
        tags = {}
        branches = {}
        tag_prefix = "refs/tags/"
        branch_prefix = "refs/remotes/origin/"
        for rev_id, ref in dep_refs:
            if not rev_id in rev_ids:
                continue
            if ref.startswith(tag_prefix):
                tags[ref[len(tag_prefix):]] = rev_id
            elif ref.startswith(branch_prefix):
                branches[ref[len(branch_prefix):]] = rev_id

        # extract the tags that look like semver
        res_map = map(try_parse_semver, tags.items())
        versions = list(filter(lambda x: x, res_map))
        # TODO: check if this sort is correct.
        versions.sort()
        refs = {**branches, **tags}

        return GitVersions(versions, refs, dep_revs)

    def dep_config_version(self, dep_id: DependencyRef, version: DependencyVersion) -> typing.Optional[EnziConfig]:
        # from enzi.config import DependencySource as DepSrc
        # from enzi.config import DependencyVersion as DepVer
        # TODO: cache dep_config to reduce io workload

        dep = self.enzi.dependecy(dep_id)

        logger.debug("dep_config_version: get dep {}".format(dep.dump_vars()))

        if dep.source.is_git() and version.is_git():
            dep_name = dep.name
            git_url = dep.source.git_url
            is_local = dep.is_local
            git_rev = version.revision
            git_db = self.git_database(dep_name, git_url)

            entries: typing.List[TreeEntry] = git_db.list_files(
                git_rev, 'Enzi.toml')
            # actually, there is only one entry
            entry = entries[0]
            data = git_db.cat_file(entry.hash)
            logger.debug('dep_config_version: dep_name={}, db_path={}'.format(
                dep_name, git_db.path))
            # logger.debug(data)
            dep_config = EnziConfig.from_str(data, git_db.path, is_local)
            return dep_config
        else:
            raise RuntimeError('INTERNAL ERROR: unreachable')


class BackendConfigGen(object):
    def __init__(self, known_backends):
        if isinstance(known_backends, KnownBackends):
            self.known_backends = [x.__name__.lower()
                                   for x in known_backends.known_backends]
        elif isinstance(known_backends, list):
            self.known_backends = known_backends
        else:
            RuntimeError(
                'known_backends must be list or an instance of KnownBackends.')
        self.known_backends.append('vsim')
        # print(self.known_backends)

    def get(self, *, tool_name, tool_config, work_name, work_root, toplevel, fileset):
        # if tool_name.lower() == 'ies':
            # return py_copy.copy(self.ies(tool_config, work_name, work_root, toplevel, fileset))
        # elif tool_name.lower() == 'questa':
            # return
        tool_name = tool_name.lower()
        if tool_name in self.known_backends:
            config = getattr(self, tool_name)(
                tool_config, work_name, work_root, toplevel, fileset)
            return py_copy.copy(config)
        else:
            raise RuntimeError(
                'currently, Enzi does not support {} backend'.format(tool_name))

    def ies(self, ies_config, work_name, work_root, toplevel, fileset):
        config = {}

        config['toplevel'] = toplevel
        config['proj_dir'] = work_root
        config['fileset'] = fileset.get('files', [])

        if not ies_config:
            return config

        config['name'] = ies_config.get('name', '')
        config['gen_waves'] = ies_config.get('gen_waves', True)

        config['compile_log'] = ies_config.get('compile_log', '')
        config['vlog_opts'] = opts2str(ies_config.get('vlog_opts', []))
        config['vhdl_opts'] = opts2str(ies_config.get('vhdl_opts', []))
        config['vlog_defines'] = opts2str(
            ies_config.get('vlog_defines', []))
        config['vhdl_defines'] = opts2str(
            ies_config.get('vhdl_defines', []))

        config['elab_opts'] = opts2str(ies_config.get('elab_opts', []))
        config['link_libs'] = opts2str(ies_config.get('link_libs', []))
        config['elaborate_log'] = ies_config.get('elaborate_log', '')

        config['sim_opts'] = opts2str(ies_config.get('sim_opts', []))
        config['simulate_log'] = ies_config.get('simulate_log', '')
        config['silence_mode'] = ies_config.get('silence_mode', False)

        return config

    def vsim(self, vsim_config, work_name, work_root, toplevel, fileset):
        return self.questa(vsim_config, work_name, work_root, toplevel, fileset)

    def questa(self, questa_config, work_name, work_root, toplevel, fileset):
        config = {}

        config['toplevel'] = toplevel
        config['fileset'] = fileset.get('files', [])

        if not questa_config:
            return config

        config['name'] = questa_config.get('name', '')

        config['compile_log'] = questa_config.get('compile_log', '')
        config['vlog_opts'] = opts2str(questa_config.get('vlog_opts', []))
        config['vhdl_opts'] = opts2str(questa_config.get('vhdl_opts', []))
        config['vlog_defines'] = opts2str(
            questa_config.get('vlog_defines', []))
        config['vhdl_defines'] = opts2str(
            questa_config.get('vhdl_defines', []))

        config['elab_opts'] = opts2str(questa_config.get('elab_opts', []))
        config['link_libs'] = opts2str(questa_config.get('link_libs', []))
        config['elaborate_log'] = questa_config.get('elaborate_log', '')

        config['sim_opts'] = opts2str(questa_config.get('sim_opts', []))
        config['simulate_log'] = questa_config.get('simulate_log', '')
        config['silence_mode'] = questa_config.get('silence_mode', False)

        return config
