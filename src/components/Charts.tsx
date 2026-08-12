import {useMemo} from 'react';
import ReactECharts from 'echarts-for-react';
import type {EChartsOption} from 'echarts';
import type {Point} from '../types';

export type ChartTheme='light'|'dark';

export interface ChartPalette{
  accent:string;
  rise:string;
  ink:string;
  muted:string;
  faint:string;
  gridX:string;
  gridY:string;
  zero:string;
  panel:string;
  hover:string;
  button:string;
  area:string;
  areaSelected:string;
  areaMuted:string;
  secondary:string;
  watch:string;
  unavailable:string;
  sparkOff:string;
}

const FALLBACK_PALETTES:Record<ChartTheme,ChartPalette>={
  light:{
    accent:'#0047c7',rise:'#c00000',ink:'#000000',muted:'#4a4f56',faint:'#4a4f56',
    gridX:'#f2f3f5',gridY:'#e6e8ec',zero:'#8b9198',panel:'#ffffff',hover:'#f2f4f7',
    button:'#9aa0a8',area:'rgba(0,71,199,.08)',areaSelected:'rgba(0,71,199,.13)',
    areaMuted:'rgba(0,71,199,.05)',secondary:'#6a6f76',watch:'#6a6f76',
    unavailable:'#6a6f76',sparkOff:'#a8adb4',
  },
  dark:{
    accent:'#4d9bff',rise:'#ff5a52',ink:'#ffffff',muted:'#9aa0a8',faint:'#9aa0a8',
    gridX:'#101216',gridY:'#1c1f24',zero:'#4a4f57',panel:'#0a0b0d',hover:'#14171b',
    button:'#4a4f57',area:'rgba(77,155,255,.15)',areaSelected:'rgba(77,155,255,.22)',
    areaMuted:'rgba(77,155,255,.07)',secondary:'#9aa0a8',watch:'#9aa0a8',
    unavailable:'#7a8088',sparkOff:'#4a5058',
  },
};

const CSS_VARIABLES:Record<keyof ChartPalette,string>={
  accent:'--accent',rise:'--rise',ink:'--ink',muted:'--muted',faint:'--faint',
  gridX:'--gridx',gridY:'--gridy',zero:'--zero',panel:'--panel',hover:'--hover',
  button:'--btn2',area:'--area',areaSelected:'--area2',areaMuted:'--area3',
  secondary:'--s3',watch:'--watch',unavailable:'--unavail',sparkOff:'--sparkoff',
};

/** Resolve CSS custom properties before handing colours to ECharts' canvas renderer. */
export function resolveChartPalette(theme:ChartTheme):ChartPalette{
  const fallback=FALLBACK_PALETTES[theme];
  if(typeof window==='undefined'||typeof document==='undefined')return {...fallback};
  const computed=window.getComputedStyle(document.documentElement);
  return (Object.keys(CSS_VARIABLES) as Array<keyof ChartPalette>).reduce((out,key)=>{
    out[key]=computed.getPropertyValue(CSS_VARIABLES[key]).trim()||fallback[key];
    return out;
  },{} as ChartPalette);
}

type SeriesFileLike={observations:readonly Point[];label?:string};
type PointsLike={points:readonly Point[];label?:string};
export type ChartPoints=readonly Point[]|SeriesFileLike|PointsLike;
export type SeriesMap=Readonly<Record<string,ChartPoints>>;

export interface OverlayUnion{
  dates:string[];
  series:Record<string,Array<number|null>>;
}

/** Compatibility shape used by the dashboard's shared union helper. */
export interface OverlayValuesUnion{
  dates:readonly string[];
  values:Readonly<Record<string,readonly (number|null)[]>>;
}

export type OverlayData=SeriesMap|OverlayUnion|OverlayValuesUnion;
export type SelectedSeries=readonly string[]|ReadonlySet<string>|Readonly<Record<string,boolean|0|1>>;

