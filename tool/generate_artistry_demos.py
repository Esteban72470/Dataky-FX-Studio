"""Reproduce three directed VFX studies, their plans and optional render sheets.

    python -m tool.generate_artistry_demos --render

Recipes contain native Roblox objects and baked numeric tracks only. The small
solid cores, feather and shards are intentional geometric accents; ribbons and
curved beams carry the motion. No generated image or unverified flipbook needed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
import math
from pathlib import Path

if __package__:
    from .fx_builder import Recipe, CS, NS, NR
    from .fx_motion import bake_motion
    from .fx_schema import validate_project
    from . import fx_artistry, fx_tools
else:
    from fx_builder import Recipe, CS, NS, NR
    from fx_motion import bake_motion
    from fx_schema import validate_project
    import fx_artistry
    import fx_tools

ROOT = Path(__file__).resolve().parent.parent
AZURE, ICE, NAVY = [0.08, .61, 1], [.76, .96, 1], [.025, .10, .22]
AMBER, CREAM, PETROL = [1, .55, .09], [1, .91, .61], [.025, .24, .27]
VIOLET, IVORY, INK = [.57, .27, 1], [1, .93, .77], [.115, .055, .23]
THIN_CRESCENT = "rbxassetid://17388368201"
TRIPLE_CRESCENT = "rbxassetid://14242056438"
STAR = "rbxassetid://73245886600206"
FINE_STAR = "rbxassetid://110719867330869"


class Study:
    def __init__(self, ident, title, duration, camera):
        self.fx = Recipe(title, duration, camera, ident=ident, background="#101a29")
        self.layers = []

    @contextmanager
    def layer(self, ident, role, purpose, phase, depth):
        before = len(self.fx.d["nodes"])
        yield
        self.layers.append({"id": ident, "role": role, "purpose": purpose, "phase": phase,
                            "depth": depth, "nodes": [n["id"] for n in self.fx.d["nodes"][before:]]})

    def motion(self, **spec):
        self.fx.d = bake_motion(self.fx.d, spec)

    def track(self, node, prop, keys):
        self.fx.anim(node, prop, keys)
        cls = next(n["class"] for n in self.fx.d["nodes"] if n["id"] == node)
        if cls in ("Part", "MeshPart") and prop in ("Position", "Transparency"):
            self.fx.d["animations"][-1]["runtime"] = True

    def show(self, node, start, end, transparency=0, fade=.12):
        keys = [(0, 1)] if start > 0 else []
        keys += [(start, 1), (start + .012, transparency), (max(start+.013, end-fade), transparency), (end, 1)]
        self.track(node, "Transparency", keys)

    def body(self, ident, pos, size, color, start, end, *, shape="Ball", ori=(0, 0, 0), transparency=0, neon=False):
        self.fx.part(ident, pos, size, Color=color, Shape=shape, Orientation=list(ori),
                     Material="Neon" if neon else "SmoothPlastic")
        self.show(ident, start, end, transparency)
        return ident

    def beam(self, ident, parent, first, last, color, width, start, end, *, curve=(0, 0),
             axes=((1, 0, 0), (1, 0, 0)), tip=.04, emission=.6, transparency=.08):
        a, b = ident + "_a", ident + "_b"
        self.fx.att(a, parent, first, Axis=list(axes[0]))
        self.fx.att(b, parent, last, Axis=list(axes[1]))
        self.fx.d["nodes"].append({"id": ident, "class": "Beam", "name": ident, "parent": parent,
            "properties": {"Attachment0": a, "Attachment1": b, "Color": CS((0,color),(1,color)),
                "Width0": width, "Width1": tip, "CurveSize0": curve[0], "CurveSize1": curve[1],
                "Segments": 28, "FaceCamera": True, "LightEmission": emission, "LightInfluence": 0,
                "Texture": "", "Brightness": 1, "Transparency": NS((0,transparency),(1,.55))},
            "timing": {"start": start, "duration": end-start, "mode": "continuous", "count": 1}})
        for prop, peak in (("Width0", width), ("Width1", tip)):
            self.track(ident, prop, [(start,0), (start+.025,peak), (end-.065,peak*.45), (end,0)])

    def ribbon(self, ident, parent, offset, width, color, start, end, *, lifetime=.28, opacity=.15):
        a, b = ident+"_a", ident+"_b"
        self.fx.att(a, parent, [offset[0],offset[1]-width/2,offset[2]])
        self.fx.att(b, parent, [offset[0],offset[1]+width/2,offset[2]])
        self.fx.trail(ident, parent, a, b, Color=CS((0,color),(1,color)),
                      Lifetime=lifetime, MinLength=.015, MaxLength=7, WidthScale=NS((0,1),(1,.05)),
                      Transparency=NS((0,opacity),(.65,.45),(1,1)), LightEmission=.5, Brightness=1,
                      _timing={"start":start,"duration":end-start,"mode":"continuous","count":1})

    def glint(self, ident, parent, start, color, *, size=.85, texture=STAR, count=1, life=.22):
        self.fx.em(ident, parent, texture, start=start, count=count, Lifetime=NR(life),
                   Size=NS((0,size*.35),(.18,size),(1,0)), Transparency=NS((0,.1),(.4,.15),(1,1)),
                   Color=CS((0,color),(1,color)), LightEmission=.65, Brightness=1,
                   Rotation=NR(15), Speed=NR(0), ZOffset=.04)

    def fragments(self, prefix, point, direction, color, start, count=4):
        for i in range(count):
            drift = [(i-(count-1)/2)*.23, (i%2)*.25-.1, (i%3-1)*.3]
            first = [point[j]+drift[j]*.3 for j in range(3)]
            last = [point[j]+direction[j]*(.75+.24*i)+drift[j] for j in range(3)]
            node = self.body(prefix+str(i), first, [.12+.03*i,.33+.06*i,.10], color,
                             start, start+.55, shape="Block", ori=(15*i,20,25+19*i))
            self.motion(node=node,type="arc",start=start,duration=.47,**{"from":first,"to":last},
                        height=.35+.08*i,samples=31,easing="out")
            self.motion(node=node,type="spin",start=start,duration=.5,axis="z",degrees=75+20*i,samples=21)

    def finish(self, brief, cuts, times):
        # Visual revision after the first contact sheets: readable close framing,
        # tapered fragments and meaningful depth, rather than more global glow.
        camera = self.fx.d['camera']
        camera['position'] = [3.4, 6.2, 12.8]
        camera['fov'] = 47
        for node in self.fx.d['nodes']:
            if node['class'] == 'Part' and any(token in node['id'] for token in ('chip', 'shard', 'flake')):
                self.motion(node=node['id'], type='tween', property='Size',
                            **{'from': node['properties']['Size'], 'to': [.015, .04, .015]},
                            start=1.3 if 'chip' in node['id'] else 1.65 if 'shard' in node['id'] else 1.93,
                            duration=.3, samples=21, easing='in')
        names = fx_artistry.PHASES
        brief = {**brief,"layers":self.layers,"phases":[{"name":name,"start":cuts[i],"duration":cuts[i+1]-cuts[i],
                    "easing":("in" if name=="charge" else "out" if name in ("impact","dissipation") else "linear")}
                    for i,name in enumerate(names)],"budget":{"particles":100,"emitters":12,"lights":3,"parts":40}}
        project = self.fx.to_dict()
        plan = fx_artistry.create_plan(project,brief)
        assigned = [n for layer in plan["layers"] for n in layer["nodes"]]
        assert set(assigned)=={n["id"] for n in project["nodes"]}, "Every node needs an artistic role"
        return {"project":project,"brief":brief,"times":times}


def slash_azure():
    s = Study("artistry-slash-azur", "Étude A · Lame de marée", 2.45,
              {"position":[10,8,18],"target":[.2,3,0],"fov":43})
    with s.layer("setup", "accent", "Supports invisibles et anticipation orientée vers le point de coupe.", "anticipation", "background"):
        s.fx.part("space",size=(.05,.05,.05))
        s.beam("drawback","space",[-4.2,1.5,-.1],[-3.3,2.5,-.1],AZURE,.13,.08,.47,curve=(.7,.5),axes=((0,1,0),(1,1,0)))
        s.fx.att("grip","space",[-4,1.6,0])
        s.glint("charge_tip","grip",.32,ICE,size=.45,texture=FINE_STAR,life=.2)
    path = [[-4,1.6,0],[-2.8,6.1,-1.15],[1.2,6,.7],[4.1,2.8,0]]
    with s.layer("blade", "primary", "Trois rubans inégaux dessinent une seule lame courbe ; une pointe solide fixe sa direction.", "release", "midground"):
        s.body("blade_tip",path[0],[.24,.56,.22],ICE,.48,1.17,neon=True)
        s.motion(node="blade_tip",type="bezier",points=path,start=.48,duration=.59,samples=91,easing="in")
        s.motion(node="blade_tip",type="spin",axis="z",degrees=-125,start=.48,duration=.59,samples=45)
        s.ribbon("navy_back","blade_tip",[0,0,-.13],.92,NAVY,.49,1.08,lifetime=.31,opacity=.1)
        s.ribbon("azure_edge","blade_tip",[0,0,0],.51,AZURE,.49,1.08,lifetime=.29,opacity=.04)
        s.ribbon("ice_hairline","blade_tip",[.08,.19,.12],.11,ICE,.5,1.07,lifetime=.25,opacity=.04)
    with s.layer("crescent", "secondary", "Un seul accent de croissant prolonge la lame sans remplacer sa trajectoire volumétrique.", "release", "foreground"):
        s.fx.att("blade_center","space",[-.1,3.85,.2])
        s.fx.em("crescent_texture","blade_center",THIN_CRESCENT,start=.79,count=1,Lifetime=NR(.24),
                 Size=NS((0,2.4),(.24,3.5),(1,3.8)),Color=CS((0,AZURE),(1,ICE)),
                 Transparency=NS((0,.16),(.4,.28),(1,1)),Rotation=NR(-37),LightEmission=.5,Squash=NS((0,.4),(1,.7)))
        # The earlier detached crescent read as a second attack. A short, locked
        # curl now hugs the moving tip and turns with the slash.
        s.fx.d['nodes'][-1]['parent'] = 'blade_tip'
        s.fx.d['nodes'][-1]['properties'].update(LockedToPart=True, Size=NS((0,1.2),(.3,2.0),(1,1.5)), Rotation=NR(30))
        s.ribbon('outer_whip','blade_tip',[-.18,.5,-.45],.12,AZURE,.54,1.09,lifetime=.19,opacity=.2)
        s.ribbon('inner_whip','blade_tip',[.12,-.4,.38],.07,ICE,.58,1.09,lifetime=.22,opacity=.13)
    with s.layer("pinch", "primary", "Impact pincé au bout du parcours : deux arêtes convergent vers un petit foyer, sans anneau radial.", "impact", "foreground"):
        hit=[4.1,2.8,0]
        s.fx.att("hit","space",hit)
        s.body("impact_needle",hit,[.16,1.25,.20],ICE,1.065,1.34,neon=True,ori=(0,0,-35))
        s.motion(node="impact_needle",type="squash",start=1.07,duration=.22,axis="y",amount=1.8,samples=25)
        s.beam("pinch_upper","space",[3,4.2,.06],hit,AZURE,.38,1.06,1.44,curve=(1.2,.4),axes=((1,-.2,0),(1,-1,0)))
        s.beam("pinch_lower","space",[2.8,1.6,-.06],hit,ICE,.19,1.075,1.39,curve=(1,.4),axes=((1,.2,0),(1,1,0)))
        s.glint("hit_star","hit",1.07,ICE,size=1.0,life=.22)
        s.fx.em('directed_spray','hit',FINE_STAR,start=1.08,count=12,Lifetime=NR(.18,.36),
                Speed=NR(6,16),EmissionDirection='Right',SpreadAngle=[18,28],Drag=5,
                Size=NS((0,.25),(.2,.42),(1,0)),Squash=NS((0,-2),(1,0)),Orientation='VelocityParallel',
                Color=CS((0,ICE),(1,AZURE)),Transparency=NS((0,.05),(1,1)),LightEmission=.7)
        s.fx.light("hit_light","hit",1.07,.18,AZURE,5,1.1)
    with s.layer("chips", "secondary", "Quatre copeaux poursuivent la direction de coupe et séparent les profondeurs.", "secondary", "background"):
        s.fragments("ice_chip",[4.1,2.8,0],[1,.1,0],AZURE,1.12)
    return s.finish({"theme":"Une coupe aquatique précise, vitesse croissante puis arrêt pincé.","palette":[NAVY,AZURE,ICE],
        "silhouette":"Arc en croissant ouvert vers la droite ; trois épaisseurs inégales ; impact vertical court.",
        "motion":"Retrait, Bézier accéléré montant puis descendant, mémoire courte des trails et fragments vers l'avant.",
        "character":"Duelliste de marée : attaque dirigée d'une unité TD, pas une compétence de zone.",
        "readability":"Le liseré ivoire guide l'œil, le dos marine détache la lame sur sol clair. Le trajet ne dépasse pas neuf studs.",
        "focal":[4.1,2.8,0],"power":3},[0,.25,.48,1.07,1.36,1.8,2.45],[.3,.62,.82,1.03,1.12,1.33,1.6,2.2])


def projectile_amber():
    s=Study("artistry-projectile-ambre", "Étude B · Comète à gyres",2.6,
             {"position":[11,7.5,18],"target":[.2,3.05,0],"fov":43})
    path=[[-4.2,2.3,0],[-2.4,5,-1.2],[1.6,3.1,1.25],[4.2,2.5,0]]
    with s.layer("launch", "accent", "Deux griffes de charge pointent l'unique trajectoire de tir.", "charge", "background"):
        s.fx.part("space",size=(.05,.05,.05))
        for i,side in enumerate((-1,1)):
            s.beam("charge_claw"+str(i),"space",[-4.7,2.3+side*.75,-.15],path[0],PETROL,.24,.12,.53,
                   curve=(1,.45),axes=((1,-side,0),(1,-side*.2,0)))
        s.fx.att("launch_point","space",path[0])
        s.glint("launch_glint","launch_point",.44,AMBER,size=.6,life=.24)
    with s.layer("core", "primary", "Noyau pétrole solide et iris ambre excentré : une comète identifiable même sans les particules.", "release", "midground"):
        for ident,size,color,offset,neon in (("comet",[1.18,.82,.82],PETROL,[0,0,0],False),
                ("amber_iris",[.77,.47,.32],AMBER,[.12,0,.33],True),
                ("hot_needle",[1.05,.12,.16],CREAM,[.16,0,.50],True)):
            points=[[v+offset[j] for j,v in enumerate(p)] for p in path]
            s.body(ident,points[0],size,color,.46,1.52,neon=neon)
            s.motion(node=ident,type="bezier",points=points,start=.48,duration=.94,samples=111,easing="inOut")
        s.ribbon("comet_tail","comet",[-.3,0,.08],.34,AMBER,.49,1.43,lifetime=.28,opacity=.12)
        s.ribbon("comet_darkwake","comet",[-.45,0,-.25],.60,PETROL,.49,1.43,lifetime=.32,opacity=.18)
    with s.layer("gyres", "secondary", "Deux orbites déphasées de 180 degrés autour du noyau donnent un volume hélicoïdal lisible.", "release", "foreground"):
        for i,phase in enumerate((0,180)):
            parent="satellite"+str(i)
            s.fx.att(parent,"comet",[-.18,.75,0])
            s.motion(node=parent,type="orbit",center=[-.18,0,0],axis="x",radius=.78,end_radius=.48,
                     start_angle=phase,turns=1.8,start=.48,duration=.94,samples=121)
            s.ribbon("gyre_trail"+str(i),parent,[0,0,0],.18,AMBER if i==0 else [.10,.63,.62],.49,1.43,lifetime=.22,opacity=.08)
            s.fx.em("gyre_bead"+str(i),parent,FINE_STAR,start=.5,mode="continuous",dur=.88,
                     Rate=11,Lifetime=NR(.10),Size=NS((0,.17),(1,.07)),Transparency=NS((0,.08),(1,1)),
                     Color=CS((0,CREAM if i==0 else [.10,.63,.62]),(1,AMBER if i==0 else PETROL)),
                     LockedToPart=True,LightEmission=.5)
    with s.layer("impact", "primary", "L'iris se comprime en lentille ; deux jets se referment sur le point touché.", "impact", "foreground"):
        hit=path[-1]
        s.fx.att("hit","space",hit)
        s.body("impact_lens",hit,[.23,1.0,.72],AMBER,1.42,1.71,neon=True)
        s.motion(node="impact_lens",type="squash",axis="x",amount=.25,start=1.42,duration=.22,samples=31)
        for i,side in enumerate((-1,1)):
            s.beam("closing_jet"+str(i),"space",[3.0,2.5+side*1.05,.2*side],hit,
                   AMBER if i==0 else PETROL,.30,1.42,1.82,curve=(1.1,.7),axes=((1,-side*.3,0),(1,side,0)),tip=.025)
        s.glint("hit_punctum","hit",1.43,CREAM,size=1.1,life=.23)
        s.fx.em('forward_embers','hit',STAR,start=1.44,count=14,Lifetime=NR(.22,.45),Speed=NR(3,10),
                EmissionDirection='Right',SpreadAngle=[22,32],Drag=3,Acceleration=[0,-4,0],
                Size=NS((0,.16),(.18,.28),(1,0)),Color=CS((0,CREAM),(1,AMBER)),
                Transparency=NS((0,.05),(1,1)),LightEmission=.7)
        s.fx.light("hit_light","hit",1.43,.2,AMBER,5,1.2)
    with s.layer("shards", "secondary", "Éclats courts alignés avec le tir ; la dissipation évite une boule d'explosion.", "secondary", "background"):
        s.fragments("amber_shard",path[-1],[1,.1,0],AMBER,1.49,count=5)
    return s.finish({"theme":"Projectile mécanique magique, ambre chaud enveloppé de pétrole.","palette":[PETROL,[.10,.63,.62],AMBER,CREAM],
        "silhouette":"Petite amande sombre à iris chaud, deux gyres opposés et une queue courte, impact en lentille.",
        "motion":"Vol cubique Bézier d'une seconde ; deux orbites locales déphasées ; compression à l'arrivée et éclats vers l'avant.",
        "character":"Artilleur des marées : tir unique d'une tourelle TD dont le noyau identifie le projectile.",
        "readability":"Le pétrole porte la masse, l'ambre marque la direction. Les gyres ne masquent jamais totalement l'iris ; impact limité au bout du parcours.",
        "focal":[4.2,2.5,0],"power":3},[0,.22,.48,1.42,1.72,2.04,2.6],[.3,.65,.92,1.20,1.43,1.60,1.86,2.35])


def _staged_path(study, node, stages, offset=(0,0,0)):
    """Bake each step through the shared compiler, then join holds in one track."""
    frames=[]
    for start,duration,points in stages:
        shifted=[[value+offset[j] for j,value in enumerate(point)] for point in points]
        baked=bake_motion(study.fx.d,{"node":node,"type":"bezier","start":start,"duration":duration,
                                     "points":shifted,"samples":31,"easing":"inOut","replace":True})
        keys=next(a["keyframes"] for a in baked["animations"] if a["node"]==node and a["property"]=="Position")
        # A duplicate position at the next stage start produces the explicit hold.
        frames.extend(k for k in keys if not frames or k["time"]>frames[-1]["time"])
    study.track(node,"Position",[(key["time"],key["value"]) for key in frames])


def calligrapher_astral():
    s=Study("artistry-calligraphe-astral", "Étude C · Calligraphe astral — Signature ascendante",2.8,
            {"position":[10,8,18],"target":[.0,3.1,0],"fov":44})
    stages=[(.38,.22,[[-3.8,1.35,0],[-3.6,2.0,-.2],[-2.9,2.9,-.1],[-2.2,2.9,0]]),
            (.72,.23,[[-2.2,2.9,0],[-1.8,2.75,.1],[-1.1,4.1,.1],[-.4,4.1,0]]),
            (1.08,.25,[[-.4,4.1,0],[0,4.0,-.15],[.8,5.2,-.1],[1.6,5.2,0]]),
            (1.52,.20,[[1.6,5.2,0],[2.4,4.8,.2],[3.4,3.1,.15],[3.6,2.5,0]])]
    with s.layer("ink_setup", "accent", "Deux filaments d'encre rentrent dans la plume avant l'écriture.", "anticipation", "background"):
        s.fx.part("space",size=(.05,.05,.05))
        for i,side in enumerate((-1,1)):
            s.beam("ink_feed"+str(i),"space",[-4.6,1.1+side*.45,-.2],[-3.8,1.4,0],VIOLET,.12,.06,.43,
                   curve=(.55,.35),axes=((1,side,0),(1,-side,0)),tip=.025)
    with s.layer("quill", "primary", "Une plume ivoire à nervure sombre et six barbes violettes avance par trois paliers puis pique la cible.", "release", "midground"):
        pieces=[("quill_spine",[.12,1.50,.10],IVORY,[0,.45,0],(0,0,-32))]
        for i in range(6):
            y=-.04+i*.18
            side=-1 if i%2 else 1
            # Place the barbs on the tilted shaft instead of floating alongside.
            pieces.append(("quill_barb"+str(i),[.11,.52-.035*i,.07],VIOLET if i%2 else IVORY,
                           [.53*y+side*.13,.45+.85*y,.015],(0,0,-32+side*64)))
        for ident,size,color,offset,ori in pieces:
            start=[stages[0][2][0][j]+offset[j] for j in range(3)]
            s.body(ident,start,size,color,.19,1.82,shape="Block",ori=ori,neon=False)
            _staged_path(s,ident,stages,offset)
        s.ribbon("quill_hairline","quill_spine",[0,-.6,.04],.10,IVORY,.39,1.73,lifetime=.17,opacity=.05)
        s.ribbon("violet_inkwake","quill_spine",[0,-.6,-.08],.28,VIOLET,.39,1.73,lifetime=.28,opacity=.17)
    with s.layer("ascending_letters", "secondary", "Trois virgules distinctes montent en escalier ; chaque trait a un dos d'encre et un filet ivoire.", "release", "background"):
        strokes=[([ -3.8,1.35,-.18],[-2.2,2.9,-.18],.41,.98),
                 ([-2.2,2.9,-.18],[-.4,4.1,-.18],.76,1.35),
                 ([-.4,4.1,-.18],[1.6,5.2,-.18],1.12,1.70)]
        for i,(first,last,start,end) in enumerate(strokes):
            s.beam("letter_ink"+str(i),"space",first,last,INK,.44,start,end,
                   curve=(1.2,.8),axes=((1,-.4,0),(1,.1,0)),tip=.04,emission=0,transparency=.04)
            s.beam("letter_violet"+str(i),"space",[first[0],first[1],-.08],[last[0],last[1],-.08],VIOLET,.23,start+.01,end,
                   curve=(1.2,.8),axes=((1,-.4,0),(1,.1,0)),tip=.025,emission=.5)
            s.fx.att("letter_stop"+str(i),"space",last)
            s.glint("letter_dot"+str(i),"letter_stop"+str(i),start+.18,IVORY,size=.45,texture=FINE_STAR,life=.18)
            s.fx.em('ink_dust'+str(i),'letter_stop'+str(i),FINE_STAR,start=start+.18,count=3,
                    Lifetime=NR(.2,.38),Speed=NR(.8,2.5),Acceleration=[0,-1,0],SpreadAngle=[25,40],
                    Size=NS((0,.14),(.2,.24),(1,0)),Color=CS((0,IVORY),(1,VIOLET)),
                    Transparency=NS((0,.1),(1,1)),LightEmission=.6)
    with s.layer("final_cut", "primary", "Coupe finale étroite, oblique et dirigée : la signature pique une cible précise.", "impact", "foreground"):
        s.beam("signature_cut","space",[1.6,5.2,.12],[3.6,2.5,.12],IVORY,.26,1.54,1.95,
               curve=(.8,.5),axes=((1,-.4,0),(.2,-1,0)),tip=.02)
        s.beam("signature_shadow","space",[1.6,5.2,-.10],[3.6,2.5,-.10],VIOLET,.52,1.54,2.03,
               curve=(.8,.5),axes=((1,-.4,0),(.2,-1,0)),tip=.04,emission=.2)
        s.fx.att("punctum","space",[3.6,2.5,.2])
        s.glint("terminal_star","punctum",1.72,IVORY,size=.90,life=.19)
        s.body("terminal_nib",[3.6,2.5,.1],[.12,.82,.10],IVORY,1.7,1.94,shape="Block",ori=(0,0,-32))
        s.fx.light("ink_light","punctum",1.72,.15,VIOLET,4.0,.9)
    with s.layer("ink_flakes", "accent", "Trois éclats d'encre tombent en aval de la ponctuation ; aucun cercle de zone.", "secondary", "background"):
        s.fragments("ink_flake",[3.6,2.5,0],[.6,-.5,0],VIOLET,1.78,count=3)
    return s.finish({"theme":"L'attaque originale du Calligraphe astral : écrire trois paliers puis signer d'une coupe unique.","palette":[INK,VIOLET,IVORY],
        "silhouette":"Plume étroite, trois virgules en escalier et dernière diagonale descendante. Pas d'explosion AOE.",
        "motion":"Quatre segments Bézier avec pauses visibles à .60–.72, .95–1.08 et 1.33–1.52 ; piqué final en .20 seconde.",
        "character":"Calligraphe astral, tour de soutien offensif TD. Chaque palier inscrit une marque ; la signature consomme les trois marques.",
        "readability":"Les traits ne s'allument pas tous au même instant. L'ivoire reste concentré sur la plume et la coupe ; l'encre foncée cadre le violet sur sol clair.",
        "focal":[3.6,2.5,0],"power":3},[0,.19,.38,1.72,1.95,2.22,2.8],[.25,.51,.84,1.22,1.59,1.76,1.98,2.50])


def build_demos():
    return [slash_azure(),projectile_amber(),calligrapher_astral()]


def write_demos(*, render=False):
    demos=build_demos()
    outputs=[]
    jobs=[]
    for demo in demos:
        project=demo["project"]
        target=ROOT/"editor"/"projects"/(project["id"]+".json")
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(project,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        plan=fx_artistry.save_plan(project,demo["brief"])
        stats=fx_artistry.inspect(project,plan)
        outputs.append({"id":project["id"],"project":str(target),"plan":str(fx_artistry.location("plans",plan["id"])),
                        "counts":stats["counts"],"diagnostics":stats["diagnostics"]})
        jobs.append({"projects":[project],"out":str(ROOT/"rendus"/"demos"/(project["id"]+".png")),
                     "times":demo["times"],"size":"480x320","columns":4,"dummy":False,
                     "backgrounds":["roblox","dark"],"ground":True,"seed":7})
        camera=deepcopy(project["camera"])
        camera["position"]=[camera["position"][0]+3,camera["position"][1]+4,-14]
        jobs.append({"projects":[project],"out":str(ROOT/"rendus"/"demos"/(project["id"]+"-reverse.png")),
                     "times":[demo["times"][2],demo["times"][4],demo["times"][5]],
                     "size":"480x320","columns":3,"dummy":False,"backgrounds":["roblox","dark"],
                     "camera":[*camera["position"],*camera["target"]],"ground":True,"seed":7})
    manifest={"generator":"python -m tool.generate_artistry_demos --render","outputs":outputs,"jobs":jobs}
    dest=ROOT/"rendus"/"demos"/"manifest.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    if render:
        manifest["renders"]=fx_tools.render_batch(jobs)
    dest.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render",action="store_true",help="Render two viewpoints and two backgrounds through the existing emulator")
    args=parser.parse_args()
    result=write_demos(render=args.render)
    print(json.dumps({"outputs":result["outputs"],"rendered":bool(args.render)},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
