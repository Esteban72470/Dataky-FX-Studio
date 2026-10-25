"""Original Enuma Elish-inspired light masks, drawn with NumPy and Pillow.

No model, downloaded texture, video frame trace or uploaded Roblox ID is used.
Run with Python 3 + numpy + Pillow. All RGB pixels are white; alpha carries art.
The 4x4 wind sheet loops; particle lifetime transparency supplies dissipation.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'textures'
OUT.mkdir(parents=True,exist_ok=True)
TAU=math.tau


def grid(n):
    a=(np.arange(n,dtype=np.float32)+.5)/n*2-1
    return np.meshgrid(a,-a)


def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1)
    return t*t*(3-2*t)


def distance_angle(a,b):
    return np.arctan2(np.sin(a-b),np.cos(a-b))


def line(x,y,ax,ay,bx,by,width):
    vx=bx-ax;vy=by-ay
    q=np.clip(((x-ax)*vx+(y-ay)*vy)/(vx*vx+vy*vy+1e-12),0,1)
    d=np.hypot(x-ax-q*vx,y-ay-q*vy)
    return np.exp(-np.square(d/width)*2)


def rgba(alpha):
    alpha=np.clip(alpha,0,1)
    data=np.full((*alpha.shape,4),255,dtype=np.uint8)
    data[...,3]=np.rint(alpha*255).astype(np.uint8)
    return Image.fromarray(data,'RGBA')


def sigil(n=1024):
    x,y=grid(n);r=np.hypot(x,y);ang=np.arctan2(y,x)
    a=np.zeros_like(x)
    for radius,width,power in ((.85,.0033,.95),(.824,.0024,.55),(.738,.0035,.95),(.718,.0017,.45),(.535,.0030,.8),(.506,.0017,.45),(.218,.0045,.85)):
        a=np.maximum(a,power*np.exp(-np.square((r-radius)/width)*2))
    # A tightly packed band of original abstract radial strokes, not letters.
    for i in range(72):
        t=TAU*i/72
        inner=.755+(.004 if i%3 else 0);outer=.805
        ax,ay=inner*np.cos(t),inner*np.sin(t)
        bx,by=outer*np.cos(t),outer*np.sin(t)
        a=np.maximum(a,.72*line(x,y,ax,ay,bx,by,.0025))
        direction=1 if i%2 else -1
        mid=.774+(.009 if i%4==0 else 0)
        end=t+direction*(.021 if i%3 else .034)
        a=np.maximum(a,.72*line(x,y,mid*np.cos(t),mid*np.sin(t),mid*np.cos(end),mid*np.sin(end),.0023))
        if i%5==0:
            a=np.maximum(a,.8*line(x,y,.794*np.cos(end),.794*np.sin(end),.807*np.cos(end),.807*np.sin(end),.0025))
    # Interrupted fine orbits keep negative space, instead of gear teeth.
    for k,(radius,start,span) in enumerate(((.66,-.3,2.2),(.625,2.3,1.65),(.59,4.2,2.4),(.43,.3,2.8),(.397,3.2,2.05))):
        progress=np.mod(ang-start,TAU)
        edge=smooth(0,.05,progress)*(1-smooth(span-.05,span,progress))
        a=np.maximum(a,.74*np.exp(-np.square((r-radius)/.0035)*2)*edge)
    for k in range(8):
        t=k*TAU/8+.18
        a=np.maximum(a,.72*line(x,y,.24*np.cos(t),.24*np.sin(t),.48*np.cos(t+.27),.48*np.sin(t+.27),.0028))
    # Two coiling partial arcs through the inner disc.
    phi=np.mod(ang+.7,TAU)
    for turn in (0,1):
        target=.23+.058*(phi+turn*TAU)
        valid=(target<.58).astype(np.float32)
        a=np.maximum(a,.65*np.exp(-np.square((r-target)/.003)*2)*valid)
    return rgba(a*(1-smooth(.87,.9,r)))


def ribbon(width=512,height=128):
    x=np.linspace(0,1,width,dtype=np.float32)[None,:]
    y=np.linspace(-1,1,height,dtype=np.float32)[:,None]
    centre=.055*np.sin(x*TAU*2)+.023*np.sin(x*TAU*7+.4)
    taper=np.clip(np.sin(np.pi*x),0,1)**.42
    thickness=(.18+.022*np.sin(x*TAU*9)+.018*np.sin(x*TAU*21))*(.25+.75*taper)
    core=np.exp(-np.square((y-centre)/(thickness+1e-5))*3.8)
    feather=.25*np.exp(-np.square((y-centre)/(.38+.05*np.sin(TAU*x*4))))
    thread=.42*np.exp(-np.square((y-centre-.22*np.sin(np.pi*x))/(.025+.02*taper))*3)
    detail=.87+.13*np.sin(x*TAU*17+y*9)
    a=(core+feather+thread)*taper*detail
    a*=smooth(0,.025,x)*(1-smooth(.975,1,x))
    return rgba(a)


def ribbon_body(width=512,height=128):
    """Broad torn energy cloth, distinct from the thin hot ribbon filament."""
    x=np.linspace(0,1,width,dtype=np.float32)[None,:]
    y=np.linspace(-1,1,height,dtype=np.float32)[:,None]
    centre=.055*np.sin(TAU*x*2+.3)+.035*np.sin(TAU*x*5)
    taper=.30+.70*np.clip(np.sin(np.pi*x),0,1)**.32
    ragged=.073*np.sin(TAU*x*11+.4)+.032*np.sin(TAU*x*29)
    upper=centre+(.74+ragged)*taper
    lower=centre-(.67+.061*np.sin(TAU*x*17+1.1))*taper
    a=smooth(lower-.032,lower+.032,y)*(1-smooth(upper-.032,upper+.032,y))
    # Irregular bites into the edges, rather than holes in a light's core.
    for cx,cy,length,angle in ((.17,.61,.065,-.6),(.36,-.50,.085,.4),(.61,.62,.075,-.8),(.84,-.53,.055,.65)):
        diagonal=y-cy-angle*(x-cx)
        bite=np.exp(-np.square((x-cx)/length)*2)*np.exp(-np.square(diagonal/.18)*2)
        a*=1-.98*bite
    fold1=np.exp(-np.square((y-centre-.17*np.sin(TAU*x*2))/.055)*2)
    fold2=np.exp(-np.square((y-centre+.22+.08*np.sin(TAU*x*4))/.031)*2)
    body=.69+.12*np.sin(TAU*x*7+y*12)+.07*np.sin(TAU*x*19-y*8)
    a*=np.clip(body+.26*fold1+.20*fold2,0,1)
    a*=smooth(0,.02,x)*(1-smooth(.98,1,x))
    return rgba(a)


def star(n=512):
    x,y=grid(n);ax=np.abs(x);ay=np.abs(y)
    longx=np.clip(1-ax/.94,0,1)**1.3
    longy=np.clip(1-ay/.94,0,1)**1.3
    h=longx*np.exp(-np.square(y/(.005+.078*np.clip(1-ax,0,1)**3))*1.5)
    v=longy*np.exp(-np.square(x/(.005+.078*np.clip(1-ay,0,1)**3))*1.5)
    core=np.exp(-(x*x+y*y)/.003)
    halo=.07*np.exp(-(x*x+y*y)/.036)
    a=np.maximum(h,v)+core+halo
    return rgba(a*(1-smooth(.94,.99,np.maximum(ax,ay))))


def wind(n=512,phase=0):
    x,y=grid(n);r=np.hypot(x,y);theta=np.arctan2(y,x)
    a=np.zeros_like(x)
    for k,(radius,start,span,weight)in enumerate(((.68,-1.7,3.95,1),(.54,-1.25,3.7,.6),(.77,-.6,1.65,.42))):
        u=np.mod(theta-start-phase,TAU)/span
        active=(u<1).astype(np.float32)
        taper=np.clip(np.sin(np.pi*np.clip(u,0,1)),0,1)**.75
        target=radius+.018*np.sin(theta*4+phase*2+k)+.025*(u-.5)
        width=.015+.053*taper
        body=np.exp(-np.square((r-target)/width)*2)
        highlight=.5*np.exp(-np.square((r-target-width*.32)/(.007+.013*taper))*2)
        a=np.maximum(a,(body+highlight)*taper*active*weight)
    return rgba(a*(1-smooth(.87,.96,r)))


def spark(n=256):
    x,y=grid(n);u=(y+.9)/1.8
    taper=np.clip(np.sin(np.pi*np.clip(u,0,1)),0,1)**1.8
    active=((u>0)&(u<1)).astype(np.float32)
    axis=.025*np.sin(np.pi*u)
    a=np.exp(-np.square((x-axis)/(.006+.014*taper))*2)*taper*active
    a+=.16*np.exp(-np.square((x-axis)/.046)*2)*taper*active
    return rgba(a)


def glow(n=256):
    x,y=grid(n);r=np.hypot(x,y)
    a=.88*np.exp(-np.square(r/.16)*2)+.19*np.exp(-np.square(r/.40)*2)
    return rgba(a*(1-smooth(.72,.94,r)))


def turbulence(n=1024):
    cell=n//4;sheet=Image.new('RGBA',(n,n),(255,255,255,0))
    x,y=grid(cell);r=np.hypot(x,y);theta=np.arctan2(y,x)
    for frame in range(16):
        phase=TAU*frame/16
        a=np.zeros_like(x)
        for k in range(4):
            base=.27+k*.145
            target=base+.047*np.sin(theta*3+phase+k*.9)+.018*np.sin(theta*8-phase*2)
            width=.018+.017*(.5+.5*np.sin(theta*2-phase+k))
            arc=np.exp(-np.square((r-target)/width)*2.5)
            angular=smooth(-.35,.4,np.cos(theta-(phase*.8+k*1.1)))
            cuts=.54+.46*smooth(-.3,.7,np.sin(theta*6+phase*2+k*.8))
            a=np.maximum(a,arc*angular*cuts)
            secondary=np.exp(-np.square((r-target-.045)/.013)*2)*angular*.25
            a=np.maximum(a,secondary)
        # Fragments travel with the loop, never a static smoke ball.
        for k in range(5):
            ang=phase+k*1.24
            radius=.60+.08*np.sin(phase*2+k)
            delta=distance_angle(theta,ang)
            frag=np.exp(-np.square((r-radius)/.014)*2)*np.exp(-np.square(delta/.13)*2)
            a=np.maximum(a,frag*.6)
        a*=1-smooth(.80,.91,r)
        sheet.alpha_composite(rgba(a),(frame%4*cell,frame//4*cell))
    return sheet


def main():
    textures={'sigil':sigil(),'ribbon':ribbon(),'star':star(),'wind':wind(),'spark':spark(),'glow':glow(),'turbulence':turbulence(),'ribbon_body':ribbon_body()}
    manifest={'version':1,'author':'Codex — original procedural artwork','method':'Hand-authored NumPy/Pillow geometry and alpha fields; no local AI model',
        'source':'Original masks inspired by observed rhythm and silhouette, not extracted video artwork','local_preview_only':True,
        'upload_performed':False,'textures':[]}
    for name,im in textures.items():
        path=OUT/(name+'.png');im.save(path,optimize=True)
        a=np.asarray(im)[...,3]
        item={'name':name,'file':'textures/'+path.name,'width':im.width,'height':im.height,'grid':4 if name=='turbulence' else 0,
            'roblox_preview_uri':'rbxasset://textures/dataky-local/enuma-elish/'+path.name,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,
            'alpha_nonzero_fraction':round(float(np.mean(a>0)),5),'alpha_above_127_fraction':round(float(np.mean(a>127)),5)}
        if name=='turbulence':item.update(frames=16,frame_size=256,mode='Loop',recommended_fps=18,padding_pixels=11)
        manifest['textures'].append(item)
    (ROOT/'textures.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    review=Image.new('RGB',(len(textures)*256,600),(20,20,28));d=ImageDraw.Draw(review)
    try:
        font=ImageFont.truetype('DejaVuSans.ttf',17)
    except OSError:
        font=ImageFont.load_default()
    for i,(name,im)in enumerate(textures.items()):
        thumb=im.copy();thumb.thumbnail((240,240));tile=Image.new('RGBA',(240,240),(35,35,44,255));tile.alpha_composite(thumb,((240-thumb.width)//2,(240-thumb.height)//2));review.paste(tile.convert('RGB'),(i*256+8,42));d.text((i*256+10,10),name+' '+str(im.width)+'x'+str(im.height),font=font,fill='white')
    # Wind flipbook at half size, so individual cells can be inspected.
    full=textures['turbulence'].resize((512,512));bg=Image.new('RGBA',(512,512),(35,35,44,255));bg.alpha_composite(full)
    review.paste(bg.resize((280,280)).convert('RGB'),(1488,312))
    for j,phase in enumerate((0,4,8,12)):
        frame=textures['turbulence'].crop(((phase%4)*256,(phase//4)*256,(phase%4+1)*256,(phase//4+1)*256))
        bg=Image.new('RGBA',(256,256),(35,35,44,255));bg.alpha_composite(frame);review.paste(bg.convert('RGB'),(j*280+40,326));d.text((j*280+40,300),'wind frame '+str(phase),font=font,fill='white')
    output=ROOT/'exports'/'textures-originales.jpg'
    output.parent.mkdir(parents=True,exist_ok=True);review.save(output,quality=95)
    print(json.dumps({'textures':len(textures),'directory':str(OUT),'review':str(output),'bytes':sum(t['bytes']for t in manifest['textures'])}))


if __name__=='__main__':main()
