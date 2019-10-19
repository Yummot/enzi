# -*- coding: utf-8 -*-

import logging
import os
import platform
import pprint
import re
import shutil
import copy as py_copy

from collections.abc import Iterable
from enum import Enum, unique

from ordered_set import OrderedSet
from enzi.utils import rmtree_onerror

logger = logging.getLogger(__name__)

# use an environment variable `FM_DEBUG` to control Launcher debug output
FM_DEBUG = os.environ.get('FM_DEBUG')


@unique
class FileManagerStatus(Enum):
    INIT = 0
    FETCHED = 1
    OUTDATED = 2
    CLEANED = 3
    # a status for git repository to indicate it has been clone in the working directory
    EXIST = 4


RE = re.compile(r'`include\s*"(.*)"')


class Fileset(object):
    """
    A include files resolver for Verilog/SystemVerilog
    """

    def __init__(self, files=None):
        if files is None:
            files = OrderedSet()
        elif isinstance(files, Iterable):
            files = OrderedSet(files)
        else:
            raise ValueError('files must be iterable')
        self.files = files
        self.inc_dirs = OrderedSet()
        self.inc_files = OrderedSet()

    def is_empty(self):
        if not (self.files or self.inc_dirs or self.inc_files):
            return True
        else:
            return False

    def update(self, other):
        if not isinstance(other, Fileset):
            raise ValueError('cannot use a not Fileset object to update')
        self.files = other.files
        self.inc_dirs = other.inc_dirs
        self.inc_files = other.inc_files

    def dedup(self):
        """dedup files which are include files"""
        self.files -= self.inc_files
        self.inc_files = set()

    def merge_into(self, other):
        """merge into a new Fileset"""
        if not isinstance(other, Fileset):
            raise ValueError('cannot merge a not Fileset object')
        ret = Fileset()
        ret.files = self.files | other.files
        ret.inc_dirs = self.inc_dirs | other.inc_dirs
        ret.inc_files = self.inc_files | other.inc_files
        return ret

    def merge(self, other):
        if not isinstance(other, Fileset):
            raise ValueError('cannot merge a not Fileset object')
        self.files |= other.files
        self.inc_dirs |= other.inc_dirs
        self.inc_files |= other.inc_files

    def add_file(self, file):
        self.files.add(file)

    def add_inc_dir(self, inc_dir):
        self.inc_dirs.add(inc_dir)

    def add_inc_file(self, inc_file):
        self.inc_files.add(inc_file)

    def dump_dict(self):
        ret = {}
        ret['files'] = list(self.files)
        ret['inc_dirs'] = list(self.inc_dirs)
        ret['inc_files'] = list(self.inc_files)
        return ret


class IncDirsResolver:
    """An Include Directories Resolver for SystemVerilog/Verilog files"""
    VEXT = ('.vh', 'svh', 'v', 'sv')

    def __init__(self, files_root, files=None):
        self.files_root = files_root
        self.dfiles_cache = dict()
        if files:
            if files_root:
                f = lambda x: os.path.normpath(os.path.join(files_root, x))
                files = map(f, files)
            else:
                files = map(lambda x: os.path.normpath(x), files)
            self.fileset = Fileset(files)
        else:
            self.fileset = Fileset()

    def update_files(self, files, files_root=None):
        if files_root:
            self.files_root = files_root
        if not isinstance(files, Fileset):
            files = map(lambda x: os.path.join(self.files_root, x), files)
            self.fileset = Fileset(files)
        else:
            self.fileset.merge(files)

    def resolve(self):
        _ = list(map(self.extract_include_dirs, self.fileset.files))
        self.fileset.dedup()
        if FM_DEBUG:
            pfmt = pprint.pformat(self.fileset.dump_dict())
            logger.info("resolved: \n{}".format(pfmt))
        self.dfiles_cache = dict()
        return self.fileset

    def check_include_files(self, files_root, *, clogger=None):
        """check all include files will full paths. Internal use only."""
        if clogger is None:
            clogger = logger
        for file in self.fileset.files:
            dirname = os.path.dirname(file)
            include_files = list(self.get_include_files(file))
            if not include_files:
                continue
            for include_file in include_files:
                dname = os.path.dirname(include_file)
                ifname = os.path.basename(include_file)
                if dname and platform.system() == 'Windows':
                    dname = dname.replace('/', '\\')
                if dname:
                    incdir = os.path.join(dirname, dname)
                    incdir = os.path.join(files_root, incdir)
                    incdir = os.path.normpath(incdir)
                    ifile_path = os.path.join(incdir, ifname)
                    if not os.path.exists(ifile_path):
                        fmt = 'include file "{}" in file "{}" is not exists'
                        msg = fmt.format(include_file, file)
                        clogger.warning(msg)
                        continue
                    rel_root = os.path.relpath(incdir, files_root)
                    if rel_root.startswith('..'):
                        fmt = 'include file "{}" in file "{}" is outside the package directory'
                        msg = fmt.format(include_file, file)
                        clogger.warning(msg)

    def get_include_files(self, file):
        """return a iterator of include files of the given file"""
        with open(file, 'rb') as f:
            data = f.read().decode('utf-8')
            lines = data.splitlines()
            m = map(str.strip, lines)
            ft = filter(lambda x: x.startswith('`include'), m)
            ex = map(lambda x: RE.search(x).group(1), ft)
            return ex

    def extract_include_dirs(self, file):
        if not file.endswith(self.VEXT):
            return
        fs = self.fileset
        dirname = os.path.dirname(file)
        if not dirname in self.dfiles_cache:
            dir_files = set(os.listdir(dirname))
            self.dfiles_cache[dirname] = dir_files
        else:
            dir_files = self.dfiles_cache[dirname]
        fs.add_inc_dir(dirname)

        include_files = list(self.get_include_files(file))
        if not include_files:
            return

        for include_file in include_files:
            dname = os.path.dirname(include_file)
            if dname and platform.system() == 'Windows':
                dname = dname.replace('/', '\\')
            if dname:
                incdir = os.path.join(dirname, dname)
                if os.path.exists(incdir):
                    fname = os.path.basename(include_file)
                    include_file = os.path.join(incdir, fname)
                    fs.add_inc_dir(incdir)
                    fs.add_inc_file(include_file)
                else:
                    msg = '{} is not exists'.format(incdir)
                    logger.debug(msg)
            else:
                if include_file in dir_files:
                    include_file = os.path.join(dirname, include_file)
                    fs.add_inc_dir(dirname)
                    fs.add_inc_file(include_file)


