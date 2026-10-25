"""PhantomBloom: a spectral corolla, seven unequal petals, one convergent hit."""
import argparse
import math
if __package__:
    from .pro_vfx import Effect, NS, add, sub, mul, mix, cross, unit, ease, bezier, save_effect
else:
    from pro_vfx import Effect, NS, add, sub, mul, mix, cross, unit, ease, bezier, save_effect

INK=[.055,.006,.13]
VIOLET=[.29,.035,.68]
MAGENTA=[.92,.025,.43]
PINK=[1,.19,.61]
CYAN=[.12,.77,.87]
LENS='rbxassetid://117614171376502'
ENERGY='rbxassetid://15488087736'


def attitude(direction, roll=0):
    """Euler YXZ with local +X pointing along direction, degrees unwrapped by caller."""
    direction=unit(direction)
    # No X pitch: yaw/roll jointly point local X at the requested vector.
    return [0,math.degrees(math.atan2(-direction[2],direction[0])),math.degrees(math.asin(direction[1]))+roll]


def build():
    e=Effect('PhantomBloom',1.40,{'position':[9.2,7.8,18],'target':[0,3.7,.2],'fov':43})
    centre=[0,3.8,-1.45]
    target=[.55,3.0,2.05]
    lengths=[3.35,2.8,3.7,3.0,3.5,2.65,3.15]
    angles=[6,58,112,163,214,267,318]
    holders=[]
    endpoints=[]
    with e.layer('spectral_seed','primary','Un noyau étroit en amande s’allume derrière la cible, sans boule lumineuse.','anticipation','background'):
        for i in range(2):
            offset=[0,0,.10*i]
            points=[add(centre,[-.12,-.45,0]),add(centre,[-.45,0,0]),add(centre,[.30,.50,0]),add(centre,[.13,.68,0])]
            points=[add(p,offset) for p in points]
            e.beam('seed_spine_'+str(i),points,VIOLET if i==0 else MAGENTA,[.32 if i==0 else .09,.005],
                   .01,.83,face=True,opacity=.9,emission=.2,grow=.22,fade=.15)
        e.att('seed_lens',centre)
        e.emitter('seed_iris','seed_lens','117614171376502',.03,.77,
                  NS((0,.1),(.3,1.5),(.7,1.9),(1,0)),MAGENTA,rotation=82,
                  transparency=NS((0,.95),(.25,.3),(.7,.2),(1,1)),LightEmission=.24,Brightness=1.4)
    with e.layer('unequal_petals','primary','Sept pétales organiques creux, de longueurs et profondeurs différentes, deviennent des lames.','charge','midground'):
        for i,(length,angle) in enumerate(zip(lengths,angles)):
            theta=math.radians(angle)
            radial=[math.cos(theta),math.sin(theta),0]
            depth=(-1.00,.45,-.60,1.05,-.75,.75,-.10)[i]
            opened=add(centre,add(mul(radial,length*.48),[0,0,depth]))
            folded=add(centre,mul(radial,.12))
            holder=e.att('petal_'+str(i),folded)
            holders.append(holder)
            endpoints.append(opened)
            release=.555+i*.005
            arrival=.742+i*.004
            end_point=add(target,[.10*math.cos(theta),.10*math.sin(theta),.025*(i-3)])
            control=[opened,add(opened,add(mul(radial,.75),[0,.3,1.1])),
                     add(target,add(mul(radial,.45),[0,.35,-.7])),end_point]
            def position(t,folded=folded,opened=opened,release=release,arrival=arrival,control=control,end_point=end_point,radial=radial):
                seconds=t*1.30
                if seconds<.30:
                    return mix(folded,mix(folded,opened,.69),ease(seconds/.30,'out'))
                if seconds<.55:
                    return mix(mix(folded,opened,.69),opened,ease((seconds-.30)/.25,'inOut'))
                if seconds<release:return opened
                if seconds<arrival:return bezier(control,ease((seconds-release)/(arrival-release),'in'))
                return add(end_point,mul(radial,.22*ease(min(1,(seconds-arrival)/.25),'out')))
            e.sampled(holder,'Position',position,0,1.30,181)
            flight=attitude(sub(end_point,opened))
            # Choose the nearest equivalent roll to avoid a full turn at release.
            initial=[(-8,11,-12,15,-7,12,-10)[i],(-14,9,-17,13,-12,18,-9)[i],angle-22]
            opened_ori=[initial[0]+8,initial[1]-7,angle+5]
            while flight[2]-opened_ori[2]>180:flight[2]-=360
            while flight[2]-opened_ori[2]<-180:flight[2]+=360
            e.track(holder,'Orientation',[(0,initial),(.30,initial),(.50,opened_ori),
                                          (release,opened_ori),(release+.045,flight),(arrival,flight),(1.30,flight)])
            base=[-length*.42,0,0]
            tip=[length*.56,0,0]
            span=.48+(i%3)*.10
            top=[base,[-length*.15,span,.16], [length*.27,span*.8,-.05],tip]
            bottom=[base,[-length*.13,-span*.75,-.12],[length*.29,-span*.64,.13],tip]
            backcolor=VIOLET if i%2 else [.20,.016,.38]
            petalcolor=PINK if i in (0,3,5) else MAGENTA
            edges=[]
            # A curved, tapered membrane gives the corolla actual colour mass.
            # Two joined halves stay sharp at the root and tip; their local
            # planes rotate with each petal instead of facing the camera.
            middle=[length*.015,.07*(1 if i%2 else -1),.14]
            membranes=[
                [base,[-length*.28,.10,.05],[-length*.10,.13,.14],middle],
                [middle,[length*.18,.11,.14],[length*.42,.04,.05],tip],
            ]
            for half,points in enumerate(membranes):
                membrane='petal_membrane_'+str(i)+'_'+str(half)
                e.beam(membrane,points,[.36,.035,.57] if i%2 else [.46,.026,.42],
                       [.008,span*1.32] if half==0 else [span*1.32,.004],
                       .055+i*.013,arrival+.09,parent=holder,up=[0,1,0],
                       opacity=.76,emission=.10,brightness=1.05,grow=.19,fade=.10)
                edges.append(membrane)
            for side,points in (('top',top),('bottom',bottom)):
                body='petal_body_'+str(i)+'_'+side
                e.beam(body,points,backcolor,[.46,.04],.055+i*.013,arrival+.09,parent=holder,
                       up=[0,1,0],texture=ENERGY,opacity=.82,emission=.08,brightness=1.2,grow=.19,fade=.10)
                edge='petal_edge_'+str(i)+'_'+side
                e.beam(edge,points,petalcolor,[.075,.014],.075+i*.013,arrival+.08,parent=holder,
                       face=True,opacity=.94,emission=.24,brightness=1.15,grow=.15,fade=.09)
                edges.extend([body,edge])
            spine='petal_vein_'+str(i)
            e.beam(spine,[base,[-length*.14,.045,.10],[length*.28,-.035,.12],tip],
                   CYAN if i==1 else PINK,[.055,.003],.11+i*.013,arrival+.06,parent=holder,
                   texture='rbxassetid://15507852294',face=True,opacity=.83,emission=.25,brightness=1.3,grow=.14,fade=.08)
            blades=[]
            # As the corolla detaches its outline closes into a solid tapered
            # blade. A camera-facing inner ridge keeps that brief fast motion
            # legible even when the rotating membrane is seen edge-on.
            for half,points in enumerate(membranes):
                blade='petal_blade_'+str(i)+'_'+str(half)
                e.beam(blade,points,CYAN if i==1 else PINK if i%3==0 else MAGENTA,
                       [.006,.34] if half==0 else [.34,.002],
                       release+.018,arrival+.035,parent=holder,face=True,
                       opacity=.90,emission=.35,brightness=1.25,grow=.035,fade=.05)
                blades.append(blade)
            # Formation grows the actual geometry; convergence squeezes it into
            # a narrow blade instead of sending a full flower petal unchanged.
            for beam in edges+[spine]+blades:
                beam_node=next(n for n in e.fx.d['nodes'] if n['id']==beam)
                for suffix in ('_a','_b'):
                    node=next(n for n in e.fx.d['nodes'] if n['id']==beam+suffix)
                    p=node['properties']['Position']
                    e.track(beam+suffix,'Position',[(0,mul(p,.03)),(.27,mul(p,.83)),(.50,p),
                                                  (release,p),(arrival,mul(p,.55)),(arrival+.10,mul(p,.04))])
                # Handles must shrink with the endpoints, otherwise a tiny
                # blade keeps full-size curls after its convergence.
                for prop in ('CurveSize0','CurveSize1'):
                    handle=beam_node['properties'][prop]
                    e.track(beam,prop,[(0,handle*.03),(.27,handle*.83),(.50,handle),
                                       (release,handle),(arrival,handle*.55),(arrival+.10,handle*.04)])
            for beam in edges:
                for prop in ('Width0','Width1'):
                    track=next(t for t in e.fx.d['animations'] if t['node']==beam and t['property']==prop)
                    peak=next(n for n in e.fx.d['nodes'] if n['id']==beam)['properties'][prop]
                    start=.075+i*.013
                    if beam.startswith(('petal_edge_','petal_body_')):
                        tail=[{'time':release+.068,'value':0},{'time':arrival+.08,'value':0}]
                    else:
                        tail=[{'time':arrival-.035,'value':peak*.32},{'time':arrival+.08,'value':0}]
                    track['keyframes']=[{'time':start,'value':0},{'time':.30,'value':peak*.75},
                                        {'time':.50,'value':peak},{'time':release,'value':peak},*tail]
            e.trail('petal_wake_'+str(i),holder,.12+(i%3)*.045,petalcolor,release+.043,arrival+.02,
                    offset=[-length*.32,0,0],up=[0,1,0],lifetime=.10+(i%3)*.015,opacity=.76,emission=.25)
    with e.layer('curved_connections','secondary','Trois lignes magiques courbées relient certains pétales, sans cercle fermé.','charge','background'):
        for i,j in ((0,2),(2,4),(4,6)):
            first,last=mix(centre,endpoints[i],.62),mix(centre,endpoints[j],.58)
            control=[first,add(first,[.2,.3,-.9]),add(last,[-.4,.6,-.8]),last]
            ident='bloom_bridge_'+str(i)
            e.beam(ident,control,VIOLET,[.055,.025],.29,.58,texture='rbxassetid://9632171388',
                   face=True,opacity=.65,emission=.3,brightness=1.25,grow=.12,fade=.06)
    with e.layer('hovering_motes','accent','De fines particules flottent dans le volume de la fleur ; quelques-unes sont cyan.','anticipation','foreground'):
        for i in range(10):
            angle=i*2.4
            first=add(centre,[math.cos(angle)*(2+i%3*.6),math.sin(angle)*(2+i%2*.5),(-1+i%3)*.8])
            last=add(first,[.2,.6,.2*math.cos(angle)])
            e.travelling_spark('mote_'+str(i),[first,add(first,[-.25,.2,.2]),add(last,[-.2,.1,0]),last],
                              .06+i*.015,.59+i*.012,CYAN if i in (2,7) else PINK,
                              texture='10976611540',size=.26,width=.025,rotation=i*29,rot_speed=40)
    with e.layer('magenta_contact','primary','Les lames frappent un seul point ; flash magenta bref, blanc limité à une petite faille.','impact','foreground'):
        e.att('bloom_target',target)
        e.emitter('bloom_impact','bloom_target','117158756559879',.754,.15,
                  NS((0,.2),(.18,4.8),(.4,4.5),(1,0)),MAGENTA,rotation=-31,
                  transparency=NS((0,.3),(.15,.04),(.5,.20),(1,1)),LightEmission=.30,Brightness=1.7)
        e.emitter('cyan_impact_needle','bloom_target','91804820881066',.766,.085,
                  NS((0,.2),(.15,2.9),(1,0)),CYAN,rotation=34,LightEmission=.26,Brightness=1.8)
        e.light('bloom_light',target,MAGENTA,.75,.88,1.2,4.7)
        for i in range(10):
            angle=i*2.4
            end=add(target,[math.cos(angle)*(1.6+(i%3)*.4),math.sin(angle)*1.6+.25,(i%3-1)*.8])
            e.travelling_spark('crystal_'+str(i),[target,add(target,[math.cos(angle)*1.3,math.sin(angle)*1.3,.4]),
                                                add(end,[0,.5,0]),end],
                              .77+i*.003,1.15+(i%4)*.045,CYAN if i in (1,6) else PINK,
                              texture='113718672233773',size=.62+(i%3)*.22,width=.03+(i%3)*.02,
                              rotation=-60+i*38,rot_speed=85+i*23)
    with e.layer('simulated_air_buckle','accent','Une brève double lèvre cyan/magenta simule une déformation locale ; aucune réfraction de scène prétendue.','impact','foreground'):
        for i in range(2):
            sign=1 if i else -1
            points=[add(target,[-1.25,-.75,.12+i*.04]),add(target,[-1.6,.65*sign,.1]),
                    add(target,[.95,.85*sign,.2]),add(target,[1.3,-.35,.2])]
            e.beam('air_buckle_'+str(i),points,CYAN if i==0 else MAGENTA,[.07,.01],.782+i*.015,.87+i*.015,
                   face=True,opacity=.6,emission=.3,grow=.018,fade=.05)
    with e.layer('residual_petals','secondary','Deux pétales détachés flottent lentement, suivis d’un fin filet violet qui s’éteint.','dissipation','background'):
        for i in range(2):
            first=add(target,[-.45+i*.9,.2,-.4])
            last=add(first,[-.7+i*1.3,.9,-.7+i*.2])
            e.travelling_spark('residual_petal_'+str(i),[first,add(first,[.2,.4,.3]),add(last,[-.3,.15,0]),last],
                              .94,1.37-i*.03,PINK if i==0 else VIOLET,
                              texture='117614171376502',size=1.4+i*.2,width=.035,
                              rotation=-20+i*63,rot_speed=-60+i*110)
    brief={'theme':'Une fleur spectrale se forme derrière la cible puis transforme ses sept pétales en lames convergentes.',
           'palette':[INK,VIOLET,MAGENTA,PINK,CYAN],
           'silhouette':'Corolle inégale à sept pétales effilés, membranes violettes et nervures roses en profondeur ; centre ouvert, aucun disque magique.',
           'motion':'Croissance organique 0–0,30 ; ouverture et torsion 0,30–0,55 ; sept trajectoires courbes convergent en 0,55–0,77 ; impact local et pétales résiduels jusqu’à 1,40.',
           'character':'Une unité magique élégante et inquiétante, qui piège une cible avant une frappe très brève.',
           'readability':'Le rose dessine les pétales, le violet porte l’ombre ; le cyan reste dans trois accents et ne remplit jamais la fleur.',
           'focal':target,'power':4}
    return e.finish(brief,[0,.18,.30,.55,.77,.95,1.40])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',default='v1');parser.add_argument('--no-render',action='store_true');args=parser.parse_args()
    project,brief=build()
    save_effect(project,brief,[.15,.36,.53,.67,.79,1.13],stage=args.stage,peak=.53,render=not args.no_render)
