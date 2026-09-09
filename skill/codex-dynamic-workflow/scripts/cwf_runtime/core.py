"""Single-machine workflow controller. SQLite is authority; hosts are trusted.

No arbitrary tool execution, automatic write replay, or publication occurs here.
File identities detect observed drift; they do not freeze the filesystem.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import time
from typing import Any
import uuid

from .policy import budget_admission

VERSION = '4.1.0'
SUPPORTED_CONTRACT_VERSIONS = {'3.0.0', '4.0.0', '4.1.0'}
SCHEMA = 1
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
ROLES = {'explorer', 'verifier', 'reproducer', 'designer', 'writer', 'reviewer'}
DEFAULTS = dict(approved=28, reserve=4, absolute=32, strong_approved=8,
                capacity=None, max_nodes=64, max_depth=6, max_attempts=3,
                deadline_seconds=1800)
SUPPLEMENTAL_DEFAULTS = dict(supplemental_approved=12, mainline_capacity_reserve=1)
DEFAULT_ROUTES = {
    'strong': {'model': 'gpt-6-astra', 'effort': 'high', 'profile': 'cwf_reader'},
    'ordinary': {'model': 'gpt-5.6-luna', 'effort': 'max', 'profile': 'cwf_general'},
    'economy': {'model': 'gpt-5.6-luna', 'effort': 'medium', 'profile': 'cwf_mechanical'},
    'writer': {'model': 'gpt-6-astra', 'effort': 'high', 'profile': 'cwf_writer'},
}


def followup_contract(contract):
    return contract.get('version') == '4.1.0' and contract.get('supplemental_protocol') == 2


class WorkflowError(ValueError):
    """A contract, state, permission, or consistency gate rejected the operation."""


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WorkflowError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def loads(text: str) -> Any:
    if not isinstance(text, str):
        raise WorkflowError('JSON input must be text')
    if len(text.encode('utf-8')) > MAX_JSON_BYTES:
        raise WorkflowError('JSON input too large')
    try:
        return json.loads(text, object_pairs_hook=unique_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(WorkflowError('nonfinite JSON number')))
    except (TypeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f'invalid JSON: {exc}') from exc


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(value: Any) -> str:
    return hashlib.sha256(dump(value).encode()).hexdigest()


def text(value, label, limit=16000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise WorkflowError(f'{label} must be a bounded nonempty string')
    return value


def identifier(value, label='id'):
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value) is None:
        raise WorkflowError(f'invalid {label}')
    return value


def mapping(value, allowed, required, label):
    if not isinstance(value, dict) or set(value) - allowed or not required <= set(value):
        raise WorkflowError(f'{label}: missing or unexpected fields')
    return value


def boolean(value, label):
    if type(value) is not bool:
        raise WorkflowError(f'{label} must be boolean')
    return value


def checked_usage(usage):
    if usage is not None:
        mapping(usage, {'input_tokens','output_tokens','cached_input_tokens'}, {'input_tokens','output_tokens'}, 'usage')
        for k, v in usage.items(): integer(v, k, 0, 10**12)
        if usage.get('cached_input_tokens',0) > usage['input_tokens']:
            raise WorkflowError('invalid cached usage')
    return usage


def integer(value, label, minimum=0, maximum=100000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise WorkflowError(f'{label} must be an integer in [{minimum}, {maximum}]')
    return value


def clean_relative(value):
    text(value, 'path', 1024)
    value = value.replace('\\', '/')
    p = PurePosixPath(value)
    if p.is_absolute() or ':' in value or any(c in value for c in '*?\x00'):
        raise WorkflowError('absolute, wildcard, or stream path refused')
    if any(part in {'', '.', '..'} for part in value.split('/')):
        raise WorkflowError('path traversal/noncanonical path refused')
    if any(part.rstrip(' .') != part for part in p.parts):
        raise WorkflowError('ambiguous Windows path refused')
    if any(part.lower() in {'.git', '.codex', '.delivery', '.cwf', '__pycache__'} for part in p.parts):
        raise WorkflowError('control/state directory is not a source target')
    if p.name.lower() in {'auth.json', 'credentials.json'} or (p.name.lower().startswith('.env') and p.name.lower() not in {'.env.example', '.env.sample'}):
        raise WorkflowError('credential source target refused')
    if any(re.fullmatch(r'(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part, re.I) for part in p.parts):
        raise WorkflowError('Windows device path refused')
    return p.as_posix()


def regular_path(root: Path, relative: str, missing=False):
    current = root
    for part in PurePosixPath(clean_relative(relative)).parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise WorkflowError(f'missing source: {relative}')
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
            raise WorkflowError(f'link/reparse path refused: {relative}')
    if not current.resolve().is_relative_to(root):
        raise WorkflowError('source escaped declared root')
    if current.exists() and current.stat().st_nlink != 1:
        raise WorkflowError(f'hard-linked source refused: {relative}')
    if current.exists() and not current.is_file():
        raise WorkflowError(f'source is not a regular file: {relative}')
    return current


def fingerprint(root: Path, paths: list[str], missing: set[str] = frozenset()):
    result = {}
    for relative in paths:
        p = regular_path(root, relative, relative in missing)
        if not p.exists():
            result[relative] = None
            continue
        with p.open('rb') as stream:
            a = os.fstat(stream.fileno())
            if a.st_size > MAX_SOURCE_BYTES:
                raise WorkflowError(f'source exceeds {MAX_SOURCE_BYTES} bytes: {relative}')
            content = stream.read(MAX_SOURCE_BYTES + 1)
            b = os.fstat(stream.fileno())
        if len(content) > MAX_SOURCE_BYTES or (a.st_size, a.st_mtime_ns) != (b.st_size, b.st_mtime_ns):
            raise WorkflowError(f'source changed during read: {relative}')
        result[relative] = hashlib.sha256(content).hexdigest()
    return result


def path_list(value, label, empty=False):
    if not isinstance(value, list) or len(value) > 128 or (not empty and not value):
        raise WorkflowError(f'{label} requires a bounded explicit path list')
    out = [clean_relative(p) for p in value]
    if len({p.casefold() for p in out}) != len(out):
        raise WorkflowError(f'duplicate/aliased path in {label}')
    return out


def validate_claims(claims, opened):
    if not isinstance(claims, list) or len(claims) > 64:
        raise WorkflowError('invalid claims')
    fields = {'proposition','evidence','existence','applicability','impact'}
    for claim in claims:
        mapping(claim, fields, fields, 'claim')
        text(claim['proposition'], 'proposition'); text(claim['impact'], 'impact')
        text(claim['existence'], 'claim existence', 20)
        text(claim['applicability'], 'claim applicability', 20)
        evidence = path_list(claim['evidence'], 'claim evidence')
        if (not set(evidence) <= set(opened) or claim['existence'] not in {'supported','disproved','unknown'}
                or claim['applicability'] not in {'supported','disproved','unknown'}):
            raise WorkflowError('claim lacks valid opened-source evidence')
    return claims


def physical(root, paths):
    return [os.path.normcase(str(Path(root) / p)).replace('\\', '/').casefold() for p in paths]


def overlap(left, right):
    return any(a == b or a.startswith(b + '/') or b.startswith(a + '/') for a in left for b in right)


DDL = '''
CREATE TABLE meta(version INTEGER NOT NULL);
INSERT INTO meta VALUES(1);
CREATE TABLE runs(id TEXT PRIMARY KEY, root TEXT NOT NULL, backend TEXT NOT NULL,
 goal TEXT NOT NULL, contract TEXT NOT NULL, contract_hash TEXT NOT NULL,
 status TEXT NOT NULL, created REAL NOT NULL, deadline REAL NOT NULL,
 used INTEGER NOT NULL DEFAULT 0, reserve_used INTEGER NOT NULL DEFAULT 0,
 strong_used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE nodes(run_id TEXT NOT NULL, id TEXT NOT NULL, spec TEXT NOT NULL,
 snapshot TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 result TEXT, current_token TEXT, PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id) REFERENCES runs(id));
CREATE TABLE deps(run_id TEXT NOT NULL, node_id TEXT NOT NULL, dep_id TEXT NOT NULL,
 PRIMARY KEY(run_id,node_id,dep_id),
 FOREIGN KEY(run_id,node_id) REFERENCES nodes(run_id,id),
 FOREIGN KEY(run_id,dep_id) REFERENCES nodes(run_id,id));
CREATE TABLE attempts(token TEXT PRIMARY KEY, run_id TEXT NOT NULL, node_id TEXT NOT NULL,
 state TEXT NOT NULL, external_id TEXT, released INTEGER NOT NULL DEFAULT 0,
 result TEXT, usage TEXT, created REAL NOT NULL, ended REAL,
 FOREIGN KEY(run_id,node_id) REFERENCES nodes(run_id,id));
CREATE TABLE claims(id TEXT PRIMARY KEY, run_id TEXT NOT NULL, node_id TEXT NOT NULL,
 attempt TEXT NOT NULL, data TEXT NOT NULL, disposition TEXT NOT NULL DEFAULT 'UNKNOWN',
 revision INTEGER NOT NULL DEFAULT 1, FOREIGN KEY(attempt) REFERENCES attempts(token));
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
 at REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL,
 FOREIGN KEY(run_id) REFERENCES runs(id));
CREATE TRIGGER event_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only events'); END;
CREATE TRIGGER event_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append-only events'); END;
CREATE INDEX holds ON attempts(released,run_id);
'''


class Runtime:
    def __init__(self, db, *, initialize=False, read_only=False):
        self.path = Path(db).absolute()
        if self.path.is_symlink():
            raise WorkflowError('database symlink refused')
        if initialize and read_only:
            raise WorkflowError('cannot initialize read-only')
        if not initialize and not self.path.is_file():
            raise WorkflowError('database does not exist; explicit init required')
        if initialize:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path.as_uri() + ('?mode=ro' if read_only else '?mode=rwc' if initialize else '?mode=rw'),
                                    uri=True, timeout=5, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.execute('PRAGMA busy_timeout=5000')
        try:
            exists = self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
            if not exists:
                if not initialize:
                    raise WorkflowError('uninitialized database')
                # No implicit import/migration of an unrelated database.
                if self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                    raise WorkflowError('unrecognized nonempty database')
                self.conn.executescript('BEGIN IMMEDIATE;\n' + DDL + '\nCOMMIT;')
            rows = self.conn.execute('SELECT version FROM meta').fetchall()
            if len(rows) != 1 or rows[0][0] != SCHEMA:
                raise WorkflowError('unsupported runtime database schema')
        except BaseException:
            self.conn.close()
            raise

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def tx(self):
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.conn.execute('COMMIT')
        except BaseException:
            self.conn.execute('ROLLBACK')
            raise

    def event(self, run, kind, data):
        self.conn.execute('INSERT INTO events(run_id,at,kind,data) VALUES(?,?,?,?)', (run, time.time(), kind, dump(data)))

    def run(self, run):
        row = self.conn.execute('SELECT * FROM runs WHERE id=?', (run,)).fetchone()
        if row is None:
            raise WorkflowError('unknown run')
        return dict(row)

    def node(self, run, node):
        row = self.conn.execute('SELECT * FROM nodes WHERE run_id=? AND id=?', (run, node)).fetchone()
        if row is None:
            raise WorkflowError('unknown node')
        return dict(row)

    def attempt(self, token):
        row = self.conn.execute('SELECT * FROM attempts WHERE token=?', (token,)).fetchone()
        if row is None:
            raise WorkflowError('unknown attempt')
        return dict(row)

    def create(self, *, root, goal, backend, bounds=None, routes=None, implement=False, run_id=None,
               capacity_scope=None, execution_pool=None, workflow='astra-mainline', acceptance_mode=None):
        if backend not in {'native', 'exec'}:
            raise WorkflowError('backend must be native or exec')
        if capacity_scope not in (None, 'database', 'backend'):
            raise WorkflowError('capacity_scope must be database or backend')
        if execution_pool not in (None, 'luna'):
            raise WorkflowError('execution_pool must be luna when selected')
        if workflow not in {'astra-mainline', 'legacy'}:
            raise WorkflowError('unknown workflow policy')
        if workflow == 'astra-mainline' and (backend != 'native' or execution_pool is not None):
            raise WorkflowError('Astra mainline requires native execution')
        source = Path(root).absolute()
        if source.is_symlink() or not source.is_dir() or getattr(source.lstat(), 'st_file_attributes', 0) & 1024:
            raise WorkflowError('project root must be an existing non-link directory')
        source = source.resolve()
        goal = text(goal, 'goal')
        boolean(implement, 'implement')
        if acceptance_mode is None:
            acceptance_mode = 'repair' if implement else 'review'
        if acceptance_mode not in {'review', 'repair'} or (acceptance_mode == 'repair' and not implement):
            raise WorkflowError('repair acceptance requires implementation authority')
        options = dict(DEFAULTS)
        if workflow == 'astra-mainline':
            options.update(SUPPLEMENTAL_DEFAULTS)
        if bounds is not None:
            mapping(bounds, set(options), set(), 'bounds')
            options.update(bounds)
        for key, value in options.items():
            if key == 'capacity' and value is None:
                continue  # Host capacity applies; no additional controller ceiling.
            integer(value, key, 0 if key in {'reserve', 'strong_approved', 'supplemental_approved'} else 1)
        if options['approved'] + options['reserve'] > options['absolute'] or options['strong_approved'] > options['approved']:
            raise WorkflowError('inconsistent allowance bounds')
        routing = loads(dump(DEFAULT_ROUTES if routes is None else routes))
        # Explicit legacy route sets stay exact; never inject a model into a saved allowance.
        mapping(routing, {'strong', 'ordinary', 'economy', 'writer'}, {'strong', 'economy', 'writer'}, 'routes')
        for route in routing.values():
            mapping(route, {'model', 'effort', 'profile'}, {'model', 'effort', 'profile'}, 'route')
            for key in ('model', 'profile'):
                if not isinstance(route[key], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,127}', route[key]):
                    raise WorkflowError('invalid route identity')
            if route['effort'] not in {'low', 'medium', 'high', 'xhigh', 'max'}:
                raise WorkflowError('unsupported effort')
        if execution_pool == 'luna':
            if backend != 'exec' or implement or capacity_scope != 'backend' or options['strong_approved'] != 0:
                raise WorkflowError('Luna pool requires exec, backend capacity, readonly scope and strong_approved=0')
            for tier in ('ordinary', 'economy'):
                if any(routing.get(tier, {}).get(k) != DEFAULT_ROUTES[tier][k] for k in ('model', 'effort')):
                    raise WorkflowError('Luna pool requires ordinary Luna/max and economy Luna/medium routes')
        if workflow == 'astra-mainline':
            for tier in ('strong', 'writer', 'ordinary', 'economy'):
                if any(routing.get(tier, {}).get(k) != DEFAULT_ROUTES[tier][k]
                       for k in ('model', 'profile', 'effort')):
                    raise WorkflowError(f'route identity mismatch for {tier}: fixed profile/model/effort must agree')
        rid = identifier(run_id or uuid.uuid4().hex)
        contract = {'version': VERSION, 'bounds': options, 'routes': routing, 'implement': implement,
                    'backend': backend, 'root': str(source), 'goal': goal, 'workflow': workflow}
        if workflow == 'astra-mainline':
            contract.update(supplemental_protocol=2, acceptance_mode=acceptance_mode)
        # Keep omitted fields and saved legacy contract hashes unchanged.
        if capacity_scope is not None: contract['capacity_scope'] = capacity_scope
        if execution_pool is not None: contract['execution_pool'] = execution_pool
        now = time.time()
        with self.tx():
            self.conn.execute('INSERT INTO runs(id,root,backend,goal,contract,contract_hash,status,created,deadline) VALUES(?,?,?,?,?,?,?,?,?)',
                              (rid, str(source), backend, goal, dump(contract), sha(contract), 'open', now, now + options['deadline_seconds']))
            self.event(rid, 'run.created', contract)
        return rid

    def open_run(self, run):
        r = self.run(run)
        if r['status'] != 'open':
            raise WorkflowError(f"run is {r['status']}")
        if time.time() >= r['deadline']:
            raise WorkflowError('run deadline reached')
        contract = loads(r['contract'])
        if contract.get('version') not in SUPPORTED_CONTRACT_VERSIONS or sha(contract) != r['contract_hash']:
            raise WorkflowError('runtime/contract identity changed; recovery requires explicit migration')
        return r, contract

    def add(self, run, specs, *, reason):
        text(reason, 'expansion reason', 2000)
        if not isinstance(specs, list) or not specs:
            raise WorkflowError('nonempty node batch required')
        with self.tx():
            r, c = self.open_run(run)
            existing = {row['id']: loads(row['spec']) for row in self.conn.execute('SELECT id,spec FROM nodes WHERE run_id=?', (run,))}
            if len(existing) + len(specs) > c['bounds']['max_nodes']:
                raise WorkflowError('graph node limit reached')
            additions = {}
            for raw in specs:
                allowed = {'id', 'role', 'task', 'sources', 'writes', 'depends', 'checks', 'risk', 'tier', 'required', 'economy_qualified', 'ordinary_qualified', 'verifies', 'supplemental', 'snapshot_root'}
                if c.get('workflow') != 'astra-mainline':
                    allowed -= {'supplemental', 'snapshot_root'}
                mapping(raw, allowed, {'id', 'role', 'task', 'sources', 'checks'}, 'node')
                s = dict(raw)
                identifier(s['id']); text(s['task'], 'task')
                if s['id'] in existing or s['id'] in additions:
                    raise WorkflowError('duplicate node id')
                if s['role'] not in ROLES:
                    raise WorkflowError('unknown logical role')
                s['sources'] = path_list(s['sources'], 'sources')
                s['writes'] = path_list(s.get('writes', []), 'writes', True)
                s.setdefault('depends', []); s.setdefault('risk', 'medium')
                s.setdefault('ordinary_qualified', False)
                s.setdefault('required', True); s.setdefault('economy_qualified', False); s.setdefault('verifies', None); s.setdefault('supplemental', False)
                boolean(s['required'], 'required'); boolean(s['economy_qualified'], 'economy_qualified')
                boolean(s['ordinary_qualified'], 'ordinary_qualified'); boolean(s['supplemental'], 'supplemental')
                s.setdefault('tier', 'ordinary' if s['ordinary_qualified'] else 'strong')
                if s['supplemental'] and (s['required'] or s['role'] == 'writer' or s['writes'] or s['verifies'] is not None or s['tier'] == 'strong'):
                    raise WorkflowError('supplemental nodes must be optional readonly non-verifying Luna work')
                if s['risk'] not in {'low', 'medium', 'high'} or s['tier'] not in {'strong', 'ordinary', 'economy'}:
                    raise WorkflowError('invalid risk/tier')
                if c.get('workflow') == 'astra-mainline' and not s['supplemental'] and s['tier'] != 'strong':
                    raise WorkflowError('mainline requires Astra strong routing')
                if 'snapshot_root' in s and not s['supplemental']:
                    raise WorkflowError('only supplemental nodes may bind a snapshot root')
                if s['supplemental']:
                    if 'snapshot_root' not in s:
                        raise WorkflowError('supplemental needs an isolated snapshot_root')
                    text(s['snapshot_root'], 'snapshot_root', 4096)
                    sr = Path(s['snapshot_root']).absolute()
                    if not sr.is_dir() or sr.is_symlink() or getattr(sr.lstat(), 'st_file_attributes', 0) & 1024 or sr.resolve() != sr:
                        raise WorkflowError('snapshot root must be a canonical non-link directory')
                    live = Path(r['root'])
                    if sr == live or sr.is_relative_to(live) or live.is_relative_to(sr):
                        raise WorkflowError('supplemental snapshot must be isolated from the live candidate')
                    s['snapshot_root'] = str(sr)
                if c.get('execution_pool') == 'luna' and (s['tier'] == 'strong' or s['risk'] == 'high' or s['role'] == 'writer'):
                    raise WorkflowError('Luna pool accepts only qualified low/medium-risk readonly ordinary/economy nodes')
                if s['tier'] == 'ordinary':
                    if not s['ordinary_qualified'] or s['risk'] not in {'low', 'medium'} or s['role'] == 'writer':
                        raise WorkflowError('ordinary quality/capability not established')
                    if 'ordinary' not in c['routes']:
                        raise WorkflowError('ordinary route absent from this run contract; select an explicit available tier')
                if s['tier'] == 'economy' and not (s['economy_qualified'] and s['risk'] == 'low' and s['role'] == 'explorer'):
                    raise WorkflowError('economy quality/capability not established')
                if not isinstance(s['depends'], list) or any(not isinstance(d,str) for d in s['depends']) or len(s['depends']) != len(set(s['depends'])):
                    raise WorkflowError('invalid dependency list')
                for dep in s['depends']:
                    identifier(dep, 'dependency')
                if not isinstance(s['checks'], list) or not s['checks'] or len(s['checks']) > 32:
                    raise WorkflowError('explicit acceptance check names required')
                for check in s['checks']:
                    text(check, 'check', 200)
                if len(s['checks']) != len(set(s['checks'])):
                    raise WorkflowError('duplicate check name')
                if s['role'] == 'writer':
                    if not c['implement'] or not s['writes'] or s['tier'] != 'strong':
                        raise WorkflowError('writer requires explicit implement authority, scope, strong route')
                    if r['backend'] == 'exec':
                        raise WorkflowError('v3 exec adapter is read-only; select native for authorized writes')
                elif s['writes']:
                    raise WorkflowError('non-writer cannot own writes')
                if s['verifies'] is not None:
                    identifier(s['verifies'], 'verification target')
                    if s['role'] not in {'verifier', 'reviewer'} or s['tier'] not in {'strong', 'ordinary'} or s['verifies'] not in s['depends']:
                        raise WorkflowError('verification requires capable role and target dependency')
                additions[s['id']] = s
            graph = existing | additions
            depth = {}
            def visit(n, active):
                if n in active:
                    raise WorkflowError('dependency cycle')
                if n not in graph:
                    raise WorkflowError('unknown dependency')
                if n not in depth:
                    depth[n] = 1 + max([visit(d, active | {n}) for d in graph[n]['depends']] or [0])
                return depth[n]
            for n in graph:
                if visit(n, set()) > c['bounds']['max_depth']:
                    raise WorkflowError('dependency depth limit reached')
                if not graph[n].get('supplemental', False) and any(graph[d].get('supplemental', False) for d in graph[n]['depends']):
                    raise WorkflowError('mainline nodes cannot depend on supplemental work')
                s = graph[n]
                if s['verifies'] is not None:
                    target = graph[s['verifies']]
                    if (target['risk'] == 'high' or target['role'] == 'writer') and s['tier'] != 'strong':
                        raise WorkflowError('high-risk and writer verification requires a strong route')
            snapshots = {row['id']: loads(row['snapshot']) for row in self.conn.execute('SELECT id,snapshot FROM nodes WHERE run_id=?', (run,))}
            def bind_sources(s):
                if s['id'] in snapshots:
                    return snapshots[s['id']]
                missing = set(s['writes'])
                target = graph.get(s['verifies'])
                if target is not None and target['role'] == 'writer':
                    original = bind_sources(target)
                    missing |= {p for p in target['writes'] if original[p] is None} & set(s['sources'])
                snap = fingerprint(Path(s.get('snapshot_root', r['root'])), sorted(set(s['sources'] + s['writes'])), missing)
                if s.get('supplemental') and snap != fingerprint(Path(r['root']), s['sources']):
                    raise WorkflowError('supplemental snapshot does not match the current candidate')
                snapshots[s['id']] = snap
                return snap
            for s in additions.values():
                snap = bind_sources(s)
                self.conn.execute('INSERT INTO nodes(run_id,id,spec,snapshot,state) VALUES(?,?,?,?,?)',
                                  (run, s['id'], dump(s), dump(snap), 'pending'))
            for s in additions.values():
                for dep in s['depends']:
                    self.conn.execute('INSERT INTO deps VALUES(?,?,?)', (run, s['id'], dep))
            self.event(run, 'graph.expanded', {'reason': reason, 'nodes': list(additions)})
        return list(additions)

    def _assert_snapshot(self, r, n, post=False):
        s = loads(n['spec']); expected = loads(n['snapshot'])
        if post and n['result']:
            expected = loads(n['result']).get('snapshot', expected)
        if s['role'] != 'writer' and any(h is None for h in expected.values()):
            raise WorkflowError(f"deferred review sources require explicit refresh: {n['id']}")
        current = fingerprint(Path(s.get('snapshot_root', r['root'])), list(expected), set(s['writes']))
        if current != expected:
            raise WorkflowError(f"candidate drift: {n['id']}")
        return current

    def _readonly_turn_receipt(self, attempt):
        rows = self.conn.execute("SELECT data FROM events WHERE run_id=? AND kind='attempt.readonly_turn_completed' ORDER BY seq", (attempt['run_id'],))
        for row in rows:
            data = loads(row['data'])
            if data['attempt'] == attempt['token']:
                return data['receipt']
        return None

    def _execution_reconciled(self, attempt):
        return bool(attempt['released']) or self._readonly_turn_receipt(attempt) is not None

    def _held_conflict(self, r, s):
        reads = physical(s.get('snapshot_root', r['root']), s['sources']); writes = physical(r['root'], s['writes'])
        rows = self.conn.execute('SELECT attempts.token,attempts.run_id,attempts.released,runs.root,nodes.spec FROM attempts JOIN runs ON runs.id=attempts.run_id JOIN nodes ON nodes.run_id=attempts.run_id AND nodes.id=attempts.node_id WHERE attempts.released=0').fetchall()
        for row in rows:
            if self._execution_reconciled(row):
                continue
            other = loads(row['spec'])
            other_reads = physical(other.get('snapshot_root', row['root']), other['sources']); other_writes = physical(row['root'], other['writes'])
            if writes and other_writes:  # One writer per coordination DB, even across worktrees.
                return True
            if overlap(writes, other_reads + other_writes) or overlap(reads, other_writes):
                return True
        return False

    def acquire(self, run, *, backend, host_capacity=None, host_active=None, mainline_slots_needed=None):
        if host_capacity is not None: integer(host_capacity, 'host_capacity', 1)
        if host_active is not None: integer(host_active, 'host_active')
        if mainline_slots_needed is not None: integer(mainline_slots_needed, 'mainline_slots_needed', 1)
        with self.tx():
            r, c = self.open_run(run)
            if backend != r['backend']:
                raise WorkflowError('backend mismatch; no automatic handoff')
            nodes = [dict(n) for n in self.conn.execute('SELECT * FROM nodes WHERE run_id=? ORDER BY rowid', (run,))]
            by_id = {n['id']: n for n in nodes}
            pending = [n for n in nodes if loads(n['spec'])['required'] and n['state'] in {'pending', 'failed', 'partial', 'interrupted', 'unknown'}]
            mandatory = len(pending)
            mandatory_strong = sum(loads(n['spec'])['tier'] == 'strong' for n in pending)
            # Opt-in separation changes capacity only, never the DB-wide source locks.
            if c.get('capacity_scope', 'database') == 'backend':
                active = self.conn.execute('SELECT COUNT(*) FROM attempts JOIN runs ON runs.id=attempts.run_id WHERE attempts.released=0 AND runs.backend=?', (backend,)).fetchone()[0]
            else:
                active = self.conn.execute('SELECT COUNT(*) FROM attempts WHERE released=0').fetchone()[0]
            strict = c.get('workflow') == 'astra-mainline'
            supplemental_used = sum(n['attempts'] for n in nodes if loads(n['spec']).get('supplemental'))
            capacity = c['bounds']['capacity']
            if host_capacity is not None:
                capacity = min(capacity, host_capacity) if capacity is not None else host_capacity
            active = max(active, host_active or 0)
            cutoff = self._supplemental_cutoff(r)
            reserve_slots = c['bounds'].get('mainline_capacity_reserve', 1)
            if followup_contract(c):
                # Protect the next known required frontier, not just a single future reviewer.
                frontier = sum(n['state'] == 'pending' and loads(n['spec'])['required']
                    and not loads(n['spec']).get('supplemental')
                    and all(by_id[d]['state'] in {'completed', 'active'} for d in loads(n['spec'])['depends'])
                    for n in nodes)
                reserve_slots = max(reserve_slots, frontier, mainline_slots_needed or 1)
            reasons = []
            for n in sorted(nodes, key=lambda n: (loads(n['spec']).get('supplemental', False), not loads(n['spec'])['required'])):
                s = loads(n['spec'])
                if n['state'] != 'pending':
                    continue
                if not all(by_id[d]['state'] == 'completed' for d in s['depends']):
                    reasons.append({'node': n['id'], 'reason': 'dependencies-incomplete'}); continue
                # A declared required independent check must exist before risky work starts.
                if s['role'] == 'writer' or (s['risk'] == 'high' and s['verifies'] is None):
                    if not any(loads(x['spec'])['verifies'] == n['id'] and loads(x['spec'])['required'] for x in nodes):
                        reasons.append({'node': n['id'], 'reason': 'required-verifier-not-declared'}); continue
                if self._held_conflict(r, s):
                    reasons.append({'node': n['id'], 'reason': 'source-writer-lock'}); continue
                try:
                    self._assert_snapshot(r, n)
                    for dep in s['depends']:
                        self._historical_write_evidence(r, by_id[dep], nodes)
                except WorkflowError as exc:
                    reasons.append({'node': n['id'], 'reason': str(exc)}); continue
                b = c['bounds']
                if strict and s.get('supplemental'):
                    why = None
                    if cutoff: why = 'supplemental-cutoff-after-mainline-acceptance'
                    elif supplemental_used >= b['supplemental_approved']: why = 'supplemental-allowance-exhausted'
                    elif capacity is None or (followup_contract(c) and host_capacity is None): why = 'host-capacity-unknown'
                    elif followup_contract(c) and host_active is None: why = 'host-active-unknown'
                    elif active + 1 + reserve_slots > capacity: why = 'mainline-capacity-reserved'
                    elif r['used'] + 1 + max(mandatory_strong, b['strong_approved'] - r['strong_used']) > min(b['approved'], b['absolute']): why = 'mainline-allowance-reserved'
                    if why:
                        reasons.append({'node': n['id'], 'reason': why}); continue
                decision = budget_admission(approved=b['approved'], reserve=b['reserve'], absolute=b['absolute'],
                    used=r['used'], reserve_used=r['reserve_used'], strong_used=r['strong_used'], strong_approved=b['strong_approved'],
                    economy=s['tier'] != 'strong',
                    economy_qualified=s.get('ordinary_qualified', False) if s['tier'] == 'ordinary' else s['economy_qualified'],
                    reserve_eligible=s['tier'] == 'economy' and not s.get('supplemental'), active=active, capacity=capacity,
                    mandatory_pending=mandatory, mandatory_strong_pending=mandatory_strong,
                    optional=not s['required'], consumes_mandatory=s['required'])
                if decision.outcome != 'allow':
                    reasons.append({'node': n['id'], 'reason': decision.reason}); continue
                if n['attempts'] >= b['max_attempts']:
                    reasons.append({'node': n['id'], 'reason': 'attempt-limit'}); continue
                token = uuid.uuid4().hex
                self.conn.execute('INSERT INTO attempts(token,run_id,node_id,state,created) VALUES(?,?,?,?,?)', (token, run, n['id'], 'reserved', time.time()))
                self.conn.execute('UPDATE nodes SET state=?,attempts=attempts+1,current_token=? WHERE run_id=? AND id=?', ('active', token, run, n['id']))
                self.conn.execute('UPDATE runs SET used=used+1,reserve_used=reserve_used+?,strong_used=strong_used+? WHERE id=?',
                                  (int(decision.reason == 'cumulative-economy-reserve'), int(s['tier'] == 'strong'), run))
                self.event(run, 'attempt.reserved', {'node': n['id'], 'attempt': token, 'allowance': decision.reason,
                    **({'host_capacity':host_capacity, 'host_active':host_active, 'effective_capacity':capacity,
                        'accounted_active':active, 'mainline_reserve':reserve_slots} if followup_contract(c) else {})})
                route = c['routes']['writer' if s['role'] == 'writer' else s['tier']]
                return {'admitted': True, 'run_id': run, 'node_id': n['id'], 'attempt': token, 'backend': backend,
                        'contract_hash': r['contract_hash'], 'root': s.get('snapshot_root', r['root']), 'candidate_root': r['root'], 'goal': r['goal'],
                        'task': s, 'snapshot': loads(n['snapshot']), 'route': route, 'deadline': r['deadline'],
                        'permissions': {'write_files': s['writes'], 'delete_files': False, 'publication': False, 'child_spawn': False, 'peer_messaging': False}}
            self.event(run, 'admission.deferred', {'reasons': reasons})
            return {'admitted': False, 'reasons': reasons}

    def bind(self, token, external_id, *, backend):
        text(external_id, 'external_id', 256)
        with self.tx():
            a = self.attempt(token); r, _ = self.open_run(a['run_id'])
            if backend != r['backend']:
                raise WorkflowError('backend mismatch')
            n = self.node(a['run_id'], a['node_id'])
            if n['current_token'] != token or a['released'] or a['state'] not in {'reserved', 'running'}:
                raise WorkflowError('stale/terminal attempt cannot bind')
            if a['external_id'] is not None and a['external_id'] != external_id:
                raise WorkflowError('external identity already bound')
            if a['external_id'] == external_id:
                return
            self.conn.execute('UPDATE attempts SET state=?,external_id=? WHERE token=?', ('running', external_id, token))
            self.event(a['run_id'], 'attempt.bound', {'attempt': token, 'external_id': external_id})

    def complete(self, token, result, *, external_id, backend, usage=None):
        # The host, not the model result, supplies identity, usage and terminal attestation.
        fields = {'outcome','summary','sources_opened','checks','changed_files','claims'}
        current_run = self.run(self.attempt(token)['run_id'])
        allowed = fields | ({'notes'} if followup_contract(loads(current_run['contract'])) else set())
        mapping(result, allowed, fields, 'result')
        text(result['summary'], 'summary')
        text(result['outcome'], 'result outcome', 20)
        if result['outcome'] not in {'completed', 'partial', 'failed'}:
            raise WorkflowError('invalid result outcome')
        checked_usage(usage)
        with self.tx():
            a = self.attempt(token); r = self.run(a['run_id']); n = self.node(a['run_id'], a['node_id']); s = loads(n['spec'])
            if r['backend'] != backend or a['external_id'] is None or a['external_id'] != external_id:
                raise WorkflowError('result identity/backend mismatch')
            envelope = {'payload':result, 'usage':usage}
            if a['state'] in {'completed','partial','failed'} and a['result']:
                old = loads(a['result'])
                if old['submission'] == envelope:
                    return {'state':a['state'], 'idempotent':True}
                raise WorkflowError('conflicting duplicate completion')
            if n['current_token'] != token or a['released'] or a['state'] not in {'reserved','running'}:
                raise WorkflowError('stale/fenced completion')
            opened = path_list(result['sources_opened'], 'sources_opened', result['outcome'] != 'completed')
            changed = path_list(result['changed_files'], 'changed_files', True)
            if not set(opened) <= set(s['sources']) or not set(changed) <= set(s['writes']):
                raise WorkflowError('result exceeds source/write scope')
            if result['outcome'] == 'completed' and set(opened) != set(s['sources']):
                raise WorkflowError('required raw sources not all opened')
            checks = result['checks']
            if not isinstance(checks,list) or len(checks) > 64:
                raise WorkflowError('invalid checks')
            named = {}
            for check in checks:
                mapping(check, {'name','status'}, {'name','status'}, 'check')
                text(check['name'],'check name',200)
                text(check['status'], 'check status', 20)
                if check['name'] in named or check['status'] not in {'PASS','FAIL','UNKNOWN','NOT_RUN'}:
                    raise WorkflowError('invalid/duplicate check result')
                named[check['name']] = check['status']
            if result['outcome'] == 'completed' and any(named.get(k) != 'PASS' for k in s['checks']):
                raise WorkflowError('mandatory acceptance checks incomplete')
            claims = validate_claims(result['claims'], opened)
            if followup_contract(loads(r['contract'])):
                claims = [{**claim,'evidence':path_list(claim['evidence'],'claim evidence')} for claim in claims]
            notes = result.get('notes', [])
            if not isinstance(notes, list) or len(notes) > 12:
                raise WorkflowError('notes must be a bounded list')
            for note in notes:
                mapping(note, {'text','evidence'}, {'text','evidence'}, 'note')
                text(note['text'], 'note text', 1000)
                if not set(path_list(note['evidence'], 'note evidence', True)) <= set(opened):
                    raise WorkflowError('note exceeds opened sources')
            before = loads(n['snapshot'])
            current = fingerprint(Path(s.get('snapshot_root', r['root'])), list(before), set(s['writes']))
            drift = [p for p in before if current[p] != before[p]]
            outcome = result['outcome']
            if s['role'] == 'writer':
                if not set(drift) <= set(s['writes']) or set(changed) != set(drift):
                    raise WorkflowError('writer changed-file receipt does not match observed source effects')
                if any(before[p] is not None and current[p] is None for p in drift):
                    outcome = 'partial'  # Deletions need manual effect reconciliation in v3.
            elif drift:
                outcome = 'partial'
            saved = {'submission':envelope,'snapshot':current,'evidence_snapshot':before,'drift':drift,
                     'blocked_effects':['deletion:'+p for p in drift if before[p] is not None and current[p] is None],
                     'provenance':'trusted-host-attestation; sources are observed fingerprints'}
            self.conn.execute('UPDATE attempts SET state=?,result=?,usage=?,ended=? WHERE token=?',
                              (outcome,dump(saved),dump(usage) if usage is not None else None,time.time(),token))
            self.conn.execute('UPDATE nodes SET state=?,result=? WHERE run_id=? AND id=?', (outcome,dump(saved),a['run_id'],a['node_id']))
            for index, claim in enumerate(claims):
                data={'claim':claim,'snapshot':before,'evidence_valid':not drift}
                self.conn.execute('INSERT INTO claims(id,run_id,node_id,attempt,data) VALUES(?,?,?,?,?)',
                                  (f'{token}-{index}',a['run_id'],a['node_id'],token,dump(data)))
            self.event(a['run_id'],'attempt.completed',{'attempt':token,'state':outcome,'drift':drift,'blocked_effects':saved['blocked_effects'],'usage':usage})
            return {'state':outcome,'idempotent':False}

    def release(self, token, *, external_id, confirmed, reason, kind='host-resource', receipt=None, usage=None):
        if confirmed is not True: raise WorkflowError('explicit host termination/closure confirmation required')
        text(reason,'release reason',2000)
        checked_usage(usage)
        text(kind,'release kind',40)
        if kind not in {'host-resource', 'readonly-turn-completed'}:
            raise WorkflowError('unknown release kind')
        if kind == 'host-resource' and receipt is not None:
            raise WorkflowError('turn receipt requires readonly-turn-completed kind')
        with self.tx():
            a=self.attempt(token)
            if external_id != a['external_id']:
                raise WorkflowError('termination identity mismatch')
            if usage is not None:
                if kind != 'host-resource' or self.run(a['run_id'])['backend'] != 'exec':
                    raise WorkflowError('release usage requires confirmed exec resource release')
                if a['usage'] is not None and loads(a['usage']) != usage:
                    raise WorkflowError('conflicting observed usage')
                self.conn.execute('UPDATE attempts SET usage=? WHERE token=?', (dump(usage),token))
            if kind == 'readonly-turn-completed':
                r=self.run(a['run_id']); n=self.node(a['run_id'],a['node_id']); s=loads(n['spec'])
                if (r['backend'] != 'native' or not external_id or a['state'] != 'completed'
                        or not a['result'] or n['current_token'] != token or s['role']=='writer' or s['writes']):
                    raise WorkflowError('turn completion receipt requires an accepted current native readonly result')
                fields={'attempt','external_id','status','observed_via','observed_at','tools_settled'}
                mapping(receipt, fields, fields, 'host turn receipt')
                text(receipt['observed_at'],'host observation time',100)
                try:
                    observed=datetime.fromisoformat(receipt['observed_at'].replace('Z','+00:00'))
                    if observed.utcoffset() != timezone.utc.utcoffset(observed):
                        raise ValueError('UTC required')
                    observed_seconds=observed.timestamp()
                except (ValueError, OverflowError):
                    raise WorkflowError('host observation time must be a UTC ISO timestamp') from None
                # datetime truncates to microseconds; a Windows 100ns clock tick
                # may round across that boundary when stored as a float. Allow
                # one receipt quantum plus one float ULP only at completion.
                completion_tolerance = 1e-6 + math.ulp(a['ended'])
                if a['ended'] - observed_seconds > completion_tolerance or observed_seconds > time.time():
                    raise WorkflowError('host observation must follow accepted completion and not be in the future')
                if (receipt['attempt'] != token or receipt['external_id'] != external_id
                        or receipt['status'] != 'completed' or receipt['observed_via'] != 'collaboration.list_agents'
                        or receipt['tools_settled'] is not True):
                    raise WorkflowError('host turn receipt identity, completed status and settled tools are required')
                previous=self._readonly_turn_receipt(a)
                if previous is not None:
                    if previous != receipt: raise WorkflowError('conflicting host turn receipt')
                    return {'execution_reconciled':True,'host_resources_released':bool(a['released']),'idempotent':True}
                if a['released']: raise WorkflowError('host resources already released')
                self._assert_snapshot(r,n,True)
                self.event(a['run_id'],'attempt.readonly_turn_completed',
                           {'attempt':token,'external_id':external_id,'receipt':receipt,'reason':reason,
                            'host_resource_state':'UNKNOWN'})
                return {'execution_reconciled':True,'host_resources_released':False,'idempotent':False}
            if a['released']: return
            if a['state'] in {'reserved','running'}:
                self.conn.execute('UPDATE attempts SET state=?,ended=? WHERE token=?',('interrupted',time.time(),token))
                self.conn.execute('UPDATE nodes SET state=? WHERE run_id=? AND id=? AND current_token=?',('interrupted',a['run_id'],a['node_id'],token))
            self.conn.execute('UPDATE attempts SET released=1 WHERE token=?',(token,))
            self.event(a['run_id'],'attempt.released',{'attempt':token,'external_id':external_id,'reason':reason,'host_confirmed':True,'usage':usage})

    def retry(self, run, node, *, reason):
        text(reason,'retry reason',2000)
        with self.tx():
            r,c=self.open_run(run); n=self.node(run,node); s=loads(n['spec'])
            if s['writes'] or s['role']=='writer': raise WorkflowError('automatic/manual runtime writer replay is not supported')
            if n['state'] not in {'failed','partial','interrupted','unknown'}: raise WorkflowError('node is not retryable')
            a=self.attempt(n['current_token'])
            if not a['released']: raise WorkflowError('termination must be confirmed before retry')
            if n['attempts']>=c['bounds']['max_attempts']: raise WorkflowError('attempt limit reached')
            self._assert_snapshot(r,n)
            self.conn.execute('UPDATE nodes SET state=?,result=NULL,current_token=NULL WHERE run_id=? AND id=?',('pending',run,node))
            self.event(run,'node.retry_requested',{'node':node,'previous_attempt':a['token'],'reason':reason})

    def resume(self, run, *, contract_hash, reason, extend_deadline_seconds=0):
        """Explicit trusted-controller resume; never infer termination or replay a writer."""
        text(reason, 'resume reason', 2000)
        integer(extend_deadline_seconds, 'deadline extension', 0, 86400)
        with self.tx():
            r = self.run(run); c = loads(r['contract'])
            if r['status'] != 'open' or contract_hash != r['contract_hash'] or sha(c) != contract_hash or c.get('version') not in SUPPORTED_CONTRACT_VERSIONS:
                raise WorkflowError('run state or current contract identity does not permit resume')
            if self.conn.execute('SELECT 1 FROM attempts WHERE run_id=? AND released=0', (run,)).fetchone():
                raise WorkflowError('all prior host activity must be reconciled before resume')
            if time.time() >= r['deadline'] and not extend_deadline_seconds:
                raise WorkflowError('expired deadline needs explicit controller extension')
            retry_nodes = []
            for row in self.conn.execute('SELECT * FROM nodes WHERE run_id=?', (run,)):
                n = dict(row); s = loads(n['spec'])
                if s['role'] == 'writer' and n['attempts']:
                    raise WorkflowError('mixed/write execution recovery is not implemented; inspect effects manually')
                self._assert_snapshot(r, n, n['state'] == 'completed')
                if n['state'] in {'failed','partial','interrupted','unknown'}:
                    if n['attempts'] >= c['bounds']['max_attempts']:
                        raise WorkflowError('retry attempt limit reached')
                    retry_nodes.append(n['id'])
            for node in retry_nodes:
                self.conn.execute('UPDATE nodes SET state=?,result=NULL,current_token=NULL WHERE run_id=? AND id=?', ('pending',run,node))
            if extend_deadline_seconds:
                self.conn.execute('UPDATE runs SET deadline=? WHERE id=?', (max(time.time(),r['deadline'])+extend_deadline_seconds,run))
            self.event(run,'run.resumed',{'nodes':retry_nodes,'reason':reason,'contract_hash':contract_hash,
                       'deadline_extension':extend_deadline_seconds,'budget_reset':False})
        return self.status(run)

    def _historical_write_evidence(self, r, n, nodes):
        """Recognize only explicit descendant writes as superseding historical bytes.

        This does NOT make an earlier analysis evidence about the new candidate.
        Final writer and reviewer gates still apply to the actual current bytes.
        """
        expected = loads(n['result'])['snapshot']
        current = fingerprint(Path(r['root']), list(expected), set(loads(n['spec'])['writes']))
        if current == expected:
            return []
        descendants = {n['id']}
        changed = True
        while changed:
            old = set(descendants)
            descendants |= {x['id'] for x in nodes if set(loads(x['spec'])['depends']) & descendants}
            changed = descendants != old
        writers = [x for x in nodes if x['id'] != n['id'] and x['id'] in descendants and x['state']=='completed' and loads(x['spec'])['role']=='writer']
        writers.sort(key=lambda x: self.attempt(x['current_token'])['ended'])
        historical = []
        for path, before in expected.items():
            if current[path] == before:
                continue
            chain = before
            for w in writers:
                ws = loads(w['spec']); wr = loads(w['result'])
                if path in ws['writes'] and wr['evidence_snapshot'].get(path) == chain:
                    chain = wr['snapshot'].get(path)
            if chain != current[path]:
                raise WorkflowError(f"candidate drift not explained by an authorized descendant writer: {n['id']}:{path}")
            historical.append(path)
        return historical

    def refresh(self, run, node, *, reason):
        """Explicitly rebind a NEVER EXECUTED pending task, e.g. post-writer review."""
        text(reason,'refresh reason',2000)
        with self.tx():
            r,_=self.open_run(run); n=self.node(run,node); s=loads(n['spec'])
            if n['state']!='pending' or n['attempts']!=0: raise WorkflowError('only never-executed pending nodes may refresh; create a successor otherwise')
            if s.get('supplemental'):
                raise WorkflowError('snapshot probes require a new node, not refresh')
            before=loads(n['snapshot'])
            deferred = {p for p,h in before.items() if h is None} if s['role'] != 'writer' else set()
            if deferred:
                target=self.node(run,s['verifies']); target_spec=loads(target['spec'])
                if target_spec['role'] != 'writer' or target['state'] != 'completed' or not self._execution_reconciled(self.attempt(target['current_token'])):
                    raise WorkflowError('deferred review refresh requires a completed reconciled writer')
                self._assert_snapshot(r,target,True)
            after=fingerprint(Path(r['root']),list(before),set(s['writes']))
            if deferred:
                created=loads(target['result'])['snapshot']
                if any(p not in target_spec['writes'] or created.get(p) is None or after[p] != created[p] for p in deferred):
                    raise WorkflowError('deferred review source was not created by its verified writer')
            self.conn.execute('UPDATE nodes SET snapshot=? WHERE run_id=? AND id=?',(dump(after),run,node))
            self.event(run,'node.source_rebound',{'node':node,'before':before,'after':after,'reason':reason})

    def cancel(self, run, *, reason):
        text(reason,'cancellation reason',2000)
        with self.tx():
            r=self.run(run)
            if r['status'] in {'completed','cancelled'}: raise WorkflowError('run already closed')
            self.conn.execute('UPDATE runs SET status=? WHERE id=?',('cancelled',run))
            self.conn.execute("UPDATE nodes SET state='cancelled' WHERE run_id=? AND state='pending'",(run,))
            self.event(run,'run.cancelled',{'reason':reason,'active_termination':'host must confirm release'})

    def decide(self, claim_id, disposition, *, reason):
        if disposition not in {'ADOPT','REJECT','UNKNOWN','contested'}: raise WorkflowError('invalid disposition')
        text(reason,'decision reason',2000)
        with self.tx():
            row=self.conn.execute('SELECT * FROM claims WHERE id=?',(claim_id,)).fetchone()
            if row is None: raise WorkflowError('unknown claim')
            r,_=self.open_run(row['run_id']); n=self.node(row['run_id'],row['node_id'])
            if loads(n['spec']).get('supplemental'):
                raise WorkflowError('supplemental findings require Root triage, not direct adoption')
            if disposition in {'ADOPT','REJECT'}:
                if row['attempt'] != n['current_token']:
                    raise WorkflowError('historical attempt claim cannot inherit current acceptance')
                if n['state']!='completed' or not loads(row['data'])['evidence_valid']: raise WorkflowError('unverified evidence cannot be adopted')
                self._assert_snapshot(r,n,True)
                self._quality_gate(r,n)
            self.conn.execute('UPDATE claims SET disposition=?,revision=revision+1 WHERE id=?',(disposition,claim_id))
            self.event(row['run_id'],'claim.decided',{'claim':claim_id,'disposition':disposition,'reason':reason,'revision':row['revision']+1})

    def _quality_gate(self,r,n,*,allow_historical=False):
        s=loads(n['spec'])
        if s['tier'] == 'ordinary' and s['verifies'] is not None:
            target_node = self.node(r['id'], s['verifies'])
            target = loads(target_node['result'])['snapshot']
            snap = loads(n['snapshot'])
            if (self.attempt(n['current_token'])['external_id'] == self.attempt(target_node['current_token'])['external_id']
                    or not all(p in snap and snap[p] == h for p,h in target.items())):
                raise WorkflowError(f"independent current-candidate verification missing: {n['id']}")
        if s['verifies'] is not None or (s['risk']!='high' and not s['writes']): return
        target=loads(n['result'])['snapshot']
        for other in self.conn.execute("SELECT * FROM nodes WHERE run_id=? AND state='completed' AND id<>?",(r['id'],n['id'])):
            o=loads(other['spec'])
            if (o['verifies']==n['id'] and o['tier']=='strong' and o['role'] in {'verifier','reviewer'}
                    and (loads(r['contract']).get('workflow') != 'astra-mainline' or o['required'])):
                author = self.attempt(n['current_token'])
                checker = self.attempt(other['current_token'])
                if author['external_id'] == checker['external_id']:
                    continue  # A renamed node on the same host agent is not a non-author.
                snap=loads(other['snapshot'])
                if all(p in snap and snap[p]==h for p,h in target.items()):
                    if allow_historical:
                        nodes=[dict(x) for x in self.conn.execute('SELECT * FROM nodes WHERE run_id=?',(r['id'],))]
                        self._historical_write_evidence(r,dict(other),nodes)
                    else:
                        self._assert_snapshot(r,dict(other),True)
                    return
        raise WorkflowError(f"independent current-candidate verification missing: {n['id']}")

    def _latest_events(self, run, kind, key='claim'):
        latest = {}
        for row in self.conn.execute('SELECT seq,data FROM events WHERE run_id=? AND kind=? ORDER BY seq', (run,kind)):
            data = loads(row['data']); latest[data[key]] = {**data, '_seq':row['seq']}
        return latest

    def _require_followup(self, r):
        c = loads(r['contract'])
        if r['status'] != 'open' or not followup_contract(c) or sha(c) != r['contract_hash']:
            raise WorkflowError('operation requires an open v4.1 supplemental contract')
        return c

    def triage(self, claim_id, disposition, *, reason, target=None, duplicate_of=None):
        """Root screening; a child cannot classify its own delivery risk."""
        with self.tx():
            return self._triage_one(claim_id, disposition, reason=reason, target=target, duplicate_of=duplicate_of)

    def screen(self, run, decisions):
        """Atomically screen a bounded batch; semantic judgments remain Root's duty."""
        if not isinstance(decisions, list) or not 1 <= len(decisions) <= 64:
            raise WorkflowError('screen requires 1..64 decisions')
        with self.tx():
            self._require_followup(self.run(run)); seen = set(); result = []
            for d in decisions:
                mapping(d, {'claim','disposition','reason','target','duplicate_of'}, {'claim','disposition','reason'}, 'screen decision')
                text(d['claim'], 'claim id', 256)
                row = self.conn.execute('SELECT run_id FROM claims WHERE id=?', (d['claim'],)).fetchone()
                if row is None or row['run_id'] != run or d['claim'] in seen:
                    raise WorkflowError('screen claim must be unique and belong to this run')
                seen.add(d['claim'])
                result.append(self._triage_one(d['claim'], d['disposition'], reason=d['reason'],
                              target=d.get('target'), duplicate_of=d.get('duplicate_of')))
            return result

    def _triage_one(self, claim_id, disposition, *, reason, target=None, duplicate_of=None):
        text(disposition, 'triage disposition', 30); text(reason, 'triage reason', 2000)
        row = self.conn.execute('SELECT * FROM claims WHERE id=?', (claim_id,)).fetchone()
        if row is None: raise WorkflowError('unknown claim')
        r = self.run(row['run_id']); c = loads(r['contract']); newer = followup_contract(c)
        if r['status'] != 'open' or c.get('workflow') != 'astra-mainline' or sha(c) != r['contract_hash']:
            raise WorkflowError('triage requires an open Astra mainline contract')
        allowed = {'dismissed', 'advisory', 'promoted'} | ({'duplicate'} if newer else set())
        if disposition not in allowed: raise WorkflowError('invalid supplemental triage disposition')
        if not loads(self.node(r['id'], row['node_id'])['spec']).get('supplemental'):
            raise WorkflowError('triage is only for supplemental claims')
        paths = loads(row['data'])['claim']['evidence']
        candidate = fingerprint(Path(r['root']), paths, set(paths))
        decisions = self._latest_events(r['id'], 'supplemental.triaged') if newer else {}
        previous = decisions.get(claim_id)
        if previous and previous['disposition'] == 'promoted' and disposition != 'promoted':
            raise WorkflowError('promoted findings require explicit resolution, not demotion')
        if disposition == 'promoted':
            identifier(target, 'promotion target')
            t = self.node(r['id'], target); ts = loads(t['spec'])
            if ts.get('supplemental') or not ts['required'] or ts['tier'] != 'strong' or t['attempts']:
                raise WorkflowError('promotion needs a never-executed required Astra mainline node')
            if not set(paths) <= set(ts['sources']):
                raise WorkflowError('promotion target must cover the claim evidence')
            if any(loads(t['snapshot']).get(p) != h for p,h in candidate.items()):
                raise WorkflowError('promotion target is not bound to the current candidate')
        elif target is not None:
            raise WorkflowError('only promoted findings have a target')
        if disposition == 'duplicate':
            text(duplicate_of, 'canonical claim id', 256)
            canonical = self.conn.execute('SELECT * FROM claims WHERE id=?', (duplicate_of,)).fetchone()
            if (canonical is None or canonical['run_id'] != r['id']
                    or not loads(self.node(r['id'],canonical['node_id'])['spec']).get('supplemental')
                    or not set(paths) <= set(loads(canonical['data'])['claim']['evidence'])):
                raise WorkflowError('duplicate must reference a same-run supplemental claim covering its evidence')
            visited = {claim_id}; current = duplicate_of
            while current is not None:
                if len(visited) > 64: raise WorkflowError('duplicate chain too deep')
                if current in visited: raise WorkflowError('duplicate claim cycle')
                visited.add(current); d = decisions.get(current, {})
                current = d.get('duplicate_of') if d.get('disposition') == 'duplicate' else None
        elif duplicate_of is not None:
            raise WorkflowError('only duplicate screening accepts duplicate_of')
        data = {'claim':claim_id, 'disposition':disposition, 'target':target, 'candidate':candidate, 'reason':reason}
        if disposition == 'duplicate': data['duplicate_of'] = duplicate_of
        self.event(r['id'], 'supplemental.triaged', data)
        return {'claim':claim_id, 'disposition':disposition, 'target':target}

    def resolve(self, claim_id, outcome, *, reason, node=None):
        """Resolve a promoted issue, not merely its investigation task."""
        text(outcome, 'resolution outcome', 30); text(reason, 'resolution reason', 2000)
        if outcome not in {'reported','disproved','fixed','blocking'}:
            raise WorkflowError('invalid issue resolution')
        with self.tx():
            row = self.conn.execute('SELECT * FROM claims WHERE id=?', (claim_id,)).fetchone()
            if row is None: raise WorkflowError('unknown claim')
            r = self.run(row['run_id']); c = self._require_followup(r)
            promotion = self._latest_events(r['id'], 'supplemental.triaged').get(claim_id)
            if not promotion or promotion['disposition'] != 'promoted':
                raise WorkflowError('resolution requires a promoted finding')
            if outcome == 'reported' and c['acceptance_mode'] != 'review':
                raise WorkflowError('reported is not a repair acceptance outcome')
            paths = loads(row['data'])['claim']['evidence']
            if outcome != 'blocking':
                target = self.node(r['id'], promotion['target'])
                if target['state'] != 'completed': raise WorkflowError('promoted investigation is incomplete')
                node = node or promotion['target']; n = self.node(r['id'], node); spec = loads(n['spec'])
                if (n['state'] != 'completed' or spec.get('supplemental') or not spec['required']
                        or spec['tier'] != 'strong' or not set(paths) <= set(spec['sources'])):
                    raise WorkflowError('resolution requires completed required Astra evidence covering the finding')
                # Resolution must answer this investigation, not borrow unrelated old work.
                ancestors = set(); pending = [node]
                while pending:
                    current = pending.pop()
                    if current in ancestors: continue
                    ancestors.add(current)
                    pending.extend(loads(self.node(r['id'],current)['spec'])['depends'])
                if promotion['target'] not in ancestors:
                    raise WorkflowError('resolution must follow the promoted investigation')
                self._assert_snapshot(r,n,True); self._quality_gate(r,n)
                if not self._execution_reconciled(self.attempt(n['current_token'])):
                    raise WorkflowError('resolution evidence execution is not reconciled')
                if outcome == 'fixed':
                    if spec['verifies'] is None: raise WorkflowError('fixed requires independent writer verification')
                    writer = self.node(r['id'], spec['verifies']); ws = loads(writer['spec'])
                    if (ws['role'] != 'writer' or writer['state'] != 'completed'
                            or not loads(writer['result'])['submission']['payload']['changed_files']):
                        raise WorkflowError('fixed requires an observed implementation change')
                    if self.attempt(n['current_token'])['external_id'] == self.attempt(writer['current_token'])['external_id']:
                        raise WorkflowError('fixed requires a non-author resolution verifier')
                    if not set(loads(writer['result'])['snapshot']) <= set(loads(n['snapshot'])):
                        raise WorkflowError('resolution verifier must cover the writer candidate')
                    self._quality_gate(r,writer)
                # The whole resolution evidence set, not only finder-selected files, is bound.
                paths = sorted(set(paths) | set(spec['sources']) | set(spec['writes']))
            elif node is not None:
                raise WorkflowError('blocking resolution does not claim a completed evidence node')
            data = {'claim':claim_id, 'outcome':outcome, 'reason':reason, 'node':node,
                    'promotion_seq':promotion['_seq'], 'candidate':fingerprint(Path(r['root']), paths, set(paths))}
            self.event(r['id'], 'supplemental.resolved', data)
            return data

    def _followup_claim_gaps(self, r, nodes):
        decisions = self._latest_events(r['id'], 'supplemental.triaged')
        resolutions = self._latest_events(r['id'], 'supplemental.resolved')
        by_id = {n['id']:n for n in nodes}
        claims = {row['id']:row for row in self.conn.execute('SELECT * FROM claims WHERE run_id=?',(r['id'],))
                  if loads(by_id[row['node_id']]['spec']).get('supplemental')}
        memo = {}; source_cache = {}
        def current_binding(binding):
            for path in binding:
                if path not in source_cache:
                    source_cache[path] = fingerprint(Path(r['root']),[path],{path})[path]
            return {path:source_cache[path] for path in binding}
        def inspect(cid, visiting):
            if cid in memo: return memo[cid]
            if len(visiting) > 64: return 'duplicate-chain-too-deep'
            if cid in visiting: return 'duplicate-cycle'
            d = decisions.get(cid)
            if cid not in claims or d is None: return 'untriaged'
            if d['disposition'] == 'promoted':
                n = by_id.get(d['target']); resolution = resolutions.get(cid)
                if n is None or n['state'] != 'completed': return 'promoted-mainline-incomplete'
                if not resolution or resolution['promotion_seq'] != d['_seq']: return 'issue-resolution-missing'
                if resolution['outcome'] == 'blocking': return 'issue-still-blocking'
                binding = resolution['candidate']
            else:
                binding = d['candidate']
            try:
                if current_binding(binding) != binding:
                    return 'resolution candidate changed' if d['disposition']=='promoted' else 'triage candidate changed'
            except (OSError, WorkflowError) as exc: return str(exc)
            error = inspect(d['duplicate_of'], visiting | {cid}) if d['disposition']=='duplicate' else None
            memo[cid] = error
            return error
        return [{'claim':cid,'reason':error} for cid in claims if (error := inspect(cid,set())) is not None]

    def report_findings(self, token, report, *, external_id, backend):
        """Retain early host-delivered evidence even if the probe is later interrupted."""
        fields = {'report_id','sources_opened','claims'}
        mapping(report, fields, fields, 'incremental report'); identifier(report['report_id'], 'report id')
        with self.tx():
            a = self.attempt(token); r = self.run(a['run_id']); self._require_followup(r)
            n = self.node(r['id'],a['node_id']); spec = loads(n['spec'])
            if backend != r['backend'] or not external_id or external_id != a['external_id']:
                raise WorkflowError('incremental report identity mismatch')
            previous = self._latest_events(r['id'],'supplemental.reported',key='report_key').get(token+'-'+report['report_id'])
            if previous:
                if previous['report'] != report: raise WorkflowError('conflicting incremental report')
                return {'claims':previous['claims'], 'idempotent':True}
            if (not spec.get('supplemental') or n['current_token'] != token or a['released']
                    or a['state'] != 'running'):
                raise WorkflowError('incremental findings require an active bound supplemental turn')
            opened = path_list(report['sources_opened'],'sources_opened')
            if not set(opened) <= set(spec['sources']): raise WorkflowError('report exceeds source scope')
            claims = [{**claim,'evidence':path_list(claim['evidence'],'claim evidence')}
                      for claim in validate_claims(report['claims'], opened)]
            count = self.conn.execute('SELECT COUNT(*) FROM claims WHERE attempt=?',(token,)).fetchone()[0]
            if not claims or count + len(claims) > 128: raise WorkflowError('incremental claim limit reached')
            before = loads(n['snapshot']); current = fingerprint(Path(spec['snapshot_root']),list(before))
            ids = []
            for i,claim in enumerate(claims):
                cid = f"{token}-report-{report['report_id']}-{i}"; ids.append(cid)
                self.conn.execute('INSERT INTO claims(id,run_id,node_id,attempt,data) VALUES(?,?,?,?,?)',
                    (cid,r['id'],n['id'],token,dump({'claim':claim,'snapshot':before,'evidence_valid':current==before})))
            self.event(r['id'],'supplemental.reported',{'report_key':token+'-'+report['report_id'],
                       'attempt':token, 'report':report, 'claims':ids})
            return {'claims':ids, 'idempotent':False}

    def _candidate(self, r, nodes):
        paths = sorted({p for n in nodes if not loads(n['spec']).get('supplemental')
                        for p in loads(n['spec'])['sources'] + loads(n['spec'])['writes']})
        return fingerprint(Path(r['root']), paths, set(paths))

    def _supplemental_cutoff(self, r):
        row = self.conn.execute("SELECT seq FROM events WHERE run_id=? AND kind='mainline.accepted' ORDER BY seq DESC LIMIT 1",(r['id'],)).fetchone()
        if row is None: return False
        if not followup_contract(loads(r['contract'])): return True
        reopened = self.conn.execute("SELECT seq FROM events WHERE run_id=? AND kind='supplemental.reopened' ORDER BY seq DESC LIMIT 1",(r['id'],)).fetchone()
        return reopened is None or reopened['seq'] < row['seq']

    def reopen_supplemental(self, run, changed_paths, *, reason):
        """Open a new candidate epoch; never reset launch counts or revive omitted nodes."""
        text(reason,'candidate change reason',2000); changed_paths = path_list(changed_paths,'changed paths')
        with self.tx():
            r,c = self.open_run(run); self._require_followup(r)
            last = self.conn.execute("SELECT data FROM events WHERE run_id=? AND kind='mainline.accepted' ORDER BY seq DESC LIMIT 1",(run,)).fetchone()
            if last is None or not self._supplemental_cutoff(r):
                raise WorkflowError('reopening requires a closed supplemental admission epoch')
            nodes = [dict(n) for n in self.conn.execute('SELECT * FROM nodes WHERE run_id=?',(run,))]
            if any(loads(n['spec'])['role']=='writer' and n['current_token']
                   and not self._execution_reconciled(self.attempt(n['current_token'])) for n in nodes):
                raise WorkflowError('settle candidate writers before reopening supplemental work')
            current = self._candidate(r,nodes); previous = loads(last['data'])['candidate']
            if not set(changed_paths) <= set(current) or not any(previous.get(p) != current[p] for p in changed_paths):
                raise WorkflowError('reopening needs changed bound candidate bytes, not a renamed task')
            self.event(run,'supplemental.reopened',{'candidate':current,'changed_paths':changed_paths,
                       'reason':reason,'budget_reset':False})
            return {'supplemental_admission_closed':False,'budget_reset':False}

    def closeout(self, run, entries):
        """Record actual host handoff/stop observations. This method starts no background work."""
        if not isinstance(entries,list) or not 1 <= len(entries) <= 64:
            raise WorkflowError('closeout requires 1..64 entries')
        with self.tx():
            r = self.run(run); self._require_followup(r); seen = set()
            for entry in entries:
                mapping(entry, {'attempt','action','reason','observed_via','receiver','until'},
                        {'attempt','action','reason','observed_via'}, 'closeout entry')
                text(entry['attempt'],'attempt token',256)
                if entry['attempt'] in seen: raise WorkflowError('duplicate closeout attempt')
                seen.add(entry['attempt']); a = self.attempt(entry['attempt'])
                if (a['run_id'] != run or not loads(self.node(run,a['node_id'])['spec']).get('supplemental')
                        or self._execution_reconciled(a)):
                    raise WorkflowError('closeout requires unreconciled task-owned supplemental execution')
                text(entry['action'],'closeout action',30); text(entry['reason'],'closeout reason',2000)
                text(entry['observed_via'],'host observation source',200)
                if entry['action'] == 'continue':
                    text(entry.get('receiver'),'actual result receiver',256)
                    until = entry.get('until')
                    if type(until) not in (int,float) or not math.isfinite(until) or not time.time() < until <= time.time()+300:
                        raise WorkflowError('continuation requires a bounded future cutoff within 300 seconds')
                elif entry['action'] not in {'stop-requested','unknown'}:
                    raise WorkflowError('invalid closeout action')
                elif 'receiver' in entry or 'until' in entry:
                    raise WorkflowError('only a real continuation may name a receiver and cutoff')
                self.event(run,'supplemental.closeout',entry)
        return {'recorded':len(entries),'host_resources_released':False}

    def _closeout_status(self, r, nodes, attempts):
        plans = self._latest_events(r['id'],'supplemental.closeout',key='attempt')
        ids = {n['id'] for n in nodes if loads(n['spec']).get('supplemental')}
        result = []
        for a in attempts:
            if a['node_id'] not in ids or self._execution_reconciled(a): continue
            plan = plans.get(a['token']); state = 'needs-host-closeout'
            if plan:
                state = plan['action']
                if state=='continue' and time.time() >= plan['until']: state='continuation-expired'
            result.append({'attempt':a['token'],'state':state,'plan':plan})
        return result

    def _supplemental_claim_gaps(self, r, nodes):
        if followup_contract(loads(r['contract'])):
            return self._followup_claim_gaps(r, nodes)
        by_id = {n['id']:n for n in nodes}; decisions = {}
        for row in self.conn.execute("SELECT data FROM events WHERE run_id=? AND kind='supplemental.triaged' ORDER BY seq", (r['id'],)):
            d = loads(row['data']); decisions[d['claim']] = d
        gaps = []
        for row in self.conn.execute('SELECT * FROM claims WHERE run_id=?', (r['id'],)):
            if not loads(by_id[row['node_id']]['spec']).get('supplemental'): continue
            d = decisions.get(row['id'])
            if d is None:
                gaps.append({'claim':row['id'],'reason':'untriaged'}); continue
            if d['disposition'] == 'promoted':
                target = by_id.get(d['target'])
                if target is None or target['state'] != 'completed':
                    gaps.append({'claim':row['id'],'reason':'promoted-mainline-incomplete'})
            else:
                try:
                    now = fingerprint(Path(r['root']), list(d['candidate']), set(d['candidate']))
                    if now != d['candidate']: raise WorkflowError('triage candidate changed')
                except (WorkflowError, OSError) as exc:
                    gaps.append({'claim':row['id'],'reason':str(exc)})
        return gaps

    def _mainline_gate(self, r, nodes, attempts):
        mainline = [n for n in nodes if not loads(n['spec']).get('supplemental')]
        if not mainline: raise WorkflowError('supplemental-only or empty graph is not completed mainline work')
        ids = {n['id'] for n in mainline}; historical = {}
        if any(a['node_id'] in ids and not self._execution_reconciled(a) for a in attempts):
            raise WorkflowError('live/unreconciled mainline execution attempts remain')
        for n in mainline:
            if n['state'] != 'completed': raise WorkflowError(f"incomplete scope (mainline): {n['id']} ({n['state']})")
            paths = self._historical_write_evidence(r, n, mainline)
            if paths: historical[n['id']] = paths
            self._quality_gate(r, n, allow_historical=True)
        if self._supplemental_claim_gaps(r, nodes):
            raise WorkflowError('supplemental evidence requires current Root triage or completed promotion')
        return historical

    def _mainline_key(self, run, nodes):
        mainline = [{k:n[k] for k in ('id','spec','state','snapshot','current_token','result')}
                    for n in nodes if not loads(n['spec']).get('supplemental')]
        claims = [dict(c) for c in self.conn.execute('SELECT * FROM claims WHERE run_id=? ORDER BY id', (run,))]
        triage = [e['data'] for e in self.conn.execute("SELECT data FROM events WHERE run_id=? AND kind='supplemental.triaged' ORDER BY seq", (run,))]
        if followup_contract(loads(self.run(run)['contract'])):
            promotions = [d for d in self._latest_events(run, 'supplemental.triaged').values()
                          if d['disposition'] == 'promoted']
            return sha({'mainline':mainline, 'promotions':promotions})
        return sha({'mainline':mainline, 'claims':claims, 'triage':triage})

    def omit(self, run, node, *, reason):
        text(reason, 'omission reason', 2000)
        with self.tx():
            r,c = self.open_run(run); n = self.node(run,node)
            if c.get('workflow') != 'astra-mainline' or not loads(n['spec']).get('supplemental'):
                raise WorkflowError('only supplemental nodes may be omitted')
            if n['state'] != 'pending': raise WorkflowError('omit only pending work; interrupt active work via the host')
            self.conn.execute("UPDATE nodes SET state='omitted' WHERE run_id=? AND id=?", (run,node))
            self.event(run,'supplemental.omitted',{'node':node,'reason':reason})

    def _finish_mainline(self, run):
        with self.tx():
            r = self.run(run); c = loads(r['contract'])
            if r['status'] != 'open' or c.get('version') not in {'4.0.0', '4.1.0'} or sha(c) != r['contract_hash']:
                raise WorkflowError('run/contract does not permit mainline acceptance')
            nodes = [dict(n) for n in self.conn.execute('SELECT * FROM nodes WHERE run_id=? ORDER BY rowid',(run,))]
            attempts = [dict(a) for a in self.conn.execute('SELECT * FROM attempts WHERE run_id=?',(run,))]
            historical = self._mainline_gate(r, nodes, attempts)
            for n in nodes:
                if loads(n['spec']).get('supplemental') and n['state'] == 'pending':
                    self.conn.execute("UPDATE nodes SET state='omitted' WHERE run_id=? AND id=?", (run,n['id']))
                    self.event(run,'supplemental.omitted',{'node':n['id'],'reason':'mainline acceptance cutoff'})
            key = self._mainline_key(run,nodes)
            self.event(run,'mainline.accepted',{'key':key,'scope':'Astra mainline; received findings triaged',
                                              'historical_write_evidence':historical,
                                              **({'candidate':self._candidate(r, nodes)} if followup_contract(c) else {})})
            # Return acceptance now; do not claim a running native turn has ended.
            if all(self._execution_reconciled(a) for a in attempts):
                self.conn.execute("UPDATE runs SET status='completed' WHERE id=?", (run,))
                self.event(run,'run.completed',{'mainline_accepted':True,'supplemental_coverage':'reported separately'})
        return self.status(run)

    def _supplemental_status(self, r, nodes, attempts):
        probes = [n for n in nodes if loads(n['spec']).get('supplemental')]
        mainline = [n for n in nodes if not loads(n['spec']).get('supplemental')]
        gaps = self._supplemental_claim_gaps(r,nodes)
        gate_error = None
        try: self._mainline_gate(r,nodes,attempts)
        except (WorkflowError,OSError) as exc: gate_error = str(exc)
        last = self.conn.execute("SELECT data FROM events WHERE run_id=? AND kind='mainline.accepted' ORDER BY seq DESC LIMIT 1",(r['id'],)).fetchone()
        accepted = bool(last and not gate_error and r['status'] != 'cancelled'
                        and loads(last['data'])['key'] == self._mainline_key(r['id'],nodes))
        return {'mainline_complete':bool(mainline) and all(n['state']=='completed' for n in mainline),
                'mainline_accepted':accepted,'mainline_gate_error':gate_error,
                'supplemental_admission_closed':self._supplemental_cutoff(r),
                **({'acceptance_state':('accepted' if accepted else 'pending-screen' if last and gaps
                     and all(g['reason']=='untriaged' for g in gaps) else 'not-accepted'),
                    'closeout':self._closeout_status(r, nodes, attempts)} if followup_contract(loads(r['contract'])) else {}),
                'supplemental_claim_gaps':gaps,
                'supplemental_coverage':{'declared':len(probes),
                    'launched':sum(n['attempts']>0 for n in probes),
                    'attempts':sum(n['attempts'] for n in probes),
                    'completed':sum(n['state']=='completed' for n in probes),
                    'omitted':sum(n['state']=='omitted' for n in probes),
                    'unfinished':sum(n['state']!='completed' for n in probes),
                    'states':{n['id']:n['state'] for n in probes}},
                'supplemental_execution_holds':sum(not self._execution_reconciled(a) for a in attempts
                     if a['node_id'] in {n['id'] for n in probes})}

    def finish(self,run):
        if loads(self.run(run)['contract']).get('workflow') == 'astra-mainline':
            return self._finish_mainline(run)
        with self.tx():
            r,_=self.open_run(run)
            nodes=[dict(n) for n in self.conn.execute('SELECT * FROM nodes WHERE run_id=?',(run,))]
            if not nodes: raise WorkflowError('empty graph is not completed work')
            if not any(not loads(n['spec']).get('supplemental', False) for n in nodes):
                raise WorkflowError('supplemental-only graph is not completed mainline work')
            attempts=self.conn.execute('SELECT * FROM attempts WHERE run_id=?',(run,)).fetchall()
            if any(not self._execution_reconciled(a) for a in attempts): raise WorkflowError('live/unreconciled execution attempts remain')
            historical = {}
            for n in nodes:
                if n['state']=='completed':
                    paths = self._historical_write_evidence(r,n,nodes)
                    if paths: historical[n['id']] = paths
                    self._quality_gate(r,n,allow_historical=True)
                elif not loads(n['spec']).get('supplemental', False):
                    raise WorkflowError(f"incomplete scope (mainline): {n['id']} ({n['state']})")
            self.conn.execute('UPDATE runs SET status=? WHERE id=?',('completed',run))
            self.event(run,'run.completed',{'nodes':len(nodes),'scope':'declared graph only','historical_write_evidence':historical})
        return self.status(run)

    def status(self,run):
        r=self.run(run)
        nodes=[dict(n) for n in self.conn.execute('SELECT * FROM nodes WHERE run_id=? ORDER BY rowid',(run,))]
        issues=[]; historical={}
        for n in nodes:
            if n['state']=='completed' and not loads(n['spec']).get('supplemental'):
                try:
                    superseded = self._historical_write_evidence(r,n,nodes)
                    if superseded: historical[n['id']] = superseded
                except (OSError,WorkflowError) as exc: issues.append(str(exc))
        attempts=[dict(a) for a in self.conn.execute('SELECT * FROM attempts WHERE run_id=? ORDER BY created',(run,))]
        execution={a['token']:self._execution_reconciled(a) for a in attempts}
        host_holds=sum(not a['released'] for a in attempts)
        incomplete=[{'id':n['id'],'state':n['state'],'required':loads(n['spec'])['required'],**({'supplemental': True} if loads(n['spec']).get('supplemental') else {})}
                    for n in nodes if n['state']!='completed']
        mainline_incomplete=[n for n in incomplete if not n.get('supplemental')]
        mainline_nodes=[n for n in nodes if not loads(n['spec']).get('supplemental',False)]
        supplemental=[n for n in nodes if loads(n['spec']).get('supplemental',False)]
        return {'run_id':run,'backend':r['backend'],'status':r['status'],
                'current_evidence_valid':any(n['state']=='completed' for n in mainline_nodes) and not issues,
                'scope_complete':bool(nodes) and not incomplete,'mainline_complete':bool(mainline_nodes) and not mainline_incomplete,
                'supplemental_coverage':{'declared':len(supplemental),'completed':sum(n['state']=='completed' for n in supplemental),'unfinished':sum(n['state']!='completed' for n in supplemental)},
                'incomplete_nodes':incomplete,
                **(self._supplemental_status(r,nodes,attempts) if loads(r['contract']).get('workflow')=='astra-mainline' else {}),
                'drift':issues,'historical_evidence':historical,
                'contract_hash':r['contract_hash'],'deadline':r['deadline'],
                'budget':{'used':r['used'],'reserve_used':r['reserve_used'],'strong_used':r['strong_used'],
                          'active_holds':host_holds,'host_resource_holds':host_holds,
                          'execution_holds':sum(not execution[a['token']] for a in attempts),
                          'unknown_usage_attempts':sum(a['usage'] is None for a in attempts)},
                'host_resources_released':host_holds==0,
                'host_resource_state':'RELEASE_CONFIRMED' if host_holds==0 else 'UNKNOWN',
                'nodes':[{'id':n['id'],'state':n['state'],'attempts':n['attempts'],'required':loads(n['spec'])['required'],**({'supplemental': True} if loads(n['spec']).get('supplemental') else {})} for n in nodes],
                'attempts':[{'attempt':a['token'],'node':a['node_id'],'state':a['state'],'external_id':a['external_id'],'released':bool(a['released']),
                             'execution_reconciled':execution[a['token']],
                             'usage':loads(a['usage']) if a['usage'] is not None else None} for a in attempts]}

    def events(self,run,after=0):
        self.run(run); integer(after,'after',0,10**12)
        return [{'seq':e['seq'],'at':e['at'],'kind':e['kind'],'data':loads(e['data'])}
                for e in self.conn.execute('SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq',(run,after))]
