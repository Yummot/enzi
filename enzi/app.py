# -*- coding: utf-8 -*-

import argparse
import datetime
import io
import logging
import os
import shutil
import sys
import toml

import colorama
from colorama import Fore, Style

from enzi.config import EnziConfigValidator
from enzi.git import Git
from enzi.project_manager import ProjectFiles
from enzi.utils import rmtree_onerror, OptionalAction, BASE_ESTRING
from enzi.frontend import Enzi

# **************** LOGGING CONFIGURATION **************** #
try:
    import coloredlogs
except Exception:
    coloredlogs = None

LOG_FMT = '%(asctime)s %(name)s[%(process)d] %(levelname)s %(message)s'
logging.basicConfig(format=LOG_FMT)
logger = logging.getLogger('Enzi')


class ProjectInitialor(object):
    """
    Initialize a enzi project with a given package name.

    If the package name directory is already exists, its reject to create the package directory.
    """

    def __init__(self, package_name, *, cwd=None):
        if cwd is None:
            cwd = os.getcwd()
        self.path = os.path.join(cwd, package_name)
        self.name = package_name
        self.git = Git(self.path)

    def init(self):
        self.init_package()
        self.init_git()

    def init_package(self):
        """Initialize the package directory, generate the Enzi.toml, and also create a src sub directory."""
        # create the package directory
        if os.path.exists(self.path):
            msg = 'path "{}" already existed, init aborted'.format(self.path)
            logger.error(msg)
            raise SystemExit(BASE_ESTRING + msg)
        os.makedirs(self.path)

        # create the src sub directory
        os.makedirs(os.path.join(self.path, 'src'))

        # get git config user.name
        default_author = self.git.spawn_with(
            lambda x: x.arg('config').arg('user.name')).strip()

        # create the Enzi.toml
        enzi_toml = os.path.join(self.path, 'Enzi.toml')
        f = io.FileIO(enzi_toml, 'w')
        writer = io.BufferedWriter(f)
        sio = EnziConfigValidator.base_file(self.name, default_author)
        file_content = sio.getvalue()
        writer.write(file_content.encode('utf-8'))
        writer.close()

    def init_git(self):
        """Initialize the git repository in the package directory"""
        self.git.spawn_with(lambda x: x.arg('init'))


