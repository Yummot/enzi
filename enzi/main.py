# -*- coding: utf-8 -*-
import argparse
import coloredlogs
import datetime
import logging
import os
import shutil
import sys

import colorama
from colorama import Fore, Style

from enzi.project_manager import ProjectFiles
from enzi.utils import rmtree_onerror
from enzi.frontend import Enzi

logger = logging.getLogger('Enzi')

if not 'coloredlogs' in sys.modules:
    coloredlogs = None


def cur_time():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


def enzi_clean(self, confirm=False):
    if not confirm:
        logger.warning('clean will clean up the build directory')
        logger.warning('Would you like to excute[y/N]:')
        _choice = input()
        choice = _choice.lower() if _choice else 'n'
        err_msg = "must input yes(y)/no(n), not " + _choice
        if not choice.startswith(('y', 'n')):
            logger.error(err_msg)
            return
        if choice == 'y' or choice == 'yes':
            confirm = True
        elif choice == 'n' or choice == 'no':
            logger.info("Nothing to do.")
            return
        else:
            logger.warning(err_msg)

    if confirm and os.path.exists('build'):
        shutil.rmtree('build', onerror=rmtree_onerror)

    if confirm and os.path.exists('Enzi.lock'):
        os.remove('Enzi.lock')

    logger.info(Fore.BLUE + 'finished cleaning')

def enzi_update(enzi: Enzi):
    logger.info('start updating')
    enzi.init(update=True)
    logger.info('updating finished')


def parse_args():
    supported_targets = ['build', 'sim', 'run', 'program_device']
    available_tasks = ['clean', 'update']
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    parser.add_argument("-l", "--log", dest="log_level", help='set Enzi self log level',
                        choices=[
                            'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    # Global options
    parser.add_argument('--root', help='Enzi project root directory',
                        default=[], action='append')
    parser.add_argument('--silence-mode', help='only capture stderr',
                        default=False, action='store_true')
    parser.add_argument('--config', help='Specify the Enzi.toml file to use')

    # clean up args.
    clean_parser = subparsers.add_parser(
        'clean', help='clean all Enzi generated files')
    clean_parser.add_argument(
        '-y', '--yes', help='skip clean up confirmation', default=False, action='store_true')
    clean_parser.set_defaults(task=enzi_clean)

    # update dependencies
    clean_parser = subparsers.add_parser(
        'update', help='update dependencies')
    clean_parser.set_defaults(task=enzi_update)

    # build subparser
    build_parser = subparsers.add_parser(
        'build', help='build the given project')
    build_parser.add_argument('--tool', help='Override the default target')
    build_parser.set_defaults(target='build')

    # run subparser
    run_parser = subparsers.add_parser('run', help='run the given project')
    run_parser.add_argument('--tool', help='Override the default tool')
    run_parser.set_defaults(target='run')

    # sim subparser
    sim_parser = subparsers.add_parser(
        'sim', help='simulate the given project')
    sim_parser.add_argument('--tool', help='Override the default tool')
    sim_parser.set_defaults(target='sim')

    # program_device subparser
    pd_parser = subparsers.add_parser(
        'program_device', help='program the given project to device')
    pd_parser.add_argument('--tool', help='Override the default tool')
    pd_parser.set_defaults(target='program_device')

    args = parser.parse_args()
    if hasattr(args, 'target') or hasattr(args, 'task'):
        return args
    else:
        logger.error('Target or Task must be specified')
        logger.error('Supported targets: {}'.format(supported_targets))
        logger.error('Available tasks: {}'.format(available_tasks))
        exit(1)


def main():
    args = parse_args()

    colorama.init()

    if args.log_level:
        log_level = getattr(logging, args.log_level)
        if coloredlogs:
            coloredlogs.install(level=log_level)
        else:
            logging.basicConfig(level=log_level)
    elif coloredlogs:
        coloredlogs.install(level='INFO')
    


    if hasattr(args, 'task') and args.task == enzi_clean:
        enzi_clean(args.yes)
        return

    if len(args.root) > 1:
        raise RuntimeError('Currently, Enzi does not support multiple roots')
    if not args.root:
        raise RuntimeError('No root directory specified.')

    if args.config:
        enzi = Enzi(args.root[0], args.config)
    else:
        enzi = Enzi(args.root[0])
    
    if hasattr(args, 'task') and args.task == enzi_update:
        enzi_update(enzi)
        return

    target = args.target

    logger.info('start `{}`'.format(target))

    enzi.init()
    enzi.silence_mode = args.silence_mode
    project_manager = ProjectFiles(enzi)
    project_manager.fetch(target)
    fileset = project_manager.get_fileset(target)
    enzi.run_target(target, fileset, args.tool)

    logger.info('`{}` done'.format(target))


if __name__ == "__main__":
    main()
