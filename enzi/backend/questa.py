# -*- coding: utf-8 -*-

import io
import logging
import os
import subprocess

from collections import OrderedDict
from functools import partial

from enzi.backend import Backend

__all__ = ('Questa', )

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class Questa(Backend):
    supported_system = ('Linux', 'Windows',)

    def __init__(self, config={}, work_root=None):
        self._gui_mode = False

        self.compile_log = config.get('compile_log', 'compile.log')
        self.vlog_opts = config.get('vlog_opts', None)
        self.vhdl_opts = config.get('vhdl_opts', None)
        self.vlog_defines = config.get('vlog_defines', None)
        self.vhdl_defines = config.get('vhdl_defines', None)

        _fileset = config.get('fileset', {})
        self.fileset = _fileset.get('files', [])
        self.inc_dirs = _fileset.get('inc_dirs', [])

        self.elab_opts = config.get('elab_opts', None)
        self.elaborate_log = config.get('elaborate_log', 'elaborate.log')

        self.link_libs = config.get('link_libs', [])
        self.simulate_log = config.get('simulate_log', 'simulate.log')
        self.sim_opts = config.get('sim_opts', None)
        super(Questa, self).__init__(config=config, work_root=work_root)

        if self.current_system == 'Linux':
            self.delegate = UnixDelegate(self)
            self._gen_scripts_name = {'vsim_compile.sh',
                                      'vsim_elaborate.sh', 'vsim-gui.tcl', 'vsim_make.mk'}
        elif self.current_system == 'Windows':
            self.delegate = WinDelegate(self)
            self._gen_scripts_name = {'vsim-gui.tcl'}
        else:
            raise ValueError('INTERNAL ERROR: unimplemented system')

    @property
    def gui_mode(self):
        return self._gui_mode

    @gui_mode.setter
    def gui_mode(self, value):
        if not isinstance(value, bool):
            raise ValueError('gui mode type must be bool!')
        self._gui_mode = value

    def configure_main(self, *, non_lazy=False):
        self.delegate.configure_main(non_lazy=non_lazy)

    def build_main(self):
        logger.info('building')
        self.delegate.build_main()

    def run_main(self):
        logger.info('running')
        self.delegate.run_main()

    def sim_main(self):
        logger.info('cleanup')
        self.delegate.sim_main()

    def clean(self):
        logger.info('cleanup')
        self.delegate.clean()


class UnixDelegate(object):
    """
    Delegate class for Running Questa Simulator Backend in UNIX like systems
    """

    def __init__(self, master: Questa):
        self.master = master

    def gen_scripts(self):
        self.master.render_template(
            'vsim_compile.sh.j2', 'vsim_compile.sh', self._compile_vars)
        self.master.render_template(
            'vsim_elaborate.sh.j2', 'vsim_elaborate.sh', self._elaborate_vars)
        self.master.render_template(
            'vsim-gui.tcl.j2', 'vsim-gui.tcl', self._sim_gui_vars)
        self.master.render_template(
            'vsim_makefile.j2', 'vsim_make.mk', self._makefile_vars)

    @property
    def gui_mode(self):
        return self.master.gui_mode

    def configure_main(self, *, non_lazy=False):
        exists = os.path.exists
        path_of = partial(os.path.join, self.master.work_root)
        all_exist = all(map(lambda x: exists(
            path_of(x)), self.master._gen_scripts_name))
        if not all_exist or non_lazy:
            logger.debug('Non lazy configuration')
            self.gen_scripts()
        else:
            logger.debug('Lazy configuration')

    def build_main(self):
        logger.info('building')
        self.master._run_tool('make', ['-f', 'vsim_make.mk', 'build'])

    def run_main(self):
        logger.info('running')
        if self.gui_mode:
            self.master._run_tool('make', ['-f', 'vsim_make.mk', 'run-gui'])
        else:
            self.master._run_tool('make', ['-f', 'vsim_make.mk', 'run'])

    def sim_main(self):
        logger.info('cleanup')
        if self.gui_mode:
            self.master._run_tool('make', ['-f', 'vsim_make.mk', 'sim-gui'])
        else:
            self.master._run_tool('make', ['-f', 'vsim_make.mk', 'sim'])

    def clean(self):
        logger.info('cleanup')
        self.master._run_tool('make', ['-f', 'vsim_make.mk', 'clean'])

    @property
    def _compile_vars(self):
        return {
            "vlog_opts": self.master.vlog_opts,
            "vhdl_opts": self.master.vhdl_opts,
            "vlog_defines": self.master.vlog_defines,
            "vhdl_defines": self.master.vhdl_defines,
            "fileset": self.master.fileset,
            "inc_dirs": self.master.inc_dirs
        }

    @property
    def _elaborate_vars(self):
        return {
            "elab_opts": self.master.elab_opts,
            "toplevel": self.master.toplevel,
        }

    @property
    def _makefile_vars(self):
        return {
            "compile_log": self.master.compile_log,
            "elaborate_log": self.master.elaborate_log,
            "simulate_log": self.master.simulate_log,
            "silence_mode": self.master.silence_mode,
            "toplevel": self.master.toplevel,
            "sim_opts": self.master.sim_opts,
            "link_libs": self.master.link_libs,
        }

    @property
    def _sim_gui_vars(self):
        return {"toplevel": self.master.toplevel}


