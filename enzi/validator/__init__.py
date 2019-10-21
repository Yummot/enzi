from enzi.validator.base import *
from enzi.validator import base
from enzi.validator import v02

__all__ = base.__all__ + ['EnziConfigValidator', 'EnziConfigV02Validator']

EnziConfigV02Validator = v02.EnziConfigValidator
EnziConfigValidator = v02.EnziConfigValidator
