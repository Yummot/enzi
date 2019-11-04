# -*- coding: utf-8 -*-

import io
import logging
import os
import subprocess

from functools import partial

from enzi.backend import Backend

__all__ = ('Questa', )

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class Questa(Backend):
    supported_system = ('Linux', 'Windows',)

    def __init__(self, config={}, work_root=None):

        self.compile_log = config.get('compile_log', 'compile.log')
        self.vlog_opts = config.get('vlog_opts', None)
        self.vhdl_opts = config.get('vhdl_opts', None)
        self.vlog_defines = config.get('vlog_defines', None)
        self.vhdl_generics = config.get('vhdl_generics', None)

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
            self._gen_scripts_name = {'vsim-gui.tcl', 'vsim-compile.tcl', 'vsim-elaborate.tcl'}
        else:
            raise ValueError('INTERNAL ERROR: unimplemented system')

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
    '''
    Delegate class for Running Questa Simulator Backend in UNIX like systems
    '''

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
        logger.info('simulating')
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
            'vlog_opts': self.master.vlog_opts,
            'vhdl_opts': self.master.vhdl_opts,
            'vlog_defines': self.master.vlog_defines,
            'vhdl_generics': self.master.vhdl_generics,
            'fileset': self.master.fileset,
        }

    @property
    def _elaborate_vars(self):
        return {
            'elab_opts': self.master.elab_opts,
            'toplevel': self.master.toplevel,
        }

    @property
    def _makefile_vars(self):
        return {
            'compile_log': self.master.compile_log,
            'elaborate_log': self.master.elaborate_log,
            'simulate_log': self.master.simulate_log,
            'silence_mode': self.master.silence_mode,
            'toplevel': self.master.toplevel,
            'sim_opts': self.master.sim_opts,
            'link_libs': self.master.link_libs,
        }

    @property
    def _sim_gui_vars(self):
        return {'toplevel': self.master.toplevel}

# TODO: update this Delegate to multiple filesets


class WinDelegate(object):
    '''
    Delegate class for Running Questa Simulator Backend in Windows
    '''

    def __init__(self, master: Questa):
        self.master: Questa = master
        self.silence_mode = self.master.silence_mode
        self.clog = self.master.compile_log if self.master.compile_log else 'compile.log'
        self.elog = self.master.elaborate_log if self.master.elaborate_log else 'elaborate.log'
        self.slog = self.master.simulate_log if self.master.simulate_log else 'simulate.log'
        self.toplevel = self.master.toplevel
        self.toplevel_opt = self.master.toplevel + '_opt'
        self.master.j2_env.filters['winpath'] = lambda x: x.replace('/', '\\')

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
            'vsim_win_compile.tcl.j2',
            'vsim_compile.tcl',
            self._compile_vars
        )
        self.master.render_template(
            'vsim_win_elaborate.tcl.j2',
            'vsim_elaborate.tcl',
            self._elaborate_vars
        )
        self.master.render_template(
            'vsim-gui.tcl.j2',
            'vsim-gui.tcl',
            self._sim_gui_vars
        )

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
            cmd_fmt = 'vsim -gui -do sim-gui.tcl {} {} {} {}'
            if self.master.silence_mode:
                cmd = cmd_fmt.format(
                    '-quiet', sim_top, sim_opts, link_libs)
                self._win_run_tool(cmd, writer)
            else:
                cmd = cmd_fmt.format('', sim_top, sim_opts, link_libs)
                self._win_run_tool(cmd, writer)
        else:
            cmd_fmt = 'vsim -c -do "run -a; exit" {} {} {} {}'
            if self.master.silence_mode:
                cmd = cmd_fmt.format(
                    '-quiet', sim_top, sim_opts, link_libs)
                self._win_run_tool(cmd, writer)
            else:
                cmd = cmd_fmt.format(
                    '', sim_top, sim_opts, link_libs)
                self._win_run_tool(cmd, writer)

        writer.close()

    def sim_main(self):
        self.build_main()
        self.run_main()

    def clean(self):
        pass

    def _compile(self):
        compile_log = self.master.compile_log
        f = io.FileIO(compile_log, 'w')
        writer = io.BufferedWriter(f)
        cmd = "vsim -c -do vsim_compile.tcl"
        self._win_run_tool(cmd, writer)

    def _elaborate(self):
        elaborate_log = self.master.elaborate_log
        f = io.FileIO(elaborate_log, 'w')
        writer = io.BufferedWriter(f)
        cmd = "vsim -c -do vsim_elaborate.tcl"
        self._win_run_tool(cmd, writer)

    @property
    def _run_vars(self):
        return {
            **self._compile_vars,
            **self._elaborate_vars,
            **self._simulate_vars
        }

    @property
    def _elaborate_vars(self):
        elab_opts = '+cover=bcefsx +acc=npr '
        if self.master.elab_opts:
            elab_opts = elab_opts + ' '.join(self.master.elab_opts)

        return {
            'elab_opts': elab_opts,
            'toplevel': self.master.toplevel,
        }

    @property
    def _compile_vars(self):
        vlog_opts = '+cover=bcefsx -incr '
        vhdl_opts = '+cover=bcefsx '
        vlog_defines = ''
        vhdl_generics = ''
        sv_input_port = '-svinputport=var '
        if self.master.vlog_opts:
            vlog_opts = vlog_opts + ' '.join(self.master.vlog_opts)
        if self.master.vhdl_opts:
            vhdl_opts = vhdl_opts + ' '.join(self.master.vhdl_opts)
        if self.master.vlog_defines:
            vlog_defines = vlog_defines + ' '.join(self.master.vlog_defines)
        if self.master.vhdl_generics:
            vhdl_generics = vhdl_generics + ' '.join(self.master.vhdl_generics)

        return {
            'vlog_opts': vlog_opts,
            'vhdl_opts': vhdl_opts,
            'vlog_defines': vlog_defines,
            'vhdl_generics': vhdl_generics,
            'fileset': self.master.fileset,
            'sv_input_port': sv_input_port,
        }

    @property
    def _simulate_vars(self):
        silence_mode = self.master.silence_mode
        sim_opts = ' '.join(self.master.sim_opts)
        link_libs = map(lambda x: ' -lib ' + x, self.master.link_libs)
        link_libs = ''.join(link_libs)

        return {
            'sim_toplevel': self.toplevel_opt,
            'silence_mode': silence_mode,
            'sim_opts': sim_opts,
            'link_libs': link_libs,
            'simulate_log': self.master.simulate_log
        }

    @property
    def _sim_gui_vars(self):
        return {'toplevel': self.master.toplevel}
