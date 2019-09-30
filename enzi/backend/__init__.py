# -*- coding: utf-8 -*-

from enzi.backend.backend import *
from enzi.backend.ies import IES
from enzi.backend.questa import Questa

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

class KnownBackends(object):
    """
    Factory class for backends.
    Currently, the available backends are: ies.
    TODO: more backends may be added, if we get acess to use them.
    """

    def __init__(self):
        known_backends = Backend.__subclasses__()
        def fn(x):
            return (x.__name__.lower(), x)
        self.known_backends = dict(map(fn, known_backends))
        self.known_backends['vsim'] = self.known_backends['questa']

    def get(self, backend_name, config, work_root):
        if not backend_name:
            raise RuntimeError('No backend name specified.')
        backend_name = backend_name.lower()
        if backend_name in self.known_backends:
            return self.known_backends[backend_name](config, work_root)
        else:
            # the given backend name is not in support list.
            raise NameError('backend name {} not found'.format(backend_name))
