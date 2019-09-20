#! /bin/python3
# -*- coding: utf-8 -*-

import argparse
import copy as py_copy
from collections import OrderedDict
import jinja2
import logging
import os
import stat
import subprocess

logger = logging.getLogger(__name__)


class FilesAction(argparse.Action):
    """
    argparse Action for Files args, support multiple inputs.
    """

    def __init__(self,
                 option_strings,
                 dest,
                 nargs=None,
                 const=None,
                 default=None,
                 type=None,
                 choices=None,
                 required=False,
                 help=None,
                 metavar=None):
        if nargs == 0:
            raise ValueError(
                'FileAction requires that nargs for append actions must be > 0')
        if const is not None and nargs != argparse.OPTIONAL:
            raise ValueError('nargs must be %r to supply const' %
                             argparse.OPTIONAL)
        super(FilesAction, self).__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            const=const,
            default=default,
            type=type,
            choices=choices,
            required=required,
            help=help,
            metavar=metavar)

    def __call__(self, parser, namespace, values, option_string=None):
        def _ensure_value(namespace, name, value):
            if getattr(namespace, name, None) is None:
                setattr(namespace, name, value)
            return getattr(namespace, name)

        path = os.path.expandvars(values[0])
        path = os.path.expanduser(path)
        path = os.path.abspath(path)

        paths = py_copy.copy(_ensure_value(namespace, self.dest, []))
        paths.append(path)

        setattr(namespace, self.dest, paths)


