"""
enzi.validator v02 and base module test
"""

import copy
import os
import io
import pytest

from enzi import validator
from enzi.validator import ValidatorError
from enzi.validator import Validator, BoolValidator
from enzi.validator import IntValidator, FloatValidator
from enzi.validator import StringValidator, StringListValidator
from enzi.validator import VersionValidator, VersionReqValidator
from enzi.validator import PackageValidator, BaseTypeValidator
from enzi.validator import DepsValidator, DependencyValidator
from enzi.validator.v02 import FilesetValidator, FilesetsValidator
from enzi.validator.v02 import ToolParamsValidator, ToolValidator
from enzi.validator.v02 import IESParamsValidator, IXSParamsValidator
from enzi.validator.v02 import QuestaParamsValidator, VsimParamsValidator
from enzi.validator.v02 import ToolsValidator, TypedMapValidator
from enzi.validator.v02 import TargetValidator, TargetsValidator
from enzi.validator.v02 import EnziConfigValidator
from enzi.config import RawConfig, PartialConfig, Config
from enzi.utils import toml_loads

PARAMS = {
    'link_libs': [],
    'gen_waves': True,
    'vlog_opts': [],
    'vhdl_opts': [],
    'vlog_defines': [],
    'vhdl_generics': [],
    'elab_opts': [],
    'sim_opts': ["-message"],
    'compile_log': 'x.log',
    'elaborate_log': 'y.log',
    'simulate_log': 'z.log'
}

TARGET = {
    'default_tool': 'ies',
    'toplevel': 'tb',
    'filesets': ['include', 'rtl', 'tb']
}


def expected(validator):
    """
    this function takes a validator and test whether the validate function raises an exception or not.
    If no exception raises, assertion failed.
    """
    with pytest.raises(ValidatorError) as excinfo:
        validator.validate()
    assert excinfo != None
    return excinfo


def expected_kvs(validator, emsg=None):
    """
    this function takes a validator and test whether the validate function raises an exception or not.
    If no exception raises, assertion failed. It is not a key-value table error, assertion failed.
    """
    excinfo = expected(validator)
    patial_emsg = 'key-value table' if emsg is None else emsg
    assert patial_emsg in excinfo.value.msg

def test_validator_chained():
    class BaseValidator(Validator):
        def validate(self):
            return self.val
        @staticmethod
        def info(this=None, *, extras=None):
            return ''
    
    v0 = BaseValidator(key='v0')
    v1 = BaseValidator(key='v1', parent=v0)
    v2 = BaseValidator(key='v2', parent=v1)
    v3 = BaseValidator(key='v3', parent=v2)

    keys = v3.chain_keys()

    assert keys == ['v0', 'v1', 'v2', 'v3']
    assert v3.chain_keys_str() == 'v0.v1.v2.v3'
    assert v3.info() == ''

def test_validator_root():
    class BaseValidator(Validator):
        def validate(self):
            return self.val
        @staticmethod
        def info(this=None, *, extras=None):
            return ''
    
    v0 = BaseValidator(key='v0')
    v1 = BaseValidator(key='v1', parent=v0)
    v2 = BaseValidator(key='v2', parent=v1)
    v3 = BaseValidator(key='v3', parent=v2)
    v4 = BaseValidator(key='v4', parent=v2)
    v5 = BaseValidator(key='v5', parent=v2)
    v6 = BaseValidator(key='v6', parent=None)
    
    assert v3.root == v0
    assert v2.root == v0
    assert v1.root == v0
    assert v0.root == v0
    assert v6.root == v6
    assert v5.root == v0
    assert v4.root == v0

def test_base_type_validator():
    class V(BaseTypeValidator):
        @staticmethod
        def info(this=None, *, extras=None):
            return ''
    val = '11111'
    validator = V(key='a', val=val, T=str)
    assert validator.validate() == val

def test_string_validator():
    val = '11111'
    validator = StringValidator(key='a', val=val)
    assert validator.validate() == val


def test_string_validator_failed():
    val = 11111
    validator = StringValidator(key='a', val=val)
    excinfo = expected(validator)
    assert excinfo.type == ValidatorError


