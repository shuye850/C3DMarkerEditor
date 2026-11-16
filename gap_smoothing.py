"""Gap-only smoothing with fixed measured endpoints and bounded Hermite tangents."""
import numpy as np


def robust_velocity(indices, values, endpoint):
    if len(indices)<2:return None
    x=np.asarray(indices,dtype=float)-endpoint
    degree=min(2,len(x)-1)
    design=np.column_stack([x**i for i in range(degree+1)])
    weights=np.ones(len(x))
    for _ in range(5):
        root=np.sqrt(weights)
        coefficients=np.linalg.lstsq(design*root[:,None],values.T*root[:,None],rcond=None)[0]
        residual=np.linalg.norm(values.T-design@coefficients,axis=1)
        scale=max(float(np.median(residual))*1.4826,1e-12)
        weights=np.minimum(1,1.5*scale/np.maximum(residual,1e-12))
    return coefficients[1]


def smooth_gap(xyz, measured, left, right, baseline, strength=1., window=7):
    """Only return missing samples; never write measured positions or extrapolate."""
    strength=float(np.clip(strength,0,1))
    if strength==0:return baseline.copy()
    before=left
    while before>0 and left-before<window-1 and measured[before-1]:before-=1
    after=right
    while after+1<len(measured) and after-right<window-1 and measured[after+1]:after+=1
    a=xyz[:,left];b=xyz[:,right];duration=right-left;secant=(b-a)/duration
    vl=robust_velocity(np.arange(before,left+1),xyz[:,before:left+1],left)
    vr=robust_velocity(np.arange(right,after+1),xyz[:,right:after+1],right)
    vl=secant.copy() if vl is None else vl.copy();vr=secant.copy() if vr is None else vr.copy()
    # Monotonicity limiter: no new coordinate overshoot beyond the two measured anchors.
    for dim in range(3):
        if abs(secant[dim])<1e-14:vl[dim]=vr[dim]=0;continue
        alpha=max(0,vl[dim]/secant[dim]);beta=max(0,vr[dim]/secant[dim])
        radius=np.hypot(alpha,beta)
        if radius>3:alpha*=3/radius;beta*=3/radius
        vl[dim]=alpha*secant[dim];vr[dim]=beta*secant[dim]
    t=np.arange(1,duration)/duration
    h00=2*t**3-3*t**2+1;h10=t**3-2*t**2+t
    h01=-2*t**3+3*t**2;h11=t**3-t**2
    hermite=a[:,None]*h00+duration*vl[:,None]*h10+b[:,None]*h01+duration*vr[:,None]*h11
    return (1-strength)*baseline+strength*hermite


def suspicious_anchor(xyz, measured, anchor, direction, window=9):
    # Compare the anchor's acceleration with preceding measured samples on its own side.
    indices=[anchor];i=anchor+direction
    while 0<=i<len(measured) and measured[i] and len(indices)<window:
        indices.append(i);i+=direction
    if len(indices)<5:return False
    values=xyz[:,indices]
    changes=np.linalg.norm(np.diff(values,n=2,axis=1),axis=0)
    background=changes[1:];median=float(np.median(background));mad=float(np.median(abs(background-median)))
    tolerance=max(5*median,median+8*1.4826*mad,1e-8)
    return bool(changes[0]>tolerance)
