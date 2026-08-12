import {describe,expect,it} from 'vitest';
import {
  buildMainChartOption,
  buildOverlayChartOption,
  buildOverlayUnion,
} from './Charts';

type LooseOption=Record<string,any>;

describe('chart option builders',()=>{
  it('adds only the in-domain spread threshold and disables animation',()=>{
    const option=buildMainChartOption({
      metricId:'sofr_iorb_spread',label:'SOFR−IORB',unit:'bp',thresholdBp:3,
      points:[
        {date:'2026-08-08',value:-12},
        {date:'2026-08-09',value:1},
        {date:'2026-08-10',value:4},
      ],
    }) as LooseOption;
    const markLines=option.series[0].markLine.data;

    expect(option.animation).toBe(false);
    expect(option.yAxis).toMatchObject({min:-15,max:5,interval:5});
    expect(markLines).toEqual(expect.arrayContaining([
      expect.objectContaining({
        yAxis:3,
        lineStyle:expect.objectContaining({type:'dashed'}),
        label:expect.objectContaining({formatter:expect.stringContaining('+3 bp')}),
      }),
    ]));
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
});
