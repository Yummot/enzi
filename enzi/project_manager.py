# -*- coding: utf-8 -*-

import logging
import os
import shutil

from enzi.file_manager import LocalFiles, FileManager, FileManagerStatus
from enzi.git import GitRepo


logger = logging.getLogger(__name__)


class ProjectFiles(FileManager):
    def __init__(self, enzi_project):
        self.lf_managers = {}
        self.cache_files = {}
        for target in enzi_project.targets:
            fileset = enzi_project.gen_target_fileset(target)
            name = '{}-target-{}'.format(enzi_project.name, target)
            config = {'fileset': fileset}
            self.lf_managers[target] = LocalFiles(name,
                                                  config, enzi_project.work_dir, enzi_project.build_dir)
            self.cache_files[target] = {'files': []}

        self.git_db_records = {}
        self.git_repos = {}

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
                    # self.git_repos[name] = GitRepo()

        self.default_target = next(iter(enzi_project.targets.keys()))
        super(ProjectFiles, self).__init__(enzi_project.name,
                                           {}, enzi_project.work_dir, enzi_project.build_dir)

    def fetch(self, target_name=None):
        if not target_name:
            target_name = self.default_target
        elif not target_name in self.lf_managers.keys():
            raise RuntimeError('Unknown target {}.'.format(target_name))

        # dep_files = []
        # for dep in self.dependencies.values():
        #     cfileset = dep.fetch();
        #     dep_files = dep_files + cfileset['files']

        ccfiles = self.lf_managers[target_name].fetch()

        # if dep_files:
        #     ccfiles['files'] = dep_files + ccfiles['files']

        self.cache_files[target_name] = ccfiles
        self.status = FileManagerStatus.FETCHED

    def clean_cache(self):
        if os.path.exists(self.files_root):
            shutil.rmtree(self.files_root)
        self.status = FileManagerStatus.CLEANED

    def get_fileset(self, target_name=None):
        if not target_name:
            target_name = self.default_target
        elif not target_name in self.lf_managers.keys():
            raise RuntimeError('target {} is not fetched.'.format(target_name))

        return self.lf_managers[target_name].fileset
