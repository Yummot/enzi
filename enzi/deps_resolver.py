from enzi.config import DependencyRef
from enzi.git import GitVersions
from typing import List, Set, Dict, Tuple, Optional
from enzi.frontend import Enzi

class Dependency(object):
    def __init__(self, name):
        self.name = name
        # the sources for this dependency <K=DependencyRef, V=DependencySource>
        self.sources = {}
        # the enzi config we chose
        self.config = None
    def source(self):
        # TODO: inspect this code
        min_source = next(iter(self.sources.keys()))
        return self.sources[min_source]

class State(object):
    __allow_states__ = ('Open', 'Locked', 'Constrained', 'Pick')
    def __init__(self, state, val=None):
        if not state in self.__allow_states__:
            raise ValueError('state must in {}'.format(self.__allow_states__))
        self.state = state
        self.value = val
    
    @staticmethod
    def Open():
        return State('Open')
    @staticmethod
    def Locked(lock_id):
        return State('Locked', lock_id)
    @staticmethod
    def Constrained(versions: dict):
        return State('Constrained', versions)
    @staticmethod
    def Pick(pick_id, versions: dict):
        return State('Pick', (pick_id, versions))
    
    def is_open(self):
        return self.state == 'Open'
    def is_locked(self):
        return self.state == 'Locked'
    def is_constrained(self):
        return self.state == 'Constrained'
    def is_pick(self):
        return self.state == 'Pick'

class DependencySource(object):
    def __init__(self, dep_id: DependencyRef, versions: GitVersions, pick = None, options = None, state = State.Open()):
        self.id = dep_id
        self.versions = versions
        self.pick = pick
        self.options = options
        self.state = state
    
    def get_pick_version(self) -> Optional[GitVersions]:
        if self.state.is_open() or self.state.is_constrained():
            return None
        else:
            return self.versions
    

class DependencyResolver(object):
    def __init__(self, enzi: Enzi):
        self.table = {}
        self.decisions = {}
        self.enzi = enzi
    
    def register_dep(self, name: str, dep: DependencyRef, versions: GitVersions):
        if not name in self.table:
            self.table[name] = Dependency(name)
        entry = self.table[name]
        entry_src = entry.source()
        if not dep in entry_src:
            entry_src[dep] = DependencySource(dep, versions)
    
    def register_dep_in_config(self, deps, config):
        def fn(items):
            name, dep = items
            # TODO: may be we should make Enzi more orthogonal, 
            # by seperating it into EnziSession and Enzi
            return (name, self.enzi.load_dependencies(name, dep))
        
        names_map = map(fn , deps.items())
        names = dict(names_map)

        dep_ids = set(map(lambda item: item[1], names.items()))

        versions = 



# dsrc = DependencySource(DependencyRef(0), GitVersions(None, None, None))

