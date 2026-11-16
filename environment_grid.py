"""Finite world-anchored room floor, independent of camera framing."""
import numpy as np


def units_per_meter(unit):
    return {'mm':1000.,'cm':100.,'m':1.}.get(str(unit).strip().lower())


def ground_geometry(ax,z,world_bounds,step,max_lines=120):
    lo=np.asarray(world_bounds[0],float).copy();hi=np.asarray(world_bounds[1],float).copy()
    # Keep exact room bounds; changing the camera never enlarges the room.
    spacing=step*max(1,int(np.ceil(float(np.max(hi-lo))/(step*max_lines))))
    xs=np.arange(np.ceil(lo[0]/spacing)*spacing,hi[0]+spacing*1e-9,spacing)
    ys=np.arange(np.ceil(lo[1]/spacing)*spacing,hi[1]+spacing*1e-9,spacing)
    lines=[[(x,lo[1],z),(x,hi[1],z)] for x in xs]+[[(lo[0],y,z),(hi[0],y,z)] for y in ys]
    major=[abs(round(value/spacing))%2==0 for value in np.r_[xs,ys]]
    polygon=[(lo[0],lo[1],z),(hi[0],lo[1],z),(hi[0],hi[1],z),(lo[0],hi[1],z)]
    return dict(lines=lines,major=major,polygon=polygon,spacing=spacing,bounds=(lo,hi))
