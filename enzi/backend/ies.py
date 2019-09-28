# -*- coding: utf-8 -*-

import logging
from collections import OrderedDict

from enzi.backend import Backend

logger = logging.getLogger(__name__)


class IES(Backend):
    def __init__(self, config={}, work_root=None):
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
        self.vlog_fileset = config.get('vlog_fileset', [])
        self.vhdl_fileset = config.get('vhdl_fileset', [])

        if self.fileset and self.vlog_fileset:
            self.fileset = [
                x for x in self.fileset if not x in self.vlog_fileset]

        if self.fileset and self.vhdl_fileset:
            self.fileset = [
                x for x in self.fileset if not x in self.vhdl_fileset]

        # IES elaborate step config
        self.elab_opts = config.get('elab_opts', None)
        self.link_libs = config.get('link_libs', [])
        self.elaborate_log = config.get('elaborate_log', None)

        # IES Simulation step config
        self.simulate_log = config.get('simulate_log', None)
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
                                  'nc_elaborate.sh', 'nc_simulate.sh', 'nc_run.sh', 'Makefile']

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
