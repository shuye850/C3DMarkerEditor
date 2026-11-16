import colorsys
import hashlib
import numpy as np
from marker_names import storage_name

# Virtual centers are used only for drawing, never written to the C3D.
VIRTUAL = {
    '@neck':('CLAV','C7'), '@thorax':('STRN','T10'),
    '@pelvis':('LASI','RASI','LPSI','RPSI'),
    '@left_wrist':('LWRA','LWRB'), '@right_wrist':('RWRA','RWRB'),
    '@left_ankle':('LANK','LMMA'), '@right_ankle':('RANK','RMMA'),
}
EDGES = [
    ('LFHD','RFHD'),('RFHD','RBHD'),('RBHD','LBHD'),('LBHD','LFHD'),
    ('LBHD','C7'),('RBHD','C7'),
    ('LSHO','@neck'),('@neck','RSHO'),('@neck','@thorax'),('@thorax','@pelvis'),
    ('CLAV','STRN'),('C7','T10'),('T10','RBAK'),
    ('LASI','RASI'),('RASI','RPSI'),('RPSI','LPSI'),('LPSI','LASI'),
]
for side,word in [('L','left'),('R','right')]:
    EDGES += [(side+'SHO',side+'ELB'),(side+'ELB','@'+word+'_wrist'),
        (side+'WRA',side+'WRB'),('@'+word+'_wrist',side+'FIN'),
        (side+'SHO',side+'UPA'),(side+'ELB',side+'FRM'),
        (side+'ASI',side+'KNE'),(side+'KNE','@'+word+'_ankle'),
        (side+'ANK',side+'MMA'),('@'+word+'_ankle',side+'TOE'),
        (side+'ANK',side+'HEE'),(side+'HEE',side+'TOE'),
        (side+'ASI',side+'THI'),(side+'KNE',side+'TIB')]

def slot_color(name):
    code=storage_name(name)
    digest=int.from_bytes(hashlib.sha256(code.encode('utf-8')).digest()[:4],'big')/2**32
    if code in ['LSHO','LUPA','LELB','LFRM','LWRA','LWRB','LFIN']:
        hue=.54+.08*digest  # left arm: cyan to blue
    elif code in ['RSHO','RUPA','RELB','RFRM','RWRA','RWRB','RFIN']:
        hue=.015+.065*digest  # right arm: red to orange
    elif code in ['LASI','LPSI','LTHI','LKNE','LTIB','LANK','LMMA','LHEE','LTOE']:
        hue=.30+.12*digest  # left leg: green
    elif code in ['RASI','RPSI','RTHI','RKNE','RTIB','RANK','RMMA','RHEE','RTOE']:
        hue=.73+.10*digest  # right leg: purple
    elif code.startswith('WAND'):
        hue=.12+.025*digest  # wand: gold
    else:
        hue=.11+.035*digest  # head and torso: amber
    return colorsys.hsv_to_rgb(hue,.66+.2*digest,.68+.2*digest)

def segments(slots,xyz,status,frame,body_slots=None,connections=None):
    nodes={storage_name(name):xyz[:,j,frame] for j,name in enumerate(slots)
        if (body_slots is None or name in body_slots) and status[j,frame] and np.isfinite(xyz[:,j,frame]).all()}
    synthetic=set()
    for name,required in VIRTUAL.items():
        if all(k in nodes for k in required):
            nodes[name]=np.mean([nodes[k] for k in required],axis=0);synthetic.add(name)
        elif name in ['@left_ankle','@right_ankle'] and required[1] not in (body_slots or slots) and required[0] in nodes:
            nodes[name]=nodes[required[0]];synthetic.add(name)
    lines=[];colors=[]
    for a,b in (connections or EDGES):
        if a in nodes and b in nodes:
            lines.append([nodes[a],nodes[b]])
            colors.append(slot_color(b if b not in synthetic else a))
    return lines,colors
