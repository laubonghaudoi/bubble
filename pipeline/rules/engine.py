def liquidity_rule(spreads:list[dict],technical=False,confirmation=False,reserve_drain=False,srf=False):
    vals=[x['value'] for x in spreads if x['value'] is not None]; latest=vals[-1] if vals else None
    positive=sum(1 for x in reversed(vals) if x>0) if latest and all(x>0 for x in vals[-min(3,len(vals)):]) else (1 if latest and latest>0 else 0)
    level='normal'
    if latest is not None:
      if latest>3:level='warning' if len(vals)>1 and vals[-2]>3 and not technical else 'watch'
      elif positive>=3:level='watch'
      elif latest>0:level='info'
    score=(1 if level in ('watch','warning') else 0)+(1 if confirmation else 0)+(1 if reserve_drain else 0)+(1 if srf else 0)
    return {'level':level,'raw_score':score,'confirmed_score':score,'confidence':'medium' if technical else 'high','consecutive_positive':positive}
