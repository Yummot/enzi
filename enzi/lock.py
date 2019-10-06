import logging
import os
import pprint
import toml
import typing
import copy as py_copy

from enzi import __version__
from enzi.config import Locked, flat_git_records

logger = logging.getLogger(__name__)

LOCKED_HEADER = '# Auto generated by Enzi v{}'.format(__version__)


class LockLoader(object):
    def __init__(self, enzi, lock_path):
        lock_file = os.path.join(lock_path, 'Enzi.lock')

        self.lock_existing: typing.Optional[Locked]
        self.lock_path: str = lock_path
        self.enzi: enzi.frontend.Enzi = enzi
        self.lock_file = lock_file
        if os.path.exists(lock_file):
            self.lock_existing = Locked.load(lock_file)
        else:
            self.lock_existing = None

    def load(self, update=False):
        # check if config file metatdata change after the exiting lockfile was generated.
        if self.lock_existing:
            config_path = self.lock_existing.config_path
            config_mtime = self.lock_existing.config_mtime
            mtime_changed = config_mtime < self.enzi.config_mtime
            path_changed = config_path != self.enzi.config_path
            changed = mtime_changed or path_changed
            update = update or changed
            if changed:
                msg = "Enzi Config File was modified since last execution"
                logger.debug(msg)

        if update or not self.lock_existing:
            from enzi.deps_resolver import DependencyResolver
            if update:
                fmt = 'LockLoader: lock file {} outdated'
                msg = fmt.format(self.lock_file)
                logger.debug(msg)
                logger.debug('LockLoader: start updating')
            else:
                fmt = 'LockLoader: create new lock file {}'
                msg = fmt.format(self.lock_file)
                logger.debug(msg)

            resolver = DependencyResolver(self.enzi)
            new_locked = resolver.resolve()

            lock_file_buf = [LOCKED_HEADER]

            if self.enzi.git_db_records:
                git_db_records = self.enzi.git_db_records
                new_locked.add_cache('git', git_db_records)
                logger.debug(
                    'LockLoader: database records\n{}'.format(git_db_records))

            locked_dump = new_locked.dumps()
            dumps_str = toml.dumps(locked_dump)
            lock_file_buf.append(dumps_str)

            lock_file_data = '\n'.join(lock_file_buf)
            with open(self.lock_file, 'w') as f:
                f.write(lock_file_data)

            self.lock_existing = new_locked
        else:
            logger.debug(
                'LockLoader: lock file {} up to date'.format(self.lock_file))

        if update:
            logger.debug('LockLoader: update finished')
        return self.lock_existing
