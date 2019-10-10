# -*- coding: utf-8 -*-

import logging
import os
import shutil
import copy as py_copy
from enum import Enum, unique

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
        self.cache_files = {'files': []}
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
        self.fileset = {'files': list(files_map)}
        self.build_root = build_root

    def fetch(self):
        for file in self.fileset['files']:
            src_file = join_path(self.proj_root, file)
            dst_file = join_path(self.files_root, file)
            
            if os.path.exists(src_file):
                dst_dir = os.path.dirname(dst_file)
                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir)
                shutil.copyfile(src_file, dst_file)
                if self.build_root:
                    dst_file = os.path.relpath(dst_file, self.proj_root)
                self.cache_files['files'].append(dst_file)
            else:
                msg = 'File {} not found.'.format(src_file)
                logger.error(msg)
                raise FileNotFoundError(msg)
        self.status = FileManagerStatus.FETCHED
        return self.cache_files
