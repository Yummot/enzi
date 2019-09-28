# -*- coding: utf-8 -*-

import argparse

from enzi.project_manager import ProjectFiles
from enzi.frontend import Enzi

try:
    import coloredlogs, logging
    coloredlogs.install(level='DEBUG')
except:
    import logging

logger = logging.getLogger(__name__)

def parse_args():
    supported_targets = ['build', 'sim', 'run', 'program_device']
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title='Target')

    parser.add_argument("-l", "--log", dest="log_level", help='set Enzi self log level',
                        choices=[
                            'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    # Global options
    parser.add_argument('--root', help='Enzi project root directory',
                        default=[], action='append')
    parser.add_argument('--silence-mode', help='only capture stderr',
                        default=False, action='store_true')
    parser.add_argument('--config', help='Specify the Enzi.toml file to use')

    # TODO: Add clean up args.

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
    if hasattr(args, 'target'):
        return args
    else:

        raise RuntimeError(
            'Target must be specified (option: {}).'.format(supported_targets))


def main():
    args = parse_args()
    target = args.target

    if len(args.root) > 1:
        raise RuntimeError('Currently, Enzi does not support multiple roots')
    if not args.root:
        raise RuntimeError('No root directory specified.')

    if args.config:
        s = Enzi(args.root[0], args.config)
    else:
        s = Enzi(args.root[0])

    if args.log_level:
        logging.basicConfig(level=getattr(logging, args.log_level))
    
    s.init()
    s.silence_mode = args.silence_mode
    project_manager = ProjectFiles(s)
    project_manager.fetch(target)
    fileset = project_manager.get_fileset(target)
    s.run_target(target, fileset, args.tool)
    print('enzi {} done'.format(target))


if __name__ == "__main__":
    main()
