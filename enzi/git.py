from enzi.file_manager import FileManager, FileManagerStatus, join_path
import logging
import os
import shutil
import copy as py_copy
import subprocess
from enzi.utils import Launcher
from enzi.parse_config import Config

logger = logging.getLogger(__name__)


class GitRepo(FileManager):
    """
    Manage a git repo which a enzi project,
    assume this is call after deps is resolved
    """
    def __init__(self, config, proj_root, files_root):
        if 'path' in config:
            config['local'] = True  # LocalFiles must be local
            self.path = config['path']
        elif 'url' in config:
            config['local'] = False
            self.url = config['url']
        super(GitRepo, self).__init__(config, proj_root, files_root)

        if config['use_version']:
            self.version = config['version']
        else:
            self.commit = config['commit']

        self.name = config['name']
        self.repo_path = os.path.join(self.files_root, self.name)

    def clean_cache(self):
        if os.path.exists(self.repo_path):
            shutil.rmtree(self.repo_path)

    def _fetch_repo(self):
        origin_path = self.path if self.is_local else self.url
            
        if os.path.exists(self.repo_path):
            self.clean_cache()

        logger.info("Cloning dependency {} into {}".format(
            self.name, self.files_root))
        git_args = ['clone', '-q', origin_path, self.repo_path]
        try:
            Launcher('git', git_args).run()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(str(e))

    def _checkout(self):
        version = self.version if self.version.startswith('v') else 'v' + self.version
        commit = self.commit if hasattr(self, 'commit') else version
        git_args = ['-C', self.repo_path,'checkout', '-q', commit]
        try:
            Launcher('git', git_args).run()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(str(e))

    def _detect_files(self):
        repo_path = self.repo_path
        # # check invalid deps
        # for dep_name, dep in config.dependencies.items():
        #     if self.is_local and dep.is_remote:
        #         raise RuntimeError('Remote Dependency {}\'s dependency \
        #             {} is a local dependency'.format(self.name, dep_name))
        if self.status != FileManagerStatus.FETCHED:
            return

        config = Config(os.path.join(repo_path, 'Enzi.toml'))
        _files = []
        for value in config.filesets.values():
            _files = _files + value.get('files', [])
        self.fileset = { 'files': _files }
        
        for file in self.fileset['files']:
            cached_file = join_path(repo_path, file)
            self.cache_files['files'].append(cached_file)

    def fetch(self):
        self._fetch_repo()
        self._checkout()
        self.status = FileManagerStatus.FETCHED
        self._detect_files()
        return self.cache_files
