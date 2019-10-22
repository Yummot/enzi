# -*- coding: utf-8 -*-

import logging
import os
import pprint
import typing
import copy as py_copy
import networkx as nx

import enzi.project_manager
from enzi import config
from enzi.backend import KnownBackends
from enzi.config import RawConfig
from enzi.config import DependencyRef, DependencySource
from enzi.config import DependencyVersion, DependencyEntry, DependencyTable
from enzi.git import Git, GitVersions, TreeEntry
from enzi.lock import LockLoader
from enzi.utils import realpath, PathBuf

logger = logging.getLogger('Enzi')


def opts2str(opts):
    if type(opts) == list:
        return ' '.join(opts)
    else:
        return str(opts)


class Enzi(object):
    supported_targets = ['build', 'sim', 'run', 'program_device']
    __default_config__ = 'Enzi.toml'

    def __init__(self, work_dir='.', config_name='Enzi.toml', **kwargs):
        self.work_dir = realpath(work_dir)
        self.build_dir = os.path.join(self.work_dir, 'build')
        work_root_config = os.path.join(self.work_dir, config_name)
        self.config_path = work_root_config
        if os.path.exists(work_root_config):
            config = RawConfig(work_root_config).validate()
            self.config = config
        else:
            raise RuntimeError('No {} in this directory.'.format(config_name))

        # mitime in nanosecond
        self.config_mtime = self.config.file_stat.st_mtime_ns
        # targets is a reference for self.config.targets for convenience.
        self.targets = config.targets
        self.is_local = config.is_local

        self.filesets = config.filesets
        self.package = config.package
        self.name = config.name
        # self.dependencies = config.dependencies
        self.dependencies = DependencyTable()
        self.work_name = py_copy.copy(self.package['name'])
        self.tools = config.tools
        self.known_backends = KnownBackends()
        self.backend_conf_generator = BackendConfigGen(self.known_backends)

        # database
        self.database_path: PathBuf = PathBuf(self.build_dir).join('database')
        self.build_deps_path: PathBuf = PathBuf(self.build_dir).join('deps')
        self.git_db_records: typing.MutableMapping[str,
                                                   typing.MutableSet[str]] = {}

        # check if we need update database
        potential_lock_file = os.path.join(self.work_dir, 'Enzi.lock')
        self.locked = None
        if os.path.exists(potential_lock_file) and not self.config.dependencies:
            self.need_update = False
        elif os.path.exists(potential_lock_file) and self.database_path.exists():
            self.need_update = False
        elif os.path.exists(potential_lock_file) and not self.database_path.exists():
            if self.config.dependencies:
                logger.warning(
                    'no database directory found, but there is an Enzi.lock file.')
                logger.warning('Create a new database.')
            self.need_update = True
        else:
            self.need_update = None
        
        self.deps_graph = nx.DiGraph()
        self.initialized = False

        # lazy configure decision
        # if lazy_configure, no running self.configure to backend
        non_lazy = kwargs.get('non_lazy', False)
        self.non_lazy_configure = non_lazy

    def init(self, *, update=False):
        """
        Initialize the Enzi object, resolve dependencies and etc.
        """
        if self.initialized:
            return

        if not self.need_update is None:
            update |= self.need_update

        # TODO: add more useful data in lock file
        msg = 'Enzi:init: this project has dependencies, launching LockLoader'
        if update:
            msg = 'Enzi:init: this project has dependencies, launching LockLoader'
        else:
            msg = 'Enzi:init: launching LockLoader'
        
        logger.debug(msg)
        locked = LockLoader(self, self.work_dir).load(update)

        if locked.cache and 'git' in locked.cache:
            self.git_db_records = locked.cache['git']

        self.locked = locked

        dep_msg = pprint.pformat(locked.dep_dumps())
        cache_msg = pprint.pformat(locked.cache)
        logger.debug('Enzi:init: locked deps:\n{}'.format(dep_msg))
        logger.debug('Enzi:init: locked caches:\n{}'.format(cache_msg))

        if self.config_mtime != locked.config_mtime:
            self.non_lazy_configure = True

        if not self.config.dependencies:
            logger.debug('Enzi:init: this project has no dependencies')

        self.init_deps_graph()
        self.initialized = True

    def init_deps_graph(self):
        if not self.locked:
            raise RuntimeError('Enzi Frontend is not initialized')
        
        # root node
        root = self.name
        deps_graph = self.deps_graph
        deps_graph.add_node(root)

        for dep in self.config.dependencies:
            deps_graph.add_edge(root, dep)
        
        for dep_name, dep in self.locked.dependencies.items():
            this_deps = dep.dependencies
            m = map(lambda d: deps_graph.add_edge(dep_name, d), this_deps)
            _ = list(m)

        if logger.getEffectiveLevel() <= logging.DEBUG:
            pfmt = pprint.pformat(nx.dfs_successors(self.deps_graph))
            msg = 'the initialized deps graph is: \n{}'.format(pfmt)
            logger.debug(msg)

    def get_flat_fileset(self):
        """Get all the files listed in config.filesets"""
        return self.config.get_flat_fileset()

    def check_filesets(self):
        conf = self.config.into()
        conf.check_filesets()

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

    def load_dependency(self, name, dep: config.Dependency, econfig):
        if not isinstance(dep, config.Dependency):
            raise ValueError('dep must be an instance of config.Dependency')
        logger.debug('Loading dependency {} for {} with {}'.format(
            name, econfig.name, dep.git_url))
        src = config.DependencySource(dep.git_url, dep.is_local)
        dep_ref = self.dependencies.add(DependencyEntry(name, src))
        logger.debug('load_dependency: loaded(ref_id={}) {}'.format(
            dep_ref, self.dependencies.list[dep_ref.id].dump_vars()))

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
        getattr(backend, 'configure')(non_lazy=self.non_lazy_configure)

    def excute(self, target_name, backend):
        self.check_target_availability(target_name)
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

            if tool_name == 'vsim':
                logger.warning(
                    'Treat vsim tool request as using questa simulator')
                tool_config = self.tools.get('questa', {})
            else:
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
        for fileset_name in self.targets[target_name]['filesets']:
            fileset = self.filesets.get(
                fileset_name, {'files': [], })
            _files = _files + fileset.get('files', [])
        return {'files': _files, }


