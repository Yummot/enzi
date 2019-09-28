#! /bin/python3
# -*- coding: utf-8 -*-

import argparse
import jinja2
import logging
import os
import stat
import subprocess
import copy as py_copy
from collections import OrderedDict

from enzi.utils import realpath

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

        path = realpath(values[0])

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
    Convert a value to string that is suitable to be passed to an Backend

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

class BackendCallback(object):
    def pre(self):
        pass

    def post(self):
        pass


class Backend(object):
    """
    initialize an Backend object

    @param  config:     An dict contains Backend configurations.
                        It must contain an key name which store current project name.
    @param  work_root:  The root directory of running this Backend work
    """

    supported_ops = ['build', 'sim', 'run', 'program_device']

    def __init__(self, config={}, work_root=None):
        if config is None:
            raise RuntimeError(
                "An minimal config for running Backend with \"name\" must provide.")
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

        # TODO: currently, each Backend op only support one callback, multi-callbacks for one op may be added.
        self.cbs = {
            'build': BackendCallback(),
            'run': BackendCallback(),
            'sim': BackendCallback(),
            'program_device': BackendCallback()
        }

        self._gen_scripts_name = None

    # TODO: Add a checker fn to abort running Backend without the corresponding Backend tool.

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
        logger.debug("Running {} with args: {}" .format(cmd, args))

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
    
    def clean(self):
        pass
