"""Whole-interval replacements, with measured anchors strictly outside the selection."""
import numpy as np
from scipy.interpolate import PchipInterpolator
from gap_smoothing import robust_velocity


def replacement_curve(xyz, measured, start, end, method='bezier', tension=.7, window=7):
    left=np.flatnonzero(measured[:start]);right=np.flatnonzero(measured[end+1:])+end+1
    if not len(left) or not len(right):raise ValueError('选区两侧都需要可靠实测点，不能在文件首尾外推')
    left,right=int(left[-1]),int(right[0]);a=xyz[:,left];b=xyz[:,right];duration=right-left
    secant=(b-a)/duration;vl=secant.copy();vr=secant.copy()
    if method=='bezier':
        before=left
        while before>0 and left-before<window-1 and measured[before-1]:before-=1
        after=right
        while after+1<len(measured) and after-right<window-1 and measured[after+1]:after+=1
        estimate=robust_velocity(np.arange(before,left+1),xyz[:,before:left+1],left)
        if estimate is not None:vl=secant+tension*(estimate-secant)
        estimate=robust_velocity(np.arange(right,after+1),xyz[:,right:after+1],right)
        if estimate is not None:vr=secant+tension*(estimate-secant)
        # Limit the three-dimensional handle length, not monotonicity per coordinate.
        # A legitimate turn can have equal endpoint coordinates and opposite tangents.
        samples=[]
        if left>before:samples.extend(np.linalg.norm(np.diff(xyz[:,before:left+1],axis=1),axis=0))
        if after>right:samples.extend(np.linalg.norm(np.diff(xyz[:,right:after+1],axis=1),axis=0))
        local_speed=float(np.median(samples)) if samples else float(np.linalg.norm(secant))
        handle_bound=max(.75*np.linalg.norm(b-a),.75*local_speed*duration,1e-12)
        for velocity in [vl,vr]:
            length=np.linalg.norm(velocity)*duration/3
            if length>handle_bound:velocity*=handle_bound/length
    elif method not in ['linear','pchip']:raise ValueError('修复方法无效')
    controls=np.stack([a,a+vl*duration/3,b-vr*duration/3,b],axis=1)
    t=np.arange(1,duration)/duration
    values=(1-t)**3*controls[:,0,None]+3*(1-t)**2*t*controls[:,1,None]+3*(1-t)*t*t*controls[:,2,None]+t**3*controls[:,3,None]
    if method=='pchip':
        before=left
        while before>0 and left-before<window-1 and measured[before-1]:before-=1
        after=right
        while after+1<len(measured) and after-right<window-1 and measured[after+1]:after+=1
        support=np.r_[np.arange(before,left+1),np.arange(right,after+1)]
        values=PchipInterpolator(support,xyz[:,support],axis=1)(np.arange(left+1,right))
    line=a[:,None]+(b-a)[:,None]*t
    deviation=float(np.max(np.linalg.norm(values-line,axis=0))) if values.shape[1] else 0.
    reference_note='参考不足，退回直线' if method=='bezier' and before==left and after==right else ('趋势接近直线' if method=='bezier' and deviation<1e-6 else '')
    return dict(deviation=deviation,reference_note=reference_note,left=left,right=right,start=left+1,end=right-1,values=values.tolist(),controls=controls.tolist(),anchors=np.stack([a,b],axis=1).tolist())
