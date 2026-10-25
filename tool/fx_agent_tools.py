"""Shared action surface for HTTP and MCP; parameter validation lives in modules."""
from __future__ import annotations

import importlib


def module(name):
    return importlib.import_module('.' + name, __package__) if __package__ else importlib.import_module(name)


def project_from(args):
    if isinstance(args.get('project'), dict):
        return args['project']
    if args.get('project_id'):
        return module('fx_tools').load(args['project_id'])
    raise ValueError('project ou project_id requis')


def perform(action, args):
    if not isinstance(args, dict):
        raise ValueError('Paramètres : objet JSON requis')
    art = module('fx_artistry')
    if action == 'schema':
        return {'direction': art.schema(), 'motion': module('fx_motion').motion_schema()}
    if action == 'plan':
        return art.save_plan(project_from(args), args.get('brief'))
    if action in ('inspect', 'profile'):
        project = project_from(args)
        plan = args.get('plan') or (art.load_plan(project['id']) if project.get('id') else None)
        if action == 'inspect':
            return art.inspect(project, plan)
        return art.quality_profile(project, args.get('quality', 'high'), reduced=args.get('reduced', False),
                                   plan=plan, max_particles=args.get('max_particles', 600))
    if action == 'motion':
        return {'project': module('fx_motion').bake_motion(project_from(args), args.get('specs'))}
    if action == 'batch':
        return {'project': art.apply_operations(project_from(args), args.get('operations'))}
    if action == 'review_create':
        project = project_from(args)
        plan = args.get('plan') or (art.load_plan(project['id']) if project.get('id') else None)
        return art.create_review(project, plan, max_attempts=args.get('max_attempts', 3), vision=args.get('vision', False))
    if action == 'review_capture':
        return art.capture_review(args.get('id'), args.get('project'), size=args.get('size', '480x270'), plan=args.get('plan'))
    if action == 'review_submit':
        return art.submit_review(args.get('id'), attempt=args.get('attempt'), observer=args.get('observer'),
                                 decision=args.get('decision'), observations=args.get('observations'))
    if action == 'review_get':
        return art.get_review(args.get('id'))
    if action == 'review_list':
        return {'reviews': art.list_reviews(args.get('project_id'))}
    assets = module('fx_assets')
    if action == 'asset_search':
        return assets.search(**{key: args[key] for key in ('collection', 'shape', 'style', 'color', 'usage', 'category', 'query', 'kind', 'limit', 'offset') if key in args})
    if action == 'asset_annotate':
        return assets.annotate_asset(args.get('asset_id'), args.get('collection', 'textures'), args.get('metadata'),
                                     observer=args.get('observer'), evidence=args.get('evidence'))
    if action == 'reference_add':
        return assets.add_reference(args.get('path'), args.get('kind'), args.get('observations'),
                                    observer=args.get('observer'), name=args.get('name'), source=args.get('source'))
    if action == 'reference_list':
        return {'references': assets.list_references()}
    raise ValueError('Action artistique inconnue : ' + str(action))


