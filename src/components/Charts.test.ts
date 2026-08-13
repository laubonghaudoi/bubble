import {describe,expect,it} from 'vitest';
import {
  buildMainChartOption,
  buildOverlayChartOption,
  buildOverlayUnion,
  OVERLAY_CONFIG,
  resolveChartPalette,
  formatMetricValue,
  referenceLineVisibility,
  type ReferenceLine,
} from './Charts';

type LooseOption=Record<string,any>;

describe('chart option builders',()=>{
  it('keeps meaningful precision for sub-billion operation data',()=>{
    expect(formatMetricValue(0.725,'USD bn')).toBe('0.725B');
    expect(formatMetricValue(12.738,'USD bn')).toBe('12.7B');
    expect(formatMetricValue(0,'USD bn')).toBe('0B');
  });
  it('renders supplied spread thresholds with their exact values and styles, without a silent 3 bp default',()=>{
    const option=buildMainChartOption({
      metricId:'sofr_iorb_spread_bp',label:'SOFR−IORB',unit:'bp',
      points:[
        {date:'2026-08-08',value:-5},
        {date:'2026-08-09',value:1},
        {date:'2026-08-10',value:5},
      ],
      referenceLines:[
        {id:'video-yellow-spread',value:0,label:'持續 >0 · 黃燈條件',tone:'warning',lineType:'dashed'},
        {id:'video-red-spread',value:4,label:'+4 bp · 紅燈利差線',tone:'danger',lineType:'solid'},
      ],
    }) as LooseOption;
    const markLines=option.series[0].markLine.data;

    expect(option.animation).toBe(false);
    expect(option.yAxis).toMatchObject({min:-5,max:5});
    expect(option.series[0]).toMatchObject({
      lineStyle:{color:'#0064FA'},
      itemStyle:{color:'#0064FA'},
    });
    expect(markLines.filter((line:LooseOption)=>line.yAxis===0)).toHaveLength(1);
    expect(markLines).toEqual([
      expect.objectContaining({
        id:'video-yellow-spread',yAxis:0,referenceTone:'warning',referenceLineType:'dashed',
        lineStyle:expect.objectContaining({color:'#8A4A00',type:'dashed'}),
      }),
      expect.objectContaining({
        id:'video-red-spread',yAxis:4,referenceTone:'danger',referenceLineType:'solid',
        lineStyle:expect.objectContaining({color:'#E51503',type:'solid'}),
      }),
    ]);
    expect(markLines.some((line:LooseOption)=>line.yAxis===3)).toBe(false);
    expect(option.aria.label.description).toContain('數值 4.0 bp（圖內可見）');
  });

  it('keeps out-of-range annotations out of the plot and the data-derived domain',()=>{
    const points=[{date:'2026-08-05',value:100},{date:'2026-08-12',value:110}];
    const baseline=buildMainChartOption({
      metricId:'tga_daily',label:'TGA',unit:'USD bn',points,
    }) as LooseOption;
    const annotated=buildMainChartOption({
      metricId:'tga_daily',label:'TGA',unit:'USD bn',points,
      referenceLines:[{
        id:'far-target',value:1_000,label:'1.00T · VIDEO SOURCE TARGET',tone:'neutral',lineType:'dashed',
      }],
    }) as LooseOption;

    expect(annotated.yAxis).toMatchObject({
      min:baseline.yAxis.min,max:baseline.yAxis.max,interval:baseline.yAxis.interval,
    });
    expect(annotated.series[0].markLine).toBeUndefined();
    expect(annotated.aria.label.description).toContain('數值 1,000B（超出目前圖域）');
  });

  it('styles all three reserve formula lines from typed reference metadata',()=>{
    const option=buildMainChartOption({
      metricId:'reserve_balances',label:'Reserve balances',unit:'USD bn',
      points:[{date:'2026-08-05',value:2400},{date:'2026-08-12',value:3000}],
      referenceLines:[
        {id:'yellow',value:2910,label:'2.91T · VIDEO YELLOW ZONE',tone:'warning',lineType:'dashed'},
        {id:'red',value:2790,label:'2.79T · VIDEO RED CONFIRMATION',tone:'danger',lineType:'dashed'},
        {id:'extreme',value:2510,label:'2.51T · VIDEO EXTREME LINE',tone:'extreme',lineType:'dash-dot'},
      ],
    }) as LooseOption;
    const lines=option.series[0].markLine.data;

    expect(lines.map((line:LooseOption)=>line.yAxis)).toEqual([2910,2790,2510]);
    expect(lines[0]).toMatchObject({referenceTone:'warning',lineStyle:{color:'#8A4A00',type:'dashed'}});
    expect(lines[1]).toMatchObject({referenceTone:'danger',lineStyle:{color:'#E51503',type:'dashed'}});
    expect(lines[2]).toMatchObject({
      referenceTone:'extreme',referenceLineType:'dash-dot',lineStyle:{color:'#E51503',type:[8,4,2,4]},
    });
  });

  it('renders the TGA operational floor and source target as two independent lines',()=>{
    const option=buildMainChartOption({
      metricId:'tga_daily',label:'TGA',unit:'USD bn',
      points:[{date:'2026-08-05',value:900},{date:'2026-08-12',value:1050}],
      referenceLines:[
        {id:'tga-floor',value:950,label:'0.95T · OPERATIONAL FLOOR',tone:'warning',lineType:'dashed'},
        {id:'tga-target',value:1000,label:'1.00T · VIDEO SOURCE TARGET',tone:'neutral',lineType:'solid'},
      ],
    }) as LooseOption;

    expect(option.series[0].markLine.data).toEqual([
      expect.objectContaining({id:'tga-floor',yAxis:950,referenceTone:'warning'}),
      expect.objectContaining({id:'tga-target',yAxis:1000,referenceTone:'neutral'}),
    ]);
    expect(option.aria.label.description).toContain('0.95T · OPERATIONAL FLOOR，數值 950B（圖內可見）');
    expect(option.aria.label.description).toContain('1.00T · VIDEO SOURCE TARGET，數值 1,000B（圖內可見）');
  });

  it('classifies reference-line visibility without changing or dropping valid inputs',()=>{
    const lines:ReferenceLine[]=[
      {id:'inside',value:0,label:'inside',tone:'warning',lineType:'dashed'},
      {id:'outside',value:3,label:'outside',tone:'danger',lineType:'solid'},
    ];

    expect(referenceLineVisibility(lines,{min:-1,max:1})).toEqual({
      visible:[lines[0]],outOfRange:[lines[1]],
    });
  });

  it('formats percentage axes and tooltips with one percent suffix',()=>{
    const option=buildMainChartOption({
      metricId:'sofr',label:'SOFR',unit:'percent',
      points:[{date:'2026-08-10',value:3.65}],
    }) as LooseOption;
    const axisFormatter=option.yAxis.axisLabel.formatter as (value:number)=>string;
    const tooltipFormatter=option.tooltip.formatter as (params:unknown)=>string;
    const tooltip=tooltipFormatter([{axisValue:'2026-08-10',value:3.65}]);

    expect(axisFormatter(3.65)).toBe('3.65%');
    expect(tooltip.match(/%/g)).toHaveLength(1);
  });

  it('gives a flat series a narrow non-zero chart domain',()=>{
    const option=buildMainChartOption({
      metricId:'iorb',label:'IORB',unit:'percent',
      points:[{date:'2026-08-09',value:3.65},{date:'2026-08-10',value:3.65}],
    }) as LooseOption;

    expect(option.yAxis.min).toBeLessThan(3.65);
    expect(option.yAxis.max).toBeGreaterThan(3.65);
    expect(option.yAxis.max-option.yAxis.min).toBeLessThan(0.5);
  });

  it('describes a LAST_GOOD data status as last-good rather than latest',()=>{
    const option=buildMainChartOption({
      metricId:'sofr_iorb_spread_bp',label:'SOFR−IORB',unit:'bp',dataStatus:'LAST_GOOD',
      points:[{date:'2026-08-10',value:1.2}],
    }) as LooseOption;
    const description=option.aria.label.description as string;

    expect(description).toContain('最後成功觀察值為 1.2 bp');
    expect(description).toContain('並非今日新值');
    expect(description).not.toContain('最新為');
  });

  it('renders SRF classification markers and exposes the full 2-of-3 evidence in tooltip and ARIA',()=>{
    const option=buildMainChartOption({
      metricId:'srf_accepted',label:'SRF accepted',unit:'USD bn',
      srfAlertWindow:{positiveDays:2,requiredPositiveDays:2,windowDays:3},
      points:[
        {
          date:'2026-08-10',value:2,accepted_amount_usd_bn:2,
          alert_eligible_accepted_amount_usd_bn:2,exercise_accepted_amount_usd_bn:0,
          has_technical_exercise:false,technical_exercise:false,
          operation_count:2,exercise_operation_count:0,classification_complete:true,
        },
        {
          date:'2026-08-11',value:4,accepted_amount_usd_bn:4,
          alert_eligible_accepted_amount_usd_bn:0,exercise_accepted_amount_usd_bn:4,
          has_technical_exercise:true,technical_exercise:true,
          operation_count:1,exercise_operation_count:1,classification_complete:true,
        },
        {
          date:'2026-08-12',value:5,accepted_amount_usd_bn:5,
          alert_eligible_accepted_amount_usd_bn:3,exercise_accepted_amount_usd_bn:2,
          has_technical_exercise:true,technical_exercise:false,
          operation_count:3,exercise_operation_count:1,classification_complete:true,
        },
      ],
    }) as LooseOption;
    const markers=option.series[0].markPoint.data;
    const tooltip=option.tooltip.formatter([{
      axisValue:'2026-08-12',value:5,dataIndex:2,
    }]);

    expect(markers).toEqual([
      expect.objectContaining({markerKind:'nontechnical',symbol:'circle',itemStyle:{color:'#E51503',borderColor:'#E51503',borderWidth:1}}),
      expect.objectContaining({markerKind:'technical',symbol:'diamond',itemStyle:{color:'#767676',borderColor:'#FFFFFF',borderWidth:1}}),
      expect.objectContaining({markerKind:'mixed',symbol:'circle',itemStyle:{color:'#E51503',borderColor:'#767676',borderWidth:2}}),
    ]);
    expect(tooltip).toContain('TOTAL ACCEPTED&nbsp;&nbsp;<b>5.0B</b>');
    expect(tooltip).toContain('ALERT ELIGIBLE&nbsp;&nbsp;<b>3.0B</b>');
    expect(tooltip).toContain('TECHNICAL ACCEPTED&nbsp;&nbsp;<b>2.0B</b>');
    expect(tooltip).toContain('CLASSIFICATION&nbsp;&nbsp;<b>MIXED</b>');
    expect(tooltip).toContain('OPERATIONS / EXERCISES&nbsp;&nbsp;<b>3 / 1</b>');
    expect(tooltip).toContain('COUNTS TOWARD RULE&nbsp;&nbsp;<b>YES · COUNTS TOWARD SRF_RISING');
    expect(tooltip).toContain('LATEST 3-DAY COUNT 2 · RULE 2-OF-3');
    expect(option.aria.label.description).toContain('technical-only 灰色菱形 1 個');
    expect(option.aria.label.description).toContain('mixed 紅點灰框 1 個');
    expect(option.aria.label.description).toContain('規則門檻 2-of-3');
    expect(option.graphic).toBeUndefined();
  });

  it('fails closed with a visible degraded state when SRF classification metadata is missing or incomplete',()=>{
    const option=buildMainChartOption({
      metricId:'srf_accepted',label:'SRF accepted',unit:'USD bn',
      points:[
        {date:'2026-08-10',value:2},
        {
          date:'2026-08-11',value:4,accepted_amount_usd_bn:4,
          alert_eligible_accepted_amount_usd_bn:4,exercise_accepted_amount_usd_bn:0,
          has_technical_exercise:false,technical_exercise:false,classification_complete:false,
        },
      ],
    }) as LooseOption;
    const tooltip=option.tooltip.formatter([{axisValue:'2026-08-11',value:4,dataIndex:1}]);

    expect(option.series[0].markPoint).toBeUndefined();
    expect(option.graphic[0].style.text).toBe('DEGRADED · SRF CLASSIFICATION UNAVAILABLE');
    expect(option.graphic[0].style.font).toBe('11px DM Mono');
    expect(option.aria.label.description).toContain('DEGRADED');
    expect(option.aria.label.description).toContain('未知日期不推斷 marker');
    expect(tooltip).toContain('DEGRADED · SRF CLASSIFICATION METADATA UNAVAILABLE');
    expect(tooltip).toContain('no alert marker is inferred');
  });

  it('sorts the overlay union and aligns absent observations to null',()=>{
    const union=buildOverlayUnion({
      sofr:[
        {date:'2026-08-10',value:3.63},
        {date:'2026-08-08',value:3.61},
      ],
      iorb:[
        {date:'2026-08-09',value:3.65},
        {date:'2026-08-10',value:3.65},
      ],
    });

    expect(union.dates).toEqual(['2026-08-08','2026-08-09','2026-08-10']);
    expect(union.series.sofr).toEqual([3.61,null,3.63]);
    expect(union.series.iorb).toEqual([null,3.65,3.65]);
  });

  it('uses union-aligned null data, connects gaps, and disables overlay animation',()=>{
    const option=buildOverlayChartOption({
      series:{
        dates:['2026-08-10','2026-08-08','2026-08-09'],
        values:{
          sofr:[3.63,3.61,null],
          iorb:[null,null,3.65],
        },
      },
      selected:{sofr:1,iorb:1},
    }) as LooseOption;

    expect(option.animation).toBe(false);
    expect(option.xAxis.data).toEqual(['2026-08-08','2026-08-09','2026-08-10']);
    expect(option.series[0]).toMatchObject({name:'SOFR',data:[3.61,null,3.63],connectNulls:true});
    expect(option.series[1]).toMatchObject({name:'IORB',data:[null,3.65,null],connectNulls:true});
    expect(option.yAxis.axisLabel.formatter(3.65)).toBe('3.65%');
  });

  it('identifies only non-OK overlay series as last-good in the accessible summary',()=>{
    const option=buildOverlayChartOption({
      series:{
        sofr:[{date:'2026-08-10',value:3.63}],
        iorb:[{date:'2026-08-10',value:3.65}],
      },
      selected:{sofr:true,iorb:true},
      lastGoodIds:['sofr'],
    }) as LooseOption;
    const description=option.aria.label.description as string;

    expect(description).toContain('SOFR（最後成功值，並非今日新值）');
    expect(description).toContain('IORB');
    expect(description).not.toContain('IORB（最後成功值');
  });

  it('keeps the ordered overlay config and fallback canvas colours in one source of truth',()=>{
    expect(OVERLAY_CONFIG).toEqual([
      {id:'sofr',label:'SOFR',colour:'#0064FA',cssVariable:'--series-sofr'},
      {id:'iorb',label:'IORB',colour:'#E51503',cssVariable:'--series-iorb'},
      {id:'effr',label:'EFFR',colour:'#000000',cssVariable:'--series-effr'},
      {id:'obfr',label:'OBFR',colour:'#338736',cssVariable:'--series-obfr'},
      {id:'tgcr',label:'TGCR',colour:'#8A4A00',cssVariable:'--series-tgcr'},
      {id:'bgcr',label:'BGCR',colour:'#767676',cssVariable:'--series-bgcr'},
    ]);

    const palette=resolveChartPalette();
    const option=buildOverlayChartOption({
      series:Object.fromEntries(OVERLAY_CONFIG.map(({id})=>[
        id,[{date:'2026-08-10',value:3.65}],
      ])),
      selected:OVERLAY_CONFIG.map(({id})=>id),
      palette,
    }) as LooseOption;

    expect(option.series.map((item:LooseOption)=>[item.name,item.lineStyle.color])).toEqual([
      ['SOFR','#0064FA'],
      ['IORB','#E51503'],
      ['EFFR','#000000'],
      ['OBFR','#338736'],
      ['TGCR','#8A4A00'],
      ['BGCR','#767676'],
    ]);
  });
});
