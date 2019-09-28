import logging
import os
import pprint
import toml
import typing
import copy as py_copy

import enzi
from enzi.config import Locked

logger = logging.getLogger(__name__)


def flat_records(item):
    name, records = item
    if len(records) == 1:
        record = list(records)[0]
        return (name, {'path': record})
    else:
        return (name, {'path': records})


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

    # TODO: Enzi add update arg
    def load(self, update=False):
        if update or not self.lock_existing:
            from enzi.deps_resolver import DependencyResolver
            if update:
                logger.debug(
                    'LockLoader: lock file {} outdated'.format(self.lock_file))
            else:
                logger.debug(
                    'LockLoader: create new lock file {}'.format(self.lock_file))

            resolver = DependencyResolver(self.enzi)
            new_locked = resolver.resolve()
            locked_dump = new_locked.dumps()

            lock_file_buf = ['# Auto generated by Enzi']
            deps_map_str = toml.dumps(locked_dump)
            lock_file_buf.append(deps_map_str)

            if self.enzi.git_db_records:
                git_db_records = dict(
                    map(flat_records, self.enzi.git_db_records.items()))
                caches_dict = {'cache': {'git': git_db_records}}

                caches_str = toml.dumps(caches_dict)
                lock_file_buf.append(caches_str)

                logger.debug(
                    'LockLoader: database records\n{}'.format(caches_str))

            lock_file_data = '\n'.join(lock_file_buf)
            with open(self.lock_file, 'w') as f:
                f.write(lock_file_data)

            self.lock_existing = new_locked
        else:
            logger.debug(
                'LockLoader: lock file {} up to date'.format(self.lock_file))
        return self.lock_existing