# Specific tools are discoverable without memorizing an opaque action name.
def definitions(project_inputs):
    obj = {'type': 'object'}
    definitions = [
        ('artistry_schema', 'Schéma de direction, couches, phases, revue visuelle et mouvements procéduraux. Lire avant de construire.', {}),
        ('plan_effect', 'Enregistre un plan artistique : palette, silhouette, focal, six phases et rôle de chaque couche liée aux IDs. Aucun jugement visuel inventé.', {**project_inputs, 'brief': obj}),
        ('inspect_composition', 'Budgets conservateurs et liens des couches ; les métriques ne jugent pas la beauté.', project_inputs),
        ('animate_procedural', 'Compile Bézier, arc, hélice, orbite, oscillation, rotation, squash ou tween vers des pistes Roblox ; batch 1–128, remplacement explicite.', {**project_inputs, 'specs': {'type': ['object', 'array'], 'items': obj}}),
        ('edit_effect_batch', 'Modifications transactionnelles 1–100 : add_node(value), remove_node(node), properties(node,values), timing(node,value), animation(value), motion(value). Valide la recette finale.', {**project_inputs, 'operations': {'type': 'array', 'minItems': 1, 'maxItems': 100, 'items': obj}}),
        ('quality_profile', 'Crée une variante de densité high/medium/low et réduction lumineuse ; priorité aux couches principales, budget total d’émissions configurable.', {**project_inputs, 'quality': {'type': 'string', 'enum': ['high', 'medium', 'low']}, 'reduced': {'type': 'boolean'}, 'max_particles': {'type': 'integer', 'minimum': 1, 'maximum': 100000}}),
        ('start_visual_review', 'Démarre une session de 1–8 tentatives ; vision=false attend une validation humaine réelle. Ne lance aucun modèle.', {**project_inputs, 'max_attempts': {'type': 'integer', 'minimum': 1, 'maximum': 8}, 'vision': {'type': 'boolean'}}),
        ('capture_visual_review', 'Capture deux vues et deux fonds aux phases clés ; joint les planches à inspecter. Compare automatiquement avec la version précédente. plan remplace le plan si les couches ont changé.', {'id': {'type': 'string'}, 'project': obj, 'plan': obj, 'size': {'type': 'string'}}),
        ('submit_visual_review', 'Après avoir regardé les planches, documente les neuf critères puis approve/revise. Une correction réelle est nécessaire avant une nouvelle tentative.', {'id': {'type': 'string'}, 'attempt': {'type': 'integer'}, 'observer': {'type': 'string', 'enum': ['human', 'vision']}, 'decision': {'type': 'string', 'enum': ['approve', 'revise']}, 'observations': obj}),
        ('search_art_assets', 'Recherche forme/style/couleur/usage dans les observations vérifiées, catégorie dans les tags. Inconnu reste inconnu. Joint les miniatures candidates.', {key: {'type': 'integer' if key in ('limit', 'offset') else 'string'} for key in ('collection', 'shape', 'style', 'color', 'usage', 'category', 'query', 'kind', 'limit', 'offset')}),
        ('annotate_art_asset', 'Enrichit progressivement un asset vu ; metadata shape/style/color/usage/category, provenance human/vision et evidence chemin local réel.', {'asset_id': {'type': 'string'}, 'collection': {'type': 'string'}, 'metadata': obj, 'observer': {'type': 'string', 'enum': ['human', 'vision']}, 'evidence': {'type': 'string'}}),
        ('add_art_reference', 'Conserve image/spritesheet/vidéo locale avec observations explicites et provenance. Inspiration originale ; aucune analyse vidéo simulée.', {'path': {'type': 'string'}, 'kind': {'type': 'string', 'enum': ['image', 'spritesheet', 'video']}, 'observations': obj, 'observer': {'type': 'string', 'enum': ['human', 'vision']}, 'name': {'type': 'string'}, 'source': {'type': 'string'}}),
        ('list_art_references', 'Références visuelles enregistrées avec observations et chemins accessibles.', {}),
        ('get_visual_review', 'Recharge une session de revue, ses versions, critiques, captures et état.', {'id': {'type': 'string'}}),
        ('list_visual_reviews', 'Liste compacte des sessions, éventuellement filtrée par projet.', {'project_id': {'type': 'string'}}),
    ]
    required = {'plan_effect': ['brief'], 'animate_procedural': ['specs'], 'edit_effect_batch': ['operations'],
                'capture_visual_review': ['id'], 'submit_visual_review': ['id', 'attempt', 'observer', 'decision', 'observations'],
                'get_visual_review': ['id'],
                'annotate_art_asset': ['asset_id', 'metadata', 'observer', 'evidence'],
                'add_art_reference': ['path', 'kind', 'observations', 'observer']}
    return [{'name': name, 'description': description, 'inputSchema': {'type': 'object', 'properties': props, 'required': required.get(name, [])}}
            for name, description, props in definitions]


ACTIONS = {'artistry_schema': 'schema', 'plan_effect': 'plan', 'inspect_composition': 'inspect',
           'animate_procedural': 'motion', 'edit_effect_batch': 'batch', 'quality_profile': 'profile',
           'start_visual_review': 'review_create', 'capture_visual_review': 'review_capture', 'submit_visual_review': 'review_submit',
           'search_art_assets': 'asset_search', 'annotate_art_asset': 'asset_annotate', 'add_art_reference': 'reference_add',
           'list_art_references': 'reference_list', 'get_visual_review': 'review_get', 'list_visual_reviews': 'review_list'}
