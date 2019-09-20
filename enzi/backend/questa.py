from enzi.backend import Backend
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)

class Questa(Backend):
    def __init__(self, config=None, work_root=None):
        self._gui_mode = False
        super(Questa, self).__init__(config=config, work_root=work_root)

    @property
    def gui_mode(self):
        return self._gui_mode

    @gui_mode.setter
    def gui_mode(self, value):
        if not isinstance(value, bool):
            raise ValueError('score must be an integer!')
        self._gui_mode = value

    def gen_scripts(self):
        pass

    def configure_main(self):
        pass
    
    def build_main(self):
        pass

    def run_main(self):
        pass
    
    def sim_main(self):
        pass
    
    def clean(self):
        pass
    