class BackendConfigGen(object):
    def __init__(self, known_backends):
        if isinstance(known_backends, KnownBackends):
            self.known_backends = list(known_backends.known_backends.keys())
        elif isinstance(known_backends, list):
            self.known_backends = known_backends
        else:
            RuntimeError(
                'known_backends must be list or an instance of KnownBackends.')

    def get(self, *, tool_name, tool_config, work_name, work_root, toplevel, fileset):
        tool_name = tool_name.lower()
        if tool_name in self.known_backends:
            logger.debug(
                'BackendConfigGen: generated config for backend {}'.format(tool_name))
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
        config['fileset'] = fileset

        if not ies_config:
            return config

        config['name'] = ies_config.get('name', '')
        config['silence_mode'] = ies_config.get('silence_mode', False)

        config['gen_waves'] = ies_config.get('gen_waves', True)
        config['use_uvm'] = ies_config.get('use_uvm', False)
        config['compile_log'] = ies_config.get('compile_log', 'compile.log')
        config['vlog_opts'] = opts2str(ies_config.get('vlog_opts', []))
        config['vhdl_opts'] = opts2str(ies_config.get('vhdl_opts', []))
        config['vlog_defines'] = opts2str(
            ies_config.get('vlog_defines', []))
        config['vhdl_generics'] = opts2str(
            ies_config.get('vhdl_generics', []))

        config['elab_opts'] = opts2str(ies_config.get('elab_opts', []))
        config['link_libs'] = opts2str(ies_config.get('link_libs', []))
        config['elaborate_log'] = ies_config.get(
            'elaborate_log', 'elaborate.log')

        config['sim_opts'] = opts2str(ies_config.get('sim_opts', []))
        config['simulate_log'] = ies_config.get('simulate_log', 'simulate.log')

        return config

    def vsim(self, vsim_config, work_name, work_root, toplevel, fileset):
        return self.questa(vsim_config, work_name, work_root, toplevel, fileset)

    def questa(self, questa_config, work_name, work_root, toplevel, fileset):
        config = {}

        config['toplevel'] = toplevel
        config['fileset'] = fileset

        if not questa_config:
            return config

        config['name'] = questa_config.get('name', '')
        config['silence_mode'] = questa_config.get('silence_mode', False)

        config['compile_log'] = questa_config.get('compile_log', 'compile.log')
        config['vlog_opts'] = opts2str(questa_config.get('vlog_opts', []))
        config['vhdl_opts'] = opts2str(questa_config.get('vhdl_opts', []))
        config['vlog_defines'] = opts2str(
            questa_config.get('vlog_defines', []))
        config['vhdl_generics'] = opts2str(
            questa_config.get('vhdl_generics', []))

        config['elab_opts'] = opts2str(questa_config.get('elab_opts', []))
        config['link_libs'] = opts2str(questa_config.get('link_libs', []))
        config['elaborate_log'] = questa_config.get(
            'elaborate_log', 'elaborate.log')

        config['sim_opts'] = opts2str(questa_config.get('sim_opts', []))
        config['simulate_log'] = questa_config.get(
            'simulate_log', 'simulate.log')

        return config

    def vivado(self, vivado_config, work_name, work_root, toplevel, fileset):
        config = {}

        config['toplevel'] = toplevel
        config['fileset'] = fileset

        if not vivado_config:
            return config
        
        config['name'] = vivado_config.get('name', '')
        config['silence_mode'] = vivado_config.get('silence_mode', False)
        config['bitstream_name'] = vivado_config.get('bitstream_name', config['name'])
        config['device_part'] = vivado_config.get('device_part')
        config['vlog_params'] = config.get('vlog_params', {})
        config['generics'] = config.get('generics', {})
        config['vlog_defines'] = config.get('vlog_defines', {})
        config['synth_only'] =config.get('synth_only', False)
        config['build_project_only'] = config.get('build_project_only', False)

        return config
