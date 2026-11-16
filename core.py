"""C3D trajectory assignment and conservative gap reconstruction."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from datetime import datetime
import shutil
import copy
from pathlib import Path,PureWindowsPath
import numpy as np
import ezc3d
from scipy.interpolate import PchipInterpolator
from gap_smoothing import smooth_gap, suspicious_anchor
from segment_repair import replacement_curve
from model_schemes import BODY39,PRESETS,infer_scheme,validate_scheme

# Editable starting template; verify against the actual laboratory marker protocol.

def _ezc3d_uses_ascii_staging(path):
    """Whether this Windows ezc3d build needs an ASCII filename workaround."""
    return os.name == 'nt' and not str(Path(path)).isascii()

def read_c3d(path):
    """Load a C3D, staging Unicode Windows paths for ezc3d's native reader."""
    path=Path(path)
    if not _ezc3d_uses_ascii_staging(path): return ezc3d.c3d(str(path))
    with tempfile.TemporaryDirectory(prefix='c3d-') as folder:
        staged=Path(folder)/'input.c3d'
        shutil.copy2(path,staged)
        return ezc3d.c3d(str(staged))

def write_c3d(c3d,path):
    """Write a C3D, staging Unicode Windows paths for ezc3d's native writer."""
    path=Path(path)
    if not _ezc3d_uses_ascii_staging(path):
        c3d.write(str(path));return
    with tempfile.TemporaryDirectory(prefix='c3d-') as folder:
        staged=Path(folder)/'output.c3d'
        c3d.write(str(staged))
        shutil.copy2(staged,path)

