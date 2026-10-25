"""Hand-authored Enuma Elish study; no local model and no preset VFX blocks.

Timeline = reference clip minus 2.8 seconds. Textures are original procedural
drawings in draw_textures.py. The recipe remains editable in Dataky FX Studio.
"""
from pathlib import Path
import json
import math
import random
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tool.fx_builder import Recipe,NS,CS,NR
from tool.fx_schema import validate_project
from tool.fx_export import export_project
from tool.fx_rbxmx import export_rbxmx

HERE=Path(__file__).resolve().parent
TEX='rbxasset://textures/dataky-local/enuma-elish/'
RED=(1,.008,.026); CRIMSON=(.34,.001,.012); PALE=(1,.62,.64); WHITE=(1,.96,.91)
RNG=random.Random(421)
DURATION=29.4
fx=Recipe('Enuma Elish · Rupture écarlate',DURATION,ident='enuma-elish-rupture',
    camera={'position':[45,27,52],'target':[0,15,0],'fov':48},background='#090511')
fx._add({'id':'enuma','class':'Folder','name':'ENUMA ELISH · création manuelle','parent':None,'properties':{}})


def host(ident,pos=(0,0,0),size=(.1,.1,.1),**props):
    return fx.part(ident,pos,size,parent='enuma',name=ident.replace('_',' '),**props)


def anim(ident,prop,keys):
    unique={round(float(t),5):value for t,value in keys}
    fx.anim(ident,prop,sorted(unique.items()))
    if prop in {'Position','Transparency'} and any(n['id']==ident and n['class'] in {'Part','MeshPart'} for n in fx.d['nodes']):
        fx.d['animations'][-1]['runtime']=True


def emit(ident,parent,texture,at,span,rate=0,count=1,**props):
    defaults=dict(Color=CS((0,WHITE),(.25,RED),(1,CRIMSON)),
        Size=NS((0,.2),(.15,2),(1,0)),Transparency=NS((0,1),(.12,.05),(.7,.2),(1,1)),
        Lifetime=NR(.5,1),Speed=NR(0),LightEmission=.45,Brightness=2,
        Rotation=NR(-180,180),RotSpeed=NR(-30,30),SpreadAngle=[180,180])
    defaults.update(props)
    ident=fx.em(ident,parent,TEX+texture+'.png',start=at,dur=span,
        mode='continuous' if rate else 'burst',count=count,Rate=rate,**defaults)
    return ident


def axis(ident,parent,p,tangent,up=(0,1,0)):
    norm=math.sqrt(sum(v*v for v in tangent))
    x=[v/norm for v in tangent]
    d=sum(x[i]*up[i]for i in range(3)); y=[up[i]-x[i]*d for i in range(3)]
    yn=math.sqrt(sum(v*v for v in y)); y=[v/yn for v in y]
    fx.att(ident,parent,p,Axis=x,SecondaryAxis=y,Visible=False)


def beam(ident,parent,a,b,at,end,width,color=RED,curve0=0,curve1=0,bright=2,texture='ribbon',face=False,opacity=.12,speed=.7):
    fx._add({'id':ident,'class':'Beam','name':ident.replace('_',' '),'parent':parent,
        'properties':{'Attachment0':a,'Attachment1':b,'Texture':TEX+texture+'.png','Color':CS((0,color),(1,color)),
            'Transparency':NS((0,1),(.075,opacity),(.925,opacity),(1,1)),
            'Width0':width,'Width1':width*.76,'CurveSize0':curve0,'CurveSize1':curve1,
            'TextureMode':'Wrap','TextureLength':14,'TextureSpeed':speed,'FaceCamera':face,'Segments':24,
            'LightEmission':.55,'LightInfluence':0,'Brightness':bright,'Enabled':True},
        'timing':{'start':at,'duration':end-at,'mode':'continuous','count':1}})
    envelope=[(0,0),(at,0),(at+.38,width),(min(end-.25,max(at+.4,18.8)),width*1.1),
        (min(end-.18,20.5),width*1.5),(end-.1,width*.8),(end,0)]
    envelope=[(t,v)for t,v in envelope if 0<=t<=end]
    anim(ident,'Width0',envelope)
    anim(ident,'Width1',[(t,v*.76)for t,v in envelope])
    return ident