def test_string_list_validator():
    val = ['a', 'b', 'c']
    validator = StringListValidator(key='a', val=val)

    assert validator.validate() == val

    validator.val.append(1)
    excinfo = expected(validator)
    assert excinfo.type == ValidatorError
    assert excinfo.value.msg == 'all value must be string'
    assert excinfo.value.chained == 'a'

    validator.val = 'a'
    excinfo = expected(validator)
    assert excinfo.value.msg == 'value(a) must be a string list'

def test_version_validator():
    val = '0.1.0'
    validator = VersionValidator(key='v', val=val)
    assert validator.validate() == val
    
    validator.val += '/'
    expected(validator)

def test_version_req_validator():
    val = '>0.4.3, <0.6.0'
    validator = VersionReqValidator(key='v', val=val)
    assert validator.validate() == val

    validator.val += '/'
    expected(validator)

def test_package_validator():
    val = {'name': 'a', 'version': '1', 'authors': ['a']}
    validator = PackageValidator(key='p', val=copy.deepcopy(val))

    assert validator.validate() == val

    validator.val['name'] = 11111
    excinfo = expected(validator)
    assert excinfo.value.msg == 'type must be string'

    validator.val['name'] = copy.copy(val['name'])
    validator.val['version'] = 1111
    excinfo = expected(validator)
    assert 'must be a semver version string' in excinfo.value.msg

    validator.val['version'] = copy.copy(val['version'])
    validator.val['authors'] = 1111
    with pytest.raises(ValidatorError) as excinfo:
        validator.validate()

    assert excinfo.value.msg == 'value(1111) must be a string list'

    del validator.val['authors']
    excinfo = expected(validator)
    assert excinfo.value.msg == r"missing keys: {'authors'}"

    validator.val['authors'] = copy.copy(val['authors'])
    validator.val['unknown'] = 'unknown'
    excinfo = expected(validator)
    assert excinfo.value.msg == r"unknown keys: {'unknown'}"


def test_dependency_validator():
    val = {
        'path': '/a/b/c',
        'url': 'http://localhost',
        'commit': '8aef1',
        'version': '0.1.0'
    }

    validator = DependencyValidator(key='d', val=copy.deepcopy(val))

    excinfo = expected(validator)
    assert excinfo.value.msg == 'path and url cannot be the specified at the same time'

    del validator.val['url']
    excinfo = expected(validator)
    assert excinfo.value.msg == 'commit and version cannot be the specified at the same time'

    del validator.val['commit']
    validator.val['unknown'] = 'unknown'
    excinfo = expected(validator)
    assert excinfo.value.msg == r"unknown keys: {'unknown'}"

    del validator.val['unknown']
    del val['url']
    del val['commit']
    assert validator.validate() == val

    val['version'] = '>0.4.3, <0.6.0'
    validator.val['version'] = val['version']
    assert validator.validate() == val

    validator.val = list(validator.val.items())
    expected_kvs(validator)


def test_deps_validator():
    val = {
        'd0': {
            'url': 'http://localhost',
            'commit': '8aef1',
        },
        'd1': {
            'path': '/a/b/c',
            'commit': '8aef1',
        }
    }

    validator = DepsValidator(key='d', val=copy.deepcopy(val))

    assert validator.validate() == val

    validator.val['xxx'] = {}
    excinfo = expected(validator)
    assert excinfo.value.msg == 'missing keys (path/url) and (commit/version)'

    del validator.val['xxx']
    del validator.val['d0']
    del val['d0']
    assert validator.validate() == val

    validator.val = list(validator.val.items())
    expected_kvs(validator)


def test_file_set_validator():
    val = {
        "files": [
            "./mock/src/arb_tree.sv",
            "./mock/src/req_mux2.sv",
            "./mock/src/req_rr_flag.sv",
        ],
    }

    validator = FilesetValidator(key='rtl', val=copy.deepcopy(val))

    assert validator.validate() == val

    validator.val['rtl'] = []
    einfo = expected(validator)
    assert "unknown" in einfo.value.msg

    validator.val = list(validator.val.items())
    expected_kvs(validator)

    validator.val = dict(validator.val)
    del validator.val['files']
    einfo = expected(validator)
    assert "missing" in einfo.value.msg

    val['include_files'] = ['xxx.sv']
    validator.val = copy.deepcopy(val)
    assert validator.validate() == val


