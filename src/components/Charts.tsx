import {useMemo} from 'react';
import ReactECharts from 'echarts-for-react';
import type {EChartsOption} from 'echarts';
import type {Point} from '../types';

export const OVERLAY_CONFIG=[
  {id:'sofr',label:'SOFR',colour:'#0064FA',cssVariable:'--series-sofr'},
  {id:'iorb',label:'IORB',colour:'#E51503',cssVariable:'--series-iorb'},
  {id:'effr',label:'EFFR',colour:'#000000',cssVariable:'--series-effr'},
  {id:'obfr',label:'OBFR',colour:'#338736',cssVariable:'--series-obfr'},
  {id:'tgcr',label:'TGCR',colour:'#8A4A00',cssVariable:'--series-tgcr'},
  {id:'bgcr',label:'BGCR',colour:'#767676',cssVariable:'--series-bgcr'},
] as const satisfies ReadonlyArray<{id:string;label:string;colour:string;cssVariable:string}>;

type OverlayId=(typeof OVERLAY_CONFIG)[number]['id'];
const EMPTY_LAST_GOOD_IDS:readonly string[]=[];
const LAST_GOOD_A11Y='最後成功值，並非今日新值';

export interface ChartPalette{
  main:string;
  action:string;
  threshold:string;
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
  orange:string;
  green:string;
  red:string;
  sparkOff:string;
  series:Record<OverlayId,string>;
}

const FALLBACK_PALETTE:ChartPalette={
  main:'#0064FA',action:'#0064FA',threshold:'#E51503',ink:'#000000',muted:'#545454',
  faint:'#767676',gridX:'#F8F8F8',gridY:'#EFEFEF',zero:'#767676',panel:'#FFFFFF',
  hover:'#F8F8F8',button:'#B3B3B3',area:'rgba(0,100,250,.08)',
  areaSelected:'rgba(0,100,250,.16)',areaMuted:'rgba(0,100,250,.04)',
  orange:'#8A4A00',green:'#338736',red:'#E51503',sparkOff:'#B3B3B3',
  series:Object.fromEntries(OVERLAY_CONFIG.map(({id,colour})=>[id,colour])) as Record<OverlayId,string>,
};

type CorePaletteKey=Exclude<keyof ChartPalette,'series'>;
const CSS_VARIABLES:Record<CorePaletteKey,string>={
  main:'--action',action:'--action',threshold:'--negative-fg',ink:'--ink',muted:'--chart-muted',faint:'--faint',
  gridX:'--gridx',gridY:'--gridy',zero:'--zero',panel:'--panel',hover:'--hover',
  button:'--btn',area:'--area-main',areaSelected:'--area-selected',areaMuted:'--area-muted',
  orange:'--warning-fg',green:'--positive-fg',red:'--negative-fg',sparkOff:'--sparkoff',
};

/** Resolve CSS custom properties before handing colours to ECharts' canvas renderer. */
export function resolveChartPalette():ChartPalette{
  if(typeof window==='undefined'||typeof document==='undefined')return {
    ...FALLBACK_PALETTE,series:{...FALLBACK_PALETTE.series},
  };
  const computed=window.getComputedStyle(document.documentElement);
  const core=(Object.keys(CSS_VARIABLES) as CorePaletteKey[]).reduce((out,key)=>{
    out[key]=computed.getPropertyValue(CSS_VARIABLES[key]).trim()||FALLBACK_PALETTE[key];
    return out;
  },{} as Omit<ChartPalette,'series'>);
  const series=Object.fromEntries(OVERLAY_CONFIG.map(({id,colour,cssVariable})=>[
    id,computed.getPropertyValue(cssVariable).trim()||colour,
  ])) as Record<OverlayId,string>;
  return {...core,series};
}

/**
 * Main-chart observations may carry SRF classification metadata in addition
 * to the public numeric point envelope.  Classification fields are optional
 * so old/partial artifacts degrade explicitly instead of being interpreted as
 * non-technical zero use.
 */
