# -*- coding: utf-8 -*-

import io
import logging
import re
import os
import subprocess

from collections.abc import Mapping, Iterable
from functools import partial
from ordered_set import OrderedSet

from enzi.backend import Backend
from enzi.utils import flat_map

__all__ = ('Vivado', )

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

def inc_dir_filter(files):
    """inc_dir_filter for vivado"""
    if not files:
        return ''

    dedup_files = OrderedSet()
    if isinstance(files, Mapping):
        m = map(lambda i: dedup_files.update(i), files.values())
    elif isinstance(files, list):
        m = map(lambda i: dedup_files.update(i), files)
    else:
        fmt = 'unreachable files type shouldn\'t be {}'
        msg = fmt.format(files.__class__.__name__)
        logger.error(msg)
        raise RuntimeError(msg)
    _ = set(m)
    return ' '.join(dedup_files)


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
        except Exception:
            logger.error('Cannot call vivado, make sure it is in path.')
            raise SystemExit(1)

    @staticmethod
    def get_relpath(files, root):
        if not root or not files:
            return files
        if type(files) == list:
            m = map(lambda x: os.path.relpath(x, root), files)
            return list(m)
        elif isinstance(files, Mapping):
            def _relpath(item):
                file, incdirs = item
                file = os.path.relpath(file, root)
                if isinstance(incdirs, Iterable):
                    _m = map(lambda x: os.path.relpath(x, root), incdirs)
                    incdirs = list(_m)
                else:
                    incdirs = os.path.relpath(incdirs, root)
                return (file, incdirs)
            m = map(_relpath, files.items())
            return dict(m)
        else:
            raise RuntimeError('unreachable!')

    def __init__(self, config={}, work_root=None):
        self.version = Vivado.get_version()

        # vivado work root
        if not work_root:
            work_root = Vivado.__work_dir__
        else:
            work_root = os.path.join(work_root, Vivado.__work_dir__)
            os.makedirs(work_root, exist_ok=True)

        super(Vivado, self).__init__(config=config, work_root=work_root)

        self.bitstream_name = config.get('bitstream_name', self.name)

        self.device_part = config.get('device_part')
        if not self.device_part:
            logger.error('No device_part is provided.')
            raise SystemExit(1)

        self.vlog_params = config.get('vlog_params', {})
        self.generics = config.get('generics', {})
        self.vlog_defines = config.get('vlog_defines', {})

        # construct src_files for vivado backend
        self.src_files = self.fileset

        # filter relative path
        # construct inc_dirs for vivado backend
        inc_dirs = []
        ext_f = lambda x: inc_dirs.extend(x.get_flat_incdirs())
        m = map(ext_f, self.fileset.values())
        _ = list(m)
        self.inc_dirs = Vivado.get_relpath(inc_dirs, work_root)

        self.synth_only = config.get('synth_only', False)
        self.build_project_only = config.get('build_project_only', False)

        flattern = flat_map(lambda x: x.files, self.src_files.values())
        has_xci = any(filter(lambda x: 'xci' in x, flattern))
        self.has_xci = has_xci

        self.j2_env.filters['src_file_filter'] = self.src_file_filter
        self.j2_env.filters['inc_dir_filter'] = inc_dir_filter

        # for vivado gen scripts' name only available after rendering the scripts
        self._gen_scripts_name = None
        self.configured = False

    def src_file_filter(self, f):
        file_types = {
            'vh': 'read_verilog',
            'v': 'read_verilog',
            'svh': 'read_verilog -sv',
            'sv': 'read_verilog -sv',
            'vhd': 'read_vhdl',
            'vhdl': 'read_vhdl',
            'xci': 'read_ip',
            'xdc': 'read_xdc',
            'tcl': 'source',
            'sdc': 'read_xdc -unmanaged',
        }
        _, ext = os.path.splitext(f)
        if ext:
            ext = ext[1:].lower()
        if ext in file_types:
            f = os.path.relpath(f, self.work_root)
            return file_types[ext] + ' ' + f
        else:
            return ''

    @property
    def _makefile_vars(self):
        return {'name': self.name}

    @property
    def _program_vars(self):
        return {
            'bitstream_name': self.name,
            'device_part': self.device_part
        }

    @property
    def _project_vars(self):
        return {
            'name': self.name,
            'device_part': self.device_part,
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
        self.render_template('vivado_project.tcl.j2',
                             proj_tcl, self._project_vars)
        self.render_template('vivado_program.tcl.j2',
                             prog_tcl, self._program_vars)
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

        # check bitstream existence
        bitstream_name = self.bitstream_name + '.bit'
        bitstream_path = os.path.join(self.work_root, bitstream_name)
        if not os.path.exists(bitstream_path):
            logger.error('Bitstream not exists.Call enzi build to build bitstream.')
            raise SystemExit(1)

        self._run_tool('make', ['program_device'])

    def run_main(self):
        logger.debug('running')
        self.program_device()
