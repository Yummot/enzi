# -*- coding: utf-8 -*-

import io
import logging
import os
import subprocess

from functools import partial

from enzi.backend import Backend

__all__ = ('Vivado', )

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class Vivado(Backend):
    """Vivado backend"""
    # TODO: add Windows support
    supported_system = ('Linux', )