type OverlayColourKey='accent'|'rise'|'ink'|'secondary'|'watch'|'unavailable';
export const OVERLAY_CONFIG=[
  {id:'sofr',label:'SOFR',colour:'accent'},
  {id:'iorb',label:'IORB',colour:'rise'},
  {id:'effr',label:'EFFR',colour:'ink'},
  {id:'obfr',label:'OBFR',colour:'secondary'},
  {id:'tgcr',label:'TGCR',colour:'watch'},
  {id:'bgcr',label:'BGCR',colour:'unavailable'},
] as const satisfies ReadonlyArray<{id:string;label:string;colour:OverlayColourKey}>;

const isFiniteNumber=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value);

function orderedPoints(points:readonly Point[]):Point[]{
  return points
    .filter(point=>typeof point.date==='string'&&point.date.length>0)
    .map(point=>({date:point.date,value:isFiniteNumber(point.value)?point.value:null}))
    .sort((a,b)=>a.date.localeCompare(b.date));
}

function pointsFrom(value:ChartPoints):readonly Point[]{
  if('observations' in value)return value.observations;
  if('points' in value)return value.points;
  return value;
}

function isAlignedOverlay(value:OverlayData):value is OverlayUnion|OverlayValuesUnion{
  if(!Array.isArray((value as OverlayUnion).dates))return false;
  const aligned='series' in value?value.series:'values' in value?value.values:null;
  return aligned!=null&&typeof aligned==='object'&&!Array.isArray(aligned);
}

/** Build one sorted date domain and preserve nulls for dates absent from each rate series. */
export function buildOverlayUnion(input:SeriesMap):OverlayUnion{
  const dates=new Set<string>();
  const bySeries:Record<string,Map<string,number|null>>={};

  for(const [id,raw] of Object.entries(input)){
    const byDate=new Map<string,number|null>();
    for(const point of orderedPoints(pointsFrom(raw))){
      dates.add(point.date);
      byDate.set(point.date,point.value);
    }
    bySeries[id]=byDate;
  }

  const sortedDates=[...dates].sort((a,b)=>a.localeCompare(b));
  const series=Object.fromEntries(Object.entries(bySeries).map(([id,byDate])=>[
    id,
    sortedDates.map(date=>byDate.has(date)?(byDate.get(date)??null):null),
  ]));
  return {dates:sortedDates,series};
}

function normaliseOverlayData(input:OverlayData):OverlayUnion{
  if(!isAlignedOverlay(input))return buildOverlayUnion(input);
  const aligned='series' in input?input.series:input.values;
  const reconstructed:Record<string,Point[]>={};
  for(const [id,values] of Object.entries(aligned)){
    reconstructed[id]=input.dates.map((date,index)=>({
      date,
      value:isFiniteNumber(values[index])?values[index]:null,
    }));
  }
  return buildOverlayUnion(reconstructed);
}

function unitKind(unit:string):'percent'|'bp'|'usd-bn'|'plain'{
  const normalised=unit.trim().toLowerCase();
  if(normalised==='%'||normalised.includes('percent')||normalised==='pct')return 'percent';
  if(normalised==='bp'||normalised.includes('basis point'))return 'bp';
  if(normalised==='usd bn'||normalised.includes('billion'))return 'usd-bn';
  return 'plain';
}

function numericValue(value:number|string):number|null{
  if(typeof value==='number')return Number.isFinite(value)?value:null;
  const parsed=Number.parseFloat(value.replace(/[%B,]/g,''));
  return Number.isFinite(parsed)?parsed:null;
}

export function formatMetricValue(value:number|null|undefined,unit:string):string{
  if(!isFiniteNumber(value))return '—';
  const kind=unitKind(unit);
  const digits=kind==='percent'?2:kind==='bp'?1:kind==='usd-bn'?0:2;
  const formatted=new Intl.NumberFormat('en-US',{
    minimumFractionDigits:digits,
    maximumFractionDigits:digits,
  }).format(value);
  if(kind==='percent')return `${formatted}%`;
  if(kind==='bp')return `${formatted} bp`;
  if(kind==='usd-bn')return `${formatted}B`;
  return formatted;
}

