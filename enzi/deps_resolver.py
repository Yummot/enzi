from enzi.config import DependencyRef
# from enzi.config import DependencySource
from enzi.config import Config as EnziConfig
from enzi.git import GitVersions
from typing import List, Set, Dict, Tuple, Optional
from enzi.frontend import Enzi, EnziIO
from enzi.utils import flat_map, unique
from semver import VersionInfo as Version
import copy as py_copy
import logging
import itertools
import enzi.config
import typing

logger = logging.getLogger(__name__)


class Dependency(object):
    def __init__(self, name: str):
        self.name = name
        # the sources for this dependency <K=DependencyRef, V=DependencySource>
        self.sources: typing.MutableMapping[DependencyRef, DependencySource] = {}
        # the enzi config we chose
        self.config: typing.Optional[EnziConfig] = None

    def source(self):
        # TODO: inspect this code
        min_source = next(iter(self.sources.keys()))
        return self.sources[min_source]

# TODO: rewrite in more python way


class DependencyConstraint(object):
    __allow_cons__ = ("Version", "Revision")

    def __init__(self, cons, val=None):
        if not cons in self.__allow_cons__:
            raise ValueError('dep cons must in {}'.format(self.__allow_cons__))
        self.cons: str = cons
        if val is None or isinstance(val, Version) or type(val) == str:
            self.value: typing.Union[str, Version, None] = val
            # if self.value is str, it might be revision hash or version comparison str
        else:
            raise ValueError(
                'dep cons\'s value must be semver.VersionInfo or str')

    def __str__(self):
        return str(self.value)

    @staticmethod
    def Version(version: Version):
        return DependencyConstraint('Version', version)

    @staticmethod
    def Revision(revision: str):
        return DependencyConstraint('Revision', revision)

    @staticmethod
    def From(dep: enzi.config.DependencySource):
        if dep.use_version:
            return DependencyConstraint.Version(dep.version)
        else:
            return DependencyConstraint.Revision(dep.commit)

    def is_version(self):
        return self.cons == 'Version'

    def is_revision(self):
        return self.cons == 'Revision'

# TODO: rewrite in more python way


class State(object):
    __allow_states__ = ('Open', 'Locked', 'Constrained', 'Pick')

    def __init__(self, state, val=None):
        if not state in self.__allow_states__:
            raise ValueError('state must in {}'.format(self.__allow_states__))
        self.state: str = state
        self.value: typing.Union[int, set, None] = val

    @staticmethod
    def Open():
        return State('Open')

    @staticmethod
    def Locked(lock_id: int):
        return State('Locked', lock_id)

    @staticmethod
    def Constrained(versions: set):
        return State('Constrained', versions)

    @staticmethod
    def Pick(pick_id, versions: set):
        return State('Pick', (pick_id, versions))

    def is_open(self):
        return self.state == 'Open'

    def is_locked(self):
        return self.state == 'Locked'

    def is_constrained(self):
        return self.state == 'Constrained'

    def is_pick(self):
        return self.state == 'Pick'
    
    def pick(self):
        if self.is_pick():
            return self.value[0]
        elif self.is_locked():
            return self.value

    @property
    def ids(self) -> set:
        if self.is_constrained():
            return self.value
        elif self.is_pick():
            return self.value[1]
        else:
            raise RuntimeError('INTERNAL ERROR: unreachable')

    @ids.setter
    def ids(self, ids):
        if not type(id) == set:
            raise ValueError('ids must be a set')

        if self.is_constrained():
            self.value = ids
        elif self.is_pick():
            self.value[1] = ids
        else:
            raise RuntimeError(
                'INTERNAL ERROR: try to set ids for a State::{}'.format(self.state))


def dump_cons_map(cons_map: dict):
    str_buf = []
    names = cons_map.keys()
    names = sorted(names)
    str_buf.append('{')
    for name in names:
        cons = cons_map[name]
        str_buf.append('\n\t\"{{{}}}\" :'.format(name))
        for pkg_name, con in cons:
            str_buf.append(' {}({});'.format(con, pkg_name))
    str_buf.append('\n}')
    return ''.join(str_buf)


