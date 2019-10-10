# -*- coding: utf-8 -*-

import logging
import os
import subprocess
from collections import OrderedDict

from enzi.backend import Backend

__all__ = ('Questa', )

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class Questa(Backend):
    supported_system = ('Linux', 'Windows',)

    def __init__(self, config={}, work_root=None):
        self._gui_mode = False

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

        self.elab_opts = config.get('elab_opts', None)
        self.elaborate_log = config.get('elaborate_log', None)

        self.link_libs = config.get('link_libs', [])
        self.simulate_log = config.get('simulate_log', None)
        self.sim_opts = config.get('sim_opts', None)
        super(Questa, self).__init__(config=config, work_root=work_root)

        if self.current_system == 'Linux':
            self.delegate = UnixDelegate(self)
        elif self.current_system == 'Windows':
            self.delegate = WinDelegate(self)
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

    def configure_main(self):
        self.delegate.configure_main()

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
            'compile.sh.j2', 'compile.sh', self._compile_vars)
        self.master.render_template(
            'elaborate.sh.j2', 'elaborate.sh', self._elaborate_vars)
        self.master.render_template(
            'sim-gui.tcl.j2', 'sim-gui.tcl', self._sim_gui_vars)
        self.master.render_template(
            'makefile.j2', 'Makefile', self._makefile_vars)
        self.master._gen_scripts_name = ['compile.sh',
                                         'elaborate.sh', 'sim-gui.tcl', 'Makfile']

    @property
    def gui_mode(self):
        return self.master.gui_mode

    def configure_main(self):
        self.gen_scripts()

    def build_main(self):
        logger.info('building')
        self.master._run_tool('make', ['build'])

    def run_main(self):
        logger.info('running')
        if self.gui_mode:
            self.master._run_tool('make', ['run-gui'])
        else:
            self.master._run_tool('make', ['run'])

    def sim_main(self):
        logger.info('cleanup')
        if self.gui_mode:
            self.master._run_tool('make', ['sim-gui'])
        else:
            self.master._run_tool('make', ['sim'])

    def clean(self):
        logger.info('cleanup')
        self.master._run_tool('make', ['clean'])

    @property
    def _compile_vars(self):
        return {
            "vlog_opts": self.master.vlog_opts,
            "vhdl_opts": self.master.vhdl_opts,
            "vlog_defines": self.master.vlog_defines,
            "vhdl_defines": self.master.vhdl_defines,
            "fileset": self.master.fileset,
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
        self.clog = self.master.compile_log if self.master.compile_log else "compile.log"
        self.elog = self.master.elaborate_log if self.master.elaborate_log else "elaborate.log"
        self.slog = self.master.simulate_log if self.master.simulate_log else "simulate.log"
        self.toplevel = self.master.toplevel
        self.toplevel_opt = self.master.toplevel + '_opt'
        self.fileset = list(map(lambda x: x.replace('/', '\\'), self.master.fileset))

    def _win_run_tool(self, cmd, log=None):
        if log is None:
            p = subprocess.Popen(cmd, cwd=self.master.work_root)
        else:
            p = subprocess.Popen(cmd, cwd=self.master.work_root, stdout=log, stderr=log)
        p.communicate()
        if p.returncode:
            log_name = log.name
            raise RuntimeError('cmd: {} error, see {} for details'.format(cmd, log_name))

    @property
    def gui_mode(self):
        return self.master.gui_mode

    def gen_scripts(self):
        self.master.render_template(
            'sim-gui.tcl.j2', 'sim-gui.tcl', self._sim_gui_vars)
        self.master._gen_scripts_name = ['sim-gui.tcl']

    def configure_main(self):
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
        with open(log_name, 'w') as f:
            if self.gui_mode:
                cmd_fmt = 'vsim {} -do sim-gui.tcl {} {} {} {}'
                if self.master.silence_mode:
                    cmd = cmd_fmt.format('', '-quiet', sim_top, sim_opts, link_libs)
                    self._win_run_tool(cmd, f)
                else:
                    cmd = cmd_fmt.format('', '', sim_top, sim_opts, link_libs)
                    self._win_run_tool(cmd,f )
            else:
                cmd_fmt = 'vsim {} -do "run -a" {} {} {} {}'
                if self.master.silence_mode:
                    cmd = cmd_fmt.format('-c', '-quiet', sim_top, sim_opts, link_libs)
                    self._win_run_tool(cmd, f)
                else:
                    cmd = cmd_fmt.format('-c', '', sim_top, sim_opts, link_libs)
                    self._win_run_tool(cmd, f)

    def sim_main(self):
        self.run_main()

    def clean(self):        
        pass

    def _compile(self):
        cvars = self._compile_vars
        fileset = cvars['fileset']
        vlog_opts = cvars['vlog_opts']
        vhdl_opts = cvars['vhdl_opts']
        vlog_defines = cvars['vlog_defines']
        vhdl_defines = cvars['vhdl_defines']
        sv = cvars['sv_input_port']
        log_name = self.master.compile_log
        if os.path.exists(log_name):
            os.remove(log_name)
        with open(log_name, 'a') as f:        
            for file in fileset:
                if file.endswith((".vhd", '.vhdl')):
                    self._vhdl(file, vhdl_opts, vhdl_defines, f)
                    pass
                elif file.endswith(('.sv', '.svh')):
                    self._vlog(file, vlog_opts, vlog_defines, sv, f)
                    pass
                elif file.endswith(('.vhd', '.vhdl')):
                    self._vlog(file, vlog_opts, vlog_defines, f)
                    pass

    def _elaborate(self):
        evars = self._elaborate_vars
        elab_opts = evars['elab_opts']
        toplevel = 'work.' + evars['toplevel']
        args = [elab_opts, toplevel, '-o', self.toplevel_opt]
        args = ' '.join(args)
        cmd = 'vopt ' + args
        log_name = self.master.elaborate_log
        with open(log_name, 'w') as f:
            self._win_run_tool(cmd, f)

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
        vlog_opts = "+cover=bcefsx -incr"
        vhdl_opts = "+cover=bcefsx "
        vlog_defines = ""
        vhdl_defines = ""
        sv_input_port = "-svinputport=var"
        if self.master.vlog_opts:
            vlog_opts = vlog_opts + self.master.vlog_opts
        if self.master.vhdl_opts:
            vhdl_opts = vhdl_opts + self.master.vhdl_opts
        if self.master.vlog_defines:
            vlog_defines = vlog_defines + self.master.vlog_defines
        if self.master.vhdl_defines:
            vhdl_defines = vhdl_defines + self.master.vhdl_defines
        return {
            "vlog_opts": vlog_opts,
            "vhdl_opts": vhdl_opts,
            "vlog_defines": vlog_defines,
            "vhdl_defines": vhdl_defines,
            "fileset": self.fileset,
            "sv_input_port": sv_input_port,
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
