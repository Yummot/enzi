# -*- coding: utf-8 -*-

import logging
import os
import shutil
import copy as py_copy
from enum import Enum, unique

logger = logging.getLogger(__name__)


@unique
class FileManagerStatus(Enum):
    INIT = 0
    FETCHED = 1
    OUTDATE = 2
    CLEANED = 3


class FileManager(object):
    """
    FileManager: Manage files from different enzi project.

    @param config: dict, contains extra configuration.
    @param files_root: storage location, relative path, relative to proj_root.
    @param porj_root: current running project root, abspath/relpath.
    """

    def __init__(self, config, proj_root, files_root):
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
            shutil.rmtree(self.files_root)


def join_path(root, file_path):
    return os.path.normpath(os.path.join(root, file_path))


class LocalFiles(FileManager):
    def __init__(self, config, proj_root, files_root):
        config['local'] = True  # LocalFiles must be local
        super(LocalFiles, self).__init__(config, proj_root, files_root)
        if not 'fileset' in config:
            raise RuntimeError('LocalFiles must be initilized with a fileset')
        self.fileset = config['fileset']

        # self.origin_files = [join_path(proj_root, file_path)
        #                      for file_path in config['fileset']]
        # self.cache_files = [join_path(files_root, file_path)
        #                     for file_path in self.origin_files]

    def fetch(self):
        for file in self.fileset['files']:
            src_file = join_path(self.proj_root, file)
            dst_file = join_path(self.files_root, file)
            if os.path.exists(src_file):
                dst_dir = os.path.dirname(dst_file)
                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir)
                shutil.copyfile(src_file, dst_file)
                self.cache_files['files'].append(dst_file)
            else:
                msg = 'File {} not found.'.format(src_file)
                logger.error(msg)
                raise FileNotFoundError(msg)
        self.status = FileManagerStatus.FETCHED
        return self.cache_files
