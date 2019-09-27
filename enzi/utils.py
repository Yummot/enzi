import subprocess
import logging
import sys
import os
import copy as py_copy
import importlib
from itertools import chain
from semver import VersionInfo as Version
import typing

logger = logging.getLogger(__name__)

# launcher from fusesoc https://github.com/olofk/fusesoc/tree/master/fusesoc


def try_parse_semver(tag_and_id):
    tag, tag_id = tag_and_id
    if tag.startswith('v'):
        try:
            return (Version.parse(tag[1:]), tag_id)
        except ValueError:
            return None
    else:
        return None

# TODO: code review, can we improve performance ?


def unique(iterable: typing.Iterable[typing.Any]):
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


def flat_map(f, items):
    """
    Creates an iterator that works like map, but flattens nested Iteratorable.
    """
    return chain.from_iterable(map(f, items))


class Launcher:
    def __init__(self, cmd, args=[], cwd=None):
        self.cmd = cmd
        self.args = args
        self.cwd = cwd

    # def run(self):
    def run(self, get_output: bool=False):
        # if self.cwd:
        #   logger.debug('cwd:' + self.cwd)
        # logger.debug('    ' + str(self))
        _run = subprocess.check_output if get_output else subprocess.check_call
        # _run = subprocess.check_output
        try:
            output = _run([self.cmd] + self.args,
                          cwd=self.cwd,
                          stdin=subprocess.PIPE)
            if get_output:
                return output.decode("utf-8")
            else:
                return output
        except FileNotFoundError as e:
            logger.error("Launcher: {}".format(e))
            raise RuntimeError("Command '" + self.cmd +
                               "' not found. Make sure it is in $PATH")
        except subprocess.CalledProcessError:
            self.errormsg = '"{}" exited with an error code. See stderr for details.'
            raise RuntimeError(self.errormsg.format(str(self)))

    def __str__(self):
        return ' '.join([self.cmd] + self.args)
