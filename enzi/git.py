import logging
import os
import shutil
import subprocess
import semver
import typing
import copy as py_copy

from enzi.config import Config
from enzi.file_manager import FileManager, FileManagerStatus, join_path
from enzi.utils import Launcher, realpath

logger = logging.getLogger(__name__)

class GitVersions(object):
    def __init__(self, versions, refs, revisions):
        """
        @param versions: List[Tuple[semver.VersionInfo, str]]
        @param refs: Dict[str, str]
        @param revisions: List[str]
        """
        self.versions: typing.List[typing.Tuple[semver.VersionInfo, str]] = versions
        self.refs: typing.MutableMapping[str, str] = refs
        self.revisions: typing.List[str] = revisions
    
    def __repr__(self):
        str_buf = ['GitVersions {']
        str_buf.append('\tversions: {}'.format(self.versions))
        str_buf.append('\trefs: {}'.format(self.refs))
        str_buf.append('\trevisions: {}'.format(self.revisions))
        str_buf.append('}')
        return '\n'.join(str_buf)

# TODO: safely remove this class
class GitRepo(FileManager):
    """
    DEPRECATED
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
        version = self.version if self.version.startswith(
            'v') else 'v' + self.version
        commit = self.commit if hasattr(self, 'commit') else version
        git_args = ['-C', self.repo_path, 'checkout', '-q', commit]
        try:
            Launcher('git', git_args).run()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(str(e))

    def _detect_files(self):
        repo_path = self.repo_path
        # # check invalid deps
        # for dep_name, dep in config.dependencies.items():
        #     if self.is_local and dep.is_remote:
        #         raise RuntimeError('Remote DependencySource {}\'s DependencySource \
        #             {} is a local DependencySource'.format(self.name, dep_name))
        if self.status != FileManagerStatus.FETCHED:
            return

        config = Config(os.path.join(repo_path, 'Enzi.toml'))
        _files = []
        for value in config.filesets.values():
            _files = _files + value.get('files', [])
        self.fileset = {'files': _files}

        for file in self.fileset['files']:
            cached_file = join_path(repo_path, file)
            self.cache_files['files'].append(cached_file)

    def fetch(self):
        self._fetch_repo()
        self._checkout()
        self.status = FileManagerStatus.FETCHED
        self._detect_files()
        return self.cache_files


class GitCommand(object):
    def __init__(self):
        self.cmd = 'git'
        self.args = []

    def arg(self, arg):
        self.args.append(str(arg))
        return self

# inspired by bender https://github.com/fabianschuiki/bender


class Git(object):
    def __init__(self, path, enzi_io=None):
        """
        Init a Git database,
        Store a real path of the cwd on where this Git is operated.
        """
        if not os.path.isabs(path):
            path = realpath(path)
        self.path = path
        self.enzi_io = enzi_io

    def spawn(self, cmd: GitCommand):
        return Launcher(cmd.cmd, cmd.args, self.path).run(True)

    def spawn_with(self, f):
        cmd = GitCommand()
        f(cmd)
        return self.spawn(cmd)

    # fetch the tags and refs of a remote git repository
    def fetch(self, remote):
        self.spawn_with(lambda x: x.arg('fetch').arg('--prune').arg(remote))
        self.spawn_with(lambda x: 
            x.arg('fetch').arg('--tags').arg('--prune').arg(remote))

    def init_repo(self, dst_path, url_path):
        """
        Initialize a git repository at the given path
        """
        self.spawn_with(lambda x: x.arg('init').arg('--bare'))
        self.spawn_with(lambda x: x.arg('remote').arg('add').arg('origin').arg(url_path))
        self.fetch('origin')

    def list_refs(self):
        refs = self.spawn_with(lambda x: x.arg('show-ref'))
        ret = []
        for line in refs.splitlines():
            fields = line.split()
            # TODO: bender said: Handle the case where the line might not contain enough
            # information or is missing some fields.
            rev_id = fields[0]
            ref = fields[1]
            rev_id = rev_id + '^{commit}'
            rev_id = self.spawn_with(lambda x:
                x.arg('rev-parse').arg('--verify').arg(rev_id)
            ).strip()
            ret.append((rev_id, ref))
        return ret
    
    def list_revs(self):
        revs = self.spawn_with(lambda x:
            x.arg('rev-list').arg('--all').arg('--date-order')).splitlines()
        return revs     

    def current_checkout(self):
        return self.spawn_with(lambda x: 
            x.arg('rev-parse').arg('--revs-only').arg('HEAD^{commit}')
        ).splitlines()[0]
    
    def cat_file(self, hash):
        return self.spawn_with(lambda x: 
            x.arg('cat-file').arg('blob').arg(hash))
    
    def list_files(self, rev_id, path=None):

        lines = self.spawn_with(lambda x:
            x.arg('ls-tree').arg(rev_id)
        ).splitlines()
        return list(map(TreeEntry.parse, lines))

class TreeEntry(object):
    def __init__(self, input: str):
        tab_idx = input.find('\t')
        meta, name = input[0:tab_idx], input[tab_idx+1:]
        meta_fields = meta.split()
        self.name = name
        self.hash = meta_fields[2]
        self.kind = meta_fields[1]
        self.mode = meta_fields[0]

    @staticmethod
    def parse(input):
        return TreeEntry(input)

    def __str__(self):
        return 'TreeEntry{{ name: {}, hash: {}, kind: {} }}'.format(
            self.name, self.hash, self.kind)

# import pprint
# git = Git('./build/xxx')
# if os.path.exists('./build/xxx'):
#     shutil.rmtree('./build/xxx')
# os.makedirs('./build/xxx')
# git.init_repo('./build/xxx', 'https://github.com/Shoobx/python-graph.git')
# git.spawn_with(lambda x: 
#     x.arg('tag')
#         .arg('tag-test')
#         .arg('afd6f1cf0f04350d05ea28ad3ea567b623031ae4')
#         .arg('--force')
# )

# git.spawn_with(lambda x:
#     x.arg('clone')
#         .arg(git.path)
#         .arg('../yyy')
#         .arg('--recursive')
#         .arg('--branch')
#         .arg('tag-test')
# )
