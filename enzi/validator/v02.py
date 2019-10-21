import io
import logging
import os
import platform
import toml
import typing

from enzi.validator.base import ValidatorError, Validator
from enzi.validator.base import BoolValidator, StringValidator
from enzi.validator.base import StringListValidator, TypedMapValidator
from enzi.validator.base import PackageValidator
from enzi.validator.base import DepsValidator, tools_section_line
from enzi.validator.base import ALLOW_BACKENDS, ENZI_CONFIG_VERSIONS

logger = logging.getLogger('validator')

__all__ = [
    'FilesetValidator', 'FilesetsValidator',
    'ToolParamsValidator', 'IESParamsValidator', 'IXSParamsValidator',
    'QuestaParamsValidator', 'VsimParamsValidator',
    'ToolValidator', 'ToolsValidator',
    'TargetValidator', 'TargetsValidator',
    'EnziConfigValidator'
]


class FilesetValidator(TypedMapValidator):
    """Validator for a single fileset section"""

    __slots__ = ('val', )
    __must__ = {
        "files": StringListValidator
    }

    __optional__ = {
        "include_files": StringListValidator,
        "include_dirs": StringListValidator
    }

    def __init__(self, *, key, val, parent=None):
        # this specified each dependency Validator

        super(FilesetValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            must=FilesetValidator.__must__,
            optional=FilesetValidator.__optional__
        )
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        super().validate()

        if 'files' in self.val:
            self.check_files(self.val['files'])

        return self.val

    def check_files(self, files):
        # no empty file name strings is allowed
        for f in files:
            if not f:
                msg = 'contains an empty string'
                raise ValidatorError(self.chain_keys_str(), msg)
        # all files' paths must be relative
        for f in files:
            if os.path.isabs(f):
                msg = 'file: "{}" must be a relative path'.format(f)
                raise ValidatorError(self.chain_keys_str(), msg)
            # files must be inside the package
            if f.find('..') != -1:
                msg = 'file: "{}" is oustside this package'.format(f)
                raise ValidatorError(self.chain_keys_str(), msg)

    @staticmethod
    def info():
        return {
            'files': StringListValidator.info(),
        }


class FilesetsValidator(Validator):
    """Validator for the whole filsets section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        # this specified each dependency Validator
        super(FilesetsValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        msg = 'At least one fileset must be specified.'
        self.expect_kvs(emsg=msg)

        for k, v in self.val.items():
            validator = FilesetValidator(key=k, val=v, parent=self)
            self.val[k] = validator.validate()

        return self.val

    @staticmethod
    def info():
        return {
            'f0': FilesetValidator.info(),
            'f1': FilesetValidator.info(),
        }


class ToolParamsValidator(TypedMapValidator):
    """Validator for A tool's params section"""

    __slots__ = ('val', 'params')
    __allow__ = {}

    def __init__(self, *, key, val, parent=None, extras=None):
        (check, extras) = TypedMapValidator.check_validator_dict(extras)
        if check:
            logger.debug('ToolParamsValidator: filtered extras')
            self.params = {**ToolParamsValidator.__allow__, **extras}
        else:
            msg = 'ToolParamsValidator: Ingore non-dict type extras'
            logger.warning(msg)

        super(ToolParamsValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            must=self.__allow__,
            optional=extras
        )
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        if self.val is None:
            return self.val
        super().validate()
        return self.val

    @staticmethod
    def info():
        """
        ToolParamsValidator is just a base class, so not details info
        """
        return {}


class IESParamsValidator(ToolParamsValidator):
    """Validator for A IES tool's params section"""

    __slots__ = ('val', )
    __extras__ = {
        'link_libs': StringListValidator,
        'gen_waves': BoolValidator,
        'vlog_opts': StringListValidator,
        'vhdl_opts': StringListValidator,
        'vlog_defines': StringListValidator,
        'vhdl_generics': StringListValidator,
        'elab_opts': StringListValidator,
        'sim_opts': StringListValidator,
        'compile_log': StringValidator,
        'elaborate_log': StringValidator,
        'simulate_log': StringValidator,
        'use_uvm': BoolValidator,
    }

    def __init__(self, *, key, val, parent=None):

        super(IESParamsValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            extras=IESParamsValidator.__extras__
        )
        self.val: typing.Mapping[str, typing.Any]

    @staticmethod
    def info():
        base = ToolParamsValidator.info()
        extras = {
            'link_libs': StringListValidator.info(),
            'gen_waves': BoolValidator.info(),
            'vlog_opts': StringListValidator.info(),
            'vhdl_opts': StringListValidator.info(),
            'vlog_defines': StringListValidator.info(),
            'vhdl_generics': StringListValidator.info(),
            'elab_opts': StringListValidator.info(),
            'sim_opts': StringListValidator.info(),
            'compile_log': StringValidator.info(),
            'elaborate_log': StringValidator.info(),
            'simulate_log': StringValidator.info(),
            'use_uvm': BoolValidator.info(),
        }
        return {**base, **extras}


