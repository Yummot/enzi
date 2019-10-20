#! /bin/python3
# -*- coding: utf-8 -*-

import argparse
import io
import jinja2
import logging
import os
import platform
import stat
import subprocess
import copy as py_copy
from collections import OrderedDict

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

__all__ = ['value_str_filter', 'BackendCallback', 'Backend']


def value_str_filter(value, *, str_quote="", bool_is_str=False, bool_type=None):
    """
    Convert a value to string that is suitable to be passed to an Backend

    Internally, this filter use the str() function.

    :param str_quote: enclosed the given str with this given str_quote
    :param bool_is_str: whether to treat bool as str.
    @return: filter result
    """

    if not bool_type:
        if bool_is_str:
            bool_type = ('false', 'true')
        else:
            bool_type = (0, 1)

    if type(value) == bool:
        return str(bool_type[1]) if value else str(bool_type[0])
    elif type(value) == str:
        return str_quote + str(value) + str_quote
    else:
        return str(value)

INC_DIR_PREFIX = '+incdir+'

def inc_dirs_filter(files):
    if not files:
        return ''
    add_prefix = map(lambda f: INC_DIR_PREFIX + f, files)
    return '\n'.join(add_prefix)

def src_inc_filter(file):
    """
    filter a src file path str/dict/object to a src path string.
    If the file dict/object contain a inc_dirs key, construct a src
    path will +incdir+<inc_dir>*. 
    """
    if type(file) == str:
        return file
    if isinstance(file, dict):
        if 'inc_dirs' in file:
            idirs = inc_dirs_filter(file['inc_dir'])
            return idirs + file['src']
        else:
            return file['src']
    if hasattr(file, 'inc_dirs'):
        idirs = inc_dirs_filter(file.inc_dirs)
        return idirs + file.src
    return file.src


class BackendCallback(object):
    def pre(self):
        pass

    def post(self):
        pass


class Backend(object):
    """
    initialize an Backend object

    :param  config:     An dict contains Backend configurations.
                        It must contain an key name which store current project name.
    :param  work_root:  The root directory of running this Backend work
    """

    supported_ops = ['build', 'sim', 'run', 'program_device']
    # backend are assumed to support at least Linux('s distribution)
    supported_system = ('Linux', )
    

    def __init__(self, config={}, work_root=None):
        if config is None:
            raise RuntimeError(
                "An minimal config for running Backend with \"name\" must provide.")
        elif not (type(config) == dict or issubclass(config.__class__, dict)):
            raise RuntimeError(
                "config must be a dict.")
        try:
            self.name = config['name']
        except KeyError as e:
            raise RuntimeError(
                "Missing required parameter \"name\" in config.") from e

        self._gui_mode = config.get('gui_mode', False)
        self.toplevel = config.get('toplevel')
        if not self.toplevel:
            fmt = 'no toplevel was provided to backend{}'
            msg = fmt.format(self.__class__.__name__)
            logger.error(msg)
            raise SystemExit(128)
        self.work_root = work_root if work_root is not None else ''
        self.env = os.environ.copy()
        self.env['WORK_ROOT'] = self.work_root
        self.silence_mode = config.get('silence_mode')

        self.config = config

        # jinja2 environment
        self.j2_env = jinja2.Environment(
            loader=jinja2.PackageLoader(__package__, 'templates'),
            # loader=jinja2.FileSystemLoader('./src/templates'),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        self.j2_env.filters['value_str'] = value_str_filter
        self.j2_env.filters['inc_dirs_filter'] = inc_dirs_filter
        self.j2_env.filters['src_inc_filter'] = src_inc_filter

        # TODO: currently, each Backend op only support one callback, multi-callbacks for one op may be added.
        self.cbs = {
            'build': BackendCallback(),
            'run': BackendCallback(),
            'sim': BackendCallback(),
            'program_device': BackendCallback()
        }

        self._gen_scripts_name = set()
        self.current_system = platform.system()

    @property
    def gui_mode(self):
        return self._gui_mode

    @gui_mode.setter
    def gui_mode(self, value):
        if not isinstance(value, bool):
            raise ValueError('gui mode type must be bool!')
        self._gui_mode = value

    # TODO: Add a checker fn to abort running Backend without the corresponding Backend tool.

    def render_template(self, template_file, target_file, template_vars={}):
        template_dir = str(self.__class__.__name__).lower()
        template = self.j2_env.get_template(
            os.path.join(template_dir, template_file))
        file_path = os.path.join(self.work_root, target_file)

        f = io.FileIO(file_path, 'w')
        writer = io.BufferedWriter(f)
        data = template.render(template_vars).encode('utf-8')
        writer.write(data)
        writer.close()

        if file_path.endswith('.sh'):
            script_stat = os.stat(file_path)
            os.chmod(file_path, script_stat.st_mode | stat.S_IEXEC)

    def _run_scripts(self, scripts):
        """
        :param scripts: it contains a list of script to run, each script is a dict,
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
                    script['name'], e.returncode)) from e

    def _run_tool(self, cmd, args=[], stdout=None):
        logger.debug("Running {} with args: {}" .format(cmd, args))

        stdout = stdout if stdout else subprocess.DEVNULL

        try:
            if self.silence_mode:
                # TODO: define the silence_mode behaviour in backend._run_tool
                subprocess.check_call([cmd] + args,
                                      cwd=self.work_root,
                                      stdin=subprocess.PIPE,
                                      stdout=stdout)
            else:
                subprocess.check_call([cmd] + args,
                                      cwd=self.work_root,
                                      stdin=subprocess.PIPE)
        except FileNotFoundError as e:
            _s = "Command '{}' not found. Make sure it is in $PATH."
            raise RuntimeError(_s.format(cmd)) from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                "Error: '{}' exited {}".format(cmd, e.returncode)) from e
    
    def _backend_warn(self, fmt):
        """backend warning for an unimplemented target"""
        cls_name = self.__class__.__name__
        msg = fmt.format(cls_name)
        logger.warning(msg)
        logger.warning('Nothing to do.')

    def run_main(self):
        fmt = '{} does not have the ability to "run" HDL'
        self._backend_warn(fmt)

    def sim_main(self):
        fmt = '{} does not have the ability to simulate HDL.'
        self._backend_warn(fmt)

    def build_main(self):
        fmt = '{} does not have the ability to build HDL.'
        self._backend_warn(fmt)

    def program_device_main(self):
        fmt = '{} does not have the ability to synthesize HDL.'
        self._backend_warn(fmt)

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

    def configure_main(self, *, non_lazy=False):
        pass

    def configure(self, *, non_lazy=False):
        self.configure_main(non_lazy=non_lazy)

    def clean(self):
        pass
