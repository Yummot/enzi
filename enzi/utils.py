# -*- coding: utf-8 -*-

import argparse
import logging
import os
import subprocess
import sys
import toml
import typing

import copy as py_copy
from itertools import chain

from semver import VersionInfo as Version

logger = logging.getLogger(__name__)

# use an environment variable `LAUNCHER_DEBUG` to control Launcher debug output
LAUNCHER_DEBUG = os.environ.get('LAUNCHER_DEBUG')


def rmtree_onerror(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=onerror)``
    """
    import stat
    if not os.access(path, os.W_OK):
        # Is the error an access error ?
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise RuntimeError('{} access denied'.format(path))


def try_parse_semver(tag_and_id):
    tag, tag_id = tag_and_id
    if tag.startswith('v'):
        try:
            return (Version.parse(tag[1:]), tag_id)
        except ValueError:
            return None
    else:
        return None


def unique(iterable: typing.Iterable[typing.Any]):
    # TODO: code review, can we improve performance ?
    seen = set()
    for item in iterable:
        if item not in seen:
            seen.add(item)
            yield item


class PathBuf(object):
    def __init__(self, base=''):
        self.path = base

    def join(self, paths):
        self_copy = py_copy.copy(self)
        self_copy.path = os.path.join(self.path, paths)
        return self_copy

    def exits(self):
        return os.path.exists(self.path)

    def isabs(self):
        return os.path.isabs(self.path)

    def isdir(self):
        return os.path.isdir(self.path)

    def dirname(self):
        return os.path.dirname(self.path)

    def basename(self):
        return os.path.basename(self.path)

# pb = PathBuf('xxx')
# print(pb.join('xxxx').join('xxxx').path)
# print(pb.path)


def realpath(path):
    path = os.path.expandvars(path)
    path = os.path.expanduser(path)
    path = os.path.normpath(path)
    path = os.path.realpath(path)
    return path


def relpath(base_path: str, abs_path: str) -> typing.Optional[typing.Union[str, bytes]]:
    """
    convert given absolute path to relative path, if possible.
    the base_path is assumed to be a common path of abs_path
    """
    if not os.path.commonpath([abs_path, base_path]):
        return None

    if os.path.isabs(abs_path) and os.path.isabs(base_path):
        return os.path.relpath(abs_path, start=base_path)
    else:
        return None


def flat_map(f, items):
    """
    Creates an iterator that works like map, but flattens nested Iteratorable.
    """
    return chain.from_iterable(map(f, items))


def toml_load(path):
    """
    Load a toml file from a given path.
    Raise ValueError with nice error message if decode error.
    :param path: a path like object
    :return: dict
    """
    with open(path) as f:
        content = f.read()
    try:
        d = toml.loads(content)
        return d
    except toml.TomlDecodeError as e:
        lineno = e.lineno
        err_line = content.splitlines()[lineno - 1]
        if "Reserved escape" in e.msg:
            fmt = "Reserved escape in {}(line:{}): {}"
            msg = fmt.format(path, lineno, err_line)
            logger.error(msg)
            if '\\' in err_line:
                logger.error("Error may be caused by \\ in this line")
            raise ValueError(msg) from None


def toml_loads(content):
    """
    Load a toml file from a given string.
    Raise ValueError with nice error message if decode error.
    :param content: a string which may be a valid toml file
    :return: dict
    """
    try:
        d = toml.loads(content)
        return d
    except toml.TomlDecodeError as e:
        lineno = e.lineno
        err_line = content.splitlines()[lineno - 1]
        if "Reserved escape" in e.msg:
            fmt = "Reserved escape in content(line:{}): {}"
            msg = fmt.format(lineno, err_line)
            logger.error(msg)
            if '\\' in err_line:
                logger.error("Error may be caused by \\ in this line")
            raise ValueError(msg) from None


class FilesAction(argparse.Action):
    """
    argparse Action for Files args, support multiple inputs.
    """

    def __init__(self,
                 option_strings,
                 dest,
                 nargs=None,
                 const=None,
                 default=None,
                 type=None,
                 choices=None,
                 required=False,
                 help=None,
                 metavar=None):
        if nargs == 0:
            raise ValueError(
                'FileAction requires that nargs for append actions must be > 0')
        if const is not None and nargs != argparse.OPTIONAL:
            raise ValueError('nargs must be %r to supply const' %
                             argparse.OPTIONAL)
        super(FilesAction, self).__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            const=const,
            default=default,
            type=type,
            choices=choices,
            required=required,
            help=help,
            metavar=metavar)

    def __call__(self, parser, namespace, values, option_string=None):
        def _ensure_value(namespace, name, value):
            if getattr(namespace, name, None) is None:
                setattr(namespace, name, value)
            return getattr(namespace, name)

        path = realpath(values)

        paths = py_copy.copy(_ensure_value(namespace, self.dest, []))
        paths.append(path)

        setattr(namespace, self.dest, paths)


class FileAction(FilesAction):
    """
    argparse Action for File args, support only single input.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        def _ensure_value(namespace, name, value):
            if getattr(namespace, name, None) is None:
                setattr(namespace, name, value)
            return getattr(namespace, name)

        path = realpath(values)
        setattr(namespace, self.dest, path)

# launcher from fusesoc https://github.com/olofk/fusesoc/tree/master/fusesoc


class Launcher:
    def __init__(self, cmd, args=[], cwd=None):
        self.cmd = cmd
        self.args = args
        self.cwd = cwd

    # def run(self):
    def run(self, get_output: bool = False, *, suppress_stderr=False):
        if LAUNCHER_DEBUG:
            fmt = 'Launcher:run: cmd: \'{}\' with args: {}'
            logger.debug('Launcher:run: cwd: {}'.format(self.cwd))
            logger.debug(fmt.format(self.cmd, self.args))
        try:
            if get_output:
                output = subprocess.check_output([self.cmd] + self.args,  # pylint: disable=E1123
                                                 cwd=self.cwd,
                                                 stdin=subprocess.PIPE)
                return output.decode("utf-8")  # pylint: disable=E1101
            else:
                call_dict = {
                    'args': [self.cmd] + self.args,
                    'cwd': self.cwd,
                    'stdin': subprocess.PIPE,
                    'stdout': subprocess.DEVNULL,
                    'stderr': subprocess.DEVNULL
                }
                if suppress_stderr:
                    call_dict['stderr'] = subprocess.DEVNULL

                output = subprocess.check_call(**call_dict)
                return output
        except FileNotFoundError as e:
            msg = "Launcher: {}".format(e)
            logger.error(msg)
            raise RuntimeError(msg) from e
        except subprocess.CalledProcessError as e:
            msg = "Launcher: {}".format(e)
            logger.error(msg)
            self.errormsg = '"{}" exited with an error code. See stderr for details.'
            raise RuntimeError(self.errormsg.format(str(self))) from e

    def __str__(self):
        return ' '.join([self.cmd] + self.args)
