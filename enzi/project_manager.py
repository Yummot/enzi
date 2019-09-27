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
            config = {'fileset': fileset}
            self.lf_managers[target] = LocalFiles(
                config, enzi_project.work_dir, enzi_project.build_dir)
            self.cache_files[target] = {'files': []}

        # self.dependencies = {}

        # if enzi_project.dependencies:
        #     for dep_name, dep in enzi_project.dependencies.items():
        #         repo_config = dep.git_repo_config()
        #         self.dependencies[dep_name] = GitRepo(
        #             repo_config,  enzi_project.work_dir, enzi_project.build_dir)
        
        # print(self.dependencies)

        self.default_target = next(iter(enzi_project.targets.keys()))
        super(ProjectFiles, self).__init__(
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
        import pprint
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
