"""Small authoring helpers for the three directed showcase effects.

Only ordinary recipe nodes and baked tracks are produced. Beams can have real
3D width axes; no custom shader, generated texture or engine change is needed.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import math
from pathlib import Path

if __package__:
    from .fx_builder import Recipe, NS, CS, NR
    from .fx_motion import bake_motion
    from . import fx_tools, fx_artistry
else:
    from fx_builder import Recipe, NS, CS, NR
    from fx_motion import bake_motion
    import fx_tools, fx_artistry

ROOT = Path(__file__).resolve().parent.parent


def add(a, b): return [x + y for x, y in zip(a, b)]
def sub(a, b): return [x - y for x, y in zip(a, b)]
def mul(a, k): return [x * k for x in a]
def length(a): return math.sqrt(sum(x*x for x in a))
def unit(a): return mul(a, 1 / max(1e-9, length(a)))
def mix(a, b, t): return add(mul(a, 1-t), mul(b, t))
def cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def bezier(points, t):
    s = 1-t
    return [s*s*s*points[0][i] + 3*s*s*t*points[1][i] + 3*s*t*t*points[2][i] + t*t*t*points[3][i] for i in range(3)]


def tangent(points, t):
    return [3*(1-t)**2*(points[1][i]-points[0][i])+6*(1-t)*t*(points[2][i]-points[1][i])+3*t*t*(points[3][i]-points[2][i]) for i in range(3)]


def ease(t, kind='inOut'):
    if kind == 'in': return t*t*t
    if kind == 'out': return 1-(1-t)**3
    if kind == 'inOut': return 4*t**3 if t < .5 else 1-(-2*t+2)**3/2
    return t


class Effect:
    def __init__(self, name, duration, camera):
        self.name = name
        self.fx = Recipe(name, duration, camera, ident=name, background='#080d1c')
        self.layers = []
        self.specs = []
        self.fx.part('space', size=(.01, .01, .01))
        self.current = None

    @contextmanager
    def layer(self, ident, role, purpose, phase, depth):
        before = len(self.fx.d['nodes'])
        yield
        self.layers.append({'id':ident, 'role':role, 'purpose':purpose, 'phase':phase, 'depth':depth,
                            'nodes':[n['id'] for n in self.fx.d['nodes'][before:]]})

    def node(self, cls, ident, parent='space', properties=None, timing=None):
        node = {'id':ident, 'name':ident, 'class':cls, 'parent':parent, 'properties':deepcopy(properties or {})}
        if timing is not None: node['timing'] = deepcopy(timing)
        return self.fx._add(node)

    def att(self, ident, position=(0,0,0), parent='space', axis=None, up=None):
        props = {}
        if axis is not None: props['Axis'] = unit(axis)
        if up is not None: props['SecondaryAxis'] = unit(up)
        return self.fx.att(ident, parent, position, **props)

    def carrier(self, ident, position=(0,0,0)):
        return self.fx.part(ident, position, (.01,.01,.01))

    def track(self, node, prop, keys):
        cleaned = []
        for t, value in sorted(keys, key=lambda p:p[0]):
            point = (round(float(t), 7), deepcopy(value))
            if cleaned and point[0] == cleaned[-1][0]: cleaned[-1] = point
            else: cleaned.append(point)
        self.fx.anim(node, prop, cleaned)
        if prop in ('Position','Transparency') and next(n['class'] for n in self.fx.d['nodes'] if n['id']==node) in ('Part','MeshPart'):
            self.fx.d['animations'][-1]['runtime'] = True

    def sampled(self, node, prop, fn, start, end, count=41):
        self.track(node, prop, [(start+(end-start)*i/(count-1),fn(i/(count-1))) for i in range(count)])

    def motion(self, node, kind, **spec):
        self.specs.append({'node':node,'type':kind,**spec})

    def beam(self, ident, points, color, widths, start, end, *, texture='', up=(0,1,0),
             face=False, opacity=.9, emission=.3, brightness=1, parent='space', grow=.025, fade=.14):
        a, b = ident+'_a', ident+'_b'
        first, last = sub(points[1],points[0]), sub(points[3],points[2])
        self.att(a, points[0], parent, first, up)
        self.att(b, points[3], parent, last, up)
        props={'Attachment0':a,'Attachment1':b,'Color':CS((0,color),(1,color)),
               'Transparency':NS((0,1-opacity),(1,1-opacity)), 'Texture':texture,
               'TextureMode':'Stretch','TextureLength':1,'TextureSpeed':0,
               'Width0':widths[0],'Width1':widths[1], 'CurveSize0':length(first),'CurveSize1':length(last),
               'Segments':24,'FaceCamera':face,'LightEmission':emission,'LightInfluence':0,'Brightness':brightness}
        self.node('Beam',ident,parent,props,{'start':start,'duration':end-start,'mode':'continuous','count':1})
        peak = min(start+grow, end-.002)
        falling = max(peak+.001,end-fade)
        for prop, width in zip(('Width0','Width1'),widths):
            self.track(ident,prop,[(start,0),(peak,width),(falling,width*.9),(end,0)])
        return ident

    def curved_strip(self, ident, points, color, width, start, end, *, pieces=6, sweep=.09,
                     texture='', depth=0, up=(0,1,0), opacity=.95, emission=.2, brightness=1):
        """Continuous tapered silhouette, with exact cubic sub-curves and a timed sweep."""
        for i in range(pieces):
            t, u = i/pieces, (i+1)/pieces
            a, d = bezier(points,t), bezier(points,u)
            control = [a,add(a,mul(tangent(points,t),(u-t)/3)),sub(d,mul(tangent(points,u),(u-t)/3)),d]
            control = [add(p,[0,0,depth]) for p in control]
            w = [max(.005,width*math.sin(math.pi*v)**.7) for v in (t,u)]
            self.beam(ident+'_'+str(i),control,color,w,start+sweep*t,end,
                      texture=texture,up=up,opacity=opacity,emission=emission,brightness=brightness)

    def emitter(self, ident, parent, texture, start, life, size, color, *, count=1, dur=.012,
                speed=0, rotation=0, rot_speed=0, transparency=None, mode='burst', rate=0, **props):
        size = size if isinstance(size,list) else NS((0,size*.15),(.15,size),(.65,size*.8),(1,0))
        transparency = transparency if transparency is not None else NS((0,.15),(.16,.02),(.65,.22),(1,1))
        return self.fx.em(ident,parent,'rbxassetid://'+str(texture) if str(texture).isdigit() else texture,
                          start=start,count=count,dur=dur,mode=mode,Rate=rate,
                          Lifetime=NR(life) if isinstance(life,(int,float)) else list(life),
                          Size=size,Color=CS((0,color),(1,color)),Transparency=transparency,
                          Speed=NR(speed) if isinstance(speed,(int,float)) else list(speed),
                          Rotation=NR(rotation) if isinstance(rotation,(int,float)) else list(rotation),
                          RotSpeed=NR(rot_speed) if isinstance(rot_speed,(int,float)) else list(rot_speed),**props)

    def trail(self, ident, parent, width, color, start, end, *, texture='', offset=(0,0,0),
              up=(0,1,0), lifetime=.14, emission=.4, opacity=.75, face=True):
        a,b = ident+'_a',ident+'_b'
        self.att(a,add(offset,mul(up,-width*.5)),parent)
        self.att(b,add(offset,mul(up,width*.5)),parent)
        return self.fx.trail(ident,parent,a,b,texture,Color=CS((0,color),(.25,color),(1,mul(color,.45))),
                             Lifetime=lifetime,MinLength=.015,MaxLength=18,FaceCamera=face,
                             WidthScale=NS((0,1),(.35,.65),(1,0)),
                             Transparency=NS((0,1-opacity),(.4,.35),(1,1)),LightEmission=emission,Brightness=1,
                             _timing={'start':start,'duration':end-start,'mode':'continuous','count':1})

    def travelling_spark(self, ident, points, start, end, color, *, texture='10976611540', size=.24,
                         width=.05, trail_color=None, curve='out', rotation=13, rot_speed=70):
        head=self.att(ident+'_head',points[0])
        self.motion(head,'bezier',points=points,start=start,duration=end-start,easing=curve,samples=41)
        self.emitter(ident+'_flake',head,texture,start,end-start,NS((0,size*.3),(.12,size),(.72,size*.55),(1,0)),color,
                     LockedToPart=True,LightEmission=.5,Brightness=1.1,rotation=rotation,rot_speed=rot_speed)
        self.trail(ident+'_trail',head,width,trail_color or color,start,end-.03,lifetime=.1,opacity=.6)

    def light(self, ident, point, color, start, end, brightness=2, radius=8):
        parent=self.att(ident+'_origin',point)
        return self.fx.light(ident,parent,start,end-start,color,radius,brightness,fall=end-start)

    def finish(self, brief, phase_cuts):
        if self.specs: self.fx.d=bake_motion(self.fx.d,self.specs)
        self.layers.insert(0,{'id':'coordinate_origin','role':'accent','purpose':'Repère spatial invisible, partagé par les couches.',
                             'phase':'anticipation','depth':'midground','nodes':['space']})
        brief={**brief,'layers':self.layers,'phases':[{'name':name,'start':phase_cuts[i],
                   'duration':phase_cuts[i+1]-phase_cuts[i],'easing':'in' if name=='charge' else 'out' if name=='dissipation' else 'linear'}
                   for i,name in enumerate(fx_artistry.PHASES)],'budget':{'particles':500,'emitters':80,'parts':80,'lights':4}}
        recipe=self.fx.to_dict()
        plan=fx_artistry.create_plan(recipe,brief)
        assert {n['id'] for n in recipe['nodes']}=={ident for layer in plan['layers'] for ident in layer['nodes']}
        return recipe,brief


def save_effect(recipe, brief, times, *, stage='v1', peak=None, render=True):
    name=recipe['id']
    folder=ROOT/'rendus'/'pro'/name
    folder.mkdir(parents=True,exist_ok=True)
    project=ROOT/'editor'/'projects'/(name+'.json')
    project.write_text(json.dumps(recipe,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (folder/('recipe-'+stage+'.json')).write_text(json.dumps(recipe,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    plan=fx_artistry.save_plan(recipe,brief)
    camera=recipe['camera']
    jobs=[{'projects':[recipe],'out':str(folder/('hero-'+stage+'.png')),'times':times,'size':'480x360',
           'backgrounds':['roblox','dark'],'camera':[*camera['position'],*camera['target']],
           'dummy':False,'seed':17,'framesDir':str(folder/('frames-'+stage))},
          {'projects':[recipe],'out':str(folder/('tower-'+stage+'.png')),'times':times,'size':'400x300',
           'camera':[12,16,20,*camera['target']],'backgrounds':['roblox','dark'],'dummy':True,'seed':17,
           'framesDir':str(folder/('tower-frames-'+stage))}]
    if peak is not None:
        jobs.append({'projects':[recipe],'out':str(folder/('peak-'+stage+'.png')),'times':[peak],
                     'size':'960x720','dummy':False,'background':'dark','seed':17})
    manifest={'effect':name,'stage':stage,'times':times,'project':str(project),'layers':plan['layers'],
              'report':fx_artistry.inspect(recipe,plan),'jobs':jobs}
    if render: manifest['renders']=fx_tools.render_batch(jobs)
    (folder/('manifest-'+stage+'.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'effect':name,'nodes':len(recipe['nodes']),'tracks':len(recipe['animations']),
                      'counts':manifest['report']['counts'],'folder':str(folder),'warnings':manifest['report']['warnings']},ensure_ascii=False))
    return manifest
