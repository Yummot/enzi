import copy
from test_validator_v02 import expected, expected_kvs
from test_validator_v02 import PARAMS
from enzi.validator import StringListValidator, BoolValidator
from enzi.validator import IntValidator, FloatValidator
from enzi.validator.v03 import AnyBaseValidator, ParamsDictValidator
from enzi.validator.v03 import ToolValidator, ToolsValidator
from enzi.validator.v03 import IESValidator, IXSValidator
from enzi.validator.v03 import QuestaValidator, VsimValidator
from enzi.validator.v03 import VivadoValidator
from enzi.validator.v03 import EnziConfigValidator as V03ECValidator

from enzi.validator import EnziConfigValidator

VIVADO_TOOL = {
    'bitstream_name': 'abc',
    'device_part': 'zynq7000',
    'vlog_params': {
        'PARAMI': 1,
        'PARAMB': True,
        'PARAMS': 'S',
        'PARAMF': 1.0,
    },
    'generics': {
        'GENERICI': 1,
        'GENERICB': True,
        'GENERICS': 'S',
        'GENERICF': 1.0,
    },
    'vlog_defines': {
        'DEFINEI': 1,
        'DEFINEB': True,
        'DEFINES': 'S',
        'DEFINEF': 1.0,
    },
    'synth_only': False,
    'build_project_only': True,
}

def test_any_base_validator():
    validator = AnyBaseValidator(key='any', val=1)
    assert validator.validate()
    validator.val = True
    assert validator.validate()
    validator.val = '1'
    assert validator.validate()
    validator.val = 0.1
    assert validator.validate()
    validator.val = []
    expected(validator)

def test_params_dict_validator():
    val = {
        'a': 1,
        'b': True,
        'c': 'a',
        'd': 1.0,
        'e': []
    }

    validator = ParamsDictValidator(key='pd', val=copy.deepcopy(val))
    expected(validator)

    val.pop('e', None)
    validator.val.pop('e', None)
    assert validator.validate() == val

def test_tool_validator():
    val = {
        "link_libs": [],
        "gen_waves": True,
        'I': 1,
        'F': 1.1
    }

    extras = {
        'link_libs': StringListValidator,
        'gen_waves': BoolValidator,
        'I': IntValidator,
        'F': FloatValidator
    }

    validator = ToolValidator(
        key='d',
        val=copy.deepcopy(val),
        extras=extras
    )

    assert validator.validate() == val

def test_ies_validator():
    validator = IESValidator(key='ies', val=copy.deepcopy(PARAMS))
    assert validator.validate() == PARAMS

def test_ixs_validator():
    validator = IXSValidator(key='ixs', val=copy.deepcopy(PARAMS))
    assert validator.validate() == PARAMS


def test_questa_validator():
    validator = QuestaValidator(key='questa', val=copy.deepcopy(PARAMS))
    assert validator.validate() == PARAMS


def test_vsim_validator():
    val = copy.deepcopy(PARAMS)
    validator = VsimValidator(key='vsim', val=copy.deepcopy(val))
    assert validator.validate() == val

    validator.val['unknown'] = 'unknown'
    einfo = expected(validator)
    assert "unknown" in einfo.value.msg

def test_vivado_validator():
    val = copy.deepcopy(VIVADO_TOOL)
    validator = VivadoValidator(key='vivado', val=copy.deepcopy(val))
    assert validator.validate() == val

def test_tools_validator():
    val = [
        ('ies', copy.deepcopy(PARAMS)),
        ('ixs', copy.deepcopy(PARAMS))
    ]

    validator = ToolsValidator(key='tools', val=copy.deepcopy(val))
    # print(validator.__optional__)
    expected_kvs(validator)

    val = dict(val)
    validator.val = dict(validator.val)
    assert validator.validate() == val

    ies = validator.val['ies']
    validator.val.pop('ies', None)
    validator.val['IES'] = ies
    assert validator.validate() == val

def test_v03_ec_validator():
    import io, os, pprint
    from enzi.utils import toml_loads
    try:
        if os.path.exists('tests/TestEnziV03.toml'):
            f = io.FileIO('tests/TestEnziV03.toml', 'r')
        elif os.path.exists('TestEnziV03.toml'):
            f = io.FileIO('TestEnziV03.toml', 'r')
        else:
            return
        reader = io.BufferedReader(f)
        data = reader.read()
        reader.close()
    except Exception:
        return

    data = data.decode('utf-8')
    conf = toml_loads(data)
    validator = V03ECValidator(copy.deepcopy(conf), '.')

    assert validator.validate()
    assert validator.val == conf
    assert validator.info() != None

def test_get_v03_validator():
    validator = EnziConfigValidator({'enzi_version': '0.3'})
    assert isinstance(validator.validator, V03ECValidator)
