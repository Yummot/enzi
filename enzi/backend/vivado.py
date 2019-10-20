# -*- coding: utf-8 -*-

import io
import logging
import re
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

    @staticmethod
    def get_version():
        try:
            output = subprocess.check_output(['vivado', '-version'],  # pylint: disable=E1123
                                         stdin=subprocess.PIPE)
            return output.decode('utf-8').splitlines()[0]
        except Exception as e:
            logger.error(e)
            raise SystemExit(1)

    def __init__(self, config={}, work_root=None):
        self.version = Vivado.get_version()
        
        super(Vivado, self).__init__(config=config, work_root=work_root)
        
        self.bitstream_name = config.get('bitstream_name', self.name)
        
        self.device_part = config.get('device_part')
        if not self.device_part:
            logger.error('No device_part is provided.')
            raise SystemExit(1)
        
        self.vlog_params = config.get('vlog_params', {})
        self.generics = config.get('generics', {})
        self.vlog_defines = config.get('vlog_defines', {})
        self.src_files = config.get('src_files', [])
        self.inc_dirs = config.get('inc_dirs', [])
        
        has_xci = any(filter(lambda x: 'xci' in x, self.src_files))
        self.has_xci = has_xci
        