class EnziApp(object):
    """
    Enzi Cli Application
    """

    __tasks__ = {'clean', 'update'}
    __targets__ = {'build', 'sim', 'run', 'program_device'}

    def __init__(self):
        (self.args, self.parser) = EnziApp.parse_args()
        self.enzi = None
        self.init()

    def init(self):
        self.init_logger()

    def run(self):
        if self.args.enzi_config_help:
            self.enzi_config_help()
            return

        # tasks
        args = self.args
        if args.enzi_config_help:
            self.enzi_config_help()
            return

        is_task = hasattr(args, 'task')

        if is_task and args.task == 'clean':
            self.clean()
            return

        if is_task and args.task == 'init':
            self.init_package()
            return

        if not args.root:
            raise RuntimeError('No root directory specified.')

        # if update, root must be specified
        if args.config:
            self.enzi = Enzi(
                args.root[0],
                args.config,
                non_lazy=self.args.non_lazy)
        else:
            self.enzi = Enzi(args.root[0], non_lazy=self.args.non_lazy)
        if is_task and args.task == 'update':
            self.update_deps()
            return

        # targets
        self.run_target()

    def run_target(self, **kwargs):
        """
        run Enzi target
        """
        enzi = kwargs.get('enzi', self.enzi)
        target = self.args.target
        if target is None:
            return
        self.info('start `{}`'.format(target))
        enzi.init()
        enzi.silence_mode = self.args.silence_mode
        project_manager = ProjectFiles(enzi)
        project_manager.fetch(target)
        fileset = project_manager.get_fileset(target)
        enzi.run_target(target, fileset, self.args.tool)
        self.info('`{}` done'.format(target))

    def init_logger(self):
        """
        get properly log warnning and log error function
        """

        if self.args.log_level:
            log_level = getattr(logging, self.args.log_level)
            if coloredlogs:
                coloredlogs.install(level=log_level, fmt=LOG_FMT)
            else:
                logging.basicConfig(level=log_level)
                ch = logging.StreamHandler()
                formatter = logging.Formatter(LOG_FMT)
                ch.setFormatter(formatter)
        elif coloredlogs:
            coloredlogs.install(level='INFO', fmt=LOG_FMT)

        if coloredlogs:
            effective_level = coloredlogs.get_level()
        else:
            effective_level = logger.getEffectiveLevel()

        if effective_level > logging.WARNING:
            self.warning = logger.critical
        else:
            self.warning = logger.warning

        if effective_level > logging.ERROR:
            self.error = logger.critical
        else:
            self.error = logger.error

        self.info = logger.info
        self.debug = logger.debug
        self.exception = logger.exception
        self.critical = logger.critical

    def init_package(self):
        """Initialize an Enzi Package/Project"""
        package_name = self.args.name
        if package_name is None:
            msg = 'an package name must provide for enzi init'
            logging.error(msg)
            raise SystemExit(BASE_ESTRING + msg)

        initializer = ProjectInitialor(package_name)
        initializer.init()

    def enzi_config_help(self):
        config_name = self.args.enzi_config_help
        if config_name is sys.stdout or isinstance(config_name, io.TextIOWrapper):
            self.info('Here is the template Enzi.toml file\'s key-values hints:')
            sio = EnziConfigValidator.info()
            print(sio.getvalue())
            sio.close()
        elif isinstance(config_name, (str, bytes)):
            sio = EnziConfigValidator.info()
            info = sio.getvalue().encode('utf-8')
            sio.close()

            outfile_dir = os.path.dirname(config_name)

            # Make sure the output file directory exists.
            # Enzi will not create the directory if it doesn't exist.
            if outfile_dir and not os.path.exists(outfile_dir):
                outname = os.path.basename(config_name)
                fmt = 'path \'{}\' for \'{}\' does not exist'
                msg = fmt.format(outfile_dir, outname)
                self.error(msg)
                sys.exit(1)

            if os.path.exists(config_name):
                msg = '{} is already exists'.format(config_name)
                self.error(msg)
                sys.exit(1)

            outfile = io.FileIO(config_name, 'w')
            owriter = io.BufferedWriter(outfile)
            owriter.write(info)
            owriter.close()
            msg = 'Generated the template Enzi.toml file\'s key-values hints in ' + config_name
            self.info(msg)

    def update_deps(self, **kwargs):
        """
        the default behaviour of enzi update
        """
        enzi = kwargs.get('enzi', self.enzi)
        if not isinstance(enzi, Enzi):
            return
        self.info('start updating')
        enzi.init(update=True)
        self.info('updating finished')

    def clean(self, **kwargs):
        """
        Enzi clean task, enzi [--root ROOT] [--config CONFIG] [--silence-mode] clean [--yes]
        """
        yes = kwargs.get('yes', self.args.yes)
        root = kwargs.get('root', self.args.root)
        config_name = kwargs.get('config', self.args.config)

        if yes:
            root = root
            if root:
                fmt = 'clean will clean up the build directory in \'{}\''
                msg = fmt.format(root)
                self.warning(msg)
            else:
                self.warning('clean will clean up the build directory')

        confirm = self.get_confirm()

        if confirm != True:
            return

        root = root if root else '.'
        config_name = config_name if config_name else 'Enzi.toml'
        config_root = os.path.join(root, config_name)
        valid_root = os.path.exists(config_root)

        if not valid_root:
            msg = 'No {} in root directory \'{}\''.format(config_name, root)
            self.warning(msg)
            logger.info("Nothing to do.")
            return

        if confirm and os.path.exists('build'):
            shutil.rmtree('build', onerror=rmtree_onerror)

        if confirm and os.path.exists('Enzi.lock'):
            os.remove('Enzi.lock')

        logger.info(Fore.BLUE + 'finished cleaning')

    def get_confirm(self):
        self.warning('Would you like to execute[y/N]: ')
        _choice = input()
        choice = _choice.lower() if _choice else 'n'
        err_msg = "must input yes(y)/no(n), not " + _choice
        if not choice.startswith(('y', 'n')):
            self.error(err_msg)
            return
        if choice == 'y' or choice == 'yes':
            confirm = True
        elif choice == 'n' or choice == 'no':
            self.info("Nothing to do.")
            confirm = False
        else:
            self.error(err_msg)
            confirm = None

        return confirm

    @staticmethod
    def parse_args():
        supported_targets = ['build', 'sim', 'run', 'program_device']
        available_tasks = ['clean', 'update']
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        parser.add_argument("-l", "--log", dest="log_level", help='Set Enzi self log level',
                            choices=[
                                'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        # Global options
        parser.add_argument('--root', help='Enzi project root directory')
        parser.add_argument('--silence-mode', '-s', help='Only capture stderr',
                            action='store_true')
        parser.add_argument(
            '--config', help='Specify the Enzi.toml file to use')
        parser.add_argument(
            '--non-lazy',
            help='Force Enzi to (re)generated corresponding backend configuration when running target',
            action='store_true')
        parser.add_argument('--enzi-config-help',
                            help='Output an Enzi.toml file\'s key-values hints. \
                                If no output file is specified, Enzi will print to stdout.',
                            action=OptionalAction, default=sys.stdout)

        # clean up args.
        clean_parser = subparsers.add_parser(
            'clean', help='Clean all Enzi generated files')
        clean_parser.add_argument(
            '-y', '--yes', help='Skip clean up confirmation', action='store_true')
        clean_parser.set_defaults(task='clean')

        # update dependencies
        update_parser = subparsers.add_parser(
            'update', help='Update dependencies')
        update_parser.set_defaults(task='update')

        # init task
        init_parser = subparsers.add_parser(
            'init', help='init an Enzi package with a given package name')
        init_parser.add_argument(
            'name', help='the package name to initialize', action=OptionalAction)
        init_parser.set_defaults(task='init')

        # build subparser
        build_parser = subparsers.add_parser(
            'build', help='Build the given project')
        build_parser.add_argument('--tool', help='Override the default target')
        build_parser.set_defaults(target='build')

        # run subparser
        run_parser = subparsers.add_parser('run', help='Run the given project')
        run_parser.add_argument('--tool', help='Override the default tool')
        run_parser.set_defaults(target='run')

        # sim subparser
        sim_parser = subparsers.add_parser(
            'sim', help='Simulate the given project')
        sim_parser.add_argument('--tool', help='Override the default tool')
        sim_parser.set_defaults(target='sim')

        # program_device subparser
        pd_parser = subparsers.add_parser(
            'program_device', help='Program the given project to device')
        pd_parser.add_argument('--tool', help='Override the default tool')
        pd_parser.set_defaults(target='program_device')

        args = parser.parse_args()

        if not args.enzi_config_help is None:
            return (args, parser)

        if hasattr(args, 'target') or hasattr(args, 'task'):
            return (args, parser)
        else:
            logger.error('Target or Task must be specified')
            logger.error('Supported targets: {}'.format(supported_targets))
            logger.error('Available tasks: {}'.format(available_tasks))
            sys.exit(1)
