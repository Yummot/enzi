# -*- coding: utf-8 -*-

import logging
import os

from collections import OrderedDict
from functools import partial

from enzi.backend import Backend

__all__ = ('IES', )

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class IES(Backend):
    def __init__(self, config={}, work_root=None):
        CDSHOME = os.environ.get('CDSHOME', None)
        if not CDSHOME:
            msg = 'CDSHOME environment variable is not set, you must set it as the path to IES install folder'
            logger.error(msg)
            raise SystemExit(1)

        # general run config
        self.gen_waves = config.get('gen_waves', True)
        self.proj_dir = config.get('proj_dir', '.')

        # IES compile step config
        self.compile_log = config.get('compile_log', None)
        self.vlog_opts = config.get('vlog_opts', None)
        self.vhdl_opts = config.get('vhdl_opts', None)
        self.vlog_defines = config.get('vlog_defines', None)
        self.vhdl_defines = config.get('vhdl_defines', None)

        _fileset = config.get('fileset', {})
        self.fileset = _fileset.get('files', [])
        self.inc_dirs = _fileset.get('inc_dirs', [])

        self.use_uvm = config.get('use_uvm', False)

        # IES elaborate step config
        self.elab_opts = config.get('elab_opts', None)
        self.link_libs = config.get('link_libs', [])
        self.elaborate_log = config.get('elaborate_log', None)

        # IES Simulation step config
        self.simulate_log = config.get('simulate_log', None)
        self.sim_opts = config.get('sim_opts', None)

        self._gui_mode = False

        super(IES, self).__init__(config=config, work_root=work_root)

        self._gen_scripts_name = {'nc_waves.tcl', 'nc_setup.sh', 'nc_compile.sh',
                                  'nc_elaborate.sh', 'nc_simulate.sh', 'nc_run.sh', 'nc_make.mk'}

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
    def _simulate_vars(self):
        return {
            'sim_opts': self.sim_opts, 
            'toplevel': self.toplevel, 
            'gen_waves': self.gen_waves, 
            "simulate_log": self.simulate_log,
            "use_uvm": self.use_uvm,
        }

    @property
    def _compile_vars(self):
        return {
            "vlog_opts": self.vlog_opts,
            "vhdl_opts": self.vhdl_opts,
            'compile_log': self.compile_log,
            "vlog_defines": self.vlog_defines,
            "vhdl_defines": self.vhdl_defines,
            "fileset": self.fileset,
            "inc_dirs": self.inc_dirs,
            "use_uvm": self.use_uvm,
        }

    @property
    def _elaborate_vars(self):
        return {
            "elab_opts": self.elab_opts,
            "elaborate_log": self.elaborate_log,
            "link_libs": self.link_libs,
            "toplevel": self.toplevel,
            "use_uvm": self.use_uvm,
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
            raise ValueError('gui mode type must be bool!')
        self._gui_mode = value

    def gen_scripts(self):
        self.render_template('nc_waves.tcl.j2',
                             'nc_waves.tcl', self._waves_vars)
        self.render_template(
            'nc_setup.sh.j2', 'nc_setup.sh', self._setup_vars)
        self.render_template('nc_compile.sh.j2',
                             'nc_compile.sh', self._compile_vars)
        self.render_template('nc_elaborate.sh.j2',
                             'nc_elaborate.sh', self._elaborate_vars)
        self.render_template('nc_simulate.sh.j2',
                             'nc_simulate.sh', self._simulate_vars)
        self.render_template('nc_run.sh.j2', 'nc_run.sh', self._run_vars)
        self.render_template(
            'nc_makefile.j2', 'nc_make.mk', self._makefile_vars)

    def configure_main(self, non_lazy=False):
        exists = os.path.exists
        path_of = partial(os.path.join, self.work_root)
        all_exist = all(map(lambda x: exists(
            path_of(x)), self._gen_scripts_name))
        if not all_exist or non_lazy:
            logger.debug('Non lazy configuration')
            self.gen_scripts()
        else:
            logger.debug('Lazy configuration')

    def build_main(self):
        logger.info('building')
        self._run_tool('make', ['-f', 'nc_make.mk', 'build'])

    def run_main(self):
        logger.info('running')
        if self.gui_mode:
            self._run_tool('make', ['-f', 'nc_make.mk', 'run-gui'])
        else:
            self._run_tool('make', ['-f', 'nc_make.mk', 'run'])

    def sim_main(self):
        logger.info('cleanup')
        if self.gui_mode:
            self._run_tool('make', ['-f', 'nc_make.mk', 'sim-gui'])
        else:
            self._run_tool('make', ['-f', 'nc_make.mk', 'sim'])

    def clean(self):
        logger.info('cleanup')
        self._run_tool('make', ['-f', 'nc_make.mk', 'clean'])

    def clean_waves(self):
        if self.gen_waves:
            self._run_tool('make', ['-f', 'nc_make.mk', 'clean_waves'])
