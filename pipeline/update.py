from __future__ import annotations
import argparse,csv,io,json,urllib.parse,urllib.request
from datetime import datetime,timezone,timedelta,date
from pathlib import Path
from pipeline.catalog import CORE,OPTIONAL,SOURCES,manifest
from pipeline.io import atomic_json,read_json
from pipeline.transforms.core import asof_join,changes,spread_bp,technical_flags,weekly_changes
from pipeline.rules.engine import liquidity_rule
OUT=Path('public/data'); NOW=datetime.now(timezone.utc); RETRIEVED=NOW.isoformat().replace('+00:00','Z')
def get_json(url):
 req=urllib.request.Request(url,headers={'User-Agent':'USD-Liquidity-Dashboard research@example.com','Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
def nyfed(metric,days=60):
 end=NOW.date();start=end-timedelta(days=days);segment='secured' if metric in ('sofr','tgcr','bgcr') else 'unsecured'
 u=f'https://markets.newyorkfed.org/api/rates/{segment}/{metric}/search.json?startDate={start}&endDate={end}&type=rate'
 rows=get_json(u).get('refRates');
 if not isinstance(rows,list):raise ValueError('NY Fed response missing refRates')
 out=[{'date':r['effectiveDate'],'value':float(r['percentRate'])} for r in rows if r.get('effectiveDate') and r.get('percentRate') is not None]
 return sorted(out,key=lambda x:x['date'])
def fred(series,days=None,scale=1):
 raw=urllib.request.urlopen(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}',timeout=20).read().decode();rows=[]
 for r in csv.DictReader(io.StringIO(raw)):
  v=r.get(series)
  if v and v!='.':rows.append({'date':r['observation_date'],'value':round(float(v)/scale,4)})
 return rows[-days:] if days else rows
def tga():
 u='https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance?filter=account_type:eq:Treasury%20General%20Account%20(TGA)%20Closing%20Balance&sort=-record_date&page[size]=45'
 rows=get_json(u).get('data');out=[]
 if not isinstance(rows,list):raise ValueError('FiscalData response missing data')
 for r in rows:
  raw=r.get('close_today_bal');raw=r.get('open_today_bal') if raw in (None,'null','') else raw
  if raw not in (None,'null',''):out.append({'date':r['record_date'],'value':round(float(str(raw).replace(',',''))/1000,3)})
 return sorted(out,key=lambda x:x['date'])
def unavailable(label,unit,status):return {'label':label,'value':None,'unit':unit,'as_of':None,'quality':'paid_required' if status=='paid_data_unavailable' else 'proxy','status':status,'flags':[],'short_series':[]}
def run(mode='incremental'):
 old=read_json(OUT/'snapshot.json',{}) or {}; metrics={};health={}; series={};errors={}
 fetches={'sofr':lambda:nyfed('sofr'),'effr':lambda:nyfed('effr'),'obfr':lambda:nyfed('obfr'),'tgcr':lambda:nyfed('tgcr'),'bgcr':lambda:nyfed('bgcr'),'iorb':lambda:fred('IORB',90),'reserve_balances':lambda:fred('WRESBAL',20,1000),'fed_total_assets':lambda:fred('WALCL',20,1000),'tga_weekly_h41':lambda:fred('WTREGEN',20,1000),'tga_daily':tga}
 for mid,(label,unit,sid) in CORE.items():
  if mid in ('sofr_iorb_spread','on_rrp','srf_usage'):continue
  try:series[mid]=fetches[mid]();status='ok'
  except Exception as e:
   prior=read_json(OUT/f'series/{mid}.json',{}).get('observations',[]);series[mid]=prior;status='stale' if prior else 'error';errors[mid]=str(e)
  obs=series[mid];ch=changes(obs);metrics[mid]={'label':label,'value':obs[-1]['value'] if obs else None,'unit':unit,'as_of':obs[-1]['date'] if obs else None,**ch,'quality':'official','status':status,'flags':[],'short_series':obs[-22:],'source_ids':[sid]}
  health[sid]=status
 # derived spread uses backward policy regime join
 joined=asof_join(series.get('sofr',[]),series.get('iorb',[]));series['sofr_iorb_spread']=[{'date':x['date'],'value':spread_bp(x['left'],x['right'])} for x in joined];obs=series['sofr_iorb_spread'];ch=changes(obs);market=obs[-1]['date'] if obs else None
 flags=technical_flags(date.fromisoformat(market)) if market else [];rule=liquidity_rule(obs,bool(flags))
 metrics['sofr_iorb_spread']={'label':'SOFR−IORB 利差','value':obs[-1]['value'] if obs else None,'unit':'bp','as_of':market,**ch,'quality':'derived_official','status':'ok' if obs else 'error','flags':flags+(['positive_spread'] if obs and obs[-1]['value']>0 else []),'short_series':obs[-22:],'source_ids':['nyfed','fred'],'consecutive_positive':rule['consecutive_positive']}
 # explicitly unavailable until official operation parsers have valid observations
 for mid in ('on_rrp','srf_usage'):
  label,unit,sid=CORE[mid];prior=old.get('metrics',{}).get(mid);metrics[mid]=prior if prior and prior.get('value') is not None else unavailable(label,unit,'missing');health[sid]=health.get(sid,'ok')
 for mid,(label,unit,sid,status) in OPTIONAL.items():metrics[mid]=unavailable(label,unit,status)
 src={};
 for sid,(name,url,freq,quality) in SOURCES.items():
  relevant=[m for m in metrics.values() if sid in m.get('source_ids',[])]
  asof=max((m['as_of'] for m in relevant if m.get('as_of')),default=None);st=health.get(sid,'missing')
  src[sid]={'name':name,'url':url,'status':st,'as_of':asof,'retrieved_at':RETRIEVED if st=='ok' else None,'frequency':freq,'quality':quality,'error':errors.get(sid)}
 source_counts={k:sum(1 for x in src.values() if x['status']==k) for k in ('ok','stale','error','missing')}
 latest=metrics['sofr_iorb_spread'];v=latest['value'];headline='核心官方數據暫時未齊，結論信心偏低。' if v is None else ('隔夜融資利差高於操作觀察線，需要留意持續性。' if v>3 else '美元流動性整體保持中性，暫未見廣泛資金壓力。')
 explanations={'headline':headline,'bullets':[{'metric_id':'sofr_iorb_spread','observation':f"SOFR−IORB 最新為 {v:+.1f} bp。" if v is not None else 'SOFR−IORB 暫時缺失。','meaning':'相對 IORB 上升通常代表 secured overnight funding 變貴。','caveat':'單日變化亦可能來自月尾或 Treasury settlement，唔足以證明準備金短缺。','confidence':rule['confidence']}]}
 switch_status='tightening' if rule['confirmed_score']>=3 else 'watch' if rule['confirmed_score']>=2 else 'neutral'
 snapshot={'schema_version':'1.0.0','generated_at':RETRIEVED,'market_date':market,'overall_status':switch_status,'switches':{'liquidity_fuel':{'status':switch_status,'score':rule['confirmed_score'],'confidence':rule['confidence'],'summary':'價格、準備金及 backstop 分組判讀。'},'market_ignition':{'status':'unavailable','score':0,'confidence':'low','summary':'公開代理指標尚未完成更新。'},'fundamental_exit':{'status':'unavailable','score':0,'confidence':'low','summary':'季度 CapEx／訂單資料待發布。'}},'metrics':metrics,'technical_context':[{'date':market,'flags':flags,'note':'月尾／季尾資產負債表調整可能暫時推高 repo rate。'}] if flags else [],'alerts':[] if rule['level']=='normal' else [{'level':rule['level'],'title':'SOFR−IORB 觀察訊號','detail':'保留 raw signal；技術日只降低信心。'}],'explanations':explanations,'source_health':source_counts,'sources':src,'composite':rule}
 for item in manifest():
  mid=item['id'];o=series.get(mid,[]);atomic_json(OUT/f'series/{mid}.json',{'schema_version':'1.0.0','metric_id':mid,'label':item['label'],'unit':item['unit'],'frequency':item['frequency'],'quality':item['quality'],'status':metrics[mid]['status'],'as_of':metrics[mid]['as_of'],'retrieved_at':RETRIEVED,'source_ids':metrics[mid].get('source_ids',[]),'methodology':item['methodology'],'knowledge':{k:item[k] for k in ('role','layer','question_answered','why_track','false_positives','confirm_with','cannot_conclude')},'observations':o})
 atomic_json(OUT/'manifest.json',{'schema_version':'1.0.0','generated_at':RETRIEVED,'metrics':manifest()});atomic_json(OUT/'snapshot.json',snapshot);atomic_json(OUT/'alerts.json',snapshot['alerts']);atomic_json(OUT/'events.json',snapshot['technical_context'])
 return snapshot
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--mode',default='incremental');a=p.parse_args();run(a.mode)
