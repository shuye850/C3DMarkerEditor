"""UI translations. Storage and C3D labels retain laboratory abbreviations."""
import re

NAMES = {
    'LFHD':'左前头部', 'RFHD':'右前头部', 'LBHD':'左后头部', 'RBHD':'右后头部',
    'C7':'第七颈椎', 'T10':'第十胸椎', 'CLAV':'锁骨', 'STRN':'胸骨', 'RBAK':'右背部',
    'LSHO':'左肩', 'LUPA':'左上臂', 'LELB':'左肘', 'LFRM':'左前臂',
    'LWRA':'左腕部A', 'LWRB':'左腕部B', 'LFIN':'左手部',
    'RSHO':'右肩', 'RUPA':'右上臂', 'RELB':'右肘', 'RFRM':'右前臂',
    'RWRA':'右腕部A', 'RWRB':'右腕部B', 'RFIN':'右手部',
    'LASI':'左髂前上棘', 'RASI':'右髂前上棘', 'LPSI':'左髂后上棘', 'RPSI':'右髂后上棘',
    'LTHI':'左大腿', 'LKNE':'左膝', 'LTIB':'左小腿', 'LANK':'左外踝', 'LMMA':'左内踝', 'LHEE':'左足跟', 'LTOE':'左前足',
    'RTHI':'右大腿', 'RKNE':'右膝', 'RTIB':'右小腿', 'RANK':'右外踝', 'RMMA':'右内踝', 'RHEE':'右足跟', 'RTOE':'右前足',
}

def display_name(code):
    match=re.search(r'WAND\s*(\d+)',code,re.IGNORECASE) or re.fullmatch(r'AUX(\d+)',code)
    if match:
        number=match.group(1);return f'附加标记点{number}（AUX{number}）'
    if '灯棒' in code:return code.replace('灯棒','附加')
    return f'{NAMES[code]}（{code}）' if code in NAMES else code

def storage_name(text):
    """Recognize only our exact UI names, preserving arbitrary custom labels."""
    match=re.fullmatch(r'附加标记点(\d+)（AUX\1）',text)
    if match:return 'AUX'+match.group(1)
    return next((code for code in NAMES if display_name(code)==text), text)