class Session:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.c3d = read_c3d(self.path)
        self.points = self.c3d['data']['points'].copy()
        self.labels = [str(s).strip() for s in self.c3d['parameters']['POINT']['LABELS']['value']]
        self.rate = float(self.c3d['parameters']['POINT']['RATE']['value'][0])
        self.frames = self.points.shape[2]
        # ezc3d exposes the header frame index as zero-based. UI uses C3D frame numbers.
        self.first = int(self.c3d['header']['points']['first_frame']) + 1
        residual = self.c3d['data']['meta_points']['residuals'][0]
        self.valid = np.isfinite(self.points[:3]).all(axis=0) & (residual >= 0)
        self.identity_edits=[]
        self.slot_channels={}
        self.base_labels=list(self.labels)
        self.custom_channels={}
        self.markers=[dict(label=f'R{i}',origin=i,start=0,end=self.frames-1) for i in range(len(self.labels))]
        self.effective_meta={k:v.copy() for k,v in self.c3d['data']['meta_points'].items()}
        self.original_source_index=np.broadcast_to(np.arange(len(self.labels))[:,None],self.valid.shape).copy()
        self.slots = list(BODY39)
        self.model_scheme=copy.deepcopy(PRESETS[0])
        self.fill_excluded=[]
        # Each assignment uses zero-based inclusive frame indices.
        self.assignments = []
        self.public_pairings=None
        self.max_gap_seconds = 0.1
        self.repairs=[]
        self.fill_enabled = False
        self.fill_method = 'pchip'
        self.fill_tension = .7
        self.fill_jobs = None
        self.fill_smoothing = 0.
        self.fill_smooth_window = 7
        self.history = []
        self.future = []

    @staticmethod
    def is_wand(name):
        return 'WAND' in name.upper() or '灯棒' in name

    @staticmethod
    def is_auxiliary(name):
        return name not in set(BODY39+['LHEE','RHEE'])

    def default_fill_exclusions(self):
        return [name for name in self.slots if name not in self.model_scheme['body_slots']]

    def set_fill_excluded(self,names):
        if any(name not in self.slots for name in names):raise ValueError('排除清单包含未知位置')
        normalized=[name for name in self.slots if name in names]
        if normalized!=self.fill_excluded:self.checkpoint();self.fill_excluded=normalized

    def snapshot(self):
        return json.loads(json.dumps(dict(slots=self.slots,model_scheme=self.model_scheme, assignments=self.assignments,markers=self.markers,custom_channels=self.custom_channels,public_pairings=self.public_pairings,
            max_gap_seconds=self.max_gap_seconds,fill_excluded=self.fill_excluded, fill_enabled=self.fill_enabled,repairs=self.repairs,fill_method=self.fill_method,fill_tension=self.fill_tension,fill_jobs=self.fill_jobs,fill_smoothing=self.fill_smoothing,fill_smooth_window=self.fill_smooth_window,identity_edits=self.identity_edits,slot_channels=self.slot_channels)))

    def checkpoint(self):
        self.history.append(self.snapshot()); self.future.clear()

    def marker_sources(self,marker):
        """Resolve one public original ID to backend owners, including edited channels."""
        m=self.markers[marker];owners=np.full(self.frames,-1,dtype=int)
        if m['origin'] is None:
            source=self.custom_channels[m['channel']];mask=self.valid[source].copy();mask[:m['start']]=False;mask[m['end']+1:]=False;owners[mask]=source
        else:
            for source in range(len(self.labels)):
                mask=(self.original_source_index[source]==m['origin'])&self.valid[source]
                owners[mask]=source
            owners[:m['start']]=-1;owners[m['end']+1:]=-1
        return owners

    def marker_source(self,marker,frame):
        owners=self.marker_sources(marker)
        if owners[frame]>=0:return int(owners[frame])
        frames=np.flatnonzero(owners>=0)
        return int(owners[frames[np.argmin(abs(frames-frame))]]) if len(frames) else None

    def public_marker_for(self,source,frame):
        if source<0 or source>=len(self.labels):return None
        origin=int(self.original_source_index[source,frame])
        for i,m in enumerate(self.markers):
            if m['start']<=frame<=m['end'] and ((origin>=0 and m['origin']==origin) or (m['origin'] is None and self.custom_channels[m['channel']]==source)):return i
        return None

    def edit_marker_labels(self,labels):
        if len(labels)<len(self.markers) or any(not x.strip() for x in labels) or len(set(labels))!=len(labels):raise ValueError('编号不能为空或重复；已有编号不能删除，新增编号请写在末尾。')
        self.checkpoint()
        for marker,label in zip(self.markers,labels):marker['label']=label
        for label in labels[len(self.markers):]:
            key=f'user_{len(self.custom_channels)}';self.custom_channels[key]=len(self.labels)
            self.markers.append(dict(label=label,origin=None,channel=key,start=0,end=self.frames-1));self.rebuild_identities()

    def split_marker(self,marker,frame,label):
        m=self.markers[marker]
        if not m['start']<frame<=m['end']:raise ValueError('拆分帧必须在该点时间范围内部，且两段都至少包含一帧。')
        if not label.strip():raise ValueError('新编号不能为空。')
        existing=next((i for i,x in enumerate(self.markers) if x['label']==label),None)
        if existing is not None:
            target=self.markers[existing]
            if target['origin'] is not None or self.valid[self.custom_channels[target['channel']]].any():raise ValueError('该编号已有数据，请使用新编号或新增的空编号。')
        owners=self.marker_sources(marker);end=m['end'];self.checkpoint()
        if existing is None:
            key=f'user_{len(self.custom_channels)}';channel=len(self.labels);self.custom_channels[key]=channel;self.rebuild_identities()
        else:key=self.markers[existing]['channel'];channel=self.custom_channels[key]
        for source in np.unique(owners[frame:end+1]):
            if source<0:continue
            mask=owners==source;mask[:frame]=False;mask[end+1:]=False
            for lo,hi in self._runs(mask):
                self.identity_edits.append(dict(destinations=[int(source),channel],sources=[channel,int(source)],start=int(lo),end=int(hi)))
        result=[]
        for a in self.assignments:
            mask=np.zeros(self.frames,dtype=bool);mask[a['start']:a['end']+1]=True
            moved=mask&(owners==a['source']);moved[:frame]=False;moved[end+1:]=False
            for lo,hi in self._runs(mask&~moved):result.append(dict(a,start=int(lo),end=int(hi)))
            for lo,hi in self._runs(moved):result.append(dict(a,source=channel,start=int(lo),end=int(hi)))
        self.assignments=result;self.rebuild_identities();m['end']=frame-1
        new=dict(label=label,origin=m['origin'],start=frame,end=end)
        if m['origin'] is None:new['channel']=key
        if existing is not None:self.markers[existing]=new;new_index=existing
        else:self.markers.append(new);new_index=len(self.markers)-1
        if self.public_pairings is not None:
            rules=[]
            for rule in self.public_pairings:
                if rule['marker']!=marker or rule['end']<frame:rules.append(rule);continue
                if rule['start']<frame:rules.append(dict(rule,end=frame-1))
                rules.append(dict(rule,marker=new_index,start=max(frame,rule['start'])))
            self.public_pairings=rules
        return new_index

    def pairing_matrix(self):
        """One public marker per anatomical slot and frame, including missing samples."""
        matrix=np.full((len(self.slots),self.frames),-1,dtype=int)
        if self.public_pairings is not None:
            for rule in self.public_pairings:matrix[self.slots.index(rule['slot']),rule['start']:rule['end']+1]=rule['marker']
            return matrix
        for a in self.assignments:
            row=self.slots.index(a['slot']);lo=a['start'];hi=a['end']
            found=[]
            for marker,m in enumerate(self.markers):
                left=max(lo,m['start']);right=min(hi,m['end'])
                if left>right:continue
                if m['origin'] is None:mask=np.full(right-left+1,a['source']==self.custom_channels[m['channel']])
                else:mask=self.original_source_index[a['source'],left:right+1]==m['origin']
                if mask.any():
                    values=matrix[row,left:right+1];values[mask]=marker;found.append(marker)
            if len(found)==1:
                m=self.markers[found[0]];left=max(lo,m['start']);right=min(hi,m['end'])
                values=matrix[row,left:right+1];values[values<0]=found[0]
        # A legacy channel may be listed under multiple names in empty ranges.
        for frame in range(self.frames):
            seen=set()
            for row in np.flatnonzero(matrix[:,frame]>=0):
                marker=int(matrix[row,frame])
                if marker in seen:matrix[row,frame]=-1
                else:seen.add(marker)
        return matrix

    def exchange_marker(self,marker,slot,start,end):
        if not 0<=marker<len(self.markers) or slot not in self.slots or not 0<=start<=end<self.frames:raise ValueError('无效编号、关键点或时间范围。')
        m=self.markers[marker];start=max(start,m['start']);end=min(end,m['end'])
        if start>end:raise ValueError('选区与编号的时间范围没有重叠。')
        matrix=self.pairing_matrix();target=self.slots.index(slot)
        for frame in range(start,end+1):
            previous=np.flatnonzero(matrix[:,frame]==marker)
            if len(previous) and previous[0]!=target:matrix[previous[0],frame]=matrix[target,frame]
            matrix[target,frame]=marker
        self._commit_pairing_matrix(matrix,start,end)

    def clear_pairing(self,start,end,marker=None,slot=None):
        matrix=self.pairing_matrix()
        if marker is not None:
            part=matrix[:,start:end+1];part[part==marker]=-1
        elif slot in self.slots:matrix[self.slots.index(slot),start:end+1]=-1
        else:raise ValueError('请先选择编号或关键点。')
        self._commit_pairing_matrix(matrix,start,end)

    def _commit_pairing_matrix(self,matrix,start,end):
        previous=self.pairing_matrix()
        affected={self.slots[row] for row in range(len(self.slots)) if np.any(previous[row]!=matrix[row])}
        if not affected:return
        rules=[];assignments=[];owner_cache={}
        for row,slot in enumerate(self.slots):
            values=matrix[row];edges=np.r_[0,np.flatnonzero(np.diff(values))+1,self.frames]
            for lo,stop in zip(edges[:-1],edges[1:]):
                marker=int(values[lo])
                if marker<0:continue
                rules.append(dict(slot=slot,marker=marker,start=int(lo),end=int(stop-1)))
                if marker not in owner_cache:owner_cache[marker]=self.marker_sources(marker)
                owners=owner_cache[marker][lo:stop];bounds=np.r_[0,np.flatnonzero(np.diff(owners))+1,len(owners)]
                for left,right in zip(bounds[:-1],bounds[1:]):
                    if owners[left]>=0:assignments.append(dict(slot=slot,source=int(owners[left]),start=int(lo+left),end=int(lo+right-1)))
        self.checkpoint();self.public_pairings=rules;self.assignments=assignments
        self.repairs=[r for r in self.repairs if r['slot'] not in affected or not np.any(previous[self.slots.index(r['slot']),r['left']:r['right']+1]!=matrix[self.slots.index(r['slot']),r['left']:r['right']+1])]

    def source_details(self):
        return [dict(marker=m.copy(),owners=self._runs(self.marker_sources(i)>=0),internal_sources=sorted(set(int(x) for x in self.marker_sources(i) if x>=0))) for i,m in enumerate(self.markers)]

    def place_marker_interval(self,marker,slot,start,end):
        start=max(start,self.markers[marker]['start']);end=min(end,self.markers[marker]['end'])
        if start>end:raise ValueError('选区与此编号的时间范围没有重叠。')
        work=copy.copy(self)
        for key,value in self.snapshot().items():setattr(work,key,copy.deepcopy(value))
        work.history=[];work.future=[];work.rebuild_identities();position=start;changed=False;target=None
        while position<=end:
            owners=work.marker_sources(marker);source=int(owners[position])
            if source<0:position+=1;continue
            stop=position
            while stop<end and owners[stop+1] in (-1,source):stop+=1
            target=work.place_interval(source,slot,position,stop);changed=True;position=stop+1
        if not changed:raise ValueError('此编号在选区内没有有效坐标。')
        self.checkpoint();self.restore(work.snapshot());return target

    def pair_marker_name(self,marker,slot):
        owners=self.marker_sources(marker)
        if not np.any(owners>=0):raise ValueError('此编号还没有数据，请先拆分或接入轨迹。')
        mapping=np.full((len(self.slots),self.frames),-1,dtype=int)
        for a in self.assignments:mapping[self.slots.index(a['slot']),a['start']:a['end']+1]=a['source']
        target=self.slots.index(slot)
        for frame in np.flatnonzero(owners>=0):
            source=owners[frame];previous=np.flatnonzero(mapping[:,frame]==source)
            if len(previous) and previous[0]!=target:mapping[previous[0],frame]=mapping[target,frame]
            mapping[target,frame]=source
        result=[]
        for row,name in enumerate(self.slots):
            values=mapping[row];bounds=np.r_[0,np.flatnonzero(np.diff(values))+1,self.frames]
            for lo,stop in zip(bounds[:-1],bounds[1:]):
                if values[lo]>=0:result.append(dict(slot=name,source=int(values[lo]),start=int(lo),end=int(stop-1)))
        self.checkpoint();self.assignments=result;self.repairs=[]

    def restore(self, state):
        for k, v in state.items(): setattr(self, k, v)
        self.rebuild_identities()

    def undo(self):
        if self.history:
            self.future.append(self.snapshot()); self.restore(self.history.pop())

    def redo(self):
        if self.future:
            self.history.append(self.snapshot()); self.restore(self.future.pop())

    def correct_medial_ankles(self):
        """User protocol: old heel assignments actually contain medial ankle markers."""
        rename={old:new for old,new in [('LHEE','LMMA'),('RHEE','RMMA')] if old in self.slots}
        if not rename:return False
        if any(new in self.slots for new in rename.values()):
            raise ValueError('项目同时包含足跟和内踝槽位，请先检查，避免覆盖已有配对')
        self.checkpoint()
        self.slots=[rename.get(name,name) for name in self.slots]
        for assignment in self.assignments:
            assignment['slot']=rename.get(assignment['slot'],assignment['slot'])
        return True

    def assign(self, slot, source, start, end):
        if slot not in self.slots or not 0 <= source < len(self.labels):
            raise ValueError('无效的槽位或原始点')
        if not 0 <= start <= end < self.frames:
            raise ValueError('帧范围无效')
        for a in self.assignments:
            lo, hi = max(start,a['start']), min(end,a['end'])
            if lo > hi: continue
            if a['slot'] == slot:
                if np.any(self.valid[source,lo:hi+1] & self.valid[a['source'],lo:hi+1]):
                    raise ValueError('槽位在此区间已有有效数据，请先移除冲突配对')
            elif a['source'] == source and np.any(self.valid[source,lo:hi+1]):
                raise ValueError('同一原始点在此区间已经配给其他槽位')
        self.checkpoint()
        self.assignments.append(dict(slot=slot,source=int(source),start=int(start),end=int(end)))

    def bind_identity(self, slot, source):
        """Establish one logical ID for an anatomical slot throughout the trial."""
        if slot not in self.slots or not 0<=source<len(self.labels):raise ValueError('无效槽位或编号')
        related=[a for a in self.assignments if a['slot']==slot or a['source']==source]
        if any(a['slot']!=slot or a['source']!=source for a in related):
            raise ValueError('此槽位或编号已有其他配对，不能直接覆盖。请检查已有记录，或使用原分段配对模式。')
        replacement=dict(slot=slot,source=int(source),start=0,end=self.frames-1)
        if related==[replacement]:return
        self.checkpoint()
        self.assignments=[a for a in self.assignments if a not in related]+[replacement]

    def pair_fixed_marker(self,source,slot):
        """Change full-trial anatomical associations without moving marker samples."""
        if slot not in self.slots or not 0<=source<len(self.labels):raise ValueError('无效编号或关键点')
        old={a['slot'] for a in self.assignments if a['source']==source}
        targets={a['source'] for a in self.assignments if a['slot']==slot}
        if len(old)>1 or len(targets)>1:raise ValueError('此点存在多个分段配对，请先取消相关配对，再建立全程配对。')
        self.checkpoint()
        affected=old|{slot}
        self.assignments=[a for a in self.assignments if a['slot'] not in affected and a['source']!=source]
        self.assignments.append(dict(slot=slot,source=int(source),start=0,end=self.frames-1))
        if old and targets and source not in targets and slot not in old:
            self.assignments.append(dict(slot=next(iter(old)),source=int(next(iter(targets))),start=0,end=self.frames-1))
        self.repairs=[r for r in self.repairs if r['slot'] not in affected]

    def unpair_slot(self,slot):
        if slot not in self.slots:raise ValueError('无效关键点')
        if not any(a['slot']==slot for a in self.assignments):return
        self.checkpoint();self.assignments=[a for a in self.assignments if a['slot']!=slot]
        self.repairs=[r for r in self.repairs if r['slot']!=slot]

    def build(self, fill=True, repair=True):
        xyz = np.full((3,len(self.slots),self.frames), np.nan)
        # 0 missing, 1 measured, 2 interpolated
        status = np.zeros((len(self.slots),self.frames), dtype=np.uint8)
        origin = np.full((len(self.slots),self.frames), -1, dtype=int)
        for a in self.assignments:
            j = self.slots.index(a['slot']); idx = np.arange(a['start'],a['end']+1)
            idx = idx[self.valid[a['source'],idx]]
            xyz[:,j,idx] = self.points[:3,a['source'],idx]
            status[j,idx] = 1; origin[j,idx] = a['source']
        if self.fill_enabled and fill:
            measured=status==1;plans=self.fill_plans()
            for j,name in enumerate(self.slots):
                if name in self.fill_excluded:continue
                relevant=[job for job in plans if name in job['slots']]
                if not relevant:continue
                good=np.flatnonzero(measured[j])
                for left,right in zip(good[:-1],good[1:]):
                    count=right-left-1
                    if count<=0:continue
                    job=next((job for job in reversed(relevant) if left+1>=job['start'] and right-1<=job['end'] and count<=int(np.floor(job['max_gap_seconds']*self.rate+1e-9))),None)
                    if job is None:continue
                    target=np.arange(left+1,right);before=left;after=right
                    while before>0 and left-before<3 and measured[j,before-1]:before-=1
                    while after+1<self.frames and after-right<3 and measured[j,after+1]:after+=1
                    support=np.r_[np.arange(before,left+1),np.arange(right,after+1)]
                    if job['method']=='bezier':values=np.asarray(replacement_curve(xyz[:,j],measured[j],left+1,right-1,'bezier',job.get('tension',.7),job.get('smooth_window',7))['values'])
                    elif job['method']=='pchip' and len(support)>=3:values=PchipInterpolator(support,xyz[:,j,support],axis=1)(target)
                    else:
                        weight=(target-left)/(right-left);values=xyz[:,j,left,None]*(1-weight)+xyz[:,j,right,None]*weight
                    if job['method']!='bezier':values=smooth_gap(xyz[:,j],measured[j],left,right,values,job.get('smooth_strength',0.),job.get('smooth_window',7))
                    if np.isfinite(values).all():xyz[:,j,target]=values;status[j,target]=2
        if repair:
            for item in self.repairs:
                if item['slot'] not in self.slots or item['slot'] in self.fill_excluded:continue
                j=self.slots.index(item['slot']);lo,hi=item['start'],item['end']
                xyz[:,j,lo:hi+1]=np.asarray(item['values']);status[j,lo:hi+1]=3;origin[j,lo:hi+1]=-1
        return xyz,status,origin

    def repair_preview(self, slot, start, end, method='bezier', tension=.7, window=7):
        if slot not in self.slots or not 0<=start<=end<self.frames:raise ValueError('请选中位置并框选需要替换的区间')
        if slot in self.fill_excluded:raise ValueError('此位置已排除补帧，请在排除清单中调整后再处理')
        if not np.isfinite(tension) or not 0<=tension<=1 or not 3<=window<=31:raise ValueError('曲线参数无效')
        xyz,status,_=self.build(fill=False,repair=False);j=self.slots.index(slot)
        item=replacement_curve(xyz[:,j],status[j]==1,start,end,method,tension,window)
        item.update(slot=slot,method=method,tension=float(tension),window=int(window))
        return item

    def apply_repair(self, item):
        if item['slot'] not in self.slots:raise ValueError('目标位置已变化')
        values=np.asarray(item['values']);lo,hi=item['start'],item['end']
        if not 0<=lo<=hi<self.frames or values.shape!=(3,hi-lo+1) or not np.isfinite(values).all():raise ValueError('修复结果无效')
        self.checkpoint();self.repairs.append(copy.deepcopy(item))

    def remove_repairs(self, slot, start, end):
        if slot not in self.slots or not 0<=start<=end<self.frames:raise ValueError('范围无效')
        self.checkpoint();remaining=[]
        for item in self.repairs:
            lo,hi=item['start'],item['end']
            if item['slot']!=slot or hi<start or lo>end:remaining.append(item);continue
            if lo<start:remaining.append(dict(item,end=start-1,values=np.asarray(item['values'])[:,:start-lo].tolist()))
            if hi>end:remaining.append(dict(item,start=end+1,values=np.asarray(item['values'])[:,end+1-lo:].tolist()))
        self.repairs=remaining

    def fill_plans(self):
        if self.fill_jobs is not None:return self.fill_jobs
        return [dict(slots=list(self.slots),start=0,end=self.frames-1,method=self.fill_method,max_gap_seconds=self.max_gap_seconds,smooth_strength=self.fill_smoothing,smooth_window=self.fill_smooth_window,tension=self.fill_tension)]

    def add_fill_job(self, slots, start, end, method, max_gap_seconds, smooth_strength=0., smooth_window=7, tension=.7):
        slots=[name for name in dict.fromkeys(slots) if name not in self.fill_excluded]
        if not slots or any(n not in self.slots for n in slots):raise ValueError('请选择已校准的人体位置')
        if not 0<=start<=end<self.frames or method not in ['linear','pchip','bezier']:raise ValueError('补帧范围或方法无效')
        if not np.isfinite(max_gap_seconds) or max_gap_seconds<0:raise ValueError('缺口阈值无效')
        if not np.isfinite(smooth_strength) or not 0<=smooth_strength<=1 or not isinstance(smooth_window,int) or not 3<=smooth_window<=31:raise ValueError('平滑参数无效')
        if not np.isfinite(tension) or not 0<=tension<=1:raise ValueError('弯曲程度无效')
        self.checkpoint()
        jobs=copy.deepcopy(self.fill_plans()) if self.fill_enabled else []
        jobs.append(dict(slots=slots,start=int(start),end=int(end),method=method,max_gap_seconds=float(max_gap_seconds),smooth_strength=float(smooth_strength),smooth_window=smooth_window,tension=float(tension)))
        self.fill_jobs=jobs;self.fill_enabled=True;self.fill_method=method;self.max_gap_seconds=float(max_gap_seconds);self.fill_smoothing=float(smooth_strength);self.fill_smooth_window=smooth_window;self.fill_tension=float(tension)

    def remove_fill_range(self, slots, start, end):
        if not 0<=start<=end<self.frames:raise ValueError('范围无效')
        self.checkpoint();jobs=[]
        for job in self.fill_plans():
            affected=[n for n in job['slots'] if n in slots]
            untouched=[n for n in job['slots'] if n not in slots]
            if not affected or job['end']<start or job['start']>end:jobs.append(copy.deepcopy(job));continue
            if untouched:jobs.append(dict(job,slots=untouched))
            if job['start']<start:jobs.append(dict(job,slots=affected,end=start-1))
            if job['end']>end:jobs.append(dict(job,slots=affected,start=end+1))
        self.fill_jobs=jobs

    def gap_report(self, slots, start, end, maximum, measured_result=None, current_result=None):
        original,measured,_=measured_result if measured_result is not None else self.build(fill=False,repair=False)
        _,current,_=current_result if current_result is not None else self.build();rows=[]
        for name in slots:
            if name in self.fill_excluded:continue
            j=self.slots.index(name)
            for lo,hi in self._runs(measured[j]==0):
                if hi<start or lo>end:continue
                reason='可补'
                if lo==0 or hi==self.frames-1:reason='缺少两端参考'
                elif lo<start or hi>end:reason='缺口跨出选区'
                elif (hi-lo+1)/self.rate>maximum+1e-9:reason='超过长度阈值'
                manually_repaired=np.all(current[j,lo:hi+1]>=2) and np.any(current[j,lo:hi+1]==3)
                if np.all(current[j,lo:hi+1]>=2):reason='已补（整段修复）' if manually_repaired else '已补（插值）'
                if not manually_repaired and lo>0 and hi+1<self.frames and (suspicious_anchor(original[:,j],measured[j]==1,lo-1,-1) or suspicious_anchor(original[:,j],measured[j]==1,hi+1,1)):
                    reason+=' · 实测边界突变'
                if not manually_repaired and lo>0 and hi+1<self.frames and (lo<3 or hi+3>=self.frames
                    or not np.all(measured[j,lo-3:lo]==1) or not np.all(measured[j,hi+1:hi+4]==1)):
                    reason+=' · 边界参考较少'
                rows.append(dict(slot=name,start=int(lo),end=int(hi),frames=int(hi-lo+1),seconds=(hi-lo+1)/self.rate,status=reason))
        for name in slots:
            if name in self.fill_excluded:continue
            j=self.slots.index(name)
            for lo,hi in self._runs(measured[j]==1):
                if hi-lo>1 or lo==0 or hi==self.frames-1 or hi<start or lo>end:continue
                if measured[j,lo-1] or measured[j,hi+1]:continue
                done=np.all(current[j,lo:hi+1]==3)
                rows.append(dict(slot=name,start=int(lo),end=int(hi),frames=int(hi-lo+1),seconds=(hi-lo+1)/self.rate,status='已补（整段修复）' if done else '孤立有效点 · 建议检查'))
        return rows

    def rebuild_identities(self):
        base=self.c3d['data']['points'];extra=len(self.slot_channels)+len(self.custom_channels)
        channels={**self.slot_channels,**self.custom_channels}
        self.labels=self.base_labels+[name for name,index in sorted(channels.items(),key=lambda item:item[1])]
        self.points=np.concatenate([base.copy(),np.zeros((4,extra,self.frames))],axis=1)
        self.points[:3,base.shape[1]:]=np.nan
        self.effective_meta={}
        for key,value in self.c3d['data']['meta_points'].items():
            padding=np.zeros((value.shape[0],extra,self.frames),dtype=value.dtype)
            if key=='residuals':padding[:]=-1
            self.effective_meta[key]=np.concatenate([value.copy(),padding],axis=1)
        self.original_source_index=np.full(self.points.shape[1:],-1,dtype=int)
        self.original_source_index[:base.shape[1]]=np.arange(base.shape[1])[:,None]
        for edit in self.identity_edits:
            dest=edit['destinations'];src=edit['sources'];sl=slice(edit['start'],edit['end']+1)
            self.points[:,dest,sl]=self.points[:,src,sl].copy()
            for values in self.effective_meta.values():values[:,dest,sl]=values[:,src,sl].copy()
            self.original_source_index[dest,sl]=self.original_source_index[src,sl].copy()
        self.valid=np.isfinite(self.points[:3]).all(axis=0)&(self.effective_meta['residuals'][0]>=0)

    def renumber_interval(self, destinations, sources, start, end):
        """Move trajectory samples among fixed logical IDs; anatomical assignments stay fixed."""
        destinations=list(destinations);sources=list(sources)
        if (len(destinations)<2 or len(set(destinations))!=len(destinations)
            or sorted(destinations)!=sorted(sources)
            or any(not isinstance(i,int) or not 0<=i<len(self.labels) for i in destinations)):
            raise ValueError('所选编号必须一一对应，每个原编号只能使用一次（可互换或循环更正）')
        if not 0<=start<=end<self.frames:raise ValueError('帧范围无效')
        if destinations==sources:raise ValueError('编号对应未改变')
        edit=dict(destinations=destinations,sources=sources,start=int(start),end=int(end))
        probe=copy.copy(self);probe.identity_edits=self.identity_edits+[edit];probe.rebuild_identities()
        # A previous segment-based assignment can become ambiguous after moving missing samples.
        for i,a in enumerate(self.assignments):
            for b in self.assignments[i+1:]:
                lo,hi=max(a['start'],b['start']),min(a['end'],b['end'])
                if lo>hi:continue
                if (a['slot']==b['slot'] or a['source']==b['source']) and np.any(
                    probe.valid[a['source'],lo:hi+1]&probe.valid[b['source'],lo:hi+1]):
                    raise ValueError('此编号更正与已有分段配对冲突，请先检查这些槽位的重叠配对。项目未修改。')
        self.checkpoint();self.identity_edits.append(edit);self.rebuild_identities()

    @staticmethod
    def _runs(mask):
        edges=np.flatnonzero(np.diff(np.r_[False,mask,False].astype(int)))
        return list(zip(edges[::2],edges[1::2]-1))

    def place_interval(self, source, slot, start, end):
        """Put a picked trajectory under a stable anatomical identity, swapping occupied data."""
        if slot not in self.slots or not 0<=source<len(self.labels):raise ValueError('请选择点和目标位置')
        if not 0<=start<=end<self.frames:raise ValueError('帧范围无效')
        original_measured=self.build(fill=False,repair=False)[0]
        selected_origin=self.original_source_index[source].copy();selected_valid=self.valid[source].copy()
        work=copy.copy(self);work.assignments=copy.deepcopy(self.assignments)
        work.slot_channels=self.slot_channels.copy();work.identity_edits=copy.deepcopy(self.identity_edits)
        work.history=[];work.future=[]
        # Normalize legacy fragment mappings once. Stable anatomical channels start empty.
        names=list(dict.fromkeys([a['slot'] for a in work.assignments]+[slot]))
        original_origins={}
        for name in names:
            origins=np.full(self.frames,-1,dtype=int)
            for a in self.assignments:
                if a['slot']==name:
                    sl=slice(a['start'],a['end']+1)
                    origins[sl]=np.where(self.valid[a['source'],sl],self.original_source_index[a['source'],sl],-1)
            original_origins[name]=origins
        for name in names:
            channel=work.slot_channels.get(name)
            previous=[a for a in work.assignments if a['slot']==name]
            if channel is not None and previous==[dict(slot=name,source=channel,start=0,end=self.frames-1)]:continue
            if channel is None:
                channel=len(work.labels);work.slot_channels[name]=channel;work.rebuild_identities()
            previous=[a for a in work.assignments if a['slot']==name]
            owners=np.full(self.frames,-1,dtype=int)
            desired=original_origins[name]
            for owner in range(len(work.labels)):
                owners[(desired>=0)&work.valid[owner]&(work.original_source_index[owner]==desired)]=owner
            for owner in np.unique(owners[owners>=0]):
                if owner==channel:continue
                mask=owners==owner
                for lo,hi in self._runs(mask):
                    work.identity_edits.append(dict(destinations=[channel,int(owner)],sources=[int(owner),channel],start=int(lo),end=int(hi)))
                work.rebuild_identities()
            work.assignments=[a for a in work.assignments if a['slot']!=name]+[dict(slot=name,source=channel,start=0,end=self.frames-1)]
        target=work.slot_channels[slot]
        owners=np.full(self.frames,source,dtype=int)
        # Locate the selected physical samples even after legacy-to-fixed migration.
        for frame in range(start,end+1):
            if selected_valid[frame]:
                matches=np.flatnonzero((work.original_source_index[:,frame]==selected_origin[frame])&work.valid[:,frame])
                if len(matches):owners[frame]=int(matches[0])
        for owner in np.unique(owners[start:end+1]):
            if owner==target:continue
            mask=owners==owner;mask[:start]=False;mask[end+1:]=False
            for lo,hi in self._runs(mask):
                work.identity_edits.append(dict(destinations=[target,int(owner)],sources=[int(owner),target],start=int(lo),end=int(hi)))
        work.rebuild_identities()
        self.checkpoint()
        self.slot_channels=work.slot_channels;self.identity_edits=work.identity_edits;self.assignments=work.assignments
        self.rebuild_identities()
        new_measured=self.build(fill=False,repair=False)[0]
        self.repairs=[item for item in self.repairs if np.array_equal(original_measured[:,self.slots.index(item['slot']),item['left']:item['right']+1],new_measured[:,self.slots.index(item['slot']),item['left']:item['right']+1],equal_nan=True)]
        return target

    def swap_interval(self, slot_a, slot_b, start, end):
        """Swap slot identity only inside an inclusive interval; never alter raw samples."""
        if slot_a==slot_b or slot_a not in self.slots or slot_b not in self.slots:
            raise ValueError('请选择两个不同的有效槽位')
        if not 0<=start<=end<self.frames:raise ValueError('帧范围无效')
        # Both identities must be established somewhere in the selected interval.
        for name in [slot_a,slot_b]:
            if not any(a['slot']==name and a['start']<=end and a['end']>=start for a in self.assignments):
                raise ValueError('两个槽位在选定区间都需要已有配对，请先完成初始配对')
        result=[]
        for a in self.assignments:
            lo,hi=max(start,a['start']),min(end,a['end'])
            if a['slot'] not in [slot_a,slot_b] or lo>hi:
                result.append(a.copy());continue
            if a['start']<lo:result.append(dict(a,end=lo-1))
            result.append(dict(a,slot=slot_b if a['slot']==slot_a else slot_a,start=lo,end=hi))
            if hi<a['end']:result.append(dict(a,start=hi+1))
        self.checkpoint();self.assignments=result

    def update_slots(self, names):
        if not names or any(not n.strip() for n in names) or len(set(names))!=len(names):
            raise ValueError('槽位名称必须非空且唯一')
        removed={a['slot'] for a in self.assignments}-set(names)
        removed|={r['slot'] for r in (self.public_pairings or [])}-set(names)
        removed|=set(self.slot_channels)-set(names)
        if removed:
            raise ValueError('以下槽位已有配对，不能直接移除或改名：'+ '、'.join(sorted(removed))+'。本次模板未修改，已有配对保留。')
        if names!=self.slots:
            self.checkpoint()
            self.fill_excluded=[name for name in names if name in self.fill_excluded or (name not in self.slots and name not in self.model_scheme['body_slots'])]
            self.slots=list(names)
            self.model_scheme['body_slots']=[n for n in self.model_scheme['body_slots'] if n in names]
            self.model_scheme['extra_slots']=[n for n in names if n not in self.model_scheme['body_slots']]

    def scheme_result(self,value):
        scheme=validate_scheme(value);requested=scheme['body_slots']+scheme['extra_slots']
        used={a['slot'] for a in self.assignments}|set(self.slot_channels)|{a['slot'] for a in (self.public_pairings or [])}|{r['slot'] for r in self.repairs}
        for job in self.fill_jobs or []:used.update(job['slots'])
        retained=[n for n in self.slots if n in used and n not in requested]
        scheme['extra_slots']+=retained
        return scheme,retained

    def apply_model_scheme(self,value):
        scheme,retained=self.scheme_result(value);names=scheme['body_slots']+scheme['extra_slots']
        if scheme==self.model_scheme and names==self.slots:return retained
        previous=set(self.model_scheme['body_slots']);old_names=set(self.slots);excluded=set(self.fill_excluded)
        self.checkpoint();self.model_scheme=scheme;self.slots=names
        self.fill_excluded=[n for n in names if n in excluded or (n in scheme['extra_slots'] and (n not in old_names or n in previous))]
        return retained

    def save_project(self, path):
        path=Path(path).resolve()
        if path==self.path:raise ValueError('不能覆盖原始 C3D')
        data = dict(version=11,source=str(self.path),sha256=self.digest,state=self.snapshot())
        try:data['source_relative']=os.path.relpath(self.path,path.parent)
        except ValueError:pass  # Different Windows drives cannot form a relative path.
        text=json.dumps(data,ensure_ascii=False,indent=2)
        descriptor,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
        try:
            with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
                stream.write(text);stream.flush();os.fsync(stream.fileno())
            if json.loads(Path(tmp).read_text(encoding='utf-8'))!=data:
                raise IOError('写入核验失败，原项目未替换')
            if path.exists():
                backup=path.with_name(path.name+'.'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.bak')
                shutil.copy2(path,backup)
            os.replace(tmp,path)
            if json.loads(path.read_text(encoding='utf-8'))!=data:raise IOError('保存后核验失败')
        finally:
            if Path(tmp).exists():Path(tmp).unlink()
        return path

    @classmethod
    def load_project(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('version',1)>11:raise ValueError('项目版本较新，请升级编辑器')
        project=Path(path).resolve();source_text=data['source']
        basename=PureWindowsPath(source_text).name if '\\' in source_text else Path(source_text).name
        candidates=[Path(source_text)]
        if data.get('source_relative'):candidates.append(project.parent/str(data['source_relative']).replace('\\','/'))
        candidates.append(project.parent/basename)
        source=next((candidate for candidate in candidates if candidate.is_file() and hashlib.sha256(candidate.read_bytes()).hexdigest()==data['sha256']),None)
        if source is None:
            if any(candidate.is_file() for candidate in candidates):raise ValueError('原始文件内容已改变，无法安全加载项目')
            raise FileNotFoundError('找不到原始 C3D。请把原始文件与项目 JSON 放在同一文件夹后重试。')
        obj = cls(source)
        state = data['state']
        if not state['slots'] or len(set(state['slots'])) != len(state['slots']):
            raise ValueError('槽位名称必须非空且唯一')
        obj.slots = state['slots']
        obj.model_scheme=validate_scheme(state.get('model_scheme',infer_scheme(obj.slots)))
        if set(obj.model_scheme['body_slots']+obj.model_scheme['extra_slots'])!=set(obj.slots):raise ValueError('项目方案与点位列表不一致')
        obj.fill_excluded=list(state.get('fill_excluded',obj.default_fill_exclusions()))
        if any(name not in obj.slots for name in obj.fill_excluded):raise ValueError('补帧排除清单包含未知位置')
        obj.slot_channels={str(k):int(v) for k,v in state.get('slot_channels',{}).items()}
        obj.custom_channels={str(k):int(v) for k,v in state.get('custom_channels',{}).items()}
        obj.markers=copy.deepcopy(state.get('markers',obj.markers))
        if any(not isinstance(m.get('label'),str) or not 0<=m['start']<=m['end']<obj.frames or (m['origin'] is not None and not 0<=m['origin']<len(obj.base_labels)) or (m['origin'] is None and m.get('channel') not in obj.custom_channels) for m in obj.markers) or len({m['label'] for m in obj.markers})!=len(obj.markers):raise ValueError('项目公开编号表损坏')
        expected=list(range(len(obj.base_labels),len(obj.base_labels)+len(obj.slot_channels)+len(obj.custom_channels)))
        if any(name not in obj.slots for name in obj.slot_channels) or sorted(list(obj.slot_channels.values())+list(obj.custom_channels.values()))!=expected:raise ValueError('项目固定编号表损坏')
        obj.rebuild_identities()
        edits=copy.deepcopy(state.get('identity_edits',[]))
        for edit in edits:
            dest,src=edit['destinations'],edit['sources']
            if (len(dest)<2 or len(set(dest))!=len(dest) or sorted(dest)!=sorted(src)
                or any(not isinstance(i,int) or not 0<=i<len(obj.labels) for i in dest)
                or not 0<=edit['start']<=edit['end']<obj.frames):
                raise ValueError('项目编号修正记录损坏')
        obj.identity_edits=edits;obj.rebuild_identities()
        for a in state['assignments']: obj.assign(**a)
        obj.max_gap_seconds = float(state['max_gap_seconds'])
        if not np.isfinite(obj.max_gap_seconds) or obj.max_gap_seconds < 0: raise ValueError('补帧阈值无效')
        obj.fill_enabled = bool(state['fill_enabled'])
        obj.fill_tension=float(state.get('fill_tension',.7))
        if not np.isfinite(obj.fill_tension) or not 0<=obj.fill_tension<=1:raise ValueError('弯曲参数无效')
        obj.fill_method=state.get('fill_method','pchip');obj.fill_jobs=copy.deepcopy(state.get('fill_jobs'))
        obj.fill_smoothing=float(state.get('fill_smoothing',0.));obj.fill_smooth_window=int(state.get('fill_smooth_window',7))
        if not np.isfinite(obj.fill_smoothing) or not 0<=obj.fill_smoothing<=1 or not 3<=obj.fill_smooth_window<=31:raise ValueError('平滑设置无效')
        if obj.fill_method not in ['linear','pchip','bezier']:raise ValueError('补帧方法无效')
        if obj.fill_jobs is not None:
            for job in obj.fill_jobs:
                if (not 0<=job['start']<=job['end']<obj.frames or job['method'] not in ['linear','pchip','bezier']
                    or not np.isfinite(job['max_gap_seconds']) or job['max_gap_seconds']<0
                    or any(n not in obj.slots for n in job['slots'])
                    or not np.isfinite(job.get('smooth_strength',0.)) or not 0<=job.get('smooth_strength',0.)<=1
                    or not np.isfinite(job.get('tension',.7)) or not 0<=job.get('tension',.7)<=1
                    or not isinstance(job.get('smooth_window',7),int) or not 3<=job.get('smooth_window',7)<=31):raise ValueError('补帧规则损坏')
        for item in state.get('repairs',[]):obj.apply_repair(item)
        obj.history.clear()
        rules=copy.deepcopy(state.get('public_pairings'))
        if rules is not None:
            matrix=np.full((len(obj.slots),obj.frames),-1,dtype=int)
            for rule in rules:
                if rule['slot'] not in obj.slots or not 0<=rule['marker']<len(obj.markers) or not 0<=rule['start']<=rule['end']<obj.frames:raise ValueError('项目配对表损坏')
                row=obj.slots.index(rule['slot']);sl=slice(rule['start'],rule['end']+1)
                if np.any(matrix[row,sl]>=0) or np.any(matrix[:,sl]==rule['marker']):raise ValueError('项目配对关系不是一一对应')
                matrix[row,sl]=rule['marker']
            obj.public_pairings=rules
        return obj

    def export(self, path):
        path = Path(path).resolve()
        if path == self.path: raise ValueError('不能覆盖原始 C3D 文件')
        xyz,status,origin = self.build()
        if not np.any(status == 1): raise ValueError('请至少完成一个点位配对')
        out = read_c3d(self.path)
        # Keep unassigned raw observations too, so labeling never discards observations.
        consumed = np.zeros(self.valid.shape,dtype=bool)
        for j in range(len(self.slots)):
            for src in np.unique(origin[j]):
                if src >= 0: consumed[src] |= origin[j] == src
        remain = self.valid & ~consumed
        raw_ids = np.flatnonzero(remain.any(axis=1))
        n = len(self.slots)+len(raw_ids)
        data = np.zeros((4,n,self.frames)); residual = np.full((1,n,self.frames),-1.0)
        cameras = np.zeros((7,n,self.frames),dtype=bool)
        original_meta = self.effective_meta
        data[:3,:len(self.slots)] = np.nan_to_num(xyz)
        for j in range(len(self.slots)):
            # Interpolated positions have no measured reconstruction residual.
            residual[0,j,status[j]>=2] = 0
            for src in np.unique(origin[j]):
                if src < 0: continue
                mask = origin[j]==src
                residual[0,j,mask] = original_meta['residuals'][0,src,mask]
                cameras[:,j,mask] = original_meta['camera_masks'][:,src,mask]
        labels = list(self.slots)
        for k,src in enumerate(raw_ids,start=len(self.slots)):
            mask = remain[src]; data[:3,k,mask] = self.points[:3,src,mask]
            residual[0,k,mask] = original_meta['residuals'][0,src,mask]
            cameras[:,k,mask] = original_meta['camera_masks'][:,src,mask]
            name = f'RAW_{src}_{self.labels[src]}'
            while name in labels: name = 'RAW_'+name
            labels.append(name)
        out['data']['points'] = data
        out['data']['meta_points']['residuals'] = residual
        out['data']['meta_points']['camera_masks'] = cameras
        out['parameters']['POINT']['LABELS']['value'] = labels
        out['parameters']['POINT']['DESCRIPTIONS']['value'] = ['Assigned slot' for _ in self.slots]+['Unassigned original fragment' for _ in raw_ids]
        # Source-specific POINT arrays may be invalid after changing point count.
        for key in ['LABELS2','DESCRIPTIONS2']:
            out['parameters']['POINT'].pop(key,None)
        write_c3d(out,path)
        original_origin=np.full_like(origin,-1)
        for j in range(len(self.slots)):
            frames=np.flatnonzero(origin[j]>=0)
            original_origin[j,frames]=self.original_source_index[origin[j,frames],frames]
        np.savez_compressed(str(path)+'.provenance.npz',status=status,source_index=origin,original_source_index=original_origin,labels=np.array(self.slots),first_frame=self.first,rate=self.rate)
        self.save_project(str(path)+'.project.json')
        return path
