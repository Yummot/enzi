from hashlib import blake2b
import logging
import os
import typing

from enzi.config import DependencyRef, DependencyVersion
from enzi.config import RawConfig
from enzi.frontend import Enzi
from enzi.git import Git, GitRepo, GitVersions, TreeEntry
from enzi.utils import PathBuf, try_parse_semver

logger = logging.getLogger(__name__)

HASH_GDEP_NAME = os.environ.get('HASH_GDEP_NAME')


class EnziIO(object):
    """
    IO Spawner class for Enzi
    """
    # TODO: Currently, EnziIO only work in sync way. We may make async an option.

    def __init__(self, enzi: Enzi):
        self.enzi = enzi

    def git_db_dir(self, name):
        # TODO: change git database name format
        if HASH_GDEP_NAME:
            name_hash_slice = blake2b(name.encode('utf-8')).hexdigest()[:16]
            db_name = '{}-{}'.format(name, name_hash_slice)
        else:
            db_name = name

        db_dir: PathBuf = self.enzi.database_path.join(
            'git').join('db').join(db_name)

        return db_dir
    
    def git_repo_dir(self, name):
        # TODO: change git database name format
        if HASH_GDEP_NAME:
            name_hash_slice = blake2b(name.encode('utf-8')).hexdigest()[:16]
            repo_name = '{}-{}'.format(name, name_hash_slice)
        else:
            repo_name = name
        repo_dir = self.enzi.build_deps_path.join(repo_name)
        
        return repo_dir

    def git_repo(self, name, db_path, revision, *, proj_root=None) -> GitRepo:
        """
        create a git repo with given db_path and revision,
        the storage path is build from enzi.build_deps_path + name + Optional[blake2b[:16]]
        """
        # TODO: change git database name format
        repo_dir = self.git_repo_dir(name)
        git = Git(repo_dir.path, self)
        if proj_root is None:
            proj_root = self.enzi.work_dir
        return GitRepo(name, proj_root, git, db_path, revision, enzi_io=self)

    def dep_versions(self, dep_id):
        dep = self.enzi.dependecy(dep_id)
        git_url = dep.source.git_url
        dep_git = self.git_database(dep.name, git_url)
        return self.git_versions(dep_git)

    def git_database(self, name, git_url) -> Git:

        # TODO: cache db_dir in Enzi
        db_dir: PathBuf = self.git_db_dir(name)
        os.makedirs(db_dir.path, exist_ok=True)
        git = Git(db_dir.path, self)

        logger.debug("EnziIO:git_database: new git_db at {}, origin: {}".format(
            db_dir.path, git_url))

        git_db_records = self.enzi.git_db_records
        if name in git_db_records:
            git_db_records[name].add(db_dir.path)
        else:
            git_db_records[name] = set([db_dir.path])

        if not db_dir.join("config").exists():
            git.spawn_with(lambda x: x.arg('init').arg('--bare'))
            git.spawn_with(lambda x: x.arg('remote').arg('add')
                           .arg('origin').arg(git_url))
            git.fetch('origin')
            return git
        else:
            db_mtime = os.stat(db_dir.join('FETCH_HEAD').path).st_mtime_ns
            if self.enzi.config_mtime < db_mtime:
                logger.debug('skip update of {}'.format(db_dir.path))
                return git
            git.fetch('origin')
            return git

    def git_versions(self, git: Git) -> GitVersions:
        dep_refs = git.list_refs()
        dep_revs = git.list_revs()

        rev_ids = set(dep_revs)

        # get tags and branches
        tags = {}
        branches = {}
        tag_prefix = "refs/tags/"
        branch_prefix = "refs/remotes/origin/"
        for rev_id, ref in dep_refs:
            if not rev_id in rev_ids:
                continue
            if ref.startswith(tag_prefix):
                tags[ref[len(tag_prefix):]] = rev_id
            elif ref.startswith(branch_prefix):
                branches[ref[len(branch_prefix):]] = rev_id

        # extract the tags that look like semver
        res_map = map(try_parse_semver, tags.items())
        versions = list(filter(lambda x: x, res_map))
        # TODO: check if this sort is correct.
        versions.sort()
        refs = {**branches, **tags}

        return GitVersions(versions, refs, dep_revs)

    def dep_config_version(self, dep_id: DependencyRef, version: DependencyVersion):
        # from enzi.config import DependencySource as DepSrc
        # from enzi.config import DependencyVersion as DepVer
        # TODO: cache dep_config to reduce io workload

        dep = self.enzi.dependecy(dep_id)

        logger.debug("dep_config_version: get dep {}".format(dep.dump_vars()))

        if dep.source.is_git() and version.is_git():
            dep_name = dep.name
            git_url = dep.source.git_url
            is_local = dep.is_local
            git_rev = version.revision
            git_db = self.git_database(dep_name, git_url)

            entries: typing.List[TreeEntry] = git_db.list_files(
                git_rev, 'Enzi.toml')
            # actually, there must be only one entry
            entry = entries[0]
            data = git_db.cat_file(entry.hash)
            logger.debug('dep_config_version: dep_name={}, db_path={}'.format(
                dep_name, git_db.path))
            # logger.debug(data)
            dep_config = RawConfig(
                data, 
                from_str=True, 
                base_path=git_db.path,
                is_local=is_local,
                git_url=git_url
            ).validate()
            return dep_config
        else:
            raise RuntimeError('INTERNAL ERROR: unreachable')