class FileAction(FilesAction):
    """
    argparse Action for File args, support only single input.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        super(FileAction, self).__call__(
            parser, namespace, values, option_string)


def value_str_filter(value, str_quote="", bool_type={False: 0, True: 1}, bool_is_str=False):
    """
    Convert a value to string that is suitable to be passed to an backend

    Internally, this filter use the str() function.

    @param str_quote: enclosed the given str with this given str_quote
    @param bool_is_str: whether to treat bool as str.
    @return: filter result
    """

    if not (0 in bool_type and 1 in bool_type):
        bool_type = {False: 'false', True: 'true'}

    if type(value) == bool:
        return str_quote + str(bool_type[value]) + str_quote if bool_is_str else str(bool_type[value])
    elif type(value) == str:
        return str_quote + str(value) + str_quote
    else:
        return str(value)

# print(value_str_filter(True))
# print(value_str_filter(False))
# print(value_str_filter(False, bool_type={ True: 1, False: 0 }))
# print(value_str_filter(False, bool_type={ True: 1, False: 0 }, bool_is_str=1))
# print(value_str_filter(False, bool_type={ True: 1, False: 0 }, bool_is_str=1))
# print(value_str_filter(False, str_quote="'", bool_type={ True: 1, False: 0 }, bool_is_str=1))
# print(value_str_filter(dict(), str_quote="'"))
# print(value_str_filter("xxxx", str_quote="'"))


class BackendCallback(object):
    def pre(self):
        pass

    def post(self):
        pass


class backend(object):
    """
    initialize an Backend object

    @param  config:     An dict contains backend configurations.
                        It must contain an key name which store current project name.
    @param  work_root:  The root directory of running this backend work
    """

    supported_ops = ['build', 'sim', 'run', 'program_device']

    def __init__(self, config=None, work_root=None):
        if config is None:
            raise RuntimeError(
                "An minimal config for running backend with \"name\" must provide.")
        elif not (type(config) == dict or issubclass(config.__class__, dict)):
            raise RuntimeError(
                "config must be a dict.")
        try:
            self.name = config['name']
        except KeyError:
            raise RuntimeError(
                "Missing required parameter \"name\" in config.")

        self.toplevel = config.get('toplevel', None)
        self.work_root = work_root if work_root is not None else ''
        self.env = os.environ.copy()
        self.env['WORK_ROOT'] = self.work_root
        self.silence_mode = config.get('silence_mode')

        # jinja2 environment
        self.j2_env = jinja2.Environment(
            loader=jinja2.PackageLoader(__package__, 'templates'),
            # loader=jinja2.FileSystemLoader('./src/templates'),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        self.j2_env.filters['value_str'] = value_str_filter

        # TODO: currently, each backend op only support one callback, multi-callbacks for one op may be added.
        self.cbs = {
            'build': BackendCallback(),
            'run': BackendCallback(),
            'sim': BackendCallback(),
            'program_device': BackendCallback()
        }

    # TODO: Add a checker fn to abort running backend without the corresponding backend tool.

    def render_template(self, template_file, target_file, template_vars={}):
        template_dir = str(self.__class__.__name__).lower()
        template = self.j2_env.get_template(
            '/'.join([template_dir, template_file]))
        file_path = os.path.join(self.work_root, target_file)
        with open(file_path, 'w') as f:
            f.write(template.render(template_vars))
            if file_path.endswith('.sh'):
                script_stat = os.stat(file_path)
                os.chmod(file_path, script_stat.st_mode | stat.S_IEXEC)

    def _run_scripts(self, scripts):
        """
        @param scripts: it contains a list of script to run, each script is a dict,
                        which may contains:
                            @key env: env for running this script.
                            @key cmd: script command to run.

        """
        for script in scripts:
            script_stat = os.stat(os.path.join(self.work_root, script))
            os.chmod(script, script_stat.mode | stat.S_IEXEC)

            backend_env = self.env.copy()
            if 'env' in script:
                backend_env.update(script['env'])
            logger.info("Running " + script['name'])
            try:
                if self.silence_mode:
                    subprocess.check_call(script['cmd'],
                                          cwd=self.work_root,
                                          #   stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL,
                                          env=backend_env)
                else:
                    subprocess.check_call(script['cmd'],
                                          cwd=self.work_root,
                                          env=backend_env)
            except subprocess.CalledProcessError as e:
                raise RuntimeError("'{}' exited with error code {}".format(
                    script['name'], e.returncode))

    def _run_tool(self, cmd, args=[]):
        logger.debug("Running " + cmd)
        logger.debug("args  : " + ' '.join(args))

        try:
            if self.silence_mode:
                # TODO: define the silence_mode behaviour in backend._run_tool
                subprocess.check_call([cmd] + args,
                                      cwd=self.work_root,
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.DEVNULL)
            else:
                subprocess.check_call([cmd] + args,
                                      cwd=self.work_root,
                                      stdin=subprocess.PIPE)
        except FileNotFoundError:
            _s = "Command '{}' not found. Make sure it is in $PATH."
            raise RuntimeError(_s.format(cmd))
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                "Error: '{}' exited {}".format(cmd, e.returncode))

    def run_main(self):
        pass

    def sim_main(self):
        pass

    def build_main(self):
        pass

    def program_device_main(self):
        pass

    def run(self):
        run_cb = self.cbs['run']
        run_cb.pre()
        self.run_main()
        run_cb.post()

    def sim(self):
        sim_cb = self.cbs['sim']
        sim_cb.pre()
        self.sim_main()
        sim_cb.post()

    def build(self):
        build_cb = self.cbs['build']
        build_cb.pre()
        self.build_main()
        build_cb.post()

    def program_device(self):
        program_device_cb = self.cbs['program_device']
        program_device_cb.pre()
        self.program_device_main()
        program_device_cb.post()

    def configure_main(self):
        pass

    def configure(self):
        self.configure_main()


class IES(backend):
    def __init__(self, config=None, work_root=None):
        # general run config
        self.gen_waves = config.get('gen_waves', True)
        self.proj_dir = config.get('proj_dir', '.')

        # IES compile step config
        self.compile_log = config.get('compile_log', None)
        self.vlog_opts = config.get('vlog_opts', None)
        self.vhdl_opts = config.get('vhdl_opts', None)
        self.vlog_defines = config.get('vlog_defines', None)
        self.vhdl_defines = config.get('vhdl_defines', None)

        _fileset = config.get('fileset', []) + config.get('files', [])
        self.fileset = list(OrderedDict.fromkeys(_fileset))
        # print(self.fileset)
        self.vlog_fileset = config.get('vlog_fileset', [])
        self.vhdl_fileset = config.get('vhdl_fileset', [])

        if self.fileset and self.vlog_fileset:
            self.fileset = [
                x for x in self.fileset if not x in self.vlog_fileset]

        if self.fileset and self.vhdl_fileset:
            self.fileset = [
                x for x in self.fileset if not x in self.vhdl_fileset]
        # print(self.fileset)

        # IES elaborate step config
        self.elab_opts = config.get('elab_opts', None)
        self.link_libs = config.get('link_libs', [])
        self.elaborate_log = config.get('elaborate_log', None)

        # IES Simulation step config
        self.simulate_log = config.get('compile_log', None)
        self.sim_opts = config.get('sim_opts', None)

        self._gui_mode = False

        super(IES, self).__init__(config=config, work_root=work_root)

    @property
    def _waves_vars(self):
        return {'toplevel': self.toplevel}

    @property
    def _run_vars(self):
        return {'proj_dir': self.proj_dir}

    @property
    def _setup_vars(self):
        return {}

    @property
    def _simluate_vars(self):
        return {'sim_opts': self.sim_opts, 'toplevel': self.toplevel, 'gen_waves': self.gen_waves, "simulate_log": self.simulate_log}

    @property
    def _compile_vars(self):
        return {
            "vlog_opts": self.vlog_opts,
            "vhdl_opts": self.vhdl_opts,
            'compile_log': self.compile_log,
            "vlog_defines": self.vlog_defines,
            "vhdl_defines": self.vhdl_defines,
            "vlog_fileset": self.vlog_fileset,
            "vhdl_fileset": self.vhdl_fileset,
            "fileset": self.fileset,
        }

    @property
    def _elaborate_vars(self):
        return {
            "elab_opts": self.elab_opts,
            "elaborate_log": self.elaborate_log,
            "link_libs": self.link_libs,
            "toplevel": self.toplevel,
        }

    @property
    def _makefile_vars(self):
        return {'gen_waves': self.gen_waves}

    @property
    def gui_mode(self):
        return self._gui_mode

    @gui_mode.setter
    def gui_mode(self, value):
        if not isinstance(value, bool):
            raise ValueError('score must be an integer!')
        self._gui_mode = value

    def gen_scripts(self):
        self.render_template('waves.tcl.j2',
                             'waves.tcl', self._waves_vars)
        self.render_template(
            'nc_setup.sh.j2', 'nc_setup.sh', self._setup_vars)
        self.render_template('nc_compile.sh.j2',
                             'nc_compile.sh', self._compile_vars)
        self.render_template('nc_elaborate.sh.j2',
                             'nc_elaborate.sh', self._elaborate_vars)
        self.render_template('nc_simulate.sh.j2',
                             'nc_simulate.sh', self._simluate_vars)
        self.render_template('nc_run.sh.j2', 'nc_run.sh', self._run_vars)
        self.render_template('nc_makefile.j2', 'Makefile', self._makefile_vars)

        self._gen_scripts_name = ['waves.tcl', 'nc_setup.sh', 'nc_compile.sh',
                                  'nc_elaborate.sh', 'nc_simulate.sh', 'nc_run.sh']

    def configure_main(self):
        self.gen_scripts()

    def build_main(self):
        logger.info('building')
        self._run_tool('make', ['build'])

    def run_main(self):
        logger.info('running')
        if self.gui_mode:
            self._run_tool('make', ['run-gui'])
        else:
            self._run_tool('make', ['run'])

    def sim_main(self):
        logger.info('cleanup')
        if self.gui_mode:
            self._run_tool('make', ['sim-gui'])
        else:
            self._run_tool('make', ['sim'])

    def clean(self):
        logger.info('cleanup')
        self._run_tool('make', ['clean'])

    def clean_waves(self):
        if self.gen_waves:
            self._run_tool('make', ['clean_waves'])


class KnownBackends(object):
    """
    Factory class for backends.
    Currently, the available backends are: ies.
    TODO: more backends may be added, if we get acess to use them.
    """

    def __init__(self):
        self.known_backends = backend.__subclasses__()

    def get(self, backend_name, config, work_root):
        if not backend_name:
            raise RuntimeError('No backend name specified.')
        for backend in self.known_backends:
            if backend_name.lower() == backend.__name__.lower():
                return backend(config, work_root)

        # given backend name is not in support list.
        raise NameError('backend name {} not found'.format(backend_name))


# ies_config = {
#     'gen_waves': True,
#     'proj_dir': os.getcwd(),
#     'toplevel': 'tb',
#     'name': 'test',
#     "vlog_fileset": [
#         "./include/test_clk_if.sv",
#         "./src/arb_tree.sv",
#         "./src/req_mux2.sv",
#         "./src/req_rr_flag.sv",
#         "./tb/tb.sv"
#     ],
# }
# ies = KnownBackends().get('ies', ies_config, './build')
# print(ies.__class__.__name__)
# ies.gen_scripts()
# ies.build()
# ies.sim()
# ies.run()
# ies.clean()
# ies.clean_waves()

# be = backend({'name': 'test'}, './build')

# config = {
#     'gen_waves': True,
#     'proj_dir': os.getcwd(),
#     'toplevel': 'tb',
#     'name': 'test',
#     "vlog_fileset": [
#         "./include/test_clk_if.sv",
#         "./src/arb_tree.sv",
#         "./src/req_mux2.sv",
#         "./src/req_rr_flag.sv",
#         "./tb/tb.sv"
#     ],
# }
# ies = IES(config, './build')
# ies.gen_scripts()

# config = {
#     'proj_dir': os.getcwd(),
#     'toplevel': 'tb',
#     'name': 'test',
#     "vlog_opts": "xxx",
#     "vhdl_opts": "xxx",
#     "compile_log": "x.log",
#     "fileset": ["x.sv", "zzz.sv"],
#     "files": ["x.sv", "y.v"],
#     "vlog_defines": "  xx",
#     "vlog_fileset": ["x.v", "y.v", "z.sv"],
#     "vhdl_defines": " xxx",
#     "vhdl_fileset": ["x.vhd", "y.vhdl", "z.sv"],
#     'elab_opts': 'xxxx',
#     'elaborate_log': 'x.log',
#     'link_libs': ['uvm', 'svunit'],
#     "sim_opts": "xxxx",
#     "simulate_log": "x.log"
# }
# ies = IES(config, './build')
# ies.gen_scripts()

# # print(os.path.join('.', "build"))

# with open('./build/be_nc_c.sh', 'w') as f:
#     t_vars = {
#         "vlog_opts": "xxx",
#         "vhdl_opts": "xxx",
#         "compile_log": "x.log",
#         "vlog_defines": "  xx",
#         "vlog_fileset": ["x.v", "y.v", "z.sv"],
#         "vhdl_defines": " xxx",
#         "vhdl_fileset": ["x.vhd", "y.vhdl", "z.sv"],
#     }
#     template = be.j2_env.get_template('./ies/nc_compile.sh.j2')
#     f.write(template.render(t_vars))

# with open('./build/be_nc_su.sh', 'w') as f:
#     t_vars = {}
#     template = be.j2_env.get_template('nc_setup.sh.j2')
#     f.write(template.render(t_vars))

# with open('./build/be_nc_r.sh', 'w') as f:
#     t_vars = {'proj_dir': '.'}
#     template = be.j2_env.get_template('nc_run.sh.j2')
#     f.write(template.render(t_vars))

# with open('./build/be_nc_si.sh', 'w') as f:
#     t_vars = {'sim_opts': ' ', 'toplevel': 'tb', 'gen_waves': True}
#     template = be.j2_env.get_template('nc_simulate.sh.j2')
#     f.write(template.render(t_vars))


# with open('./build/be_nc_w.tcl', 'w') as f:
#     t_vars = {'toplevel': 'tb'}
#     template = be.j2_env.get_template('waves.tcl.j2')
#     f.write(template.render(t_vars))

# with open('./build/be_nc_e.sh', 'w') as f:
#     t_vars = {'elab_opts': 'xxxx', 'elaborate_log': 'x.log', 'link_libs': ['uvm', 'svunit'], 'toplevel': 'tb'}
#     template = be.j2_env.get_template('nc_elaborate.sh.j2')
#     f.write(template.render(t_vars))

# x = {'a': ''}
# if 'a' in x and x['a']:
#     print('xxxx')