class DependencySource(object):
    def __init__(self, dep_id: DependencyRef, versions: GitVersions, pick=None, options=None, state=State.Open()):
        self.id: DependencyRef = dep_id
        self.versions: GitVersions = versions
        self.pick: typing.Optional[int] = pick
        self.options: typing.Optional[typing.MutableSet[int]] = options
        self.state: State = state

    def current_pick(self) -> Optional[str]:
        if self.state.is_open() or self.state.is_constrained():
            return None
        else:
            return self.versions.revisions[self.id]


class DependencyResolver(object):
    def __init__(self, enzi: Enzi):
        self.table: typing.MutableMapping[str,
                                          Dependency] = {}  # <K=str, Dependency>
        self.decisions: typing.MutableMapping[str, int] = {}  # <K=str, int>
        self.enzi = enzi

    def init(self):
        for dep in self.table.values():
            for src in dep.sources.values():
                if not src.state.is_open():
                    continue
                logger.debug('resolve init {}[{}]'.format(dep.name, src.id))

                ids = list(range(len(src.versions.revisions)))
                src.state = State.Constrained(ids)

    def mark(self):
        def inner_dep(econfig: EnziConfig):
            pkg_name = econfig.package['name']
            return map(lambda item: (item[0], (pkg_name, item[1])), econfig.dependencies)

        other_econf = filter(lambda x: x, map(
            lambda dep: dep.conf, self.table.values()))
        econfig_iter = itertools.chain([self.enzi.config, ], other_econf)
        flat_dep = flat_map(inner_dep, econfig_iter)
        dep_iter = map(lambda dep: (dep[0], dep[1][0], dep[1][1]), flat_dep)

        cons_map = {}  # <K=str, V=list[(str, DependencyConstraint)]>
        for name, pkg_name, dep in dep_iter:
            if not name in cons_map:
                cons_map[name] = []
            v = cons_map[name]
            v.append(pkg_name, DependencyConstraint.From(dep))

        logger.debug("resolve: gathered constraints {}".format(
            dump_cons_map(cons_map)))

        new_table, old_table = {}, self.table
        for name, cons in cons_map.items():
            for con in cons.values():
                logger.debug("resolve: impose {} on {}".format(con, name))
                for src in old_table[name].values():
                    self.impose(name, con, src, cons)

        self.table = new_table

    def pick(self):
        any_change = False
        open_pending = set()

        for dep in self.table.values():
            for src in dep.sources.values():
                state: State = src.state
                if state.is_open():
                    raise RuntimeError(
                        'INTERNAL ERROR: unreachable, state = Open')
                elif state.is_locked():
                    pass
                elif state.is_constrained():
                    ids = state.ids
                    any_change = True
                    logger.debug(
                        'resolve: picking version for {}[{}]'.format(dep.name, src.id))
                    pick_id = min(ids)
                    src.state = State.Pick(pick_id, ids)
                elif state.is_pick():
                    pick_id, ids = state.value
                    if not pick_id in ids:
                        logger.debug('resolve: picked version for {}[{}] no longer valid, resetting'.format(
                            dep.name, src.id))
                        if dep.config:
                            open_pending.update(dep.config.dependencies.keys())
                            any_change = True
                            src.state = State.Open()
        
        while open_pending:
            opens, open_pending = open_pending, set()
            for dep_name in opens:
                logger.debug('resolve: resetting {}'.format(dep_name))
                dep = self.table[dep_name]
                for src in dep.source.values():
                    if not src.state.is_open():
                        any_change = True
                        if dep.config:
                            open_pending.update(dep.config.dependencies.keys())
                        src.state = State.Open()

        return any_change
    
    def close(self):
        logger.debug('resolve: computing closure over dependencies')
        enzi_io = EnziIO(self.enzi)

    def req_indices(self, name: str, con: DependencyConstraint, src: DependencySource):
        if con.is_version():
            git_ver = src.versions
            con: GitVersions = con.value
            ids = dict(map(lambda eitem: (eitem[1], eitem[0]),
                           enumerate(git_ver.revisions)))

            def try_match_ver(item):
                v, h = item
                if con.match(v):
                    return ids[h]
                else:
                    return None

            revs = set(filter(lambda x: x, map(
                try_match_ver, git_ver.versions)))
            return revs
        elif con.is_revision():
            git_ver = src.versions
            git_refs: dict = git_ver.refs
            git_revs: list = git_ver.revisions
            con: str = con.value

            revs = set()

            ref = git_refs.get(con, None)
            if ref:
                idx = git_revs.index(ref)
                revs.add(idx)
            else:
                enum_revs = enumerate(git_revs)
                revs_map = map(
                    lambda item: item[0] if item[1].startswith(con) else None,
                    enum_revs
                )
                revs_filter = filter(lambda x: x, revs_map)
                revs = set(revs_filter)

            return revs
        else:
            raise RuntimeError("INTERNAL ERROR")

    def impose(self, name: str, con: DependencyConstraint, src: DependencySource, all_cons: list):
        indices = self.req_indices(name, con, src)
        if not indices:
            raise RuntimeError(
                'Dependency {} from {} cannot statisfy requirement {}'.format(
                    name,
                    self.enzi.dependecy(src.id).source,
                    str(con)
                ))

        def extract_id(state: State):
            if state.is_open():
                raise RuntimeError('INTERNAL ERROR: unreachable, state = Open')
            elif state.is_locked():
                raise RuntimeError('INTERNAL ERROR: unreachable')
            elif state.is_constrained() or state.is_pick():
                ids = state.get_ids()
                is_ids = ids.intersection(indices)
                if not is_ids:
                    msg_buf = ["Requirement {} conflicts with other requirement on dependency {}"
                               .format(str(con), name), ]
                    cons = []
                    for pkg_name, con in all_cons:
                        msg_buf.append(
                            '\n- package {} requires {}'.format(pkg_name, con))
                        cons.append(con)
                    cons = list(unique(cons))
                    msg = ''.join(msg_buf)
                    raise RuntimeError(msg)
                else:
                    return is_ids
            else:
                raise RuntimeError('INTERNAL ERROR: unreachable')

        new_ids = extract_id(src.state)

        if src.state.is_open():
            raise RuntimeError('INTERNAL ERROR: unreachable, state = Open')
        elif src.state.is_locked():
            raise RuntimeError('INTERNAL ERROR: unreachable')
        elif src.state.is_constrained() or src.state.is_pick():
            src.state.ids = new_ids
        else:
            raise RuntimeError('INTERNAL ERROR: unreachable')

    def register_dep(self, name: str, dep: DependencyRef, versions: GitVersions):
        if not name in self.table:
            self.table[name] = Dependency(name)
        entry = self.table[name]
        entry_src = entry.source()
        if not dep in entry_src:
            entry_src[dep] = DependencySource(dep, versions)

    def register_dep_in_config(self, deps, enzi_config):
        def fn(items):
            name, dep = items
            # TODO: may be we should make Enzi more orthogonal,
            # by seperating it into EnziSession and Enzi
            return (name, self.enzi.load_dependency(name, dep, enzi_config))

        enzi_io = EnziIO(self.enzi)

        names = dict(map(fn, deps.items()))
        dep_ids = set(map(lambda item: item[1], names.items()))

        versions = map(
            lambda dep_id: (dep_id, enzi_io.dep_versions(dep_id)), dep_ids
        )
        versions = dict(versions)

        for name, dep_id in names.items():
            self.register_dep(name, dep_id, py_copy.copy(versions[dep_id]))


# dsrc = DependencySource(DependencyRef(0), GitVersions(None, None, None))