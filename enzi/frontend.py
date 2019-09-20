import os
import copy as py_copy
import logging
# import file_manager
import enzi.project_manager
from enzi.backend import KnownBackends
from enzi.parse_config import Config as EnziConfig

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
        self.work_dir = work_dir
        self.build_dir = work_dir + '/build'
        work_root_config = '/'.join([work_dir, config_name])
        if os.path.exists(work_root_config):
            config = EnziConfig(work_root_config)
        else:
            raise RuntimeError('No Enzi.toml in this directory.')

        # targets is a reference for self.config.targets for convenience.
        self.targets = config.targets
        self.is_local = config.is_local

        # TODO: currently the dependencies field in a fileset of config.filesets is just an placeholder.
        self.filesets = config.filesets
        self.package = config.package
        self.work_name = py_copy.copy(self.package['name'])
        self.tools = config.tools
        self.known_backends = KnownBackends()
        self.backend_conf_generator = BackendConfigGen(self.known_backends)

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

    def run_target(self, target_name, filelist=None):
        if not target_name in self.targets:
            raise RuntimeError('{} in not in targets'.format(target_name))
        if not target_name in self.supported_targets:
            raise RuntimeError(
                '{} in not in current supprot targets'.format(target_name))

        backend = self.get_backend(target_name, filelist=filelist)
        self.configure(target_name, backend)
        self.excute(target_name, backend)

    def configure(self, target_name, backend):
        if not target_name in self.targets:
            raise RuntimeError('{} in not in targets'.format(target_name))
        if not target_name in self.supported_targets:
            raise RuntimeError(
                '{} in not in current supprot targets'.format(target_name))

        getattr(backend, 'configure')()

    def excute(self, target_name, backend):
        if not target_name in self.targets:
            raise RuntimeError('{} in not in targets'.format(target_name))
        if not target_name in self.supported_targets:
            raise RuntimeError(
                '{} in not in current supprot targets'.format(target_name))

        # backend = self.get_backend(target_name)
        getattr(backend, target_name)()

    def get_backend(self, target_name, **kwargs):
        if target_name in self.targets:
            # print(target_name)

            target = self.targets[target_name]
            target_toplevel = target.get('toplevel', '')
            target_fileset = []
            if not 'filelist' in kwargs:
                target_fileset = self.gen_target_fileset(target_name)
            else:
                target_fileset = kwargs['filelist']

            tool_name = str(target['default_tool'])
            tool_config = self.tools.get(tool_name)
            tool_config['silence_mode'] = self.silence_mode

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

            return self.known_backends.get(tool_name, backend_config, self.build_dir)
        else:
            raise RuntimeError('{} in not in targets'.format(target_name))

    def abs_fileset(self, fileset):
        ret = py_copy.copy(fileset)
        return ret

    def gen_target_fileset(self, target_name):
        if not target_name in self.targets:
            raise KeyError('{} in not in targets'.format(target_name))

        _files = []
        _deps = []
        for fileset_name in self.targets[target_name]['filesets']:
            fileset = self.filesets.get(
                fileset_name, {'files': [], 'dependencies': []})
            _files = _files + fileset.get('files', [])
            _deps = _deps + fileset.get('dependencies', [])
        return {'files': _files, 'dependencies': _deps}

    # def update_target_fileset(self, target_name, new_fileset):
    #     if not target_name in self.targets:
    #         raise KeyError('{} in not in targets'.format(target_name))

    #     self.targets[target_name]['filesets'] = new_fileset if isinstance(
    #         new_fileset, list) else []


class BackendConfigGen(object):
    def __init__(self, known_backends):
        if isinstance(known_backends, KnownBackends):
            self.known_backends = known_backends.known_backends
        elif isinstance(known_backends, list):
            self.known_backends = known_backends
        else:
            RuntimeError(
                'known_backends must be list or an instance of KnownBackends.')

    def get(self, *, tool_name, tool_config, work_name, work_root, toplevel, fileset):
        if tool_name.lower() == 'ies':
            return py_copy.copy(self.ies(tool_config, work_name, work_root, toplevel, fileset))

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


# s = Enzi('.')
# # pprint.pprint(s.gen_target_fileset('sim'))
# # pprint.pprint(
# #     s.backend_conf_generator.get(
# #         tool_name='ies',
# #         tool_config=s.tools['ies'],
# #         work_name=s.work_name,
# #         work_root='./build',
# #         toplevel=s.targets['sim']['toplevel'],
# #         fileset=s.gen_target_fileset('sim')
# #     )
# # )
# project_manager = project_manager.ProjectFiles(s)

# for target, v in s.targets.items():
#     print(target)
#     fileset = s.gen_target_fileset(target)
#     project_manager.fetch(target)
#     s.run_target(target, project_manager.get_fileset(target))

# pprint.pprint(s.gen_target_fileset('run'))

# import pprint
# pprint.pprint(s._ies_backend_config(s.tools['ies']['params'], s.targets['sim']['toplevel']))