def test_file_sets_validator():
    val = {
        "rtl": {
            "files": [
                "./mock/src/arb_tree.sv",
                "./mock/src/req_mux2.sv",
                "./mock/src/req_rr_flag.sv",
            ],
        },
        "include": {
            "files": [
                "./mock/include/test_clk_if.sv",
            ]
        },
        "tb": {
            "files": [
                "./mock/tb/tb.sv",
            ]
        },
    }

    validator = FilesetsValidator(key='fs', val=copy.deepcopy(val))

    assert validator.validate() == val

    validator.val['rtl'] = list(validator.val['rtl'].items())
    expected(validator)

    validator.val['rtl'] = dict(validator.val['rtl'])
    del validator.val['rtl']
    del val['rtl']
    assert validator.validate() == val

    del validator.val['include']
    del val['include']
    assert validator.validate() == val

    validator.val = list(validator.val.items())
    expected_kvs(validator, 'At least one')

    validator.val = dict(validator.val)

    test = '.' + val['tb']['files'][0]
    validator.val['tb']['files'][0] = test
    expected(validator)

    test = '/' + test[2:]
    validator.val['tb']['files'][0] = test
    expected(validator)


def test_tool_params_validator():
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

    validator = ToolParamsValidator(
        key='d',
        val=copy.deepcopy(val),
        extras=extras
    )

    assert validator.validate() == val


def test_ies_params_validator():
    validator = IESParamsValidator(key='ies', val=copy.deepcopy(PARAMS))
    assert validator.validate() == PARAMS


def test_ixs_params_validator():
    validator = IXSParamsValidator(key='ixs', val=copy.deepcopy(PARAMS))
    assert validator.validate() == PARAMS


def test_questa_params_validator():
    validator = QuestaParamsValidator(key='questa', val=copy.deepcopy(PARAMS))
    assert validator.validate() == PARAMS


def test_vsim_params_validator():
    val = copy.deepcopy(PARAMS)
    validator = VsimParamsValidator(key='vsim', val=copy.deepcopy(val))
    assert validator.validate() == val

    validator.val['unknown'] = 'unknown'
    einfo = expected(validator)
    assert "unknown" in einfo.value.msg

def test_tool_validator():
    val = {
        'name': 'ies',
        'params': copy.deepcopy(PARAMS)
    }

    validator = ToolValidator(key='tool', val=val)
    assert validator.validate() == val

    validator.val['name'] = 'unknown'
    einfo = expected(validator)
    assert "unknown backend: `unknown`" in einfo.value.msg

    validator.val['name'] = 'vsim'
    validator.val['params'] = list(validator.val.items())
    expected_kvs(validator)

def test_tools_validator():
    val = [
        {
            'name': 'ies',
            'params': copy.deepcopy(PARAMS)
        },
        {
            'name': 'ixs',
            'params': copy.deepcopy(PARAMS)
        }
    ]

    validator = ToolsValidator(key='tools', val=copy.deepcopy(val))
    assert validator.val == val

    validator.val[1]['params'] = []
    expected_kvs(validator)

def test_target_validator():
    val = copy.deepcopy(TARGET)
    validator = TargetValidator(key='sim', val=copy.deepcopy(val))
    assert validator.validate() == val

def test_targets_validator():
    val = {
        'sim': copy.deepcopy(TARGET),
        'run': copy.deepcopy(TARGET)
    }
    validator = TargetsValidator(key='sim', val=copy.deepcopy(val))
    assert validator.validate() == val

def test_enzi_config_validator():
    try:
        f = io.FileIO('ExampleEnzi.toml', 'r')
        reader = io.BufferedReader(f)
        data = reader.read()
        reader.close()
    except Exception:
        return
    data = data.decode('utf-8')
    conf = toml_loads(data)
    validator = EnziConfigValidator(copy.deepcopy(conf), '.')

    assert validator.validate()
    assert validator.val == conf
    assert validator.info() != None
    
