# -*- coding: utf-8 -*-

import io
import logging
import os
import platform
import toml
import typing

from enzi.validator.v02 import FilesetValidator, FilesetsValidator
from enzi.validator.v02 import TargetValidator, TargetsValidator
from enzi.validator.base import ValidatorError, Validator
from enzi.validator.base import IntValidator, FloatValidator
from enzi.validator.base import BoolValidator, StringValidator
from enzi.validator.base import StringListValidator, TypedMapValidator
from enzi.validator.base import PackageValidator
from enzi.validator.base import DepsValidator, tools_section_line
from enzi.validator.base import ALLOW_BACKENDS, ENZI_CONFIG_VERSIONS

logger = logging.getLogger('validator')

__all__ = [
    'AnyBaseValidator', 'ParamsDictValidator',
    'ToolValidator', 'IESValidator', 'IXSValidator',
    'QuestaValidator', 'VivadoValidator', 'VsimValidator',
    'ToolsValidator', 'EnziConfigValidator',
]

class AnyBaseValidator(Validator):
    """Internal use Validator, the validator allow base type as str/bool/int/float"""

    def __init__(self, *, key, val, parent=None, emsg=None):
        super(AnyBaseValidator, self).__init__(
            key=key, val=val, parent=parent)
        self.T = {str, bool, int, float, }
        default_emsg = 'type must be str/bool/int/float'
        self.emsg = emsg if emsg else default_emsg

    def validate(self):
        if not type(self.val) in self.T:
            raise ValidatorError(self.chain_keys_str(), self.emsg)
        return self.val

    @staticmethod
    def info():
        return '<str|bool|int|float>'


class ParamsDictValidator(Validator):
    """Params Dict Base Validator"""

    def __init__(self, *, key, val, parent=None):
        super(ParamsDictValidator, self).__init__(
            key=key, val=val, parent=parent)

    def validate(self):
        if not self.val:
            return self.val
        self.expect_kvs()
        for k, v in self.val.items():
            if type(k) != str:
                msg = 'key {} is not str'.format(k)
                raise ValidatorError(self.chain_keys_str(), msg)
            self.val[k] = AnyBaseValidator(
                key=k, val=v, parent=self).validate()

        return self.val

    @staticmethod
    def info():
        return {
            'strParam': StringValidator.info(),
            'boolParam': BoolValidator.info(),
            'intParam': IntValidator.info(),
            'floatParam': FloatValidator.info(),
        }


