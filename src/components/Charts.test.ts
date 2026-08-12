import {describe,expect,it} from 'vitest';
import {
  buildMainChartOption,
  buildOverlayChartOption,
  buildOverlayUnion,
  OVERLAY_CONFIG,
  resolveChartPalette,
  formatMetricValue,
} from './Charts';

type LooseOption=Record<string,any>;

describe('chart option builders',()=>{
  it('keeps meaningful precision for sub-billion operation data',()=>{
    expect(formatMetricValue(0.725,'USD bn')).toBe('0.725B');
    expect(formatMetricValue(12.738,'USD bn')).toBe('12.7B');
    expect(formatMetricValue(0,'USD bn')).toBe('0B');
  });
  it('adds only the in-domain spread threshold and disables animation',()=>{
    const option=buildMainChartOption({
      metricId:'sofr_iorb_spread_bp',label:'SOFR−IORB',unit:'bp',thresholdBp:3,
      points:[
        {date:'2026-08-08',value:-12},
        {date:'2026-08-09',value:1},
        {date:'2026-08-10',value:4},
      ],
    }) as LooseOption;
    const markLines=option.series[0].markLine.data;

    expect(option.animation).toBe(false);
    expect(option.yAxis).toMatchObject({min:-15,max:5,interval:5});
    expect(option.series[0]).toMatchObject({
      lineStyle:{color:'#0064FA'},
      itemStyle:{color:'#0064FA'},
    });
    expect(markLines).toEqual(expect.arrayContaining([
      expect.objectContaining({
        yAxis:3,
        lineStyle:expect.objectContaining({color:'#E51503',type:'dashed'}),
        label:expect.objectContaining({color:'#E51503',formatter:expect.stringContaining('+3 bp')}),
      }),
    ]));
  });

  it('adds only in-domain weekly reserve reference lines',()=>{
    const option=buildMainChartOption({
      metricId:'reserve_balances',label:'Reserve balances',unit:'USD bn',
      points:[{date:'2026-08-05',value:2700},{date:'2026-08-12',value:3000}],
      referenceLines:[
        {value:2900,label:'參考區 2.9T'},
        {value:2800,label:'參考區 2.8T'},
        {value:2500,label:'參考區 2.5T'},
      ],
    }) as LooseOption;
    expect(option.series[0].markLine.data.map((line:LooseOption)=>line.yAxis)).toEqual([2900,2800]);
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

  it('describes a non-OK main series as last-good rather than latest',()=>{
    const option=buildMainChartOption({
      metricId:'sofr_iorb_spread_bp',label:'SOFR−IORB',unit:'bp',lastGood:true,
      points:[{date:'2026-08-10',value:1.2}],
    }) as LooseOption;
    const description=option.aria.label.description as string;

    expect(description).toContain('最後成功觀察值為 1.2 bp');
    expect(description).toContain('並非今日新值');
    expect(description).not.toContain('最新為');
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