class FileManager(object):
    """
    FileManager: Manage files from different enzi project.

    :param config: dict, contains extra configuration.
    :param files_root: storage location, relative path, relative to proj_root.
    :param porj_root: current running project root, abspath/relpath.
    """

    def __init__(self, name, config, proj_root, files_root):
        _cname = self.__class__.__name__
        logger.debug('FileManager: new {}({}) with proj_root: {}, files_root: {}'.format(
            self.__class__.__name__, name, proj_root, files_root))
        self.name = name
        self.config = config
        self.proj_root = os.path.normpath(proj_root)
        self.files_root = os.path.normpath(files_root)
        self.is_local = config.get('local', False)
        self.status = FileManagerStatus.INIT
        # before fetch we have no cache files
        # self.cache_files = Fileset()
        # self.cachable = config.get('cachable', False)

    def checkout(self):
        """
        method to support caching remote project files
        """
        pass

    def fetch(self):
        """
        method to make files cache
        """
        pass

    def clean_cache(self):
        if os.path.exists(self.files_root):
            shutil.rmtree(self.files_root, onerror=rmtree_onerror)


def join_path(root, file_path):
    return os.path.normpath(os.path.join(root, file_path))


class LocalFiles(FileManager):
    # def __init__(self, name, config, proj_root, files_root):
    def __init__(self, name, config, proj_root, files_root, build_root=None):
        config['local'] = True  # LocalFiles must be local
        super(LocalFiles, self).__init__(name, config, proj_root, files_root)
        if not 'fileset' in config:
            raise RuntimeError('LocalFiles must be initilized with a fileset')

        files = config['fileset'].get('files', [])
        files_map = map(lambda p: os.path.normpath(p), files)
        self.fileset = Fileset()
        self.fileset.files = OrderedSet(files_map)
        self.build_root = build_root
        self.resolver = IncDirsResolver(files_root, [])
        self.cache_files = Fileset()

    def fetch(self):
        for file in self.fileset.files:
            src_file = join_path(self.proj_root, file)
            dst_file = join_path(self.files_root, file)

            if os.path.exists(src_file):
                dst_dir = os.path.dirname(dst_file)
                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir)
                shutil.copyfile(src_file, dst_file)
                self.cache_files.files.add(dst_file)
            else:
                msg = 'File {} not found.'.format(src_file)
                logger.error(msg)
                raise FileNotFoundError(msg)
        self.status = FileManagerStatus.FETCHED
        self.resolver.update_files(self.cache_files)

    def cached_fileset(self):
        """return a Fileset object containing the cached fileset"""
        if self.status != FileManagerStatus.FETCHED:
            self.fetch()
        ret = self.resolver.resolve()
        if FM_DEBUG:
            pfmt = pprint.pformat(ret.dump_dict())
            logger.info('cached fileset: \n{}'.format(pfmt))
        return ret
