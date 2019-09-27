# -*- coding: utf-8 -*-

from enzi.backend.backend import *
from enzi.backend.ies import IES
from enzi.backend.questa import Questa

class KnownBackends(object):
    """
    Factory class for backends.
    Currently, the available backends are: ies.
    TODO: more backends may be added, if we get acess to use them.
    """

    def __init__(self):
        self.known_backends = Backend.__subclasses__()

    def get(self, backend_name, config, work_root):
        if not backend_name:
            raise RuntimeError('No backend name specified.')
        for backend in self.known_backends:
            if backend_name.lower() == backend.__name__.lower():
                return backend(config, work_root)

        # given backend name is not in support list.
        raise NameError('backend name {} not found'.format(backend_name))