class ToolValidator(TypedMapValidator):
    """Base Validator for a tool section"""

    __allow__ = {}

    def __init__(self, *, key, val, parent=None, extras=None):
        (check, extras) = TypedMapValidator.check_validator_dict(extras)
        if check:
            logger.debug('ToolValidator: filtered extras')
            self.params = {**ToolValidator.__allow__, **extras}
        else:
            msg = 'ToolValidator: Ingore non-dict type extras'
            logger.warning(msg)
            extras = None

        super(ToolValidator, self).__init__(
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
        ToolValidator is just a base class, so not details info
        """
        return {}


class IESValidator(ToolValidator):
    """Validator for a IES tool section"""
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

        super(IESValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            extras=IESValidator.__extras__
        )
        self.val: typing.Mapping[str, typing.Any]

    @staticmethod
    def info():
        base = ToolValidator.info()
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


class IXSValidator(IESValidator):
    """
    Validator for A IXS tool's section.
    Warning: IXS backend is not available now.
    """

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(IXSValidator, self).__init__(
            key=key,
            val=val,
            parent=parent
        )
        msg = 'Currently, the IXS tool section is just a placeholder'
        logging.getLogger('IXSValidator').warning(msg)
        # logger.warning(msg)


class QuestaValidator(ToolValidator):
    """Validator for A Questa tool's section"""

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

        super(QuestaValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            extras=QuestaValidator.__extras__
        )
        self.val: typing.Mapping[str, typing.Any]

    @staticmethod
    def info():
        base = ToolValidator.info()
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


class VsimValidator(QuestaValidator):
    """Validator for A Vsim(Modelsim/Questasim) tool's section"""

    __slots__ = ('val', )

    def __init__(self, *, key, val, parent=None):
        super(VsimValidator, self).__init__(
            key=key,
            val=val,
            parent=parent
        )


class VivadoValidator(ToolValidator):
    """Validator for A Vivado tool section"""

    __extras__ = {
        'bitstream_name': StringValidator,
        'device_part': StringValidator,
        'vlog_params': ParamsDictValidator,
        'generics': ParamsDictValidator,
        'vlog_defines': ParamsDictValidator,
        'synth_only': BoolValidator,
        'build_project_only': BoolValidator,
    }

    def __init__(self, *, key, val, parent=None):
        super(VivadoValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            extras=VivadoValidator.__extras__
        )

    @staticmethod
    def info():
        base = ToolValidator.info()
        extras = {
            'bitstream_name': StringValidator.info(),
            'device_part': StringValidator.info(),
            'vlog_params': ParamsDictValidator.info(),
            'generics': ParamsDictValidator.info(),
            'vlog_defines': ParamsDictValidator.info(),
            'synth_only': BoolValidator.info(),
            'build_project_only': BoolValidator.info(),
        }
        return {**base, **extras}

class ToolsValidator(TypedMapValidator):
    """Validator for the whole tools section"""

    __optional__ = {
        'ies': IESValidator,
        'ixs': IXSValidator,
        'questa': QuestaValidator,
        'vivado': VivadoValidator,
        'vsim': VsimValidator
    }

    def __init__(self, *, key, val, parent=None):
        super(ToolsValidator, self).__init__(
            key=key,
            val=val,
            must=None,
            optional=ToolsValidator.__optional__
        )
        self.raw_keys = {}

    def check_unknown_keys(self):
        if self.val is None:
            return
        
        self.expect_kvs()
        kset = set(self.val.keys())
        unknown = kset - self._aset

        if unknown:
            raw_unknown = self.raw_keys[unknown]
            msg = 'unknown backend: {}'.format(raw_unknown)
            raise ValidatorError(self.chain_keys_str(), msg)
    
    def validate(self):
        if not self.val:
            return self.val

        self.expect_kvs()

        def record_raw(pair):
            raw = pair[0]
            new = raw.lower()
            self.raw_keys[new] = raw
            return (new, pair[1])

        self.val = dict(map(record_raw, self.val.items()))
        self.check_optional()
        return self.val

    
    @staticmethod
    def info():
        return {
            'ies': IESValidator.info(),
            'ixs': IXSValidator.info(),
            'questa': QuestaValidator.info(),
            'vivado': VivadoValidator.info(),
            'vsim': VsimValidator.info()
        }

class EnziConfigValidator(TypedMapValidator):
    """
    Validator for "Enzi.toml"
    """

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
# Optional Tools Section, use when you want to provide extra parameters for a tool.
# All parameters in a single tool param section are optional. You don\'t have to provide all parameters.
# This section is just a reminder of all the available tools and their available optional parameters.
# Also, You don\'t have to include tools section, if you don\'t need to specify the parameters of any tools.
# IMPORTANT: If you use uvm with tool ies, make sure you set ies tool params' use_uvm parameter to true. 
'''

    @staticmethod
    def construct_key(git_url, config_path):
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
        return key
    
    def __init__(self, val, config_path=None, *, git_url=None):
        key = EnziConfigValidator.construct_key(git_url, config_path)
        super(EnziConfigValidator, self).__init__(
            key=key,
            val=val,
            must=EnziConfigValidator.__must__,
            optional=EnziConfigValidator.__optional__
        )
        self.val: typing.Mapping[str, typing.Any]

    def validate(self):
        super(EnziConfigValidator, self).validate()

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
        d['enzi_version'] = '0.3'

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
        tools = {'tools': ToolsValidator.info() }
        toml.dump(tools, out)

        return out
