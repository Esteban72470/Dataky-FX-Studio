"""Art direction and evidence-based iteration around portable Dataky recipes.

Plans/reviews live beside projects, never inside exported recipes. This module
does not call a model or invent visual observations. A human or vision agent
must actually inspect the captures and submit a review before another attempt.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import uuid

if __package__:
    from .fx_schema import ValidationError, identifier, number, text, validate_project
else:
    from fx_schema import ValidationError, identifier, number, text, validate_project

ROOT = Path(__file__).resolve().parent.parent
LOCK = threading.RLock()
PHASES = ('anticipation', 'charge', 'release', 'impact', 'secondary', 'dissipation')
CRITERIA = ('depth', 'silhouette', 'readability', 'palette', 'motion', 'impact', 'composition', 'redundancy', 'overload')
ROLES = ('primary', 'secondary', 'accent')
DEPTHS = ('foreground', 'midground', 'background')
DEFAULT_BUDGET = {'particles': 600, 'emitters': 32, 'lights': 4, 'parts': 48}


def sibling(name):
    return importlib.import_module('.' + name, __package__) if __package__ else importlib.import_module(name)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        f.write(payload)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def location(kind, ident):
    identifier(ident, kind + '.id')
    return ROOT / 'editor' / 'artistry' / kind / (ident + '.json')


def fingerprint(project):
    visual = validate_project(project)
    for key in ('name', 'id', 'editor'):
        visual.pop(key, None)
    for node in visual['nodes']:
        node.pop('name', None)
    return hashlib.sha256(json.dumps(visual, sort_keys=True, allow_nan=False).encode()).hexdigest()


def review_lock(ident):
    path = location('reviews', ident)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sibling('fx_assets')._locked(path)


def schema():
    return {'phases': PHASES, 'roles': ROLES, 'depths': DEPTHS, 'reviewCriteria': CRITERIA,
            'defaultBudget': DEFAULT_BUDGET, 'maxAttempts': 8,
            'plan': {'brief': ['theme', 'palette (2–5 RGB colors)', 'silhouette', 'motion', 'character', 'readability', 'focal [x,y,z]', 'power (1–5)'],
                     'phases': '[{name,start,duration,easing}] in phase order; no overlaps',
                     'layers': '[{id,nodes:[existing IDs],role,purpose,phase,depth}]'},
            'reviewPolicy': 'No beauty score. Inspect both views/backgrounds; submit all nine criteria. Without vision: human review required.',
            'operations': ['add_node:value', 'remove_node:node,descendants?', 'properties:node,values', 'timing:node,value', 'animation:value', 'motion:value']}


def create_plan(project, brief):
    project = validate_project(project)
    if not isinstance(brief, dict):
        raise ValidationError('brief : objet requis')
    clean = {key: text(brief.get(key), 'brief.' + key, 2000, False)
             for key in ('theme', 'silhouette', 'motion', 'character', 'readability')}
    palette = brief.get('palette')
    if not isinstance(palette, list) or not 2 <= len(palette) <= 5:
        raise ValidationError('brief.palette : 2 à 5 couleurs RGB requises')
    clean['palette'] = []
    for color in palette:
        if not isinstance(color, list) or len(color) != 3:
            raise ValidationError('brief.palette : couleurs [r,g,b] normalisées requises')
        clean['palette'].append([number(v, 'palette', 0, 1) for v in color])
    focal = brief.get('focal', [0, 2, 0])
    if not isinstance(focal, list) or len(focal) != 3:
        raise ValidationError('brief.focal : trois coordonnées requises')
    clean['focal'] = [number(v, 'focal', -100000, 100000) for v in focal]
    clean['power'] = number(brief.get('power', 3), 'power', 1, 5, True)
    default = []
    start = 0
    for name, ratio in zip(PHASES, (.12, .2, .08, .15, .15, .3)):
        duration = round(project['duration'] * ratio, 7)
        default.append({'name': name, 'start': start, 'duration': duration, 'easing': 'linear'})
        start = round(start + duration, 7)
    phases = brief.get('phases', default)
    if not isinstance(phases, list) or len(phases) != 6:
        raise ValidationError('phases : six phases ordonnées requises')
    clean_phases, previous = [], 0
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict) or phase.get('name') != PHASES[index]:
            raise ValidationError('phases : ordre attendu ' + ', '.join(PHASES))
        start = number(phase.get('start'), 'phase.start', 0, project['duration'])
        duration = number(phase.get('duration'), 'phase.duration', 0, project['duration'])
        if start + 1e-6 < previous or start + duration > project['duration'] + 1e-6:
            raise ValidationError('phase : chevauchement ou fin hors de duration')
        easing = phase.get('easing', 'linear')
        if easing not in ('linear', 'in', 'out', 'inOut', 'backOut'):
            raise ValidationError('phase.easing : linear, in, out, inOut ou backOut')
        clean_phases.append({'name': phase['name'], 'start': start, 'duration': duration, 'easing': easing})
        previous = start + duration
    layers = brief.get('layers', [])
    if not isinstance(layers, list) or len(layers) > 100:
        raise ValidationError('layers : liste de 100 couches maximum')
    ids, taken, assigned, clean_layers = {n['id'] for n in project['nodes']}, set(), set(), []
    for layer in layers:
        if not isinstance(layer, dict):
            raise ValidationError('layer : objet requis')
        ident = identifier(layer.get('id'), 'layer.id')
        nodes = layer.get('nodes')
        if ident in taken or not isinstance(nodes, list) or not nodes or any(not isinstance(n, str) or n not in ids for n in nodes):
            raise ValidationError('layer : ID unique et nodes existants requis')
        if len(nodes) != len(set(nodes)) or assigned.intersection(nodes):
            raise ValidationError('layer : chaque objet appartient à une seule couche')
        if layer.get('role') not in ROLES or layer.get('depth') not in DEPTHS or layer.get('phase') not in PHASES:
            raise ValidationError('layer : role, depth ou phase invalide')
        taken.add(ident)
        assigned.update(nodes)
        clean_layers.append({**{key: layer[key] for key in ('id', 'role', 'depth', 'phase')}, 'nodes': nodes[:],
                             'purpose': text(layer.get('purpose'), 'layer.purpose', 1000, False)})
    budget = {**DEFAULT_BUDGET, **brief.get('budget', {})} if isinstance(brief.get('budget', {}), dict) else None
    if budget is None or set(budget) != set(DEFAULT_BUDGET):
        raise ValidationError('budget : particles, emitters, lights, parts requis')
    budget = {key: number(value, 'budget.' + key, 1, 100000, True) for key, value in budget.items()}
    return {'version': 1, 'project_id': project.get('id'), 'name': project['name'], 'brief': clean,
            'phases': clean_phases, 'layers': clean_layers, 'budget': budget}


def save_plan(project, brief):
    plan = create_plan(project, brief)
    ident = project.get('id') or ('plan-' + uuid.uuid4().hex[:12])
    plan.update(id=ident, updated_at=stamp())
    with LOCK:
        write(location('plans', ident), plan)
    return plan


def load_plan(ident):
    path = location('plans', ident)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def inspect(project, plan=None):
    """Conservative counts, never a visual-quality score or spatial assertion."""
    project = validate_project(project)
    if plan is not None:
        plan = create_plan(project, {**plan.get('brief', {}), 'phases': plan.get('phases'), 'layers': plan.get('layers'), 'budget': plan.get('budget')})
    counts = {'particles': 0, 'emitters': 0, 'lights': 0, 'parts': 0}
    for node in project['nodes']:
        cls, props = node['class'], node['properties']
        if cls in ('Part', 'MeshPart'):
            counts['parts'] += 1
        if cls.endswith('Light'):
            counts['lights'] += 1
        if cls == 'ParticleEmitter':
            counts['emitters'] += 1
            timing = node.get('timing', {})
            rates = [props.get('Rate', 20)] + [k['value'] for a in project['animations'] if a['node'] == node['id'] and a['property'] == 'Rate' for k in a['keyframes']]
            count = timing.get('count', 20) if timing.get('mode') == 'burst' else math.ceil(max(rates) * timing.get('duration', project['duration']))
            counts['particles'] += count
    budget = (plan or {}).get('budget', DEFAULT_BUDGET)
    diagnostics = [{'code': 'budget_' + key, 'message': f'{value} > budget {budget[key]}', 'metric': key}
                   for key, value in counts.items() if value > budget[key]]
    if not plan:
        diagnostics.append({'code': 'missing_direction', 'message': 'Définir palette, silhouette, six phases et rôle des couches.'})
    else:
        assigned = {n for layer in plan['layers'] for n in layer['nodes']}
        visible = {n['id'] for n in project['nodes'] if n['class'] in ('ParticleEmitter', 'Beam', 'Trail', 'MeshPart')}
        missing = sorted(visible - assigned)
        if missing:
            diagnostics.append({'code': 'unassigned_layers', 'nodes': missing, 'message': 'Donner une fonction artistique à ces objets.'})
        if not any(layer['role'] == 'primary' for layer in plan['layers']):
            diagnostics.append({'code': 'missing_focal_layer', 'message': 'Aucune couche principale déclarée.'})
    return {'counts': counts, 'budget': budget, 'diagnostics': diagnostics,
            'method': 'Conservative total emitted, using highest keyed Rate; not peak live particles, GPU cost or beauty.',
            'visual_review_required': list(CRITERIA), 'warnings': sibling('fx_tools').warnings(project)}


def apply_operations(project, operations):
    """Transactional batch: final validation before any caller/file is changed."""
    result = validate_project(project)
    if not isinstance(operations, list) or not 1 <= len(operations) <= 100:
        raise ValidationError('operations : liste de 1 à 100 opérations requise')
    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            raise ValidationError(f'operations[{index}] : objet requis')
        kind = op.get('op')
        node = next((n for n in result['nodes'] if n['id'] == op.get('node')), None)
        if kind == 'add_node':
            result['nodes'].append(deepcopy(op.get('value')))
        elif kind in ('remove_node', 'properties', 'timing'):
            if node is None:
                raise ValidationError(f'operations[{index}].node : objet introuvable')
            if kind == 'properties':
                if not isinstance(op.get('values'), dict):
                    raise ValidationError('properties.values : objet requis')
                node['properties'].update(deepcopy(op['values']))
            elif kind == 'timing':
                node['timing'] = deepcopy(op.get('value'))
            else:
                removed = {node['id']}
                if op.get('descendants', True) is not True:
                    if any(n.get('parent') == node['id'] for n in result['nodes']):
                        raise ValidationError('remove_node : descendants présents')
                else:
                    for _ in result['nodes']:
                        removed.update(n['id'] for n in result['nodes'] if n.get('parent') in removed)
                result['nodes'] = [n for n in result['nodes'] if n['id'] not in removed]
                result['animations'] = [a for a in result['animations'] if a['node'] not in removed]
        elif kind == 'animation':
            track = deepcopy(op.get('value'))
            if not isinstance(track, dict):
                raise ValidationError('animation.value : piste requise')
            result['animations'] = [a for a in result['animations'] if (a['node'], a['property']) != (track.get('node'), track.get('property'))]
            result['animations'].append(track)
        elif kind == 'motion':
            result = sibling('fx_motion').bake_motion(result, op.get('value'))
        else:
            raise ValidationError(f'operations[{index}].op : opération inconnue')
    return validate_project(result)


def quality_profile(project, quality='high', *, reduced=False, plan=None, max_particles=600):
    """Bake a portable density profile; preserve timing, shapes and primary roles."""
    result = validate_project(project)
    if quality not in ('high', 'medium', 'low') or not isinstance(reduced, bool):
        raise ValidationError('quality : high, medium ou low ; reduced : booléen')
    maximum = number(max_particles, 'max_particles', 1, 100000, True)
    factor = {'high': 1, 'medium': .7, 'low': .4}[quality] * (.5 if reduced else 1)
    roles = {node: layer['role'] for layer in (plan or {}).get('layers', []) for node in layer['nodes']}
    emitters = [n for n in result['nodes'] if n['class'] == 'ParticleEmitter']
    emitters.sort(key=lambda n: ROLES.index(roles.get(n['id'], 'secondary')))
    remaining = maximum
    for node in emitters:
        props, timing = node['properties'], node.get('timing', {})
        local = max(.75, factor) if roles.get(node['id']) == 'primary' and not reduced else factor
        rates = [a for a in result['animations'] if a['node'] == node['id'] and a['property'] == 'Rate']
        if timing.get('mode') == 'burst':
            count = min(remaining, int(math.floor(timing['count'] * local)))
            timing['count'] = count
            remaining -= count
        else:
            duration = timing.get('duration', result['duration'])
            peak = max([props.get('Rate', 20)] + [k['value'] for a in rates for k in a['keyframes']])
            scale = min(local, remaining / max(1e-9, peak * duration))
            props['Rate'] = props.get('Rate', 20) * scale
            for track in rates:
                for key in track['keyframes']:
                    key['value'] *= scale
            remaining -= min(remaining, math.ceil(peak * scale * duration - 1e-9))
    if reduced:
        for node in result['nodes']:
            if node['class'].endswith('Light'):
                node['properties']['Brightness'] = min(node['properties'].get('Brightness', 1), 1)
                for track in result['animations']:
                    if track['node'] == node['id'] and track['property'] == 'Brightness':
                        for key in track['keyframes']:
                            key['value'] = min(key['value'], 1)
    return {'project': validate_project(result), 'profile': {'quality': quality, 'reduced': reduced, 'max_particles': maximum},
            'report': inspect(result, plan)}


def create_review(project, plan=None, *, max_attempts=3, vision=False):
    project = validate_project(project)
    maximum = number(max_attempts, 'max_attempts', 1, 8, True)
    if not isinstance(vision, bool):
        raise ValidationError('vision : booléen requis')
    if plan is not None:
        plan = create_plan(project, {**plan.get('brief', {}), 'phases': plan.get('phases'), 'layers': plan.get('layers'), 'budget': plan.get('budget')})
    ident = 'review-' + uuid.uuid4().hex[:16]
    session = {'id': ident, 'project_id': project.get('id'), 'name': project['name'], 'created_at': stamp(),
               'max_attempts': maximum, 'vision': vision, 'state': 'ready', 'plan': plan, 'attempts': [], 'initial': project}
    with LOCK:
        write(location('reviews', ident), session)
    return session


def get_review(ident):
    path = location('reviews', ident)
    if not path.is_file():
        raise ValidationError('review : session introuvable')
    return json.loads(path.read_text(encoding='utf-8'))


def list_reviews(project_id=None):
    if project_id is not None:
        identifier(project_id, 'project_id')
    directory = ROOT / 'editor' / 'artistry' / 'reviews'
    result = []
    for file in directory.glob('review-*.json'):
        session = get_review(file.stem)
        if project_id is None or session.get('project_id') == project_id:
            result.append({key: session[key] for key in ('id', 'project_id', 'name', 'created_at', 'state', 'max_attempts')}
                          | {'attempts': len(session['attempts'])})
    return sorted(result, key=lambda s: s['created_at'], reverse=True)


def capture_review(ident, project=None, *, size='480x270', plan=None):
    with LOCK, review_lock(ident):
        session = get_review(ident)
        if session['state'] not in ('ready', 'revise') or len(session['attempts']) >= session['max_attempts']:
            raise ValidationError('review : soumettre la critique avant la prochaine tentative, ou créer une nouvelle session après la limite')
        folder = location('reviews', ident).with_suffix('')
        last = json.loads((folder / f'recipe-{len(session["attempts"])}.json').read_text(encoding='utf-8')) if session['attempts'] else session['initial']
        recipe = validate_project(project if project is not None else last)
        if session['attempts'] and fingerprint(recipe) == session['attempts'][-1]['fingerprint']:
            raise ValidationError('review : la recette est inchangée ; appliquer une correction avant de recapturer')
        plan = plan if plan is not None else session['plan']
        if plan:
            # Detect stale layer bindings/timings when a revision changes the recipe.
            plan = create_plan(recipe, {**plan['brief'], 'layers': plan['layers'], 'phases': plan['phases'], 'budget': plan['budget']})
        session['plan'] = plan
        attempt = len(session['attempts']) + 1
        folder.mkdir(parents=True, exist_ok=True)
        if plan:
            times = [min(recipe['duration'], p['start'] + p['duration'] * .5) for p in plan['phases']]
        else:
            times = [recipe['duration'] * t for t in (.06, .2, .35, .5, .7, .92)]
        # Preserve brief impacts as well as phase context. Snap beyond the 60 Hz
        # simulation step; using only phase midpoints can miss a short burst.
        burst_times = []
        for node in recipe['nodes']:
            timing = node.get('timing', {})
            if node['class'] == 'ParticleEmitter' and timing.get('mode') == 'burst' and timing.get('count', 0):
                lifetime = node['properties'].get('Lifetime', [.5, .5])
                offset = max(1 / 60, min(.06, max(lifetime) * .3))
                burst_times.append(min(recipe['duration'], timing['start'] + offset))
        # At most six representative trigger instants, avoiding near duplicates.
        triggers = []
        for value in sorted(burst_times):
            if not triggers or value - triggers[-1] > .04:
                triggers.append(value)
        times += triggers[:6]
        times = sorted(set(round(t, 5) for t in times))
        recipes = [recipe]
        if session['attempts']:
            recipes.insert(0, json.loads((folder / f'recipe-{attempt-1}.json').read_text(encoding='utf-8')))
        focal = (plan or {}).get('brief', {}).get('focal', recipe['camera']['target'])
        camera = recipe['camera']
        hero = camera['position'] + camera['target']
        distance = max(8, math.dist(camera['position'], camera['target']))
        player = [focal[0] + distance * .5, focal[1] + distance * .85, focal[2] + distance * .6, *focal]
        jobs = [{'projects': recipes, 'out': str(folder / f'attempt-{attempt}-{view}.png'), 'times': times,
                 'camera': cam, 'backgrounds': ['roblox', 'dark'], 'size': size, 'columns': 3,
                 'seed': 1, 'dummy': True, 'framesDir': str(folder / f'frames-{attempt}-{view}')}
                for view, cam in (('hero', hero), ('player', player))]
        rendered = sibling('fx_tools').render_batch(jobs)
        images = [str(Path(job['out'])) for job in jobs]
        if any(not Path(path).is_file() for path in images):
            raise ValidationError('review : le renderer n’a pas produit les deux planches')
        write(folder / f'recipe-{attempt}.json', recipe)
        record = {'number': attempt, 'fingerprint': fingerprint(recipe), 'created_at': stamp(), 'times': times,
                  'images': images, 'comparison': attempt > 1, 'metrics': inspect(recipe, plan),
                  'renderer': rendered, 'review': None}
        session['attempts'].append(record)
        session['state'] = 'awaiting_vision_review' if session['vision'] else 'awaiting_human_review'
        write(location('reviews', ident), session)
        return session


def submit_review(ident, *, attempt, observer, decision, observations):
    with LOCK, review_lock(ident):
        session = get_review(ident)
        if session['state'] not in ('awaiting_vision_review', 'awaiting_human_review'):
            raise ValidationError('review : capturer avant de soumettre une critique')
        if observer not in ('human', 'vision') or (observer == 'vision' and not session['vision']):
            raise ValidationError('observer : human requis sans capacité de vision déclarée')
        if decision not in ('approve', 'revise'):
            raise ValidationError('decision : approve ou revise requis')
        current = session['attempts'][-1]
        if isinstance(attempt, bool) or attempt != current['number']:
            raise ValidationError('attempt : la critique doit porter sur la dernière capture')
        if not isinstance(observations, dict) or set(observations) != set(CRITERIA):
            raise ValidationError('observations : renseigner les neuf critères ' + ', '.join(CRITERIA))
        clean = {key: text(value, 'observations.' + key, 2000, False) for key, value in observations.items()}
        current['review'] = {'observer': observer, 'decision': decision, 'observations': clean, 'created_at': stamp()}
        session['state'] = 'approved' if decision == 'approve' else ('exhausted' if len(session['attempts']) >= session['max_attempts'] else 'revise')
        write(location('reviews', ident), session)
        return session