def test_raw_config_to_partial_config():
    try:
        f = io.FileIO('ExampleEnzi.toml', 'r')
        reader = io.BufferedReader(f)
        data = reader.read()
        reader.close()
    except Exception:
        return
    
    data = data.decode('utf-8')
    conf = toml_loads(data)
    
    rconfig = RawConfig(data, True, '.', True, fileset_only=True)
    pconfig = rconfig.validate()
    assert isinstance(pconfig, PartialConfig)

    assert pconfig.package == conf['package']
    assert pconfig.filesets == conf['filesets']
    assert pconfig.is_local == True
    assert pconfig.file_stat == None
    assert pconfig.path == './Enzi.toml'

def test_raw_config_to_config():
    try:
        f = io.FileIO('ExampleEnzi.toml', 'r')
        reader = io.BufferedReader(f)
        data = reader.read()
        reader.close()
    except Exception:
        return
    
    data = data.decode('utf-8')
    conf = toml_loads(data)
    
    rconfig = RawConfig(data, True, '.', True)
    config = rconfig.validate()
    assert isinstance(config, Config)

    assert config.package == conf['package']
    assert config.filesets == conf['filesets']
    assert config.is_local == True
    assert config.file_stat == None
    assert config.path == './Enzi.toml'

    ori_deps = set(conf['dependencies'].keys())
    conf_deps = set(config.dependencies.keys())
    assert ori_deps == conf_deps

    ori_targets = set(conf['targets'].keys())
    conf_targets = set(config.targets.keys())
    assert ori_targets == conf_targets

    mori_tools = map(lambda x: x['name'], conf['tools'])
    ori_tools = set(mori_tools)
    conf_tools = set(config.tools.keys())
    assert ori_tools == conf_tools

def test_into():
    try:
        f = io.FileIO('ExampleEnzi.toml', 'r')
        reader = io.BufferedReader(f)
        data = reader.read()
        reader.close()
    except Exception:
        return

    data = data.decode('utf-8')
    
    rconfig = RawConfig(data, True, '.', True, fileset_only=True)
    config = rconfig.validate()
    assert isinstance(config, PartialConfig)
    
    cconfig = config.into()
    assert isinstance(cconfig, Config)

def test_content():
    try:
        f = io.FileIO('ExampleEnzi.toml', 'r')
        reader = io.BufferedReader(f)
        data = reader.read()
        reader.close()
    except Exception:
        return

    data = data.decode('utf-8')

    rconfig = RawConfig(data, True, '.', True)
    config = rconfig.validate()

    out = config.content()
    content = out.getvalue()
    print(content)
    assert content != None

def test_enzi_config_validator_key():
    v = EnziConfigValidator({}, './Enzi.toml', git_url='https://xxx.com')
    assert v.key == '<https://xxx.com/Enzi.toml>'

# tests for TypedMapValidator
@pytest.mark.skip(reason="This is a class for testing")
class TestTMValidator(TypedMapValidator):
    """validator for a single tool section"""
    __must__ = { 'name': StringValidator }
    __optional__ = { 'params': ToolParamsValidator }

    def __init__(self, *, key, val, parent=None):
        super().__init__(
            key=key,
            val=val,
            parent=parent,
            must=TestTMValidator.__must__,
            optional=TestTMValidator.__optional__
        )

    def check_tool(self, tool_name=None):
        """check if the tool is available and set the corresponding ToolParamsValidator"""
        if tool_name is None:
            tool_name = self.val['name'].lower()
        
        if not (tool_name in validator.ALLOW_BACKENDS or tool_name == 'ixs'):
            msg = 'unknown backend: `{}`'.format(tool_name)
            raise ValidatorError(self.chain_keys_str(), msg)

        params_validator = validator.v02.TPARAMS_VALIDATOR_MAP[tool_name]
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
    def info():
        return {}

def test_typed_map_validator():
    val = {
        'name': 'ies',
        'params': copy.deepcopy(PARAMS)
    }

    validator = TestTMValidator(key='tool', val=val)
    assert validator.validate() == val

    val['name'] = 'questa'
    assert validator.validate() == val

    val['unknown'] = 'unknown'
    expected(validator)

    del val['unknown']
    assert validator.validate() == val

    del val['name']
    expected(validator)

    val['name'] = 'ixs'
    validator.validate() == val