def spin(parent,at,end,speed,phase=0):
    anim(parent,'Orientation',[(0,[0,phase,0]),(at,[0,phase,0]),
        (18.5,[0,phase+(18.5-at)*speed,0]),(end,[0,phase+(18.5-at)*speed+(end-18.5)*speed*2.4,0])])


def circle(ident,r,y,at,end,width=.3,color=RED,phase=0,rate=13,halo=True):
    parent=host(ident,(0,y,0)); spin(parent,at,end,rate,phase)
    for k in range(4):
        a=k*math.tau/4
        axis(f'{ident}_p{k}',parent,[r*math.cos(a),0,r*math.sin(a)],[-math.sin(a),0,math.cos(a)])
    for k in range(4):
        a=f'{ident}_p{k}';b=f'{ident}_p{(k+1)%4}';handle=r*.55228475
        beam(f'{ident}_arc{k}',parent,a,b,at,end,width,color,handle,handle,bright=2,face=False,opacity=.12)
        if halo:beam(f'{ident}_hot{k}',parent,a,b,at,end,width*.14,WHITE,handle,handle,bright=2.1,face=True,opacity=.18)


# 0–3 s: held charge with an inward motion, brief inversion and ignition.
charge=host('01_charge_main',(1.2,3.4,0),(3,3,3))
emit('charge_coeur',charge,'glow',.25,2.1,rate=14,Lifetime=NR(.25,.4),
    Size=NS((0,.4),(.25,1.9),(1,.6)),Transparency=NS((0,.4),(.2,.12),(1,1)),
    Color=CS((0,PALE),(.3,RED),(1,CRIMSON)),Brightness=2.5,LightEmission=.7)
emit('charge_etincelles_aspirees',charge,'spark',.15,2.5,rate=25,
    Speed=NR(4,9),Shape='Sphere',ShapeStyle='Surface',ShapeInOut='Inward',
    Lifetime=NR(.3,.6),Drag=1.5,Size=NS((0,.1),(.2,.4),(1,0)),
    Orientation='VelocityParallel',Squash=NS((0,1),(1,1)),Brightness=3)
circle('charge_spirale',1.7,3.4,.4,2.75,.35,RED,rate=-100,halo=False)
flash=host('02_impact_source',(0,1.4,0))
for t,diameter in [(2.92,68),(10.22,84),(18.62,130)]:
    emit(f'impact_etoile_{str(t).replace(".","_")}',flash,'star',t,.01,count=1,Lifetime=NR(.12),
        Size=NS((0,diameter),(.25,diameter*.8),(1,0)),Transparency=NS((0,.05),(.2,.1),(1,1)),
        Brightness=4,LightEmission=.75,Color=CS((0,WHITE),(1,RED)),Rotation=NR(0),RotSpeed=NR(0))
    emit(f'impact_halo_{str(t).replace(".","_")}',flash,'glow',t,.01,count=1,Lifetime=NR(.23),
        Size=NS((0,diameter*.7),(.2,diameter),(1,diameter*1.5)),
        Transparency=NS((0,.1),(.4,.7),(1,1)),Color=CS((0,PALE),(1,RED)),LightEmission=1,Brightness=1.5)

# 3.2–28 s: the ritual seal is a custom drawn texture plus real 3D rings.
floor=host('03_sceau_sol',(0,.13,0))
emit('sceau_sigil_blanc',floor,'sigil',3.14,.01,count=1,Lifetime=NR(25.12),
    Size=NS((0,5),(.012,52),(.60,53),(.75,64),(.97,64),(1,0)),
    Transparency=NS((0,1),(.008,.07),(.65,.12),(.80,.05),(.975,.12),(1,1)),
    Color=CS((0,WHITE),(.08,PALE),(.6,PALE),(1,RED)),
    Speed=NR(.001),SpreadAngle=[0,0],EmissionDirection='Top',Orientation='VelocityPerpendicular',
    Rotation=NR(0),RotSpeed=NR(-7),LightEmission=.3,Brightness=3.0,LockedToPart=True)
