from __future__ import annotations
import math
import pandas as pd

def _benefit_total(config, time_multiplier=1.0, fixed_benefit_multiplier=1.0):
    b=config['annual_benefits']
    fixed=(b['paper_and_printing_savings']+b['error_reduction']+b['process_acceleration'])*fixed_benefit_multiplier
    if config.get('modeling_choices',{}).get('include_non_cash_benefit_in_cash_flow',False):
        fixed += b.get('citizen_satisfaction_non_cash',0.0)*fixed_benefit_multiplier
    return b['staff_time_savings']*time_multiplier+fixed

def calculate_project(config, discount_rate=None, time_multiplier=1.0, development_multiplier=1.0, annual_cost_multiplier=1.0, fixed_benefit_multiplier=1.0):
    years=config['horizon_years']; r=config['discount_rate'] if discount_rate is None else discount_rate
    inv=sum(config['investments'].values())-config['investments']['development_and_implementation']+config['investments']['development_and_implementation']*development_multiplier
    annual_cost=sum(config['annual_costs'].values())*annual_cost_multiplier; benefits=_benefit_total(config,time_multiplier,fixed_benefit_multiplier)
    equipment=config['investments']['equipment']; dep=equipment/config['equipment_depreciation_years']
    rows=[{'year':0,'investment':inv,'benefits':0,'operating_costs':0,'depreciation':0,'taxable_profit':0,'profit_tax':0,'net_profit':0,'cash_flow':-inv,'discount_factor':1.0,'pv':-inv,'cumulative_pv':-inv,'cumulative_cf':-inv}]
    for year in range(1,years+1):
        taxable=benefits-annual_cost-dep; tax=max(taxable,0)*config['profit_tax_rate']; net=taxable-tax; cf=net+dep; df=1/(1+r)**year
        rows.append({'year':year,'investment':0,'benefits':benefits,'operating_costs':annual_cost,'depreciation':dep,'taxable_profit':taxable,'profit_tax':tax,'net_profit':net,'cash_flow':cf,'discount_factor':df,'pv':cf*df,'cumulative_pv':rows[-1]['cumulative_pv']+cf*df,'cumulative_cf':rows[-1]['cumulative_cf']+cf})
    frame=pd.DataFrame(rows); frame['project']=config['system_name']
    return frame

def irr(cash_flows):
    def f(rate): return sum(cf/(1+rate)**t for t,cf in enumerate(cash_flows))
    lo,hi=-0.999,10.0; flo=f(lo); fhi=f(hi)
    if flo*fhi>0: return None
    for _ in range(300):
        mid=(lo+hi)/2; fm=f(mid)
        if abs(fm)<1e-10: return mid
        if flo*fm<=0: hi=mid; fhi=fm
        else: lo=mid; flo=fm
    return (lo+hi)/2

def payback(frame, discounted=False):
    col='cumulative_pv' if discounted else 'cumulative_cf'
    vals=frame[col].tolist()
    for i in range(1,len(vals)):
        if vals[i]>=0:
            previous=vals[i-1]; flow=frame.loc[i,'pv' if discounted else 'cash_flow']
            return (i-1)+(-previous/flow) if flow else float('inf')
    return None

def summarize(frame, config):
    investment=-frame.loc[frame['year']==0,'cash_flow'].iloc[0]; benefits=frame['benefits'].sum(); costs=investment+frame['operating_costs'].sum(); net=benefits-costs
    return {'investment':investment,'benefits':benefits,'costs':costs,'net_nominal':net,'npv':frame['pv'].sum(),'irr':irr(frame['cash_flow'].tolist()),'payback':payback(frame),'discounted_payback':payback(frame,True),'total_cash_flow':frame['cash_flow'].sum()}

def calculate_summary(config, **kwargs):
    frame=calculate_project(config,**kwargs); return frame,summarize(frame,config)

def break_even_time_savings(config):
    base=config['annual_benefits']; other=base['paper_and_printing_savings']+base['error_reduction']+base['process_acceleration']; inv=sum(config['investments'].values()); annual_cost=sum(config['annual_costs'].values()); dep=config['investments']['equipment']/config['equipment_depreciation_years']; r=config['discount_rate']; pvaf=sum(1/(1+r)**t for t in range(1,config['horizon_years']+1)); required_cf=inv/pvaf; required_benefit=(required_cf-dep)/(1-config['profit_tax_rate'])+annual_cost+dep; return {'required_annual_monetary_benefits':required_benefit,'required_time_savings':required_benefit-other,'current_time_savings':base['staff_time_savings'],'increase_percent':required_benefit-other and ((required_benefit-other)/base['staff_time_savings']-1)}

def target_time_savings(config, target_npv):
    years=config['horizon_years']; r=config['discount_rate']
    investment=sum(config['investments'].values())
    annual_cost=sum(config['annual_costs'].values())
    depreciation=config['investments']['equipment']/config['equipment_depreciation_years']
    pvaf=sum(1/(1+r)**t for t in range(1,years+1))
    required_cf=(target_npv+investment)/pvaf
    required_benefit=(required_cf-depreciation)/(1-config['profit_tax_rate'])+annual_cost+depreciation
    fixed_benefits=config['annual_benefits']['paper_and_printing_savings']+config['annual_benefits']['error_reduction']+config['annual_benefits']['process_acceleration']
    if config.get('modeling_choices',{}).get('include_non_cash_benefit_in_cash_flow',False):
        fixed_benefits += config['annual_benefits'].get('citizen_satisfaction_non_cash',0.0)
    required_time=required_benefit-fixed_benefits
    current=config['annual_benefits']['staff_time_savings']
    return {'target_npv':target_npv,'required_annual_benefit':required_benefit,'required_time_savings':required_time,'current_time_savings':current,'change_abs':required_time-current,'change_percent':required_time/current-1}

def required_time_multiplier_for_target(config, target_npv, development_multiplier=1.0, annual_cost_multiplier=1.0, fixed_benefit_multiplier=1.0, high=20.0):
    def npv_for(mult):
        _, result=calculate_summary(config, time_multiplier=mult, development_multiplier=development_multiplier, annual_cost_multiplier=annual_cost_multiplier, fixed_benefit_multiplier=fixed_benefit_multiplier)
        return result['npv']
    lo=0.0; hi=high
    if npv_for(lo)>=target_npv:
        return {'time_multiplier':lo,'npv':npv_for(lo)}
    while npv_for(hi)<target_npv and hi<1000:
        hi*=2
    if npv_for(hi)<target_npv:
        return {'time_multiplier':None,'npv':npv_for(hi)}
    for _ in range(100):
        mid=(lo+hi)/2
        if npv_for(mid)<target_npv: lo=mid
        else: hi=mid
    mult=(lo+hi)/2
    return {'time_multiplier':mult,'npv':npv_for(mult)}

def fmt(x,d=2): return ('не рассчитывается' if x is None else f'{x:,.{d}f}'.replace(',',' ').replace('.',','))
