"""Standard-library package validation. Does not prove model behavior or safety."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path('skill/codex-dynamic-workflow')
LEGACY_SKILL = Path('skill/dispatching-native-agents')
PROFILE_NAMES = ('cwf_reader', 'cwf_writer', 'cwf_sol_writer', 'cwf_general', 'cwf_mechanical')


def unique_pairs(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def load_json_object(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_pairs)
    if not isinstance(data, dict):
        raise ValueError('JSON root must be an object')
    return data


def parse_package_mapping(text: str) -> dict:
    """Parse ONLY this package's closed YAML subset, not arbitrary YAML.

    Two mapping levels, two-space indent, unique identifier keys, JSON-quoted
    single-line strings, booleans, and plain slugs ONLY for name. Full-line comments
    are allowed. Lists, anchors, merges, tags, block scalars and tabs are rejected.
    """
    result = {}; group = None
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if '\t' in line:
            raise ValueError(f'tabs are unsupported at line {lineno}')
        indent = len(line) - len(line.lstrip(' '))
        if indent not in (0, 2):
            raise ValueError(f'unsupported indentation at line {lineno}')
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_-]*):( .+)? *', line[indent:])
        if match is None:
            raise ValueError(f'unsupported mapping syntax at line {lineno}')
        key = match.group(1); raw = (match.group(2) or '').strip()
        target = result if indent == 0 else group
        if target is None:
            raise ValueError(f'orphan nested key at line {lineno}')
        if key in target:
            raise ValueError(f'duplicate metadata key: {key}')
        if not raw:
            if indent != 0:
                raise ValueError('only two mapping levels are supported')
            target[key] = {}; group = target[key]
            continue
        if raw.startswith('"'):
            value = json.loads(raw)
            if not isinstance(value,str) or any(ord(c)<32 for c in value):
                raise ValueError(f'expected single-line string: {key}')
        elif raw in ('true','false'):
            value = raw == 'true'
        elif key == 'name' and re.fullmatch(r'[a-z][a-z0-9-]*',raw):
            value = raw
        else:
            raise ValueError(f'unsupported scalar: {key}')
        target[key] = value
        if indent == 0:
            group = None
    return result


def require_keys(value: object, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f'{label} has missing or unexpected keys; expected {sorted(keys)}')


def check_frontmatter(text: str, name: str, version: str) -> None:
    lines = text.splitlines()
    if not lines or lines[0] != '---' or '---' not in lines[1:]:
        raise ValueError('invalid skill frontmatter delimiters')
    end = lines.index('---',1)
    front = parse_package_mapping('\n'.join(lines[1:end]))
    require_keys(front, {'name','description','metadata'}, 'frontmatter')
    if front['name'] != name:
        raise ValueError('skill name mismatch')
    description = front['description']
    if not isinstance(description,str) or not 1 <= len(description.strip()) <= 1024:
        raise ValueError('description must be a nonempty string, max 1024 characters')
    require_keys(front['metadata'], {'version'}, 'metadata')
    if front['metadata']['version'] != version:
        raise ValueError('skill version drift')


def check_interface(text: str, display: str, implicit: bool) -> None:
    meta = parse_package_mapping(text)
    require_keys(meta, {'interface','policy'}, 'openai.yaml')
    require_keys(meta['interface'], {'display_name','short_description','default_prompt'}, 'interface')
    require_keys(meta['policy'], {'allow_implicit_invocation'}, 'invocation policy')
    if meta['policy']['allow_implicit_invocation'] is not implicit:
        raise ValueError('incorrect implicit invocation policy')
    interface = meta['interface']
    if any(not isinstance(v,str) or not v.strip() for v in interface.values()):
        raise ValueError('interface fields must be nonempty strings')
    if interface['display_name'] != display:
        raise ValueError('display name drift')
    if not re.search(r'\$codex-dynamic-workflow(?![A-Za-z0-9_-])', interface['default_prompt']):
        raise ValueError('default_prompt must reference the exact canonical invocation')


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        policy = load_json_object(root / SKILL / 'policy.json')
        main = (root / SKILL / 'SKILL.md').read_text(encoding='utf-8')
    except (OSError, ValueError) as exc:
        return [f'missing or invalid required input: {exc}']
    version = policy.get('skill_version')
    if not isinstance(version,str) or re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) is None:
        errors.append('invalid package skill_version')
        version = 'INVALID'
    try:
        check_frontmatter(main, 'codex-dynamic-workflow', version)
    except ValueError as exc:
        errors.append(f'canonical frontmatter error: {exc}')
    if len(main.splitlines()) > 250:
        errors.append('core skill exceeds the package 250-line maintenance budget')
    if policy.get('schema_version') != 2 or policy.get('backend') != 'native-only':
        errors.append('unsupported policy schema/backend')
    if policy.get('luna_readonly_backend') != 'native':
        errors.append('Luna readonly work must use native agent tools')
    if policy.get('skill_name') != 'codex-dynamic-workflow' or policy.get('legacy_alias') != 'dispatching-native-agents':
        errors.append('skill identity/legacy alias drift')
    if policy.get('priority') != ['quality', 'automation', 'latency', 'cost', 'observability', 'recovery']:
        errors.append('priority contract changed')
    for k in ('child_spawn', 'peer_messaging', 'overlapping_writers'):
        if policy.get(k) is not False:
            errors.append(f'{k} must stay false')
    budget = policy.get('budget', {})
    if not isinstance(budget, dict):
        errors.append('budget must be an object'); budget = {}
    capacity = budget.get('max_concurrent_children')
    if 'max_concurrent_children' not in budget or (capacity is not None and (type(capacity) is not int or capacity <= 0)):
        errors.append('max_concurrent_children must be null or a positive integer')
    numeric = ('absolute_child_launches', 'approved_child_launches',
               'preauthorized_economy_reserve', 'approved_strong_child_launches',
               'max_dependency_depth', 'max_fix_cycles', 'dry_optional_expansions')
    if any(type(budget.get(k)) is not int or budget[k] <= 0 for k in numeric):
        errors.append('budget values must be positive integers, not bools')
    elif budget['approved_child_launches'] + budget['preauthorized_economy_reserve'] > budget['absolute_child_launches']:
        errors.append('reserve exceeds the absolute ceiling')
    if budget.get('enforcement') != 'instruction-only-unless-host-enforced':
        errors.append('must disclose instruction-only enforcement')
    if version.startswith('4.'):
        if policy.get('workflow') != 'astra-mainline': errors.append('v4 workflow must be astra-mainline')
        for key in ('supplemental_luna_launches', 'minimum_meaningful_luna_probes', 'mainline_capacity_reserve'):
            if type(budget.get(key)) is not int or budget[key] < 1: errors.append('invalid v4 budget field: '+key)
        if type(budget.get('minimum_meaningful_luna_probes')) is int and budget['minimum_meaningful_luna_probes'] < 3:
            errors.append('meaningful-task Luna launch intent must be at least three')
    profile_configs = {}
    for name in PROFILE_NAMES:
        try:
            data = tomllib.loads((root / 'profiles' / f'{name}.toml').read_text(encoding='utf-8'))
            profile_configs[name] = data
            if data.get('name') != name or not data.get('description') or not data.get('developer_instructions'):
                errors.append(f'invalid role metadata: {name}')
            allowed = {'name', 'description', 'model', 'model_reasoning_effort', 'sandbox_mode', 'developer_instructions'}
            if set(data) - allowed:
                errors.append(f'unexpected role configuration keys: {name}')
            if name not in {'cwf_writer','cwf_sol_writer'} and data.get('sandbox_mode') != 'read-only':
                errors.append(f'reader must request read-only: {name}')
            if name in {'cwf_writer','cwf_sol_writer'} and 'sandbox_mode' in data:
                errors.append('writer must inherit, not grant, sandbox permissions')
            flexible = version != 'INVALID' and tuple(map(int, version.split('.'))) >= (4,1,1) and name in {'cwf_reader','cwf_writer','cwf_sol_writer'}
            if flexible and 'model_reasoning_effort' in data:
                errors.append(f'runtime/profile/model/effort drift: flexible profile pins effort: {name}')
            if not data.get('model') or (not flexible and not data.get('model_reasoning_effort')):
                errors.append(f'model/effort must be explicit in the profile: {name}')
        except (OSError, ValueError) as exc:
            errors.append(f'profile error {name}: {exc}')
    for skill, name, expected_version, display, implicit in (
            (SKILL, 'codex-dynamic-workflow', version, 'Codex Dynamic Workflow', True),
            (LEGACY_SKILL, 'dispatching-native-agents', version+'-compat', 'Native Dispatch (deprecated)', False)):
        try:
            text = (root/skill/'SKILL.md').read_text(encoding='utf-8')
            check_frontmatter(text, name, expected_version)
            meta = (root/skill/'agents/openai.yaml').read_text(encoding='utf-8')
            check_interface(meta, display, implicit)
        except (OSError, ValueError) as exc:
            errors.append(f'{name} metadata error: {exc}')
    try:
        legacy_policy = load_json_object(root/LEGACY_SKILL/'policy.json')
        require_keys(legacy_policy, {'schema_version','deprecated','canonical_skill','implicit_invocation'}, 'legacy policy')
        if (type(legacy_policy['schema_version']) is not int or legacy_policy['schema_version'] != 1
                or legacy_policy['deprecated'] is not True
                or legacy_policy['canonical_skill'] != 'codex-dynamic-workflow'
                or legacy_policy['implicit_invocation'] is not False):
            errors.append('legacy alias policy drift')
    except (OSError, ValueError) as exc:
        errors.append(f'legacy policy error: {exc}')
    docs = list((root / SKILL).rglob('*.md')) + list((root / LEGACY_SKILL).rglob('*.md')) + [root / 'README.md', root / 'CHANGELOG.md']
    for path in docs:
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, ValueError) as exc:
            errors.append(str(exc)); continue
        if sum(line.startswith('```') for line in text.splitlines()) % 2:
            errors.append(f'unbalanced fence: {path.relative_to(root)}')
        for href in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
            if href.startswith(('https://', 'http://', '#')):
                continue
            dest = (path.parent / href.split('#', 1)[0]).resolve()
            if not dest.is_relative_to(root.resolve()) or not dest.is_file():
                errors.append(f'invalid local link: {path.relative_to(root)} -> {href}')
    if version != 'INVALID' and int(version.split('.')[0]) >= 3:
        rt = policy.get('runtime', {})
        if not isinstance(rt, dict) or rt.get('version') != version or rt.get('backends') != ['native'] or rt.get('backend_per_run') != 1 or rt.get('exec_writes') is not False:
            errors.append('runtime identity/backend contract drift')
        required = ['scripts/cwf.py','scripts/cwf_runtime/__init__.py','scripts/cwf_runtime/__main__.py','scripts/cwf_runtime/core.py','scripts/cwf_runtime/policy.py','scripts/cwf_runtime/executor.py','scripts/cwf_runtime/worker.py','scripts/cwf_runtime/luna_pool.py','scripts/cwf_runtime/cli.py','scripts/cwf_runtime/result.schema.json','references/runtime.md']
        if version != 'INVALID' and tuple(map(int, version.split('.'))) >= (4,1,0):
            required += ['references/followup.md','scripts/cwf_runtime/result-v41.schema.json']
        for rel in required:
            if not (root/SKILL/rel).is_file(): errors.append('missing runtime delivery file: '+rel)
        try:
            import ast
            tree=ast.parse((root/SKILL/'scripts/cwf_runtime/core.py').read_text(encoding='utf-8'))
            versions=[node.value.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets) and isinstance(node.value,ast.Constant)]
            if versions != [version]: errors.append('runtime code version drift')
            # Read literal declarations only: validation never imports the untrusted package.
            literal_tables = {n.targets[0].id:ast.literal_eval(n.value) for n in tree.body
                              if isinstance(n,ast.Assign) and len(n.targets)==1
                              and isinstance(n.targets[0],ast.Name) and isinstance(n.value,(ast.Dict,ast.Set))}
            routes = literal_tables.get('DEFAULT_ROUTES', {})
            if tuple(map(int, version.split('.'))) >= (4,1,0):
                if policy.get('runtime',{}).get('supplemental_protocol') != 2:
                    errors.append('v4.1 supplemental protocol drift')
                supported = rt.get('supported_contract_versions')
                if (not isinstance(supported,list) or any(not isinstance(v,str) for v in supported)
                        or set(supported) != literal_tables.get('SUPPORTED_CONTRACT_VERSIONS')):
                    errors.append('supported contract versions drift')
                if tuple(map(int, version.split('.'))) >= (4,2,0):
                    expected_models = {'cwf_reader':'gpt-6-astra', 'cwf_writer':'gpt-6-astra',
                                       'cwf_sol_writer':'gpt-5.6-sol', 'cwf_general':'gpt-5.6-luna',
                                       'cwf_mechanical':'gpt-5.6-luna'}
                    if any(profile_configs.get(p, {}).get('model') != model for p,model in expected_models.items()):
                        errors.append('runtime/profile/model/effort drift: v4.2 fixed model/profile identity drift')
                    expected_profiles = {'strong':'cwf_reader', 'writer':'cwf_sol_writer',
                                         'ordinary':'cwf_general', 'economy':'cwf_mechanical'}
                    for tier, name in expected_profiles.items():
                        route = routes.get(tier)
                        if not isinstance(route,dict) or (route.get('model'),route.get('profile')) != (expected_models[name],name):
                            errors.append('v4.2 fixed route identity drift: '+tier)
                    if routes.get('writer', {}).get('profile') != 'cwf_sol_writer':
                        errors.append('v4.2 default writer must be Sol')
                    if policy.get('profiles', {}).get('capable_writer') != 'cwf_sol_writer':
                        errors.append('v4.2 policy writer profile drift')
                    legacy = literal_tables.get('LEGACY_ROUTES', {})
                    expected_legacy = {tier:dict(model=expected_models[name],profile=name,
                                               effort={'ordinary':'max','economy':'medium'}.get(tier,'high'))
                                       for tier,name in (expected_profiles | {'writer':'cwf_writer'}).items()}
                    if legacy != expected_legacy:
                        errors.append('legacy Astra writer route drift')
                if set(routes) != {'strong','writer','ordinary','economy'}:
                    errors.append('runtime routing table incomplete')
                for tier,route in routes.items():
                    if not isinstance(route,dict) or any(not isinstance(route.get(k),str) for k in ('model','profile','effort')):
                        errors.append('invalid runtime route: '+tier); continue
                    profile = profile_configs.get(route.get('profile'), {})
                    flexible = tuple(map(int, version.split('.'))) >= (4,1,1) and tier in {'strong','writer'}
                    if (not profile or profile.get('model') != route.get('model')
                            or (flexible and ('model_reasoning_effort' in profile
                                or route['effort'] not in ({'low','medium','high','xhigh','max','ultra'}
                                    if route['model']=='gpt-6-astra' else {'low','medium','high','xhigh','max'})))
                            or (not flexible and profile.get('model_reasoning_effort') != route.get('effort'))):
                        errors.append('runtime/profile/model/effort drift: '+tier)

            if version.startswith('4.'):
                declarations = {}
                for node in tree.body:
                    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'dict':
                        for target in node.targets:
                            if isinstance(target, ast.Name): declarations[target.id] = {k.arg:ast.literal_eval(k.value) for k in node.value.keywords}
                expected = {'approved':'approved_child_launches','reserve':'preauthorized_economy_reserve','absolute':'absolute_child_launches','strong_approved':'approved_strong_child_launches'}
                expected_supplemental = {'supplemental_approved':'supplemental_luna_launches','mainline_capacity_reserve':'mainline_capacity_reserve'}
                for table, fields in [('DEFAULTS',expected),('SUPPLEMENTAL_DEFAULTS',expected_supplemental)]:
                    if any(declarations.get(table,{}).get(k) != budget.get(v) for k,v in fields.items()):
                        errors.append('v4 runtime/policy budget drift: '+table)
        except (OSError,ValueError,TypeError,SyntaxError) as exc: errors.append('runtime source error: '+str(exc))
    return errors


if __name__ == '__main__':
    problems = validate()
    print(json.dumps({'status': 'FAIL' if problems else 'PASS', 'errors': problems}, ensure_ascii=False, indent=2))
    sys.exit(1 if problems else 0)
