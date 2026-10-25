"""Author CelestialRiftSlash in Dataky's existing editable recipe format."""
import argparse
import math
if __package__:
    from .pro_vfx import Effect, NS, add, mul, bezier, save_effect
else:
    from pro_vfx import Effect, NS, add, mul, bezier, save_effect

BLUE=[.07,.40,1]
VIOLET=[.29,.045,.72]
INK=[.025,.006,.085]
WHITE=[.76,.91,1]
ELECTRIC='rbxassetid://9632171388'
OUTLINE='rbxassetid://9754641205'
ENERGY='rbxassetid://15507852294'


def build():
    e=Effect('CelestialRiftSlash',1.10,{'position':[7.5,8,18],'target':[.1,3.9,0],'fov':45})
    curve=[[-5.8,2.2,.2],[-5.8,8.5,-1.0],[1.7,9.2,1.1],[5.6,2.8,.1]]
    with e.layer('inward_anticipation','secondary','Huit aiguilles suivent des courbes vers le foyer avant la coupe.','anticipation','background'):
        for i in range(8):
            a=i*2.399
            first=[-2.3+math.cos(a)*(1.5+i*.16),3.2+math.sin(a)*(1.4+i*.12),math.sin(a*2)*1.1]
            target=[-2.3,3.2,0]
            e.travelling_spark('inward_'+str(i),[first,add(first,[.4,.5,.4]),[-2.8,3.7,.2],target],
                              .015+i*.009,.20,WHITE if i%3==0 else BLUE,texture='10976611540',size=.32,width=.075,curve='in')
        e.beam('unstable_line',[[-2.9,1.8,0],[-2.3,3,.25],[-2.8,3.8,-.2],[-1.8,4.7,0]],
               VIOLET,[.03,.06],.055,.24,texture=ELECTRIC,up=[1,0,0],opacity=.85,emission=.5,brightness=1.3)
        e.att('gather',[-2.3,3.2,.05])
        e.emitter('gather_flicker','gather','91804820881066',.12,.14,.7,BLUE,rotation=23,LightEmission=.6,Brightness=1.5)
    with e.layer('celestial_rift_body','primary','Une lame courbe en 3D : enveloppe violette, ciel bleu et vide sombre effilé.','release','midground'):
        e.curved_strip('outer_violet',curve,VIOLET,2.4,.202,.72,pieces=7,sweep=.083,texture=ENERGY,depth=-.26,opacity=.8,emission=.28,brightness=1.1)
        e.curved_strip('blue_mass',curve,BLUE,2.2,.208,.67,pieces=7,sweep=.083,texture=ENERGY,depth=-.06,opacity=.8,emission=.18,brightness=1.2)
        e.curved_strip('void_core',curve,INK,.12,.218,.65,pieces=7,sweep=.08,depth=.035,opacity=.8,emission=0,brightness=1)
        e.curved_strip('split_contours',curve,WHITE,.50,.212,.61,pieces=7,sweep=.083,texture=OUTLINE,depth=.10,opacity=.9,emission=.25,brightness=1.2)
        white_curve=[add(p,[0,.16,.17]) for p in curve]
        e.curved_strip('hot_seam',white_curve,WHITE,.045,.22,.58,pieces=7,sweep=.083,opacity=.98,emission=.25,brightness=1.4)
        e.att('painted_tear',[0,1.6,.15])
        e.emitter('violet_torn_back','painted_tear','17388417211',.205,.52,
                  NS((0,5),(.14,14.1),(.5,14.4),(1,15.4)),VIOLET,rotation=-75,
                  transparency=NS((0,.7),(.13,.15),(.5,.30),(1,1)),speed=.001,
                  Orientation='VelocityPerpendicular',EmissionDirection='Back',LightEmission=.10,Brightness=1.2)
        e.att('painted_lip',[0,1.6,.40])
        e.emitter('blue_torn_lip','painted_lip','17388416918',.217,.43,
                  NS((0,5),(.14,13.6),(.6,13.9),(1,14.7)),BLUE,rotation=-75,
                  transparency=NS((0,.65),(.13,.06),(.6,.17),(1,1)),speed=.001,
                  Orientation='VelocityPerpendicular',EmissionDirection='Back',LightEmission=.18,Brightness=1.4)
    with e.layer('following_cut','secondary','Deuxième entaille plus fine décalée dans le temps et en profondeur.','release','background'):
        second=[[-3.6,2.8,-1.25],[-.8,8.2,-.7],[4.6,8.6,-1.6],[6.8,4.4,-.8]]
        e.curved_strip('second_cut',second,VIOLET,.26,.255,.66,pieces=5,sweep=.07,texture=ELECTRIC,opacity=.9,emission=.45,brightness=1.6)
        e.curved_strip('second_needle',second,BLUE,.07,.268,.60,pieces=5,sweep=.06,opacity=.9,emission=.35,brightness=1.1)
    with e.layer('release_flash','accent','Flash asymétrique de deux images : le blanc ne doit pas recouvrir toute la lame.','release','foreground'):
        e.att('flash_origin',[-1.4,4.1,.45])
        e.emitter('slash_flash','flash_origin','117158756559879',.223,.065,4.5,WHITE,rotation=24,LightEmission=.8,Brightness=2.0)
        e.light('release_light',[-1,3.7,.1],BLUE,.22,.30,1.3,5)
    with e.layer('air_teeth','secondary','Quatre dents inégales cassent la régularité du croissant sans ajouter un impact en flèche.','impact','foreground'):
        for i,t in enumerate((.24,.42,.61,.77)):
            p=bezier(curve,t)
            size=(.65,1.1,.8,1.6)[i]
            e.beam('rift_tooth_'+str(i),[p,add(p,[.1,-size*.25,.2]),add(p,[.8,-size*.7,.3]),add(p,[1.3,-size,.4])],
                   VIOLET if i%2 else BLUE,[.27,.003],.30+i*.018,.65+i*.014,
                   face=True,opacity=.82,emission=.18,brightness=1.15)
    with e.layer('detaching_arcs','secondary','Arcs orbitaux courts sur plusieurs plans, détachés du contour principal.','impact','foreground'):
        for i,t in enumerate((.28,.45,.65,.82)):
            p=bezier(curve,t)
            sign=1 if i%2 else -1
            points=[add(p,[-.4,-.2,.1]),add(p,[sign*.7,1.7,sign*1.5]),add(p,[1.3,.8,sign*1.3]),add(p,[1.8,-.2,sign*.5])]
            e.beam('detached_arc_'+str(i),points,BLUE if i%2 else VIOLET,[.08,.015],.29+i*.022,.57+i*.027,
                   texture=ELECTRIC,up=[0,0,1],face=True,opacity=.8,emission=.6,brightness=1.3)
    with e.layer('vibrating_seams','accent','Les fils instables vibrent dans la profondeur pendant la déchirure.','impact','foreground'):
        for i in range(3):
            p0=add(curve[0],[i*.45,.2+i*.3,.35+i*.15])
            p3=add(curve[-1],[-.5+i*.3,.5-i*.35,.3+i*.25])
            p1=add(curve[1],[.2,-i*.4,.6]);p2=add(curve[2],[-.3,-i*.4,.3])
            ident='vibration_'+str(i)
            e.beam(ident,[p0,p1,p2,p3],WHITE if i==0 else BLUE,[.10,.025],.34+i*.016,.71,
                   texture=ELECTRIC,up=[0,1,0],face=True,opacity=.67,emission=.5,brightness=1)
            e.motion(ident+'_a','oscillation',amplitude=[.08,.10,.12],cycles=4,decay=.4,start=.35,duration=.32,samples=61)
            e.motion(ident+'_b','oscillation',amplitude=[.07,.08,-.15],cycles=4,phase=90,start=.35,duration=.32,samples=61)
    with e.layer('directional_fragments','secondary','Fragments effilés projetés le long de la coupe ; traînées courbes, pas d’explosion radiale.','secondary','foreground'):
        for i in range(8):
            t=.25+.7*i/8
            p=bezier(curve,t)
            d=[1.5+i*.1,-.4+(i%3)*.45,(-1 if i%2 else 1)*(.6+i*.1)]
            end=add(p,d)
            e.travelling_spark('rift_shard_'+str(i),[p,add(p,[1.2,.5,d[2]*.3]),add(end,[-.3,.5,0]),end],
                              .36+(i%4)*.024,.81+(i%5)*.055,BLUE if i%3 else WHITE,
                              texture='113718672233773',size=1.4+(i%4)*.23,width=.065+(i%3)*.025,
                              rotation=(i*47)%180-70,rot_speed=100+i*17)
        e.att('loose_sparks',[4.2,4.6,.2])
        e.emitter('tiny_rift_scatter','loose_sparks','10976611540',.40,[.22,.38],NS((0,.12),(.15,.20),(1,0)),BLUE,
                  count=20,speed=[7,17],rotation=[0,360],rot_speed=[-100,100],EmissionDirection='Right',
                  SpreadAngle=[24,30],Drag=5,Acceleration=[0,-3,0],LightEmission=.5,Brightness=1.3)
    with e.layer('separating_remnants','secondary','Trois tronçons quittent la fente en profondeur pendant que le corps se fragmente.','dissipation','background'):
        for i,(a,b) in enumerate(((.14,.29),(.40,.57),(.70,.85))):
            parent=e.att('remnant_anchor_'+str(i))
            pa,pd=bezier(curve,a),bezier(curve,b)
            points=[pa,bezier(curve,a+(b-a)/3),bezier(curve,a+2*(b-a)/3),pd]
            e.beam('remnant_'+str(i),points,BLUE if i==1 else VIOLET,[.20,.03],.56+i*.022,.90+i*.03,
                   parent=parent,face=True,opacity=.8,emission=.16,fade=.24)
            e.motion(parent,'bezier',points=[[0,0,0],[.3,.4,.5*(-1 if i%2 else 1)],[.8,.2,1.4*(-1 if i%2 else 1)],[1.3,-.35,1.7*(-1 if i%2 else 1)]],
                     start=.56+i*.022,duration=.34,easing='out',samples=41)
    brief={'theme':'Une entaille céleste ouvre un vide sombre bordé de bleu électrique ; déchirure dirigée, jamais explosion de zone.',
           'palette':[INK,VIOLET,BLUE,WHITE],'silhouette':'Grande lame courbe effilée à deux pointes ; seconde incision retardée et fils éclatés.',
           'motion':'Convergence 0–0,20 ; balayage 0,20–0,35 ; vibration 0,35–0,65 ; éclats courbés ralentis puis extinction avant 1,10.',
           'character':'Attaque anime puissante d’une unité de mêlée TD, qui découpe l’air devant elle.',
           'readability':'Le vide violet sombre sépare les deux fines arêtes ; les éclats suivent le mouvement et restent secondaires.',
           'focal':[.2,4.5,0],'power':5}
    return e.finish(brief,[0,.16,.20,.35,.65,.83,1.10])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',default='v1');parser.add_argument('--no-render',action='store_true');args=parser.parse_args()
    project,brief=build()
    save_effect(project,brief,[.10,.235,.32,.49,.74,.98],stage=args.stage,peak=.32,render=not args.no_render)
