# -*- coding: utf-8 -*-

import logging
import platform

from enzi.backend.backend import *
from enzi.backend.ies import IES
from enzi.backend.questa import Questa

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

cur_system = platform.system()

__all__ = ['KnownBackends', 'Questa', 'IES',
           'Backend', 'BackendCallback', 'value_str_filter']


class KnownBackends(object):
    """
    Factory class for backends.
    Currently, the available backends are: ies.
    TODO: more backends may be added, if we get acess to use them.
    """

    def __init__(self):
        known_backends = Backend.__subclasses__()
        def f(x): return (x.__name__.lower(), x)
        def g(x): return cur_system in x[1].supported_system
        self.known_backends = dict(filter(g, map(f, known_backends)))
        # hard code 'vsim' to 'questa'
        self.known_backends['vsim'] = self.known_backends['questa']

    def register_backend(self, backend):
        """
        register new backend
        :param backend: a subclass of Backend 
        """
        name = backend.__class__.__name__.lower()
        if not issubclass(backend.__class__, Backend):
            fmt = 'register_backend: backend(class:{}) must be a subclass of Backend'
            msg = fmt.format(backend.__class__)
            logger.error(msg)
            raise ValueError(msg)
        self.known_backends[name] = backend

    def get(self, backend_name, config, work_root):
        if not backend_name:
            raise RuntimeError('No backend name specified.')
        backend_name = backend_name.lower()
        if backend_name in self.known_backends:
            return self.known_backends[backend_name](config, work_root)
        else:
            # the given backend name is not in support list.
            raise NameError('backend name {} not found'.format(backend_name))
