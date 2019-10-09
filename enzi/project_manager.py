# -*- coding: utf-8 -*-

import logging
import os
import pprint
import shutil
import typing

from enzi import file_manager
from enzi.file_manager import LocalFiles, FileManager
from enzi.file_manager import FileManagerStatus
from enzi.git import GitRepo
from enzi.io import EnziIO
from enzi.utils import relpath, rmtree_onerror

logger = logging.getLogger(__name__)
# enzi_logger = logging.getLogger('Enzi')

class ProjectFiles(FileManager):
    def __init__(self, enzi_project):
        proj_root = enzi_project.work_dir

        self.lf_managers = {}
        self.cache_files = {}
        for target in enzi_project.targets:
            fileset = enzi_project.gen_target_fileset(target)
            name = '{}-target-{}'.format(enzi_project.name, target)
            config = {'fileset': fileset}
            # TODO: code review, whether we need that much of LocalFiles or not
            self.lf_managers[target] = LocalFiles(name,
                                                  config, enzi_project.work_dir, enzi_project.build_dir)
            self.cache_files[target] = {'files': []}

        self.git_db_records = {}
        self.git_repos: typing.Mapping[str, GitRepo] = {}

        enzi_io = EnziIO(enzi_project)

        self.dependencies = {}
        if enzi_project.locked:
            locked_deps = enzi_project.locked.dependencies

        if enzi_project.git_db_records:
            self.git_db_records = enzi_project.git_db_records
            for name, paths in self.git_db_records.items():
                if len(paths) != 1:
                    msg = 'unimplemented: for multiple git db paths with the same name, {}({}).'.format(
                        name, paths)
                    logger.error(msg)
                    raise RuntimeError(msg)
                else:
                    path = list(paths)[0]
                    locked_dep = locked_deps[name]
                    revision = locked_dep.revision
                    git_repo = enzi_io.git_repo(
                        name, path, revision, proj_root=proj_root)
                    self.git_repos[name] = git_repo

        self.deps_fileset = {'files': []}

        self.default_target = next(iter(enzi_project.targets.keys()))

        super(ProjectFiles, self).__init__(enzi_project.name,
                                           {}, proj_root, enzi_project.build_dir)

    def fetch(self, target_name=None):
        logger.debug('ProjectFiles:fetching')
        if not target_name:
            target_name = self.default_target
        elif not target_name in self.lf_managers.keys():
            raise RuntimeError('Unknown target {}.'.format(target_name))

        # TODO: generate fileset with deps order, maybe use DFS?
        _files = []
        _ccfiles = []
        
        # fetch all git repos
        m = map(lambda x: x.status != FileManagerStatus.EXIST, self.git_repos.values())
        any_no_exist = any(m)
        if any_no_exist:
            print('')

        for dep_name, dep in self.git_repos.items():
            logger.debug('ProjectFiles:fetch GitRepo({})'.format(dep_name))
            cache = dep.fetch()
            # extract deps fileset from git repo
            cache_files = cache['files']
            # convert absolute path into relative path
            converter = lambda path: relpath(self.files_root, path)
            files_filter = filter(lambda path: path, map(converter, cache_files))
            files = list(files_filter)
            _files = _files + files
            _ccfiles = _ccfiles + cache_files
        
        if any_no_exist:
            print('')

        self.deps_fileset['files'] = _files

        if file_manager.FM_DEBUG:
            if _ccfiles:
                self.cache_files['deps'] = { 'files': _ccfiles }
                fmt = 'ProjectFiles:fetch deps cache files:\n{}'
                data = pprint.pformat(self.cache_files['deps'])
                msg = fmt.format(data)
                logger.info(msg)

            if self.deps_fileset['files']:
                msg = pprint.pformat(self.deps_fileset)
                logger.info('ProjectFiles:fetch deps fileset:\n{}'.format(msg))

        ccfiles = self.lf_managers[target_name].fetch()

        self.cache_files[target_name] = ccfiles
        self.status = FileManagerStatus.FETCHED

    def clean_cache(self):
        if os.path.exists(self.files_root):
            shutil.rmtree(self.files_root, onerror=rmtree_onerror)
        self.status = FileManagerStatus.CLEANED

    def get_fileset(self, target_name=None):
        if not self.status == FileManagerStatus.FETCHED:
            msg = 'ProjectFiles:get_fileset try to get fileset from an outdated ProjectFiles'
            logger.error(msg)
            raise RuntimeError(msg)
        if not target_name:
            target_name = self.default_target
        elif not target_name in self.lf_managers.keys():
            raise RuntimeError('target {} is not fetched.'.format(target_name))
        
        # merge deps fileset
        local_fileset = self.lf_managers[target_name].fileset['files']
        deps_fileset = self.deps_fileset['files']
        files = deps_fileset + local_fileset
        fileset = { 'files': files }

        if file_manager.FM_DEBUG:
            fmt = 'ProjectFiles:get_fileset: result:\n{}'
            data = pprint.pformat(fileset)
            logger.info(fmt.format(data))

        return fileset
