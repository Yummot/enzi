from enzi.validator.base import *
from enzi.validator import base
from enzi.validator import v02

__all__ = base.__all__ + ['EnziConfigValidator', 'EnziConfigV02Validator']

EnziConfigV02Validator = v02.EnziConfigValidator

VEC_DICT = {
    '0.1': EnziConfigV02Validator,
    '0.2': EnziConfigV02Validator,
}

class EnziConfigValidator(Validator):
    """Enzi config V* validator dispatcher"""
    def __init__(self, val, config_path=None, *, git_url=None):
        enzi_version = val.get('enzi_version', CONFIG_CURRENT_VERSION)
        ECValidator = VEC_DICT[enzi_version]
        self.validator = ECValidator(val, config_path, git_url=git_url)
    
    def validate(self):
        return self.validator.validate()
    
    @staticmethod
    def base_file(package_name, author=None):
        """Return a latest version of the Enzi.toml base file"""
        return EnziConfigV02Validator.base_file(package_name, author)

    @staticmethod
    def info():
        return EnziConfigV02Validator.info()
