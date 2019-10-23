# -*- coding: utf-8 -*-

import logging
import os
import pprint
import shutil
import typing

import networkx as nx

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
            self.cache_files[target] = Fileset()

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
        self.deps_graph = enzi_project.deps_graph

        self.default_target = next(iter(enzi_project.targets.keys()))

        super(ProjectFiles, self).__init__(enzi_project.name,
                                           {}, proj_root, enzi_project.build_dir)

    def fetch(self, target_name=None):
        logger.debug('ProjectFiles:fetching')
        if not target_name:
            target_name = self.default_target
        elif not target_name in self.lf_managers.keys():
            raise RuntimeError('Unknown target {}.'.format(target_name))

        _files = Fileset()
        _ccfiles = Fileset()

        # fetch all git repos
        m = map(lambda x: x.status != FileManagerStatus.EXIST,
                self.git_repos.values())
        any_no_exist = any(m)
        if any_no_exist:
            logger.warning('Some dependencies\' do not exist.')

        postorder_deps = nx.dfs_postorder_nodes(self.deps_graph)
        postorder_deps = list(postorder_deps)[:-1]
        # converter = lambda path: relpath(self.files_root, path)
        for dep_name in postorder_deps:
            dep = self.git_repos.get(dep_name)
            dep.fetch()
            cache = dep.cached_fileset()
            # files_filter = filter(
            #     lambda path: path, map(converter, cache.files))
            # files = set(files_filter)
            _files.inc_dirs.update(cache.inc_dirs)
            _files.files.update(cache.files)
            _ccfiles.merge(cache)

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
        fileset = deps_fileset.merge_into(local_fileset)
        # fileset = fileset.dump_dict()

        if file_manager.FM_DEBUG:
            inc_dirs = {}
            for k, v in fileset['inc_dirs'].items():
                inc_dirs[k] = list(v)
            pfmt = pprint.pformat(inc_dirs)
            fmt = 'ProjectFiles: include directories for each file:\n{}'
            msg = fmt.format(pfmt)
            logger.info(msg)
            fmt = 'ProjectFiles:get_fileset: result:\n{}'
            pfiles = { 'files': fileset['files'] }
            pfmt = pprint.pformat(pfiles)
            logger.info(fmt.format(pfmt))

        return fileset
