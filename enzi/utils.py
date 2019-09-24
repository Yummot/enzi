import subprocess
import logging
import sys
import importlib

logger = logging.getLogger(__name__)

# launcher from fusesoc https://github.com/olofk/fusesoc/tree/master/fusesoc


class Launcher:
    def __init__(self, cmd, args=[], cwd=None):
        self.cmd = cmd
        self.args = args
        self.cwd = cwd

    def run(self):
    # def run(self, get_output=False):
        logger.debug(self.cwd)
        logger.debug('    ' + str(self))
        # _run = subprocess.check_call if get_output else subprocess.check_output
        _run = subprocess.check_output
        try:
            output = _run([self.cmd] + self.args,
                         cwd=self.cwd,
                         stdin=subprocess.PIPE)
            return output.decode("utf-8")
        except FileNotFoundError:
            raise RuntimeError("Command '" + self.cmd +
                               "' not found. Make sure it is in $PATH")
        except subprocess.CalledProcessError:
            self.errormsg = '"{}" exited with an error code. See stderr for details.'
            raise RuntimeError(self.errormsg.format(str(self)))

    def __str__(self):
        return ' '.join([self.cmd] + self.args)
    