export interface ChartPoint extends Point{
  accepted_amount_usd_bn?:number;
  alert_eligible_accepted_amount_usd_bn?:number;
  exercise_accepted_amount_usd_bn?:number;
  has_technical_exercise?:boolean;
  technical_exercise?:boolean;
  operation_count?:number;
  exercise_operation_count?:number;
  classification_complete?:boolean;
}

type SeriesFileLike={observations:readonly ChartPoint[];label?:string};
type PointsLike={points:readonly ChartPoint[];label?:string};
export type ChartPoints=readonly ChartPoint[]|SeriesFileLike|PointsLike;
export type SeriesMap=Readonly<Record<string,ChartPoints>>;

export type ReferenceLineTone='neutral'|'warning'|'danger'|'extreme'|'technical';
export type ReferenceLineType='solid'|'dashed'|'dash-dot';

export interface ReferenceLine{
  id:string;
  value:number;
  label:string;
  tone:ReferenceLineTone;
  lineType:ReferenceLineType;
}

export type ChartDataStatus='CURRENT'|'LAST_GOOD'|'PARTIAL'|'UNAVAILABLE';

export interface SrfAlertWindow{
  positiveDays:number|null;
  requiredPositiveDays:number;
  windowDays:number;
}

type NormalizedChartPoint=ChartPoint&{value:number|null};

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

const isFiniteNumber=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value);

function optionalFiniteNumber(value:unknown):number|undefined{
  return isFiniteNumber(value)?value:undefined;
}

function optionalBoolean(value:unknown):boolean|undefined{
  return typeof value==='boolean'?value:undefined;
}

function orderedPoints(points:readonly ChartPoint[]):NormalizedChartPoint[]{
  return points
    .filter(point=>typeof point.date==='string'&&point.date.length>0)
    .map(point=>({
      date:point.date,
      value:isFiniteNumber(point.value)?point.value:null,
      accepted_amount_usd_bn:optionalFiniteNumber(point.accepted_amount_usd_bn),
      alert_eligible_accepted_amount_usd_bn:optionalFiniteNumber(point.alert_eligible_accepted_amount_usd_bn),
      exercise_accepted_amount_usd_bn:optionalFiniteNumber(point.exercise_accepted_amount_usd_bn),
      has_technical_exercise:optionalBoolean(point.has_technical_exercise),
      technical_exercise:optionalBoolean(point.technical_exercise),
      operation_count:optionalFiniteNumber(point.operation_count),
      exercise_operation_count:optionalFiniteNumber(point.exercise_operation_count),
      classification_complete:optionalBoolean(point.classification_complete),
    }))
    .sort((a,b)=>a.date.localeCompare(b.date));
}

