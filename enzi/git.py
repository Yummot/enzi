# -*- coding: utf-8 -*-

import logging
import os
import shutil
import subprocess
import semver
import typing
import copy as py_copy

from enzi.config import Config, validate_git_repo
from enzi.file_manager import FileManager, FileManagerStatus, join_path
from enzi.utils import Launcher, realpath, rmtree_onerror

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


class GitCommand(object):
    def __init__(self):
        self.cmd = 'git'
        self.args = []

    def arg(self, arg):
        self.args.append(str(arg))
        return self

# inspired by bender https://github.com/fabianschuiki/bender


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

    def spawn(self, cmd: GitCommand, get_output=True, suppress_stderr=False):
        return Launcher(cmd.cmd, cmd.args, self.path).run(get_output, suppress_stderr=suppress_stderr)

    def spawn_with(self, f):
        cmd = GitCommand()
        f(cmd)
        return self.spawn(cmd)

    def quiet_spawn_with(self, f):
        cmd = GitCommand()
        f(cmd)
        return self.spawn(cmd, False, True)

    # fetch the tags and refs of a remote git repository
    def fetch(self, remote):
        self.spawn_with(lambda x: x.arg('fetch').arg(
            '-q').arg('--prune').arg(remote))
        self.spawn_with(lambda x:
                        x.arg('fetch').arg('-q').arg('--tags').arg('--prune').arg(remote))

    def init_repo(self, dst_path, url_path):
        """
        Initialize a git repository at the given path
        """
        self.spawn_with(lambda x: x.arg('init').arg('--bare'))
        self.spawn_with(lambda x: x.arg('remote').arg(
            'add').arg('origin').arg(url_path))
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
                                     x.arg(
                                         'rev-parse').arg('--verify').arg(rev_id)
                                     ).strip()
            ret.append((rev_id, ref))
        return ret

    def list_revs(self):
        revs = self.spawn_with(lambda x:
                               x.arg('rev-list').arg('--all').arg('--date-order')).splitlines()
        return revs

    def current_checkout(self):
        return self.spawn_with(lambda x:
                               x.arg(
                                   'rev-parse').arg('--revs-only').arg('HEAD^{commit}')
                               ).splitlines()[0]

    def cat_file(self, hash):
        return self.spawn_with(lambda x:
                               x.arg('cat-file').arg('blob').arg(hash))

    def list_files(self, rev_id, path=None) -> typing.List[TreeEntry]:
        def ls(cmd: GitCommand):
            cmd.arg('ls-tree').arg(rev_id)
            if path:
                cmd.arg(path)
            return cmd
        lines = self.spawn_with(ls).splitlines()
        return list(map(TreeEntry.parse, lines))


class GitRepo(FileManager):
    """
    Manage a git repo which a enzi project, using enzi.git.Git.
    Normall, this call after the dependencies of the root project is resolved.
    """

    def __init__(self, name: str, proj_root: str, git: Git, db_path: str, revision: str, *, enzi_io=None):
        files_root = os.path.dirname(git.path)
        self.db_path = db_path
        self.path = git.path
        self.revision = revision
        self.git: Git = git
        self.enzi_io = enzi_io
        self.enzi_config: typing.Optional[Config] = None
        # before fetch we don't have any known files
        self.fileset: typing.MutableMapping[str,
                                            typing.List[str]] = {'files': []}
        super(GitRepo, self).__init__(name, {}, proj_root, files_root)

    def init_repo(self):
        # lazy operation, skip init_repo if the destination of repo is exists
        if os.path.exists(self.git.path) and validate_git_repo(self.name, self.git.path, test=True):
            fmt = 'GitRepo({}):init_repo: the repo is exists in {}, skipped init_repo'
            msg = fmt.format(self.name, self.git.path)
            logger.debug(msg)
            # get the repo enzi config file
            self.detect_file()
            return
        else:
            fmt = 'GitRepo({}):init_repo: initializing repo in {}'
            msg = fmt.format(self.name, self.git.path)
            logger.debug(msg)
            self.clean_cache()
            os.makedirs(self.git.path, exist_ok=True)

        # clone from enzi database
        git = self.git
        logger.debug('GitRepo({}) initializing'.format(self.name))
        fmt = 'GitRepo({}) Cloning repo from {} to {}'
        msg = fmt.format(self.name, self.db_path, self.git.path)
        logger.debug(msg)
        db_git = Git(self.db_path, self.enzi_io)
        tmp_tag_name = 'enzi-tmp-{}'.format(self.revision)
        db_git.spawn_with(
            lambda x: x.arg('tag')
                       .arg(tmp_tag_name)
                       .arg(self.revision)
                       .arg('--force')
        )
        git.quiet_spawn_with(
            lambda x: x.arg('clone')
                       .arg('-q')
                       .arg(self.db_path)
                       .arg(self.git.path)
                       .arg('--recursive')
                       .arg('--branch')
                       .arg(tmp_tag_name)
        )

        # get the repo enzi config file
        self.detect_file()

    def detect_file(self):
        git = self.git
        config_entry = git.list_files(self.revision, 'Enzi.toml')[0]
        data = git.cat_file(config_entry.hash)
        msg = 'GitRepo({}): loaded Enzi.toml'.format(self.name)
        logger.debug(msg)
        enzi_config = Config.from_str(data, git.path, True, fileset_only=True)

        # extract repo's fileset
        _files = []
        for fileset in enzi_config.filesets.values():
            _new_files = fileset.get('files', [])
            def fn(p): return os.path.normpath(os.path.join(self.path, p))
            _new_files = map(fn, _new_files)
            _files = _files + list(_new_files)
        self.fileset['files'] = _files

        # for git repo, cache_files is the same as it's files listed on fileset
        self.cache_files['files'] = _files

    def check_outdated(self):
        head_rev = self.git.current_checkout()
        if self.status == FileManagerStatus.INIT or self.status == FileManagerStatus.OUTDATED:
            return True

        if head_rev != self.revision:
            fmt_msg = 'GitRepo({}): current revision: {} does not match requirement, fetch the required revision {}'
            logger.debug(fmt_msg.format(self.name, head_rev, self.revision))
            self.status = FileManagerStatus.OUTDATED
            all_revs = self.git.list_revs()
            if not self.revision in all_revs:
                fmt = 'GitRepo({}): cannot find required revision {}'
                err_msg = fmt.format(self.name, self.revision)
                logger.error(err_msg)
                fmt = 'GitRepo({}): suggestion: try to update the database/lock file, via enzi update'
                logger.error(fmt.format(self.name))
                raise RuntimeError(err_msg)
            return True

        return False

    def clean_cache(self):
        if os.path.exists(self.git.path):
            shutil.rmtree(self.git.path, onerror=rmtree_onerror)

    def checkout(self, revision: typing.Union[str, bytes]):
        """
        checkout revision from all available revisions in this git repo
        """
        self.git.spawn_with(
            lambda x: x.arg('checkout').arg('-q').arg(revision)
        )

    def fetch(self):
        if self.status == FileManagerStatus.INIT:
            self.init_repo()

        if self.check_outdated():
            self.checkout(self.revision)
            self.status = FileManagerStatus.FETCHED

        return self.fileset