class WinDelegate(object):
    """
    Delegate class for Running Questa Simulator Backend in Windows
    """

    def __init__(self, master: Questa):
        self.master: Questa = master
        self.silence_mode = self.master.silence_mode
        self.clog = self.master.compile_log if self.master.compile_log else "compile.log"
        self.elog = self.master.elaborate_log if self.master.elaborate_log else "elaborate.log"
        self.slog = self.master.simulate_log if self.master.simulate_log else "simulate.log"
        self.toplevel = self.master.toplevel
        self.toplevel_opt = self.master.toplevel + '_opt'
        self.fileset = list(
            map(lambda x: x.replace('/', '\\'), self.master.fileset))

    def _win_run_tool(self, cmd, log=None):
        logger.debug('cmd: {} at {}'.format(cmd, self.master.work_root))
        if log is None:
            p = subprocess.Popen(cmd, cwd=self.master.work_root)
        else:
            p = subprocess.Popen(cmd, cwd=self.master.work_root,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ = p.communicate()

        if not self.silence_mode:
            print(out.decode('utf-8'))
        log.write(out)

        if p.returncode:
            log_name = log.name
            raise RuntimeError(
                'cmd: {} error, see {} for details'.format(cmd, log_name))

    @property
    def gui_mode(self):
        return self.master.gui_mode

    def gen_scripts(self):
        self.master.render_template(
            'vsim-gui.tcl.j2', 'vsim-gui.tcl', self._sim_gui_vars)

    def configure_main(self, *, non_lazy=False):
        self.gen_scripts()

    def build_main(self):
        self._compile()
        self._elaborate()

    def run_main(self):
        svars = self._simulate_vars
        sim_opts = svars['sim_opts']
        sim_top = self.toplevel_opt
        link_libs = svars['link_libs']
        log_name = self.master.simulate_log
        log_name = os.path.join(self.master.work_root, log_name)

        f = io.FileIO(log_name, 'w')
        writer = io.BufferedWriter(f)

        if self.gui_mode:
            cmd_fmt = 'vsim {} -do sim-gui.tcl {} {} {} {}'
            if self.master.silence_mode:
                cmd = cmd_fmt.format(
                    '', '-quiet', sim_top, sim_opts, link_libs)
                self._win_run_tool(cmd, writer)
            else:
                cmd = cmd_fmt.format('', '', sim_top, sim_opts, link_libs)
                self._win_run_tool(cmd, writer)
        else:
            cmd_fmt = 'vsim {} -do "run -a" {} {} {} {}'
            if self.master.silence_mode:
                cmd = cmd_fmt.format(
                    '-c', '-quiet', sim_top, sim_opts, link_libs)
                self._win_run_tool(cmd, writer)
            else:
                cmd = cmd_fmt.format(
                    '-c', '', sim_top, sim_opts, link_libs)
                self._win_run_tool(cmd, writer)

        writer.close()

    def sim_main(self):
        self.build_main()
        self.run_main()

    def clean(self):
        pass

    def _compile(self):
        cvars = self._compile_vars
        fileset = cvars['fileset']
        vlog_opts = cvars['vlog_opts']
        inc_dirs = cvars['inc_dirs']
        vhdl_opts = cvars['vhdl_opts']
        vlog_defines = cvars['vlog_defines']
        vhdl_defines = cvars['vhdl_defines']
        sv_iport = cvars['sv_input_port']
        log_name = self.master.compile_log
        log_name = os.path.join(self.master.work_root, log_name)

        f = io.FileIO(log_name, 'w')
        writer = io.BufferedWriter(f)

        # TODO: use map-reduce
        vhdl = []
        sv = []
        verilog = []
        if inc_dirs:
            sv.extend(inc_dirs)
            verilog.extend(inc_dirs)
        for file in fileset:
            if file.endswith((".vhd", '.vhdl')):
                vhdl.append(file)
            elif file.endswith(('.sv', '.svh')):
                sv.append(file)
            elif file.endswith(('.v', '.vh')):
                verilog.append(file)

        if len(vhdl):
            self._vhdl_f(vhdl, vhdl_opts, vhdl_defines, '', writer)
        if len(sv):
            self._vlog_f(sv, vlog_opts, vlog_defines,
                         sv_iport, writer, inc_dirs=inc_dirs)
        if len(verilog):
            self._vlog_f(verilog, vlog_opts, vlog_defines,
                         '', writer, inc_dirs=inc_dirs)

        writer.close()

    def _elaborate(self):
        evars = self._elaborate_vars
        elab_opts = evars['elab_opts']
        toplevel = 'work.' + evars['toplevel']
        args = [elab_opts, toplevel, '-o', self.toplevel_opt]
        args = ' '.join(args)
        cmd = 'vopt ' + args
        log_name = self.master.elaborate_log
        log_name = os.path.join(self.master.work_root, log_name)

        f = io.FileIO(log_name, 'w')
        writer = io.BufferedWriter(f)
        self._win_run_tool(cmd, writer)
        writer.close()

    def _f_line(self, line: str):
        line = line.replace('\\', '/')
        line = '"{}"\n'.format(line)
        return line.encode('utf-8')

    def _vlog_f(self, files: list, opts: str, defines: str, sv: str = None, fd=None, *, inc_dirs=None):
        if sv:
            f_path = os.path.join(self.master.work_root, 'sv.f')
        else:
            f_path = os.path.join(self.master.work_root, 'verilog.f')
        f = io.FileIO(f_path, 'w')
        writer = io.BufferedWriter(f)
        if inc_dirs:
            f = lambda x: (x + '\n').encode('utf-8')
            m = map(f, inc_dirs)
            writer.writelines(m)
        lines = map(self._f_line, files)
        writer.writelines(lines)
        writer.close()
        fake = os.path.relpath(f_path, self.master.work_root)
        fake = fake.replace('\\', '/')
        fake_file = '-f ' + fake
        self._vlog(fake_file, opts, defines, sv, fd)

    def _vhdl_f(self, files: list, opts: str, defines: str, dummy='', fd=None):
        f_path = os.path.join(self.master.work_root, 'vhdl.f')
        f = io.FileIO(f_path, 'w')
        writer = io.BufferedWriter(f)
        lines = map(self._f_line, files)
        writer.writelines(lines)
        writer.close()
        fake = os.path.relpath(f_path, self.master.work_root)
        fake = fake.replace('\\', '/')
        fake_file = '-f ' + fake
        self._vlog(fake_file, opts, defines, dummy, fd)

    def _vlog(self, file: str, opts: str, defines: str, sv: str = None, fd=None):
        if sv:
            args = [opts, defines, '-sv', file, sv]
            args = ' '.join(args)
            cmd = 'vlog ' + args
            self._win_run_tool(cmd, fd)
        else:
            args = [opts, defines, file]
            args = ' '.join(args)
            cmd = 'vlog ' + args
            self._win_run_tool(cmd, fd)

    def _vhdl(self, file: str, opts: str, defines: str, dummy='', fd=None):
        args = [opts, defines, file, dummy]
        args = ' '.join(args)
        cmd = 'vcom ' + args
        self._win_run_tool(cmd, fd)

    @property
    def _run_vars(self):
        return {
            **self._compile_vars,
            **self._elaborate_vars,
            **self._simulate_vars
        }

    @property
    def _elaborate_vars(self):
        elab_opts = "+cover=bcefsx +acc=npr "
        if self.master.elab_opts:
            elab_opts = elab_opts + self.master.elab_opts

        return {
            "elab_opts": elab_opts,
            "toplevel": self.master.toplevel,
        }

    @property
    def _compile_vars(self):
        vlog_opts = "+cover=bcefsx -incr "
        vhdl_opts = "+cover=bcefsx "
        vlog_defines = ""
        vhdl_defines = ""
        inc_dirs = []
        sv_input_port = "-svinputport=var "
        if self.master.vlog_opts:
            vlog_opts = vlog_opts + self.master.vlog_opts
        if self.master.vhdl_opts:
            vhdl_opts = vhdl_opts + self.master.vhdl_opts
        if self.master.vlog_defines:
            vlog_defines = vlog_defines + self.master.vlog_defines
        if self.master.vhdl_defines:
            vhdl_defines = vhdl_defines + self.master.vhdl_defines
        if self.master.inc_dirs:
            idirs = list(map(lambda x: '+incdir+' + x, self.master.inc_dirs))
            inc_dirs = inc_dirs + idirs
        return {
            "vlog_opts": vlog_opts,
            "vhdl_opts": vhdl_opts,
            "vlog_defines": vlog_defines,
            "vhdl_defines": vhdl_defines,
            "fileset": self.fileset,
            "sv_input_port": sv_input_port,
            "inc_dirs": inc_dirs,
        }

    @property
    def _simulate_vars(self):
        silence_mode = self.master.silence_mode
        sim_opts = self.master.sim_opts
        link_libs = map(lambda x: ' -lib ' + x, self.master.link_libs)
        link_libs = ''.join(link_libs)

        return {
            "sim_toplevel": self.toplevel_opt,
            "silence_mode": silence_mode,
            "sim_opts": sim_opts,
            "link_libs": link_libs,
            "simulate_log": self.master.simulate_log
        }

    @property
    def _sim_gui_vars(self):
        return {"toplevel": self.master.toplevel}
