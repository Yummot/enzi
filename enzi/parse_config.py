import toml
import logging

logger = logging.getLogger(__name__)


class Config(object):
    def __init__(self, config_file):
        conf = conf = toml.load(config_file)

        if not conf:
            logger.error('Config toml file is empty.')
            raise RuntimeError('Config toml file is empty.')

        self.package = {}

        if 'package' in conf:
            if not 'name' in conf['package']:
                raise RuntimeError('package with no name is not allowed.')
            self.package = conf['package']
        else:
            raise RuntimeError(
                'package info must specify in Config toml file.')

        self.filesets = {}
        if not 'filesets' in conf:
            raise RuntimeError('At least one fileset must be specified.')
        for k, v in conf['filesets'].items():
            fileset = {}
            if 'files' in v:
                fileset['files'] = v['files']
            if 'dependencies' in v:
                fileset['dependencies'] = v['dependencies']
            self.filesets[k] = fileset

        self.targets = {}
        for target, values in conf.get('targets', {}).items():
            if not 'default_tool' in values:
                raise RuntimeError(
                    'default_tool must be set for targets.{}'.format(target))
            if not 'toplevel' in values:
                raise RuntimeError(
                    'toplevel must be set for targets.{}'.format(target))
            if not 'filesets' in values:
                raise RuntimeError(
                    'filesets must be set for targets.{}'.format(target))
            self.targets[target] = {
                'default_tool': values['default_tool'],
                'toplevel': values['toplevel'],
                'filesets': values['filesets'],
            }

        self.tools = {}
        for idx, tool in enumerate(conf.get('tools', {})):
            if not 'name' in tool:
                raise RuntimeError(
                    'tool must be set for tools<{}>'.format(idx))
            self.tools[tool['name']] = {}
            self.tools[tool['name']]['params'] = tool.get('params', {})

        self.is_local = (not 'provider' in conf)
