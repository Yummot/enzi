import logging
import os
import toml
import typing
from enzi.config import Locked
from enzi.deps_resolver import DependencyResolver

logger = logging.getLogger(__name__)

class LockLoader(object):
    def __init__(self, enzi, lock_path):
        lock_file = os.path.join(lock_path, 'Enzi.lock')

        self.lock_existing: typing.Optional[Locked]
        self.lock_path: str = lock_path
        self.enzi = enzi
        self.lock_file = lock_file
        if os.path.exists(lock_file):
            self.lock_existing = Locked.load(lock_file)
        else:
            self.lock_existing = None

    # TODO: Enzi add update arg
    def load(self, update=False):
        if update or not self.lock_existing:
            if update:
                logger.debug(
                    'LockLoader: lock file {} outdated'.format(self.lock_file))
            else:
                logger.debug(
                    'LockLoader: create new lock file {}'.format(self.lock_file))

            resolver = DependencyResolver(self.enzi)
            new_locked = resolver.resolve()
            locked_dump = new_locked.dumps()
            with open(self.lock_file, 'w') as f:
                toml.dump(locked_dump, f)
            self.lock_existing = new_locked
        else:
            logger.debug(
                'LockLoader: lock file {} up to date'.format(self.lock_file))
        return self.lock_existing