emit('sceau_halo_rouge',floor,'glow',3.15,.01,count=1,Lifetime=NR(25.13),
    Size=NS((0,4),(.02,65),(.6,68),(.8,82),(1,100)),
    Transparency=NS((0,1),(.02,.3),(.7,.4),(.82,.2),(.97,.6),(1,1)),
    Color=CS((0,RED),(1,RED)),Speed=NR(.001),SpreadAngle=[0,0],Orientation='VelocityPerpendicular',
    Rotation=NR(0),RotSpeed=NR(0),LightEmission=1,Brightness=1,LockedToPart=True)
circle('sceau_bord_exterieur',27,.24,3.2,28.2,.42,PALE,rate=8)
circle('sceau_contre_rotation',22.5,.29,3.35,28.2,.28,RED,rate=-18)
circle('sceau_coeur',12,.34,3.2,28.2,.28,WHITE,rate=27,halo=False)

# Four soft arches interrupt the rigid seal and establish depth.
for n in range(4):
    parent=host(f'04_orbite_{n}',(0,2+n*.35,0))
    spin(parent,3.35,28.2,(-1 if n%2 else 1)*(27+n*7),n*83)
    r=21+n*1.4
    axis(f'o{n}_a',parent,[-r,0,0],[1,.8,0]);axis(f'o{n}_b',parent,[r,0,0],[1,-.8,0])
    beam(f'o{n}_ruban',parent,f'o{n}_a',f'o{n}_b',3.5+n*.3,28.18,1.3+n*.3,RED,r*.7,r*.7,
        bright=1.6,face=False,opacity=.35,speed=.8)

# 10.7–28 s: six helical ribbons describe a hollow, expanding vertical volume.
for n in range(6):
    parent=host(f'05_vortex_spirale_{n}')
    start=10.6+n*.21
    spin(parent,start,28.2,(-1 if n==5 else 1)*(24+n*2),n*61)
    radius=19+n*1.5; height=41+n*1.5
    turns=1.35 if n%2 else 1.6
    delta=turns*math.tau/4
    derivatives=[]
    for k in range(5):
        t=k/4; a=delta*k
        r=radius*(.72+.28*t)
        dr=radius*.28/(turns*math.tau)
        dy=height/(turns*math.tau)
        tangent=[dr*math.cos(a)-r*math.sin(a),dy,dr*math.sin(a)+r*math.cos(a)]
        axis(f'v{n}_p{k}',parent,[r*math.cos(a),1+height*t,r*math.sin(a)],tangent)
        derivatives.append(math.sqrt(sum(v*v for v in tangent)))
    for k in range(4):
        c0=derivatives[k]*(4/3)*math.tan(delta/4)
        c1=derivatives[k+1]*(4/3)*math.tan(delta/4)
        at=start+k*.32
        beam(f'v{n}_ruban_{k}',parent,f'v{n}_p{k}',f'v{n}_p{k+1}',at,28.18,
            7.5+n*.55,PALE if n in {0,3} else RED,c0,c1,bright=1.1 if n in {0,3} else .85,
            texture='ribbon_body',face=False,opacity=.42,speed=(-.4 if n%2 else .6))
        beam(f'v{n}_fil_blanc_{k}',parent,f'v{n}_p{k}',f'v{n}_p{k+1}',at+.16,28.15,
            .48+n*.04,WHITE,c0,c1,bright=2.2,face=True,opacity=.08,speed=-1.1)

# Horizontal collars roll up the outside of the cylinder.
for i,(r,y)in enumerate([(23,8),(25,20),(27.5,34)]):
    circle(f'06_couronne_{i}',r,y,11.3+i*.72,28.15,1.6+i*.35,RED,phase=i*35,rate=-27-i*9)

