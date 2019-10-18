# -*- coding: utf-8 -*-

import logging
import os
import pprint
import shutil
import typing

from enzi import file_manager
from enzi.file_manager import LocalFiles, FileManager
from enzi.file_manager import FileManagerStatus, Fileset
from enzi.git import GitRepo
from enzi.io import EnziIO
from enzi.utils import relpath, rmtree_onerror

logger = logging.getLogger(__name__)
# enzi_logger = logging.getLogger('Enzi')


class ProjectFiles(FileManager):
    def __init__(self, enzi_project):
        proj_root = enzi_project.work_dir
        build_src_dir = os.path.join(enzi_project.build_dir, enzi_project.name)

        self.lf_managers = {}
        self.cache_files = {}
        for target in enzi_project.targets:
            fileset = enzi_project.gen_target_fileset(target)
            name = '{}-target-{}'.format(enzi_project.name, target)
            config = {'fileset': fileset}
            # TODO: code review, whether we need that much of LocalFiles or not
            self.lf_managers[target] = LocalFiles(name,
                                                  config,
                                                  enzi_project.work_dir,
                                                  build_src_dir)
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

        self.deps_fileset = Fileset()

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
        _files = Fileset()
        _ccfiles = Fileset()

        # fetch all git repos
        m = map(lambda x: x.status != FileManagerStatus.EXIST,
                self.git_repos.values())
        any_no_exist = any(m)
        if any_no_exist:
            print('')

        for dep_name, dep in self.git_repos.items():
            logger.debug('ProjectFiles:fetch GitRepo({})'.format(dep_name))
            dep.fetch()
            cache = dep.cached_fileset()
            # convert absolute path into relative path
            def converter(path): return relpath(self.files_root, path)
            files_filter = filter(
                lambda path: path, map(converter, cache.files))
            files = set(files_filter)
            _files.files |= files
            _ccfiles.merge(cache)

        if any_no_exist:
            print('')

        self.deps_fileset = _files

        if file_manager.FM_DEBUG:
            if not _ccfiles.is_empty():
                self.cache_files['deps'] = _ccfiles
                fmt = 'ProjectFiles:fetch deps cache files:\n{}'
                data = pprint.pformat(self.cache_files['deps'].dump_dict())
                msg = fmt.format(data)
                logger.info(msg)

            if not self.deps_fileset.is_empty():
                msg = pprint.pformat(self.deps_fileset.dump_dict())
                logger.info('ProjectFiles:fetch deps fileset:\n{}'.format(msg))

        self.lf_managers[target_name].fetch()
        ccfiles = self.lf_managers[target_name].cached_fileset()

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
        local_fileset = self.lf_managers[target_name].cached_fileset()
        deps_fileset = self.deps_fileset
        files = deps_fileset.merge_into(local_fileset)
        fileset = files.dump_dict()

        if file_manager.FM_DEBUG:
            fmt = 'ProjectFiles:get_fileset: result:\n{}'
            data = pprint.pformat(fileset)
            logger.info(fmt.format(data))

        return fileset