function pointsFrom(value:ChartPoints):readonly ChartPoint[]{
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
  const reconstructed:Record<string,ChartPoint[]>={};
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
  const digits=kind==='percent'?2:kind==='bp'?1:kind==='usd-bn'
    ?value===0?0:Math.abs(value)<1?3:Math.abs(value)<100?1:0
    :2;
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

type TooltipDatum={axisValue?:unknown;name?:unknown;value?:unknown;data?:unknown;seriesName?:unknown;color?:unknown;dataIndex?:unknown};

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

function srfMetadataComplete(point:NormalizedChartPoint):boolean{
  if(point.classification_complete===false)return false;
  return point.classification_complete===true||(
    isFiniteNumber(point.accepted_amount_usd_bn)&&
    isFiniteNumber(point.alert_eligible_accepted_amount_usd_bn)&&
    isFiniteNumber(point.exercise_accepted_amount_usd_bn)&&
    typeof point.has_technical_exercise==='boolean'&&
    typeof point.technical_exercise==='boolean'
  );
}

function srfCountingText(
  point:NormalizedChartPoint,
  alertWindow:SrfAlertWindow|undefined,
):string{
  if(!srfMetadataComplete(point))return 'UNKNOWN · CLASSIFICATION METADATA UNAVAILABLE';
  const eligible=point.alert_eligible_accepted_amount_usd_bn!;
  const technical=point.has_technical_exercise===true;
  const dayState=eligible>0?'YES · COUNTS TOWARD SRF_RISING':technical
    ?'NO · TECHNICAL EXERCISE EXCLUDED':'NO · NONTECHNICAL ACCEPTED AMOUNT IS ZERO';
  if(!alertWindow)return `${dayState} · WINDOW COUNT UNAVAILABLE`;
  const count=alertWindow.positiveDays==null?'UNKNOWN':String(alertWindow.positiveDays);
  return `${dayState} · LATEST ${alertWindow.windowDays}-DAY COUNT ${count} · `+
    `RULE ${alertWindow.requiredPositiveDays}-OF-${alertWindow.windowDays}`;
}

function srfTooltipRows(point:NormalizedChartPoint,alertWindow:SrfAlertWindow|undefined):string[]{
  if(!srfMetadataComplete(point))return [
    '<b>DEGRADED · SRF CLASSIFICATION METADATA UNAVAILABLE</b>',
    'Technical versus nontechnical status is unknown; no alert marker is inferred.',
  ];
  const operationCount=isFiniteNumber(point.operation_count)?String(point.operation_count):'—';
  const exerciseCount=isFiniteNumber(point.exercise_operation_count)?String(point.exercise_operation_count):'—';
  const mode=point.technical_exercise?'TECHNICAL ONLY':point.has_technical_exercise?'MIXED':'NONTECHNICAL';
  return [
    `TOTAL ACCEPTED&nbsp;&nbsp;<b>${escapeHtml(formatMetricValue(point.accepted_amount_usd_bn,'USD bn'))}</b>`,
    `ALERT ELIGIBLE&nbsp;&nbsp;<b>${escapeHtml(formatMetricValue(point.alert_eligible_accepted_amount_usd_bn,'USD bn'))}</b>`,
    `TECHNICAL ACCEPTED&nbsp;&nbsp;<b>${escapeHtml(formatMetricValue(point.exercise_accepted_amount_usd_bn,'USD bn'))}</b>`,
    `CLASSIFICATION&nbsp;&nbsp;<b>${mode}</b>`,
    `OPERATIONS / EXERCISES&nbsp;&nbsp;<b>${operationCount} / ${exerciseCount}</b>`,
    `COUNTS TOWARD RULE&nbsp;&nbsp;<b>${escapeHtml(srfCountingText(point,alertWindow))}</b>`,
  ];
}

function mainTooltipFormatter(
  params:unknown,
  unit:string,
  metricId:string,
  points:readonly NormalizedChartPoint[],
  alertWindow:SrfAlertWindow|undefined,
  srfAnnotationsEnabled:boolean,
):string{
  const item=tooltipItems(params)[0];
  if(!item)return '';
  const date=String(item.axisValue??item.name??'');
  const value=`<b>${escapeHtml(formatMetricValue(tooltipValue(item),unit))}</b>`;
  if(metricId!=='srf_accepted'||!srfAnnotationsEnabled)return `${escapeHtml(date)}<br>${value}`;
  const index=typeof item.dataIndex==='number'?item.dataIndex:points.findIndex(point=>point.date===date);
  const point=index>=0?points[index]:undefined;
  return [escapeHtml(date),value,...(point?srfTooltipRows(point,alertWindow):[
    '<b>DEGRADED · SRF CLASSIFICATION METADATA UNAVAILABLE</b>',
  ])].join('<br>');
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

export interface ReferenceLineVisibility{
  visible:ReferenceLine[];
  outOfRange:ReferenceLine[];
}

/** Keep annotations inside the data-derived domain; never expand the y-axis. */
export function referenceLineVisibility(
  referenceLines:readonly ReferenceLine[],
  bounds:{min:number;max:number}|null,
):ReferenceLineVisibility{
  const valid=referenceLines.filter(line=>isFiniteNumber(line.value));
  if(!bounds)return {visible:[],outOfRange:valid};
  return {
    visible:valid.filter(line=>line.value>=bounds.min&&line.value<=bounds.max),
    outOfRange:valid.filter(line=>line.value<bounds.min||line.value>bounds.max),
  };
}


const REFERENCE_TONES:readonly ReferenceLineTone[]=['neutral','warning','danger','extreme','technical'];
const REFERENCE_LINE_TYPES:readonly ReferenceLineType[]=['solid','dashed','dash-dot'];

function isReferenceLine(line:ReferenceLine):boolean{
  return typeof line.id==='string'&&line.id.length>0&&isFiniteNumber(line.value)&&
    typeof line.label==='string'&&line.label.length>0&&
    REFERENCE_TONES.includes(line.tone)&&
    REFERENCE_LINE_TYPES.includes(line.lineType);
}

function normaliseReferenceLines(
  referenceLines:readonly ReferenceLine[],
):ReferenceLine[]{
  const normalised=referenceLines.filter(isReferenceLine).map(line=>({...line}));
  const ids=new Set<string>();
  return normalised.filter(line=>{
    if(ids.has(line.id))return false;
    ids.add(line.id);
    return true;
  });
}

function referenceToneColour(tone:ReferenceLineTone,palette:ChartPalette):string{
  if(tone==='warning')return palette.orange;
  if(tone==='danger'||tone==='extreme')return palette.red;
  if(tone==='technical')return palette.faint;
  return palette.muted;
}

function echartsLineType(lineType:ReferenceLineType):'solid'|'dashed'|number[]{
  if(lineType==='dash-dot')return [8,4,2,4];
  return lineType;
}

type SrfMarkerKind='nontechnical'|'technical'|'mixed';

interface SrfMarkerDatum{
  coord:[string,number];
  name:string;
  markerKind:SrfMarkerKind;
  symbol:'circle'|'diamond';
  symbolSize:number;
  itemStyle:Record<string,unknown>;
}

interface SrfAnnotationResult{
  markers:SrfMarkerDatum[];
  metadataComplete:boolean;
  classifiedCount:number;
}

function srfAnnotations(
  points:readonly NormalizedChartPoint[],
  palette:ChartPalette,
):SrfAnnotationResult{
  const markers:SrfMarkerDatum[]=[];
  let classifiedCount=0;
  for(const point of points){
    if(!isFiniteNumber(point.value)||!srfMetadataComplete(point))continue;
    classifiedCount+=1;
    const eligible=point.alert_eligible_accepted_amount_usd_bn!;
    const hasTechnical=point.has_technical_exercise===true;
    const technicalOnly=point.technical_exercise===true;
    if(eligible>0){
      const mixed=hasTechnical&&!technicalOnly;
      markers.push({
        coord:[point.date,point.value],
        name:mixed?'MIXED · NONTECHNICAL USE COUNTS':'NONTECHNICAL POSITIVE USE',
        markerKind:mixed?'mixed':'nontechnical',
        symbol:'circle',symbolSize:mixed?10:8,
        itemStyle:mixed
          ?{color:palette.red,borderColor:palette.faint,borderWidth:2}
          :{color:palette.red,borderColor:palette.red,borderWidth:1},
      });
    }else if(technicalOnly){
      markers.push({
        coord:[point.date,point.value],name:'TECHNICAL EXERCISE · EXCLUDED',markerKind:'technical',
        symbol:'diamond',symbolSize:10,
        itemStyle:{color:palette.faint,borderColor:palette.panel,borderWidth:1},
      });
    }
  }
  return {
    markers,
    metadataComplete:points.length>0&&classifiedCount===points.length,
    classifiedCount,
  };
}

function dataStatusDescription(status:ChartDataStatus,lastGood:boolean):string{
  if(status==='PARTIAL')return '部分輸入可用；缺失值未被當作零。';
  if(status==='UNAVAILABLE')return '目前輸入不可用。';
  if(status==='LAST_GOOD'||lastGood)return '最後成功值，並非今日新值。';
  return '';
}

function referenceLinesDescription(
  lines:readonly ReferenceLine[],
  visibility:ReferenceLineVisibility,
  unit:string,
):string{
  if(lines.length===0)return '';
  const visibleIds=new Set(visibility.visible.map(line=>line.id));
  return `公式門檻：${lines.map(line=>
    `${line.label}，數值 ${formatMetricValue(line.value,unit)}（${visibleIds.has(line.id)?'圖內可見':'超出目前圖域'}）`
  ).join('；')}。`;
}

function srfAnnotationsDescription(
  result:SrfAnnotationResult,
  finitePointCount:number,
  alertWindow:SrfAlertWindow|undefined,
):string{
  const kindCount=(kind:SrfMarkerKind)=>result.markers.filter(marker=>marker.markerKind===kind).length;
  const markerText=`SRF 標註：非技術性 positive 紅點 ${kindCount('nontechnical')} 個，`+
    `technical-only 灰色菱形 ${kindCount('technical')} 個，mixed 紅點灰框 ${kindCount('mixed')} 個。`;
  const completeness=result.metadataComplete
    ?'分類 metadata 完整。'
    :`DEGRADED：只有 ${result.classifiedCount} / ${finitePointCount} 個有值日期具備完整分類 metadata；未知日期不推斷 marker。`;
  const windowText=alertWindow
    ?`SRF_RISING 最近 ${alertWindow.windowDays} 個 operation days 有 ${alertWindow.positiveDays==null?'未知':alertWindow.positiveDays} 個非技術性 positive；`+
      `規則門檻 ${alertWindow.requiredPositiveDays}-of-${alertWindow.windowDays}。`
    :'SRF_RISING 最新 rolling count 未提供。';
  return `${markerText}${completeness}${windowText}`;
}

export interface MainChartOptionInput{
  metricId:string;
  label:string;
  unit:string;
  points:ChartPoints;
  referenceLines?:readonly ReferenceLine[];
  lastGood?:boolean;
  dataStatus?:ChartDataStatus;
  srfAlertWindow?:SrfAlertWindow;
  srfAnnotationsEnabled?:boolean;
  palette?:ChartPalette;
}

export function buildMainChartOption({
  metricId,label,unit,points,referenceLines=[],lastGood=false,dataStatus='CURRENT',
  srfAlertWindow,srfAnnotationsEnabled=true,palette=FALLBACK_PALETTE,
}:MainChartOptionInput):EChartsOption{
  const ordered=orderedPoints(pointsFrom(points));
  const dates=ordered.map(point=>point.date);
  const values=ordered.map(point=>point.value);
  const finiteValues=values.filter(isFiniteNumber);
  const min=finiteValues.length?Math.min(...finiteValues):null;
  const max=finiteValues.length?Math.max(...finiteValues):null;
  const bounds=niceBounds(finiteValues,5);
  const normalisedReferences=normaliseReferenceLines(referenceLines);
  const referenceVisibility=referenceLineVisibility(normalisedReferences,bounds);
  let lastIndex=-1;
  for(let index=values.length-1;index>=0;index--){
    if(isFiniteNumber(values[index])){lastIndex=index;break;}
  }
  const markLines:Array<Record<string,unknown>>=[];

  const hasExplicitZero=normalisedReferences.some(line=>line.value===0);
  if(min!=null&&max!=null&&min<0&&max>0&&!hasExplicitZero){
    markLines.push({
      id:'data-zero-baseline',
      yAxis:0,
      label:{show:false},
      lineStyle:{color:palette.zero,width:1,type:'solid'},
    });
  }
  for(const line of referenceVisibility.visible){
    const colour=referenceToneColour(line.tone,palette);
    markLines.push({
      id:line.id,
      name:line.label,
      referenceTone:line.tone,
      referenceLineType:line.lineType,
      yAxis:line.value,
      label:{show:true,formatter:line.label,position:'insideEndTop',color:colour,fontSize:11},
      lineStyle:{
        color:colour,
        width:line.tone==='extreme'?1.6:line.tone==='neutral'?1:1.25,
        type:echartsLineType(line.lineType),
      },
    });
  }

  const effectiveLastGood=lastGood||dataStatus==='LAST_GOOD';
  const displayedValue=effectiveLastGood
    ?`最後成功觀察值為 ${formatMetricValue(values[lastIndex],unit)}；並非今日新值。`
    :`最新為 ${formatMetricValue(values[lastIndex],unit)}。`;
  const baseDescription=finiteValues.length
    ?`${label}，${dates[0]} 至 ${dates[dates.length-1]}，${finiteValues.length} 個觀察值，${displayedValue}`
    :`${label}暫無可用觀察值。`;
  const statusText=dataStatusDescription(dataStatus,lastGood);
  const referenceText=referenceLinesDescription(normalisedReferences,referenceVisibility,unit);
  const srfResult=metricId==='srf_accepted'&&srfAnnotationsEnabled?srfAnnotations(ordered,palette):null;
  const srfText=srfResult?srfAnnotationsDescription(srfResult,finiteValues.length,srfAlertWindow):'';
  const description=[
    baseDescription,
    effectiveLastGood&&statusText.startsWith('最後成功')?'':statusText,
    referenceText,
    srfText,
  ].filter(Boolean).join(' ');
  const pointAnnotations=metricId==='srf_accepted'
    ?srfResult?.markers??[]
    :lastIndex>=0?[{
      coord:[dates[lastIndex],values[lastIndex]],
      symbol:'circle',symbolSize:6,itemStyle:{color:palette.main},
    }]:[];
  const degradedSrf=metricId==='srf_accepted'&&srfResult&&!srfResult.metadataComplete;

  return {
    animation:false,
    aria:{enabled:true,label:{description}},
    graphic:degradedSrf?[{
      type:'text',right:14,top:10,silent:true,z:10,
      style:{
        text:'DEGRADED · SRF CLASSIFICATION UNAVAILABLE',
        fill:palette.faint,font:'10px DM Mono',backgroundColor:palette.panel,padding:[3,5],
      },
    }]:undefined,
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
      formatter:(params:unknown)=>mainTooltipFormatter(params,unit,metricId,ordered,srfAlertWindow,srfAnnotationsEnabled),
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
      lineStyle:{color:palette.main,width:1.6},
      itemStyle:{color:palette.main},
      areaStyle:{color:palette.area},
      emphasis:{focus:'series'},
      markPoint:pointAnnotations.length?{
        silent:metricId!=='srf_accepted',label:{show:false},
        data:pointAnnotations,
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
  lastGoodIds?:readonly string[];
  palette?:ChartPalette;
}

export function buildOverlayChartOption({
  series,selected,lastGoodIds=EMPTY_LAST_GOOD_IDS,palette=FALLBACK_PALETTE,
}:OverlayChartOptionInput):EChartsOption{
  const union=normaliseOverlayData(series);
  const enabled=selectedSet(selected);
  const configById=new Map<string,{id:string;label:string;colour:string;cssVariable:string}>(
    OVERLAY_CONFIG.map(item=>[item.id,item]),
  );
  const knownIds=OVERLAY_CONFIG.map(item=>item.id).filter(id=>id in union.series);
  const unknownIds=Object.keys(union.series).filter(id=>!configById.has(id)).sort();
  const ids=[...knownIds,...unknownIds].filter(id=>enabled.has(id));
  const lastGood=new Set(lastGoodIds);
  const fallbackColours=[palette.faint,palette.orange,palette.button];

  const lineSeries=ids.map((id,index)=>{
    const config=configById.get(id)??{
      id,label:id.toUpperCase(),colour:fallbackColours[index%fallbackColours.length],cssVariable:'',
    };
    const colour=id in palette.series?palette.series[id as OverlayId]:config.colour;
    return {
      name:config.label,type:'line',data:union.series[id],connectNulls:true,showSymbol:false,
      lineStyle:{color:colour,width:1.4},itemStyle:{color:colour},
      endLabel:{show:true,formatter:config.label,color:colour,fontFamily:'DM Mono',fontSize:11,distance:4},
      labelLayout:{moveOverlap:'shiftY'},
      emphasis:{focus:'series'},
    };
  });
  const description=ids.length
    ?`隔夜利率疊加圖，${union.dates[0]??'—'} 至 ${union.dates.at(-1)??'—'}，顯示 ${ids.map(id=>{
      const label=configById.get(id)?.label??id.toUpperCase();
      return lastGood.has(id)?`${label}（${LAST_GOOD_A11Y}）`:label;
    }).join('、')}。`
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
  referenceLines?:readonly ReferenceLine[];
  lastGood?:boolean;
  dataStatus?:ChartDataStatus;
  srfAlertWindow?:SrfAlertWindow;
  srfAnnotationsEnabled?:boolean;
}

export function MainMetricChart({
  metricId,label,unit,points,referenceLines=[],lastGood=false,dataStatus='CURRENT',srfAlertWindow,srfAnnotationsEnabled=true,
}:MainMetricChartProps){
  const palette=useMemo(()=>resolveChartPalette(),[]);
  const option=useMemo(()=>buildMainChartOption({
    metricId,label,unit,points,referenceLines,lastGood,dataStatus,srfAlertWindow,srfAnnotationsEnabled,palette,
  }),[metricId,label,unit,points,referenceLines,lastGood,dataStatus,srfAlertWindow,srfAnnotationsEnabled,palette]);
  return <div className="metric-chart metric-chart--main" style={{width:'100%',height:'100%',minHeight:0}}>
    <ReactECharts option={option} notMerge lazyUpdate style={{width:'100%',height:'100%'}}/>
  </div>;
}

export interface RateOverlayChartProps{
  series:OverlayData;
  selected:SelectedSeries;
  lastGoodIds?:readonly string[];
}

export function RateOverlayChart({series,selected,lastGoodIds=EMPTY_LAST_GOOD_IDS}:RateOverlayChartProps){
  const palette=useMemo(()=>resolveChartPalette(),[]);
  const option=useMemo(()=>buildOverlayChartOption({series,selected,lastGoodIds,palette}),[
    series,selected,lastGoodIds,palette,
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
  lastGood?:boolean;
}

export function Sparkline({points,selected,label,lastGood=false}:SparklineProps){
  const observations=useMemo(()=>pointsFrom(points),[points]);
  const segments=useMemo(()=>sparkSegments(observations),[observations]);
  const count=observations.filter(point=>isFiniteNumber(point.value)).length;
  const summary=`${label} 走勢，${count} 個觀察值。${lastGood?`${LAST_GOOD_A11Y}。`:''}`;
  return <svg
    className={`sparkline tape-spark${selected?' is-selected':''}`}
    width="48" height="19" viewBox="0 0 48 19" preserveAspectRatio="none"
    role="img" aria-label={summary}
  >
    <title>{summary}</title>
    {segments.map((segment,index)=><path
      key={`area-${index}`} d={segment.area}
      fill={selected?'var(--area-selected)':'var(--area-muted)'} stroke="none"
    />)}
    {segments.map((segment,index)=><path
      key={`line-${index}`} d={segment.line} fill="none"
      stroke={selected?'var(--action)':'var(--sparkoff)'} strokeWidth="1.25"
      vectorEffect="non-scaling-stroke"
    />)}
  </svg>;
}
