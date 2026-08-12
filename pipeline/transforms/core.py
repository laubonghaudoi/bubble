from __future__ import annotations
from datetime import date, timedelta

def asof_join(primary:list[dict], regime:list[dict])->list[dict]:
    rates=sorted((date.fromisoformat(x['date']),x['value']) for x in regime if x['value'] is not None)
    out=[]
    for p in primary:
        d=date.fromisoformat(p['date']); valid=[x for x in rates if x[0]<=d]
        if valid: out.append({'date':p['date'],'left':p['value'],'right':valid[-1][1]})
    return out

def spread_bp(left:float,right:float)->float:return round((left-right)*100,4)
def changes(obs:list[dict])->dict:
    vals=[x['value'] for x in obs if x['value'] is not None]
    if not vals:return {'previous':None,'delta_1d':None,'change_5d':None,'trend_5d':'unavailable'}
    d1=round(vals[-1]-vals[-2],4) if len(vals)>1 else None
    d5=round(vals[-1]-vals[-6],4) if len(vals)>5 else None
    return {'previous':vals[-2] if len(vals)>1 else None,'delta_1d':d1,'change_5d':d5,'trend_5d':'rising' if d5 is not None and d5>0 else 'falling' if d5 is not None and d5<0 else 'flat'}
def weekly_changes(obs:list[dict])->dict:
    vals=[x['value'] for x in obs if x['value'] is not None]
    return {'change_1w':round(vals[-1]-vals[-2],3) if len(vals)>1 else None,'change_4w':round(vals[-1]-vals[-5],3) if len(vals)>4 else None}
def capex_quarters(ytd:list[float],annual:float)->list[float]:return [ytd[0],ytd[1]-ytd[0],ytd[2]-ytd[1],annual-ytd[2]]
def capex_growth(values:list[float])->dict:
    qoq=[None]+[values[i]/values[i-1]-1 for i in range(1,len(values))]
    yoy=[None]*4+[values[i]/values[i-4]-1 for i in range(4,len(values))]
    return {'qoq_growth':qoq,'qoq_acceleration':[None if i<2 else qoq[i]-qoq[i-1] for i in range(len(values))],'yoy_growth':yoy,'yoy_acceleration':[None if i<5 else yoy[i]-yoy[i-1] for i in range(len(values))]}
def technical_flags(d:date)->list[str]:
    next_day=d+timedelta(days=1)
    flags=[]
    if next_day.month!=d.month:flags.append('month_end')
    if next_day.month!=d.month and d.month in (3,6,9,12):flags.append('quarter_end')
    if d.month==12 and next_day.year!=d.year:flags.append('year_end')
    return flags