export function formatAxisValue(value:number|string,unit:string):string{
  const numeric=numericValue(value);
  return numeric==null?'—':formatMetricValue(numeric,unit);
}

export function formatAxisDate(value:string):string{
  const match=/^\d{4}-(\d{2})-(\d{2})/.exec(value);
  return match?`${match[1]}/${match[2]}`:value;
}

function xAxisInterval(length:number):number{
  return Math.max(0,Math.ceil(Math.max(length,1)/6)-1);
}

function escapeHtml(value:string):string{
  return value.replace(/[&<>"']/g,char=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
  })[char] as string);
}

type TooltipDatum={axisValue?:unknown;name?:unknown;value?:unknown;data?:unknown;seriesName?:unknown;color?:unknown};

function tooltipValue(item:TooltipDatum):number|null{
  if(isFiniteNumber(item.value))return item.value;
  if(Array.isArray(item.value)&&isFiniteNumber(item.value[1]))return item.value[1];
  if(item.data&&typeof item.data==='object'&&'value' in item.data){
    const value=(item.data as {value:unknown}).value;
    if(isFiniteNumber(value))return value;
    if(Array.isArray(value)&&isFiniteNumber(value[1]))return value[1];
  }
  return null;
}

function tooltipItems(params:unknown):TooltipDatum[]{
  if(Array.isArray(params))return params as TooltipDatum[];
  return params&&typeof params==='object'?[params as TooltipDatum]:[];
}

function mainTooltipFormatter(params:unknown,unit:string):string{
  const item=tooltipItems(params)[0];
  if(!item)return '';
  const date=String(item.axisValue??item.name??'');
  return `${escapeHtml(date)}<br><b>${escapeHtml(formatMetricValue(tooltipValue(item),unit))}</b>`;
}

function overlayTooltipFormatter(params:unknown):string{
  const items=tooltipItems(params);
  if(items.length===0)return '';
  const date=String(items[0].axisValue??items[0].name??'');
  const rows=items.flatMap(item=>{
    const value=tooltipValue(item);
    if(value==null)return [];
    return [`${escapeHtml(String(item.seriesName??''))}&nbsp;&nbsp;<b>${escapeHtml(formatMetricValue(value,'percent'))}</b>`];
  });
  return [escapeHtml(date),...rows].join('<br>');
}

function signedThreshold(value:number):string{
  const formatted=Number.isInteger(value)?String(value):value.toFixed(1);
  return `${value>=0?'+':''}${formatted} bp`;
}

function niceBounds(values:readonly number[],targetSteps:number):{min:number;max:number;interval:number}|null{
  if(values.length===0)return null;
  const rawMin=Math.min(...values),rawMax=Math.max(...values);
  const extent=rawMax-rawMin;
  const pad=extent===0?Math.max(Math.abs(rawMin)*0.02,0.01):0;
  const rough=(extent||pad*2)/Math.max(1,targetSteps-1);
  const magnitude=Math.pow(10,Math.floor(Math.log10(rough)));
  const normalised=rough/magnitude;
  const factor=normalised<=1?1:normalised<=2?2:normalised<=5?5:10;
  const interval=factor*magnitude;
  return {
    min:Math.floor((rawMin-pad)/interval)*interval,
    max:Math.ceil((rawMax+pad)/interval)*interval,
    interval,
  };
}

export interface MainChartOptionInput{
  metricId:string;
  label:string;
  unit:string;
  points:ChartPoints;
  theme?:ChartTheme;
  thresholdBp?:number;
  palette?:ChartPalette;
}

