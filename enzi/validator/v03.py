import io
import logging
import os
import platform
import toml
import typing

from enzi.validator.v02 import FilesetValidator, FilesetValidator
from enzi.validator.base import ValidatorError, Validator
from enzi.validator.base import IntValidator, FloatValidator
from enzi.validator.base import BoolValidator, StringValidator
from enzi.validator.base import StringListValidator, TypedMapValidator
from enzi.validator.base import PackageValidator
from enzi.validator.base import DepsValidator, tools_section_line
from enzi.validator.base import ALLOW_BACKENDS, ENZI_CONFIG_VERSIONS

logger = logging.getLogger('validator')

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
        super(ParamsDictValidator, self).__init__(key=key, val=val, parent=parent)
    
    def validate(self):
        if not self.val:
            return self.val
        self.expect_kvs()
        for k, v in self.val.items():
            if type(k) != str:
                msg = 'key {} is not str'.format(k)
                raise ValidatorError(self.chain_keys_str(), msg)
            self.val[k] = AnyBaseValidator(key=k, val=v, parent=self).validate()

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
    """Validator for a tool section"""

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

        super(QuestValidator, self).__init__(
            key=key,
            val=val,
            parent=parent,
            extras=QuestValidator.__extras__
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
