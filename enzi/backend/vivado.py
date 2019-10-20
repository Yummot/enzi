# -*- coding: utf-8 -*-

import io
import logging
import re
import os
import subprocess

from functools import partial

from enzi.backend import Backend

__all__ = ('Vivado', )

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class Vivado(Backend):
    """Vivado backend"""
    # TODO: add Windows support
    supported_system = ('Linux', )

    __work_dir__ = 'vivado-synth'

    @staticmethod
    def get_version():
        try:
            output = subprocess.check_output(['vivado', '-version'],  # pylint: disable=E1123
                                             stdin=subprocess.PIPE)
            return output.decode('utf-8').splitlines()[0]
        except Exception as e:
            logger.error(e)
            raise SystemExit(1)
    
    @staticmethod
    def get_relpath(files, root):
        if not root or not files:
            return files
        m = map(lambda x: os.path.relpath(x, root), files)
        return list(m)

    def __init__(self, config={}, work_root=None):
        self.version = Vivado.get_version()

        # vivado work root
        if not work_root:
            work_root = Vivado.__work_dir__
        else:
            work_root = os.path.join(work_root, Vivado.__work_dir__)

        super(Vivado, self).__init__(config=config, work_root=work_root)

        self.bitstream_name = config.get('bitstream_name', self.name)

        self.device_part = config.get('device_part')
        if not self.device_part:
            logger.error('No device_part is provided.')
            raise SystemExit(1)

        self.vlog_params = config.get('vlog_params', {})
        self.generics = config.get('generics', {})
        self.vlog_defines = config.get('vlog_defines', {})
        
        _fileset = config.get('fileset', {})
        src_files = _fileset.get('files', [])
        inc_dirs = _fileset.get('inc_dirs', [])
        self.src_files = Vivado.get_relpath(src_files, work_root)
        self.inc_dirs = Vivado.get_relpath(inc_dirs, work_root)

        self.synth_only = config.get('synth_only', False)
        self.build_project_only = config.get('build_project_only', False)

        has_xci = any(filter(lambda x: 'xci' in x, self.src_files))
        self.has_xci = has_xci

        # for vivado gen scripts' name only available after rendering the scripts
        self._gen_scripts_name = None
        self.configured = False

    @property
    def _makefile_vars(self):
        return {'name': self.name}

    @property
    def _program_vars(self):
        return {
            'name': self.name,
            'device_part': self.device_part
        }

    @property
    def _project_vars(self):
        return {
            'name': self.name,
            'vlog_params': self.vlog_params,
            'generics': self.generics,
            'vlog_defines': self.vlog_defines,
            'src_files': self.src_files,
            'inc_dirs': self.inc_dirs,
            'toplevel': self.toplevel,
            'has_xci': self.has_xci
        }
    

    def gen_scripts(self):
        name = self.name
        mk = 'Makefile'
        proj_tcl = name + '.tcl'
        prog_tcl = name + '_pgm.tcl'
        run_tcl = name + '_run.tcl'
        synth_tcl = name + '_synth.tcl'

        self.render_template('vivado_makefile.j2', mk, self._makefile_vars)
        self.render_template('vivado_project.tcl.j2', proj_tcl, self._project_vars)
        self.render_template('vivado_program.tcl.j2', prog_tcl, self._program_vars)
        self.render_template('vivado_run.tcl.j2', run_tcl)
        self.render_template('vivado_synth.tcl.j2', synth_tcl)

        self._gen_scripts_name = (mk, proj_tcl, prog_tcl, run_tcl, synth_tcl)

    def configure_main(self, non_lazy=False):
        exists = os.path.exists
        path_of = partial(os.path.join, self.work_root)
        if self._gen_scripts_name:
            all_exist = all(map(lambda x: exists(
                path_of(x)), self._gen_scripts_name))
        else:
            all_exist = False
        if not all_exist or non_lazy:
            logger.debug('Non lazy configuration')
            self.gen_scripts()
        else:
            logger.debug('Lazy configuration')
        self.configured = True

    def build_main(self):
        logger.debug('building')
        if not self.configured:
            self.configure()
        
        if self.build_project_only:
            self._run_tool('make', [self._gen_scripts_name[1], ])
            return
        if self.synth_only:
            self._run_tool('make', ['synth'])
            return
        self._run_tool('make', ['all'])
    
    def program_device_main(self):
        logger.debug('programming device')
        if not self.configured:
            self.configure()
        
        if self.build_project_only:
            self._run_tool('make', [self._gen_scripts_name[1], ])
            return
        if self.synth_only:
            self._run_tool('make', ['synth'])
            return

        self._run_tool('make', ['program_device'])
    
    def run_main(self):
        logger.debug('running')
        self.program_device()