export function buildMainChartOption({
  metricId,label,unit,points,theme='light',thresholdBp=3,palette=FALLBACK_PALETTES[theme],
}:MainChartOptionInput):EChartsOption{
  const ordered=orderedPoints(pointsFrom(points));
  const dates=ordered.map(point=>point.date);
  const values=ordered.map(point=>point.value);
  const finiteValues=values.filter(isFiniteNumber);
  const min=finiteValues.length?Math.min(...finiteValues):null;
  const max=finiteValues.length?Math.max(...finiteValues):null;
  const bounds=niceBounds(finiteValues,5);
  let lastIndex=-1;
  for(let index=values.length-1;index>=0;index--){
    if(isFiniteNumber(values[index])){lastIndex=index;break;}
  }
  const markLines:Array<Record<string,unknown>>=[];

  if(min!=null&&max!=null&&min<0&&max>0){
    markLines.push({
      yAxis:0,
      label:{show:false},
      lineStyle:{color:palette.zero,width:1,type:'solid'},
    });
  }
  if(metricId==='sofr_iorb_spread'&&isFiniteNumber(thresholdBp)&&bounds&&
    thresholdBp>=bounds.min&&thresholdBp<=bounds.max){
    markLines.push({
      yAxis:thresholdBp,
      label:{show:true,formatter:`操作觀察線 ${signedThreshold(thresholdBp)}`,position:'insideEndTop',color:palette.rise,fontSize:11},
      lineStyle:{color:palette.rise,width:1,type:'dashed'},
    });
  }

  const description=finiteValues.length
    ?`${label}，${dates[0]} 至 ${dates[dates.length-1]}，${finiteValues.length} 個觀察值，最新為 ${formatMetricValue(values[lastIndex],unit)}。`
    :`${label}暫無可用觀察值。`;

  return {
    animation:false,
    aria:{enabled:true,label:{description}},
    grid:{left:58,right:14,top:16,bottom:30,containLabel:false},
    tooltip:{
      trigger:'axis',
      confine:true,
      appendToBody:false,
      backgroundColor:palette.hover,
      borderColor:palette.button,
      borderWidth:1,
      textStyle:{color:palette.ink,fontFamily:'DM Mono',fontSize:12},
      axisPointer:{
        type:'line',snap:true,
        lineStyle:{color:palette.muted,width:1,type:'dashed'},
        label:{show:false},
      },
      formatter:(params:unknown)=>mainTooltipFormatter(params,unit),
    },
    xAxis:{
      type:'category',data:dates,boundaryGap:false,
      axisLine:{show:false},axisTick:{show:false},
      axisLabel:{
        color:palette.faint,fontFamily:'DM Mono',fontSize:11,
        formatter:(value:string)=>formatAxisDate(value),
        interval:xAxisInterval(dates.length),showMinLabel:true,showMaxLabel:false,hideOverlap:true,
      },
      splitLine:{show:true,lineStyle:{color:palette.gridX,width:1}},
      axisPointer:{show:true,snap:true},
    },
    yAxis:{
      type:'value',scale:true,splitNumber:5,
      min:bounds?.min,max:bounds?.max,interval:bounds?.interval,
      axisLine:{show:false},axisTick:{show:false},
      axisLabel:{
        color:palette.faint,fontFamily:'DM Mono',fontSize:11,
        formatter:(value:number|string)=>formatAxisValue(value,unit),
      },
      splitLine:{show:true,lineStyle:{color:palette.gridY,width:1}},
    },
    series:[{
      name:label,type:'line',data:values,connectNulls:false,showSymbol:false,
      lineStyle:{color:palette.accent,width:1.6},
      itemStyle:{color:palette.accent},
      areaStyle:{color:palette.area},
      emphasis:{focus:'series'},
      markPoint:lastIndex>=0?{
        silent:true,symbol:'circle',symbolSize:6,label:{show:false},
        itemStyle:{color:palette.accent},
        data:[{coord:[dates[lastIndex],values[lastIndex]]}],
      }:undefined,
      markLine:markLines.length?{silent:true,symbol:['none','none'],data:markLines}:undefined,
    }],
  } as EChartsOption;
}