class IXSParamsValidator(IESParamsValidator):
    """
    Validator for A IXS tool's params section.
    Warning: IXS backend is not available now.
    """

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(IXSParamsValidator, self).__init__(
            key=key,
            val=val,
            parent=parent
        )
        msg = 'Currently, the IXS tool section is just a placeholder'
        logging.getLogger('IXSParamsValidator').warning(msg)
        # logger.warning(msg)


class QuestaParamsValidator(ToolParamsValidator):
    """Validator for A Questa tool's params section"""

    __slots__ = ('val', )
    __extras__ = {
        'link_libs': StringListValidator,
        'gen_waves': BoolValidator,
        'vlog_opts': StringListValidator,
        'vhdl_opts': StringListValidator,
        'vlog_defines': StringListValidator,
        'vhdl_generics': StringListValidator,
        'elab_opts': StringListValidator,
        'sim_opts': StringListValidator,
        'compile_log': StringValidator,
        'elaborate_log': StringValidator,
        'simulate_log': StringValidator
    }

    def __init__(self, *, key, val, parent=None):

        super(QuestaParamsValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            extras=QuestaParamsValidator.__extras__
        )
        self.val: typing.Mapping[str, typing.Any]

    @staticmethod
    def info():
        base = ToolParamsValidator.info()
        extras = {
            'link_libs': StringListValidator.info(),
            'gen_waves': BoolValidator.info(),
            'vlog_opts': StringListValidator.info(),
            'vhdl_opts': StringListValidator.info(),
            'vlog_defines': StringListValidator.info(),
            'vhdl_generics': StringListValidator.info(),
            'elab_opts': StringListValidator.info(),
            'sim_opts': StringListValidator.info(),
            'compile_log': StringValidator.info(),
            'elaborate_log': StringValidator.info(),
            'simulate_log': StringValidator.info()
        }
        return {**base, **extras}


