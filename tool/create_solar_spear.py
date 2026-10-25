"""SolarSpear: an assembled prismatic point, fast flight, concentrated contact."""
import argparse
import math
if __package__:
    from .pro_vfx import Effect, NS, add, mul, mix, ease, save_effect
else:
    from pro_vfx import Effect, NS, add, mul, mix, ease, save_effect

GOLD=[1,.55,.055]
ORANGE=[1,.17,.018]
RED=[.24,.012,.006]
HOT=[1,.91,.60]
FILAMENT='rbxassetid://15507852294'


def build():
    e=Effect('SolarSpear',1.0,{'position':[3,7,18],'target':[.4,3.5,0],'fov':43})
    root=e.carrier('spear_axis',[-5.0,3.5,0])
    # The carrier is invisible; three crossed, tapered textured surfaces form
    # the actual 3D spear. No sphere, cylinder or opaque rectangular main form.
    with e.layer('spear_facets','primary','Trois plans effilés croisés créent une lance prismatique volumétrique.','charge','midground'):
        for i in range(3):
            a=i*math.pi/3
            up=[0,math.cos(a),math.sin(a)]
            color=GOLD if i==0 else ORANGE if i==1 else RED
            e.beam('spear_rear_'+str(i),[[-2.7,0,0],[-2.1,.04,0],[-1.3,0,0],[-.65,0,0]],
                   color,[.035,.90],.07,.535,parent=root,up=up,texture='rbxassetid://81729442315187',
                   opacity=.95,emission=.16,brightness=1.1,grow=.19,fade=.06)
            e.beam('spear_point_'+str(i),[[-.65,0,0],[.1,0,0],[1.1,0,0],[2.25,0,0]],
                   color,[.90,.005],.095,.535,parent=root,up=up,opacity=.92,emission=.12,brightness=1.1,grow=.15,fade=.06)
            e.beam('inner_lance_'+str(i),[[-1.8,0,0],[-1,0,0],[.8,0,0],[2.4,0,0]],
                   HOT,[.16,.005],.14,.51,parent=root,up=up,texture=FILAMENT,opacity=.95,emission=.3,brightness=1.2,grow=.10,fade=.06)
        # The inspected spearhead texture supplies the carved chevron marks.
        e.att('spear_inscription',[.15,0,.10],root)
        e.emitter('spear_chevron','spear_inscription','12364066735',.11,.40,
                  NS((0,.3),(.35,2.8),(.78,2.8),(1,0)),GOLD,rotation=-90,
                  transparency=NS((0,1),(.25,.66),(.75,.66),(1,1)),speed=.001,
                  Orientation='VelocityPerpendicular',EmissionDirection='Back',LockedToPart=True,
                  LightEmission=.18,Brightness=1.2)
        e.beam('white_hot_ridge',[[-2.2,.04,.16],[-1,.04,.16],[1,.04,.16],[2.46,.04,.16]],
               HOT,[.07,.003],.16,.51,parent=root,face=True,opacity=.96,emission=.3,grow=.11,fade=.06)
        for i in range(4):
            angle=i*math.pi/2+.3
            radial=[0,math.cos(angle),math.sin(angle)]
            points=[[-1.7,0,0],add([-1.6,0,0],mul(radial,1.2)),add([-.4,0,0],mul(radial,1.05)),[.4,0,0]]
            e.beam('spear_barb_'+str(i),points,ORANGE if i%2 else GOLD,[.13,.005],.15+i*.012,.535,
                   parent=root,up=radial,opacity=.85,emission=.18,grow=.11,fade=.07)
            e.beam('barb_vein_'+str(i),points,HOT,[.035,.002],.17+i*.012,.51,
                   parent=root,face=True,opacity=.8,emission=.25,grow=.09,fade=.06)
    with e.layer('axis_travel','accent','Le pivot invisible parcourt douze studs en 0,15 seconde avec une accélération franche.','release','midground'):
        # Include this carrier in a deliberate layer even though it existed
        # before the layer context (all visible geometry stays in other layers).
        pass
    e.layers[-1]['nodes']=[root]
    e.motion(root,'bezier',points=[[-5,3.5,0],[-4.5,3.8,-.2],[1,3.8,.15],[5.4,3.5,0]],start=.30,duration=.15,easing='in',samples=61)
    with e.layer('forming_gyres','secondary','Six éclats tournent autour de l’axe et se resserrent avant le départ.','anticipation','foreground'):
        for i in range(6):
            phase=i*math.tau/6
            head=e.att('formation_head_'+str(i),[-1.6+i*.4,1.4*math.cos(phase),1.4*math.sin(phase)],root)
            def orbit(t,i=i,phase=phase):
                radius=1.65*(1-ease(t,'in'))+.08
                ang=phase+t*math.tau*1.2
                return [-1.8+i*.45+t*.35,radius*math.cos(ang),radius*math.sin(ang)]
            e.sampled(head,'Position',orbit,.015,.30,61)
            e.emitter('formation_glass_'+str(i),head,'81729442315187',.015,.30,
                      NS((0,.05),(.15,.50),(.75,.45),(1,0)),GOLD if i%2 else ORANGE,
                      rotation=23+i*31,rot_speed=130+i*19,LockedToPart=True,LightEmission=.25,Brightness=1.25)
            e.trail('formation_thread_'+str(i),head,.07,GOLD,.03,.30,lifetime=.11,opacity=.7)
    with e.layer('incomplete_collars','secondary','Deux colliers incomplets enroulés sur des profondeurs différentes se contractent autour de la pointe.','charge','background'):
        for ring,x in enumerate((-1.6,.2)):
            for seg in range(3):
                start_angle=seg*2.1+ring*.5
                points=[]
                for j in range(4):
                    ang=start_angle+j*.36
                    points.append([x,.95*math.cos(ang),.95*math.sin(ang)])
                ident=f'collar_{ring}_{seg}'
                e.beam(ident,points,ORANGE if ring else GOLD,[.065,.025],.065+ring*.03,.325,
                       parent=root,face=True,opacity=.75,emission=.25,brightness=1.1,grow=.06,fade=.07)
                for suffix,angle in (('_a',start_angle),('_b',start_angle+1.08)):
                    e.sampled(ident+suffix,'Position',lambda t,angle=angle,x=x:[x,(1.25-.88*ease(t,'in'))*math.cos(angle+t*.9),(1.25-.88*ease(t,'in'))*math.sin(angle+t*.9)],.065,.31,31)
    with e.layer('flight_wake','secondary','Trois sillages inégaux accompagnent la brusque propulsion sans cacher la pointe.','release','background'):
        for i,(width,color,offset,life) in enumerate(((.43,ORANGE,[-1.8,0,-.2],.15),(.17,GOLD,[-1.7,.12,.1],.135),(.05,HOT,[-1.5,-.08,.2],.115))):
            e.trail('axial_wake_'+str(i),root,width,color,.298,.48,offset=offset,lifetime=life,opacity=.85,emission=.2)
        for i in range(3):
            phase=i*math.tau/3
            head=e.att('flight_helix_'+str(i),[-1.2,.65*math.cos(phase),.65*math.sin(phase)],root)
            e.motion(head,'helix',center=[-1.8,0,0],axis='x',radius=.72,end_radius=.24,height=2.1,
                     turns=1.6,start_angle=math.degrees(phase),start=.30,duration=.15,samples=61)
            e.trail('helical_wake_'+str(i),head,.10 if i else .16,GOLD if i!=1 else ORANGE,.30,.485,
                    lifetime=.16,opacity=.8,emission=.25,up=[0,.7,.7])
        e.att('flight_embers',[-1.8,0,0],root)
        e.emitter('shedding_embers','flight_embers','10976611540',.30,.23,NS((0,.22),(.25,.28),(1,0)),
                  GOLD,mode='continuous',dur=.15,rate=100,speed=[.2,.8],rotation=[0,360],rot_speed=[-120,120],
                  SpreadAngle=[180,180],Drag=3,LightEmission=.25,Brightness=1.3)
    with e.layer('contact','primary','Pointe comprimée, étoile dissymétrique brève et éclats qui repartent vers l’arrière.','impact','foreground'):
        hit=[7.6,3.5,0]
        e.att('solar_contact',hit)
        e.emitter('solar_contact_star','solar_contact','91804820881066',.445,.15,
                  NS((0,.4),(.20,7),(.45,6),(1,0)),HOT,rotation=23,LightEmission=.15,Brightness=2.8)
        e.emitter('hot_contact_flash','solar_contact','117158756559879',.45,.05,
                  NS((0,.6),(.16,3.0),(1,0)),HOT,rotation=-17,LightEmission=.45,Brightness=1.4)
        e.light('solar_light',hit,GOLD,.45,.56,1.1,4)
        for i in range(9):
            angle=i*2.4
            first=add(hit,[0,.13*math.cos(angle),.13*math.sin(angle)])
            last=add(hit,[-2.2-(i%3)*1.3,math.cos(angle)*1.7,math.sin(angle)*1.5])
            e.travelling_spark('returning_shard_'+str(i),[first,add(first,[-2,.8*math.cos(angle),.5*math.sin(angle)]),add(last,[.3,.4,0]),last],
                              .46+i*.004,.83+(i%3)*.045,GOLD if i%3 else ORANGE,
                              texture='81729442315187',size=.9+(i%3)*.45,width=.055+(i%3)*.035,
                              rotation=30+i*41,rot_speed=90+i*11)
    with e.layer('collapsing_core','secondary','Une petite lentille axiale s’effondre sur le contact pendant que les filaments se détachent.','dissipation','midground'):
        for i in range(2):
            up=[0,1,0] if i==0 else [0,0,1]
            e.beam('collapse_'+str(i),[[6.2,3.5,0],[6.7,3.6,0],[7,3.5,0],[7.6,3.5,0]],
                   ORANGE,[.28,.03],.51,.72,up=up,texture=FILAMENT,opacity=.9,emission=.18,fade=.16)
    brief={'theme':'Une pointe solaire prismatique s’assemble autour d’un axe avant de traverser l’espace comme une lance.',
           'palette':[RED,ORANGE,GOLD,HOT],'silhouette':'Fer de lance allongé et rainuré, pointe chaude, trois plans en profondeur ; aucune orbe.',
           'motion':'Formation orbitale 0–0,30 ; accélération 0,30–0,45 ; contact local 0,45–0,65 ; effondrement et ralentissement jusqu’à 1,00.',
           'character':'Tir monocible d’un lancier solaire anime, concentré et brutal.',
           'readability':'Le rouge sombre fait lire les faces, l’or porte la silhouette, le blanc chaud reste sur l’axe et l’impact.',
           'focal':[7.6,3.5,0],'power':4}
    return e.finish(brief,[0,.12,.30,.45,.65,.82,1.0])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',default='v1');parser.add_argument('--no-render',action='store_true');args=parser.parse_args()
    project,brief=build()
    save_effect(project,brief,[.12,.27,.42,.465,.62,.86],stage=args.stage,peak=.42,render=not args.no_render)