function selectedSet(selected:SelectedSeries):Set<string>{
  if(Array.isArray(selected))return new Set(selected);
  if(selected instanceof Set)return new Set(selected);
  return new Set(Object.entries(selected).flatMap(([id,on])=>on?[id]:[]));
}

export interface OverlayChartOptionInput{
  series:OverlayData;
  selected:SelectedSeries;
  theme?:ChartTheme;
  palette?:ChartPalette;
}

export function buildOverlayChartOption({
  series,selected,theme='light',palette=FALLBACK_PALETTES[theme],
}:OverlayChartOptionInput):EChartsOption{
  const union=normaliseOverlayData(series);
  const enabled=selectedSet(selected);
  const configById=new Map<string,{id:string;label:string;colour:OverlayColourKey}>(
    OVERLAY_CONFIG.map(item=>[item.id,item]),
  );
  const knownIds=OVERLAY_CONFIG.map(item=>item.id).filter(id=>id in union.series);
  const unknownIds=Object.keys(union.series).filter(id=>!configById.has(id)).sort();
  const ids=[...knownIds,...unknownIds].filter(id=>enabled.has(id));
  const greyKeys:OverlayColourKey[]=['secondary','watch','unavailable'];

  const lineSeries=ids.map((id,index)=>{
    const config=configById.get(id)??{
      id,label:id.toUpperCase(),colour:greyKeys[index%greyKeys.length],
    };
    const colour=palette[config.colour];
    return {
      name:config.label,type:'line',data:union.series[id],connectNulls:true,showSymbol:false,
      lineStyle:{color:colour,width:1.4},itemStyle:{color:colour},
      endLabel:{show:true,formatter:config.label,color:colour,fontFamily:'DM Mono',fontSize:11,distance:4},
      labelLayout:{moveOverlap:'shiftY'},
      emphasis:{focus:'series'},
    };
  });
  const description=ids.length
    ?`隔夜利率疊加圖，${union.dates[0]??'—'} 至 ${union.dates.at(-1)??'—'}，顯示 ${ids.map(id=>configById.get(id)?.label??id.toUpperCase()).join('、')}。`
    :'隔夜利率疊加圖，目前未選擇任何序列。';

  return {
    animation:false,
    aria:{enabled:true,label:{description}},
    grid:{left:54,right:50,top:14,bottom:28,containLabel:false},
    tooltip:{
      trigger:'axis',confine:true,appendToBody:false,
      backgroundColor:palette.hover,borderColor:palette.button,borderWidth:1,
      textStyle:{color:palette.ink,fontFamily:'DM Mono',fontSize:12},
      axisPointer:{type:'line',lineStyle:{color:palette.muted,width:1,type:'dashed'}},
      formatter:overlayTooltipFormatter,
    },
    xAxis:{
      type:'category',data:union.dates,boundaryGap:false,
      axisLine:{show:false},axisTick:{show:false},
      axisLabel:{
        color:palette.faint,fontFamily:'DM Mono',fontSize:11,
        formatter:(value:string)=>formatAxisDate(value),
        interval:xAxisInterval(union.dates.length),showMinLabel:true,showMaxLabel:false,hideOverlap:true,
      },
      splitLine:{show:false},
    },
    yAxis:{
      type:'value',scale:true,splitNumber:4,
      axisLine:{show:false},axisTick:{show:false},
      axisLabel:{
        color:palette.faint,fontFamily:'DM Mono',fontSize:11,
        formatter:(value:number|string)=>formatAxisValue(value,'percent'),
      },
      splitLine:{show:true,lineStyle:{color:palette.gridY,width:1}},
    },
    series:lineSeries,
  } as EChartsOption;
}

export interface MainMetricChartProps{
  metricId:string;
  label:string;
  unit:string;
  points:ChartPoints;
  theme:ChartTheme;
  thresholdBp?:number;
}

