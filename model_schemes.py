"""Reusable marker-set definitions; these do not implement biomechanical solving."""
import copy
BODY39 = 'LFHD RFHD LBHD RBHD C7 T10 CLAV STRN RBAK LSHO LUPA LELB LFRM LWRA LWRB LFIN RSHO RUPA RELB RFRM RWRA RWRB RFIN LASI RASI LPSI RPSI LTHI LKNE LTIB LANK LMMA LTOE RTHI RKNE RTIB RANK RMMA RTOE'.split()
STANDARD_PIG39 = ['LHEE' if name=='LMMA' else 'RHEE' if name=='RMMA' else name for name in BODY39]
CURRENT_SCHEME_NAME = '全身 39 点自定义方案（内外踝、无足跟）'
CURRENT_SCHEME_BASIS = '基于 Vicon Plug-in Gait Full Body 标记配置；LMMA/RMMA 为本方案内踝命名，不替代官方 LHEE/RHEE 足跟的解剖含义。'
REFERENCES = [
    'https://vicon-help.atlassian.net/wiki/spaces/Nexus217/pages/350752355/Full+body+modeling+with+Plug-in+Gait',
    'https://help.vicon.com/download/attachments/11378719/Plug-in%20Gait%20Reference%20Guide.pdf',
]

PRESETS = [
    dict(id='custom_full_body_39_medial',name=CURRENT_SCHEME_NAME,body_slots=BODY39,extra_slots=[],description=CURRENT_SCHEME_BASIS,source_urls=REFERENCES),
    dict(id='vicon_pig_full_body_39',name='Vicon Plug-in Gait Full Body（标准 39 点）',body_slots=STANDARD_PIG39,extra_slots=[],description='标准全身标记配置，使用 LHEE/RHEE 足跟点；不是内踝点。本软件管理点位与显示连接，不执行 Plug-in Gait 生物力学求解。',source_urls=REFERENCES),
]

def validate_scheme(value):
    if not isinstance(value,dict):raise ValueError('方案格式无效')
    name=value.get('name','');body=value.get('body_slots');extra=value.get('extra_slots',[])
    if not isinstance(name,str) or not name.strip() or not isinstance(body,list) or not body or not isinstance(extra,list):raise ValueError('请填写方案名称和人体点位')
    codes=body+extra
    if any(not isinstance(n,str) or not n.strip() for n in codes) or len(codes)!=len(set(codes)):raise ValueError('点位名称不能为空或重复')
    result=dict(id=str(value.get('id','custom')),name=name.strip(),body_slots=body.copy(),extra_slots=extra.copy(),description=str(value.get('description','')),source_urls=list(value.get('source_urls',[])))
    if value.get('connections'):
        edges=value['connections']
        if not isinstance(edges,list) or any(not isinstance(edge,(list,tuple)) or len(edge)!=2 or edge[0]==edge[1] or any(node not in codes for node in edge) for edge in edges):raise ValueError('连接关系必须引用方案内的两个不同点位')
        result['connections']=[list(edge) for edge in edges]
    if any(not isinstance(url,str) for url in result['source_urls']):raise ValueError('方案来源格式无效')
    return result

def infer_scheme(slots):
    for preset in PRESETS:
        if set(preset['body_slots']).issubset(slots):
            result=copy.deepcopy(preset);result['extra_slots']=[n for n in slots if n not in preset['body_slots']];return result
    body=[n for n in slots if not any(word in n.upper() for word in ['WAND','AUX','灯棒'])]
    if not body:body=list(slots)
    return dict(id='custom',name='自定义标记方案',body_slots=body,extra_slots=[n for n in slots if n not in body],description='从已有项目点位推断的方案，可自行编辑。',source_urls=[])