class VsimParamsValidator(QuestaParamsValidator):
    """Validator for A Vsim(Modelsim/Questasim) tool's params section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(VsimParamsValidator, self).__init__(
            key=key,
            val=val,
            parent=parent
        )


# tools' parms validator name-validator mapping
TPARAMS_VALIDATOR_MAP = {
    'ies': IESParamsValidator,
    'ixs': IXSParamsValidator,
    'questa': QuestaParamsValidator,
    'vsim': VsimParamsValidator,
}


class ToolValidator(TypedMapValidator):
    """validator for a single tool section"""

    __must__ = {'name': StringValidator}
    __optional__ = {'params': ToolParamsValidator}

    def __init__(self, *, key, val, parent=None):
        super().__init__(
            key=key,
            val=val,
            parent=parent,
            must=ToolValidator.__must__,
            optional=ToolValidator.__optional__
        )

    def check_tool(self, tool_name=None):
        """check if the tool is available and set the corresponding ToolParamsValidator"""
        if tool_name is None:
            tool_name = self.val['name'].lower()

        if not (tool_name in ALLOW_BACKENDS or tool_name == 'ixs'):
            msg = 'unknown backend: `{}`'.format(tool_name)
            raise ValidatorError(self.chain_keys_str(), msg)

        params_validator = TPARAMS_VALIDATOR_MAP[tool_name]
        self.optional['params'] = params_validator

    def norm_name(self):
        self.val['name'] = self.val['name'].lower()

    def validate(self):
        self.check_must_only()
        self.norm_name()
        self.check_tool()
        self.check_optional(False)

        return self.val

    @staticmethod
    def info(*, tool_name=None):
        tool_name = tool_name.lower() if type(tool_name) == str else tool_name
        if tool_name is None or not tool_name in TPARAMS_VALIDATOR_MAP:
            return {
                'name': 'questa',
                'params': QuestaParamsValidator.info()
            }

        return {
            'name': tool_name,
            'params': TPARAMS_VALIDATOR_MAP[tool_name].info()
        }


class ToolsValidator(Validator):
    """Validator for the whole tools section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        # this specified each dependency Validator
        super(ToolsValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        if self.val is None:
            return self.val

        if type(self.val) != list:
            msg = 'must be an array of tool'
            raise ValidatorError(self.chain_keys_str(), msg)

        for idx, tool in enumerate(self.val):
            validator = ToolValidator(key=str(idx), val=tool, parent=self)
            self.val[idx] = validator.validate()

        return self.val

    @staticmethod
    def info():
        tool0 = ToolValidator.info()
        tool1 = ToolValidator.info()
        tool1['name'] += ' '
        return [tool0, tool1]


class TargetValidator(TypedMapValidator):
    """validator for a single target section"""

    __slots__ = ('val', )
    __allow__ = {
        'default_tool': StringValidator,
        'toplevel': StringValidator,
        'filesets': StringListValidator
    }

    def __init__(self, *, key, val, parent=None):
        super(TargetValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            must=TargetValidator.__allow__
        )
        self.val: typing.Mapping[str, typing.Any]

    @staticmethod
    def info():
        return {
            'default_tool': StringValidator.info(),
            'toplevel': StringValidator.info(),
            'filesets': StringListValidator.info()
        }


class TargetsValidator(Validator):
    """Validator for the whole tools section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        # this specified each dependency Validator
        super(TargetsValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        if self.val is None:
            return self.val

        self.expect_kvs()

        for k, v in self.val.items():
            validator = TargetValidator(key=k, val=v, parent=self)
            self.val[k] = validator.validate()

        return self.val

    @staticmethod
    def info():
        return {
            'sim': TargetValidator.info(),
            'run': TargetValidator.info(),
        }


class EnziConfigValidator(TypedMapValidator):
    """
    Validator for "Enzi.toml"
    """

    __slots__ = ('config_path', 'val')
    __must__ = {
        'enzi_version': StringValidator,
        'package': PackageValidator,
        'filesets': FilesetsValidator,
    }
    __optional__ = {
        'dependencies': DepsValidator,
        'targets': TargetsValidator,
        'tools': ToolsValidator
    }
    BASE_ESTRING = 'Enzi exits on error: '

    BASE_FILE_TARGET_COMMENT = '''
# Optional targets section, use when you want Enzi to execute some targets.
# Here is the key-values hint.
# IMPORTANT: If you use tool ies and uvm, make sure you set ies tool params.use_uvm to true.
# To see the detail tool params hint, use `enzi --enzi-config-help`
# IMPORTANT: Filesets field in targets.* is order matter, due some limitations in backend.
'''

    HEADER_COMMENT = '''
# Cheatsheet for an Enzi Configuration File, also known as `Enzi.toml`.
'''

    ENZI_VERSION_COMMENT = '''
# Enzi configuration file version
# Mandatory enzi configuration file version section, must be specified.
'''
    PACKAGE_COMMENT = '''
# This enzi project/package information:
# Mandatory package section, must be specified.
# All the keys listed bellow need to be specified.
# No additional keys are allowed.
'''
    FILESETS_COMMENT = '''
# Filesets for this enzi project/package
# At least one fileset must be provided.
'''

    TARGETS_COMMENT = '''
# Targets for this enzi project/package
# Optional Dependencies Section, use when you want to run a target.
# One or more targets can be specified, see Enzi supported targets for more details.
'''

    DEPS_COMMENT = '''
# Dependencies for this enzi project/package:
# Optional Dependencies Section, use when this Enzi package has dependencies.
# A dependency must have a `path` or `url` key, but not have them the same time.
# A dependency must have a `commit` or `path` key, but not have them the same time.
# (WARNING) if using the path key in a dependency section, it must be a absolute path.
'''

    TOOLS_COMMENT = '''
# Tools configuration for this enzi project/package:
# Optional Dependencies Section, use when you want to provide extra parameters for a tool.
# All parameters in a single tool param section are optional. You don\'t have to provide all parameters.
# This section is just a reminder of all the available tools and their available optional parameters.
# Also, You don\'t have to include tools section, if you don\'t need to specify the parameters of any tools.
# IMPORTANT: If you use tool ies and uvm, make sure you set ies tool params' use_uvm parameter to true. 
'''

    def __init__(self, val, config_path=None, *, git_url=None):

        # construct a readable EnziConfigValidator.key
        if git_url and config_path:
            cur_system = platform.system()
            is_windows = (cur_system == 'Windows')
            basename = os.path.basename(config_path)
            if not is_windows:
                raw_key = os.path.join(git_url, basename)
            else:
                raw_key = os.path.join(git_url, basename)
                first_slash = git_url.find('/')
                first_backslash = git_url.find('\\')
                if first_slash != -1 and first_backslash != -1:
                    raw_key = raw_key.replace('/', '\\')
        else:
            raw_key = config_path
        key = '<%s>' % raw_key

        super(EnziConfigValidator, self).__init__(
            key=key,
            val=val,
            must=EnziConfigValidator.__must__,
            optional=EnziConfigValidator.__optional__
        )
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        super(EnziConfigValidator, self).validate()

        # check `enzi_version`
        enzi_version = self.val['enzi_version']
        if not enzi_version in ENZI_CONFIG_VERSIONS:
            _v = StringValidator(key='enzi_version',
                                 val=enzi_version, parent=self)
            msg = 'unknown enzi_version: {}'.format(enzi_version)
            raise ValidatorError(_v.chain_keys_str(), msg)

        # check self dependency
        if 'dependencies' in self.val:
            package_name = self.val['package']['name']
            if package_name in self.val['dependencies']:
                fmt = 'Possible self dependency for package: {} at {}'
                msg = fmt.format(package_name, self.key)
                logger.error(msg)
                raise SystemExit(EnziConfigValidator.BASE_ESTRING + msg)
        return self.val

    def expect_kvs(self, *, emsg=None):
        if self.val is None:
            msg = 'Empty Enzi configuration file' if emsg is None else emsg
            raise ValidatorError(self.chain_keys_str(), msg)
        elif type(self.val) != dict:
            msg = 'must be a key-value table' if emsg is None else emsg
            raise ValidatorError(self.chain_keys_str(), msg)

    @staticmethod
    def base_dict(package_name, authors=None):
        """generate a minimal Enzi.toml's dict with given information"""
        d = {}
        d['enzi_version'] = '0.2'

        package = {'name': str(package_name), 'version': '0.1.0'}
        if authors is None:
            authors = []
        elif type(authors) == str:
            authors = [authors]
        elif type(authors) == list:
            authors = StringListValidator(
                key='authors', val=authors).validate()
        else:
            raise ValueError('authors must be a string or a string list')
        package['authors'] = authors
        d['package'] = package

        d['filesets'] = {'src': {'files': []}}

        return d

    @staticmethod
    def base_file(package_name, authors=None):
        """generate a minimal Enzi.toml's content StringIO with given information"""
        import toml
        d = EnziConfigValidator.base_dict(package_name, authors)
        sio = io.StringIO()
        sio.write(toml.dumps(d))

        sio.write(EnziConfigValidator.BASE_FILE_TARGET_COMMENT)
        targets = TargetsValidator.info()
        dtargets = {'targets': targets}
        targets_lines = toml.dumps(dtargets).splitlines()
        mlines = map(lambda x: '# {}\n'.format(x), targets_lines)
        sio.writelines(mlines)
        return sio

    @staticmethod
    def info():
        out = io.StringIO()

        out.write(EnziConfigValidator.HEADER_COMMENT)

        out.write(EnziConfigValidator.ENZI_VERSION_COMMENT)
        ev = {'enzi_version': '|'.join(ENZI_CONFIG_VERSIONS)}
        toml.dump(ev, out)

        out.write(EnziConfigValidator.PACKAGE_COMMENT)
        pack = {'package': PackageValidator.info()}
        toml.dump(pack, out)

        out.write(EnziConfigValidator.DEPS_COMMENT)
        deps = {'dependencies': DepsValidator.info()}
        toml.dump(deps, out)

        out.write(EnziConfigValidator.FILESETS_COMMENT)
        filesets = {'filesets': FilesetsValidator.info()}
        toml.dump(filesets, out)

        out.write(EnziConfigValidator.TARGETS_COMMENT)
        targets = {'targets': TargetsValidator.info()}
        toml.dump(targets, out)

        out.write(EnziConfigValidator.TOOLS_COMMENT)

        def fn(tool_name):
            tool = {'tools': [ToolValidator.info(tool_name=tool_name)]}
            lines = toml.dumps(tool).splitlines()

            toolinfo = list(map(tools_section_line, lines))
            out.writelines(toolinfo)
            out.write('\n')

        m = map(fn, TPARAMS_VALIDATOR_MAP.keys())
        _ = list(m)

        return out
