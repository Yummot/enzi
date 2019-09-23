import toml
import logging

logger = logging.getLogger(__name__)


class Dependency(object):
    def __init__(self, name, info):
        if 'path' in info and 'url' in info:
            raise RuntimeError(
                'Dependency {} cannot have path and url in the same time'.format(name))
        
        if 'path' in info and not 'url' in info:
            self.is_remote = False
            self.path = str(info['path'])
        elif not 'path' in info and 'url' in info:
            self.is_remote = True
            self.url = str(info['url'])

        if 'version' in info and 'commit' in info:
            logger.warning(
                'Dependency {} configuration has commit and version at the same time, only use version key'.format(name))
        if 'version' in info and not 'commit' in info:
            self.use_version = True
            self.version = str(info['version'])
        elif not 'version' in info and 'commit' in info:
            self.use_version = False
            self.commit = str(info['commit'])
        else:
            raise RuntimeError('Dependency {} has not version or commit key.'.format(name))
        
        self.name = name
        # print(self.name, self.is_remote, self.version or self.commit, self.path or self.url)
    def git_repo_config(self):
        config = {}
        if self.is_remote:
            config['url'] = self.url
        else:
            config['path'] = self.path
        config['use_version'] = self.use_version
        if self.use_version:
            config['version'] = self.version
        else:
            config['commit'] = self.commit
        config['name'] = self.name
        
        return config

class Config(object):
    def __init__(self, config_file, extract_dep_only=False):
        conf = conf = toml.load(config_file)

        if not conf:
            logger.error('Config toml file is empty.')
            raise RuntimeError('Config toml file is empty.')

        self.package = {}
        self.dependencies = {}
        self.filesets = {}
        self.targets = {}
        self.tools = {}
        self.is_local = (not 'provider' in conf)

        if 'package' in conf:
            if not 'name' in conf['package']:
                raise RuntimeError('package with no name is not allowed.')
            self.package = conf['package']
        else:
            raise RuntimeError(
                'package info must specify in Config toml file.')

        if not 'filesets' in conf:
            raise RuntimeError('At least one fileset must be specified.')
        for k, v in conf['filesets'].items():
            fileset = {}
            if 'files' in v:
                fileset['files'] = v['files']
            # if 'dependencies' in v:
            #     fileset['dependencies'] = v['dependencies']
            self.filesets[k] = fileset

        if 'dependencies' in conf:
            for dep, dep_conf in conf['dependencies'].items():
                self.dependencies[dep] = Dependency(dep, dep_conf)

        if not extract_dep_only:
            # targets configs
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
            # tools configs
            for idx, tool in enumerate(conf.get('tools', {})):
                if not 'name' in tool:
                    raise RuntimeError(
                        'tool must be set for tools<{}>'.format(idx))
                self.tools[tool['name']] = {}
                self.tools[tool['name']]['params'] = tool.get('params', {})