# Thin unstable spikes, not solid primitive columns.
for n in range(8):
    theta=n*math.tau/8+.1; r=22+RNG.uniform(-2,3)
    parent=host(f'07_dechirure_{n}')
    p0=[r*math.cos(theta),.4,r*math.sin(theta)]
    p1=[r*.75*math.cos(theta+.35),29+RNG.uniform(-5,13),r*.75*math.sin(theta+.35)]
    axis(f'e{n}_a',parent,p0,[.3,1,.2]);axis(f'e{n}_b',parent,p1,[-.2,1,.1])
    beam(f'e{n}_arc',parent,f'e{n}_a',f'e{n}_b',12+n*.13,28.1,.8,PALE,8,-6,
        bright=2.5,face=True,opacity=.27,speed=3)

# Upward particles, star accents and wisps; empty middle keeps the cage readable.
for n in range(10):
    theta=n*math.tau/10; r=RNG.uniform(12,25)
    parent=host(f'08_source_sceau_{n}',(r*math.cos(theta),.6,r*math.sin(theta)),(3,.25,3))
    emit(f'etoiles_{n}',parent,'star',3.35+n*.08,24.6-n*.08,rate=1.35,
        Lifetime=NR(.22,.5),Speed=NR(3,9),SpreadAngle=[14,14],
        Size=NS((0,0),(.12,5.5+n*.28),(.45,3),(1,0)),
        Color=CS((0,WHITE),(.45,PALE),(1,RED)),Rotation=NR(0),RotSpeed=NR(0),
        LightEmission=.55,Brightness=3,ZOffset=.15)
    emit(f'filaments_montants_{n}',parent,'spark',3.3,24.8,rate=8,
        Lifetime=NR(.5,1.2),Speed=NR(9,23),Acceleration=[0,8,0],SpreadAngle=[12,12],
        Size=NS((0,.12),(.15,.45),(.8,.3),(1,0)),Squash=NS((0,1.5),(1,2)),
        Orientation='VelocityParallel',Color=CS((0,PALE),(.5,RED),(1,CRIMSON)),
        LightEmission=.4,Brightness=2.4,Drag=.3)
    if n%2==0:
        emit(f'volutes_vortex_{n}',parent,'turbulence',10.7+n*.12,17-n*.12,rate=6,
            Lifetime=NR(.65,1.1),Speed=NR(11,20),Acceleration=[0,7,0],SpreadAngle=[20,20],
            Size=NS((0,2),(.2,9),(.8,12),(1,15)),
            Color=CS((0,WHITE),(.35,RED),(.85,CRIMSON),(1,CRIMSON)),
            Transparency=NS((0,1),(.15,.28),(.6,.5),(1,1)),
            FlipbookLayout='Grid4x4',FlipbookMode='Loop',FlipbookStartRandom=True,FlipbookFramerate=NR(18,24),
            LightEmission=.3,Brightness=1.7,Rotation=NR(-180,180),RotSpeed=NR(30,90))

# Climax: textured central energy and radial ejection, retaining red contours.
center=host('09_coeur_decharge',(0,18,0),(14,28,14))
emit('decharge_coeur_voile',center,'turbulence',18.8,9.35,rate=10,
    Lifetime=NR(.3,.55),Speed=NR(1,3),Size=NS((0,9),(.2,32),(.7,36),(1,38)),
    Color=CS((0,WHITE),(.4,PALE),(1,RED)),Transparency=NS((0,1),(.1,.18),(.65,.32),(1,1)),
    FlipbookLayout='Grid4x4',FlipbookMode='Loop',FlipbookStartRandom=True,FlipbookFramerate=NR(24,32),
    LightEmission=.7,Brightness=2.4,Rotation=NR(-8,8),RotSpeed=NR(0),Squash=NS((0,.9),(1,.9)),Orientation='FacingCameraWorldUp')
emit('decharge_eclats_radiaux',center,'spark',18.8,9.25,rate=28,
    Lifetime=NR(.2,.6),Speed=NR(38,74),SpreadAngle=[180,180],
    Size=NS((0,.35),(.1,1.2),(1,0)),Squash=NS((0,2),(1,2)),Orientation='VelocityParallel',
    Color=CS((0,WHITE),(.55,PALE),(1,RED)),Brightness=3.2,LightEmission=.6,Drag=.4)