export function MainMetricChart({
  metricId,label,unit,points,theme,thresholdBp=3,
}:MainMetricChartProps){
  const palette=useMemo(()=>resolveChartPalette(theme),[theme]);
  const option=useMemo(()=>buildMainChartOption({
    metricId,label,unit,points,theme,thresholdBp,palette,
  }),[metricId,label,unit,points,theme,thresholdBp,palette]);
  return <div className="metric-chart metric-chart--main" style={{width:'100%',height:'100%',minHeight:0}}>
    <ReactECharts option={option} notMerge lazyUpdate style={{width:'100%',height:'100%'}}/>
  </div>;
}

export interface RateOverlayChartProps{
  series:OverlayData;
  selected:SelectedSeries;
  theme:ChartTheme;
}

export function RateOverlayChart({series,selected,theme}:RateOverlayChartProps){
  const palette=useMemo(()=>resolveChartPalette(theme),[theme]);
  const option=useMemo(()=>buildOverlayChartOption({series,selected,theme,palette}),[
    series,selected,theme,palette,
  ]);
  return <div className="metric-chart metric-chart--overlay" style={{width:'100%',height:'100%',minHeight:0}}>
    <ReactECharts option={option} notMerge lazyUpdate style={{width:'100%',height:'100%'}}/>
  </div>;
}

interface SparkSegment{line:string;area:string}

function sparkSegments(points:readonly Point[]):SparkSegment[]{
  const width=48,height=19,pad=1.5,bottom=height-pad;
  const finite=points.flatMap((point,index)=>isFiniteNumber(point.value)?[{index,value:point.value}]:[]);
  if(finite.length===0)return [];
  const min=Math.min(...finite.map(point=>point.value));
  const max=Math.max(...finite.map(point=>point.value));
  const span=max-min||1;
  const x=(index:number)=>points.length<=1?width/2:pad+(index/(points.length-1))*(width-pad*2);
  const y=(value:number)=>pad+((max-value)/span)*(height-pad*2);
  const groups:Array<Array<{x:number;y:number}>>=[];
  let current:Array<{x:number;y:number}>=[];

  points.forEach((point,index)=>{
    if(isFiniteNumber(point.value)){
      current.push({x:x(index),y:y(point.value)});
    }else if(current.length){
      groups.push(current);current=[];
    }
  });
  if(current.length)groups.push(current);

  return groups.map(group=>{
    const line=group.map((point,index)=>`${index?'L':'M'}${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ');
    const first=group[0],last=group[group.length-1];
    const areaLine=group.map(point=>`L${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ');
    const area=`M${first.x.toFixed(2)} ${bottom.toFixed(2)} ${areaLine} L${last.x.toFixed(2)} ${bottom.toFixed(2)} Z`;
    return {line,area};
  });
}

export interface SparklineProps{
  points:ChartPoints;
  selected:boolean;
  label:string;
}

export function Sparkline({points,selected,label}:SparklineProps){
  const observations=useMemo(()=>pointsFrom(points),[points]);
  const segments=useMemo(()=>sparkSegments(observations),[observations]);
  const count=observations.filter(point=>isFiniteNumber(point.value)).length;
  const summary=`${label} 走勢，${count} 個觀察值。`;
  return <svg
    className={`sparkline tape-spark${selected?' is-selected':''}`}
    width="48" height="19" viewBox="0 0 48 19" preserveAspectRatio="none"
    role="img" aria-label={summary}
  >
    <title>{summary}</title>
    {segments.map((segment,index)=><path
      key={`area-${index}`} d={segment.area}
      fill={selected?'var(--area2)':'var(--area3)'} stroke="none"
    />)}
    {segments.map((segment,index)=><path
      key={`line-${index}`} d={segment.line} fill="none"
      stroke={selected?'var(--accent)':'var(--sparkoff)'} strokeWidth="1.25"
      vectorEffect="non-scaling-stroke"
    />)}
  </svg>;
}
