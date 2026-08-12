from datetime import date
from pipeline.transforms.core import asof_join,capex_growth,capex_quarters,changes,spread_bp,technical_flags,weekly_changes
from pipeline.rules.engine import liquidity_rule

def test_spread_percent_to_bp():assert spread_bp(5.33,5.30)==3.0
def test_iorb_asof_join_weekend():
 out=asof_join([{'date':'2026-08-10','value':5.33}],[{'date':'2026-08-07','value':5.30}]);assert out[0]['right']==5.30
def test_changes_use_observations():
 c=changes([{'value':x} for x in range(7)]);assert c['delta_1d']==1 and c['change_5d']==5 and c['trend_5d']=='rising'
def test_weekly_changes():assert weekly_changes([{'value':x} for x in range(6)])=={'change_1w':1,'change_4w':4}
def test_capex_ytd_q4_and_acceleration():
 assert capex_quarters([10,22,36],52)==[10,12,14,16]
 g=capex_growth([10,11,12,13,15,18]);assert round(g['yoy_growth'][4],2)==.5 and g['qoq_acceleration'][2] is not None
def test_end_flags():
 assert technical_flags(date(2026,6,30))==['month_end','quarter_end']
 assert technical_flags(date(2026,12,31))==['month_end','quarter_end','year_end']
def test_technical_only_changes_confidence():
 raw=liquidity_rule([{'value':4},{'value':4}],False);tech=liquidity_rule([{'value':4},{'value':4}],True)
 assert raw['raw_score']==tech['raw_score'] and raw['confidence']!=tech['confidence']
def test_correlated_confirmation_is_one_block():
 result=liquidity_rule([{'value':4},{'value':4}],confirmation=True)
 assert result['raw_score']==2