for n in range(3):
    parent=host(f'10_voile_central_{n}',(0,0,0));angle=n*math.tau/3
    axis(f'c{n}_a',parent,[math.cos(angle)*3,2,math.sin(angle)*3],[0,1,.1])
    axis(f'c{n}_b',parent,[-math.cos(angle)*2,49,-math.sin(angle)*2],[.1,1,0])
    beam(f'c{n}_decharge',parent,f'c{n}_a',f'c{n}_b',18.85+n*.08,28.16,14+n*3,
        PALE if n else WHITE,7,-7,bright=2.2,texture='ribbon_body',face=True,opacity=.20,speed=2.1+n*.3)
# Discrete crescent wisps disrupt the mechanical coils around the hot centre.
for n in range(4):
    parent=host(f'11_faille_vent_{n}',(0,7+n*9,0),(12,3,12))
    emit(f'dechirures_blanches_{n}',parent,'wind',12+n*.55,16-n*.55,rate=4,
        Lifetime=NR(.45,.8),Speed=NR(2,5),SpreadAngle=[20,20],
        Size=NS((0,4),(.18,18+n*2),(.75,26+n*2),(1,30+n*2)),
        Color=CS((0,WHITE),(.35,PALE),(.7,RED),(1,CRIMSON)),
        Transparency=NS((0,1),(.12,.15),(.55,.32),(1,1)),
        LightEmission=.5,Brightness=2.6,RotSpeed=NR(60,125))
emit('decharge_noyau_diffus',center,'glow',18.8,9.2,rate=6,
    Lifetime=NR(.25,.5),Speed=NR(0),SpreadAngle=[0,0],
    Size=NS((0,20),(.3,31),(1,34)),Squash=NS((0,.85),(1,.85)),
    Color=CS((0,WHITE),(.6,PALE),(1,RED)),Transparency=NS((0,1),(.12,.15),(.6,.35),(1,1)),
    LightEmission=1,Brightness=2.2,Rotation=NR(0),RotSpeed=NR(0),Orientation='FacingCameraWorldUp')
fx.light('lumiere_charge',charge,.3,2.45,RED,12,2,fall=2.3)
fx.light('lumiere_sceau',floor,3.2,25,RED,55,3.2,fall=24.7)
fx.light('lumiere_decharge',center,18.8,9.35,PALE,60,7,fall=9.2)

# A sharp final cut is part of the reference; stop emitters early enough for
# existing particles to die before it, then collapse the long-lived seal.
for node in fx.d['nodes']:
    if node['class']=='ParticleEmitter' and node.get('timing',{}).get('mode')=='continuous':
        end=node['timing']['start']+node['timing']['duration']
        if end>27.2:
            tail=max(node['properties'].get('Lifetime',[1,1]))
            node['timing']['duration']=max(0,28.18-tail-node['timing']['start'])
project=validate_project(fx.d)
projects=ROOT/'editor/projects'; projects.mkdir(exist_ok=True)
(projects/'enuma-elish-rupture.json').write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
exports=HERE/'exports';exports.mkdir(exist_ok=True)
(exports/'Enuma-Elish.json').write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
(exports/'Enuma-Elish.lua').write_text(export_project(project),encoding='utf-8')
(exports/'Enuma-Elish.rbxmx').write_text(export_rbxmx(project),encoding='utf-8')
(HERE/'manifest.json').write_text(json.dumps({'author':'Codex, handwritten data and generators; no local inference',
    'reference_offset_seconds':2.8,'duration':DURATION,'nodes':len(project['nodes']),'animations':len(project['animations']),
    'texture_uri_prefix':TEX,'publishing_status':'Local Studio textures; upload originals to publish to other players',
    'layers':['held charge','ritual seal','counterrotating textured rings','six rising helical ribbons','sparks and four-point glints','red-white discharge']},
    ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'project':str(projects/'enuma-elish-rupture.json'),'nodes':len(project['nodes']),'animations':len(project['animations']),
    'duration':DURATION,'texture_files':sorted({n.get('properties',{}).get('Texture','').split('/')[-1]for n in project['nodes']if n['class']in{'Beam','ParticleEmitter'}})}))
