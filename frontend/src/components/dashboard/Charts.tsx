import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts';
import type { CycleRecord } from '../../types';

interface PPLChartProps {
  history: CycleRecord[];
}

export function PPLChart({ history }: PPLChartProps) {
  const data = history.map(c => ({
    cycle: `C${c.cycle_num}`,
    forget_ppl: c.forget_ppl,
    retain_ppl: c.retain_ppl,
  }));

  return (
    <div className="bg-bg-card border border-border p-4">
      <h3 className="font-display text-sm text-text-muted tracking-wider uppercase mb-4">PPL HISTORY</h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data}>
          <XAxis
            dataKey="cycle"
            tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1c2128' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0d1117',
              border: '1px solid #1c2128',
              fontFamily: 'JetBrains Mono',
              fontSize: 11,
            }}
            labelStyle={{ color: '#8b949e' }}
          />
          <Legend
            wrapperStyle={{ fontFamily: 'JetBrains Mono', fontSize: 10 }}
            align="right"
            verticalAlign="top"
          />
          <Line
            type="monotone"
            dataKey="forget_ppl"
            stroke="#00e5a0"
            strokeWidth={2}
            dot={{ r: 3, fill: '#00e5a0' }}
            name="Forget PPL"
          />
          <Line
            type="monotone"
            dataKey="retain_ppl"
            stroke="#ff3b30"
            strokeWidth={2}
            dot={{ r: 3, fill: '#ff3b30' }}
            name="Retain PPL"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

interface MAEChartProps {
  history: CycleRecord[];
}

export function MAEChart({ history }: MAEChartProps) {
  const data = history.map(c => ({
    cycle: `C${c.cycle_num}`,
    mae: c.mae_validation,
  }));

  return (
    <div className="bg-bg-card border border-border p-4">
      <h3 className="font-display text-sm text-text-muted tracking-wider uppercase mb-4">PREDICTION MAE</h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data}>
          <XAxis
            dataKey="cycle"
            tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1c2128' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#8b949e', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            axisLine={false}
            tickLine={false}
            domain={[0, 'auto']}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0d1117',
              border: '1px solid #1c2128',
              fontFamily: 'JetBrains Mono',
              fontSize: 11,
            }}
            labelStyle={{ color: '#8b949e' }}
          />
          <ReferenceLine
            y={2.0}
            stroke="#f5a623"
            strokeDasharray="4 4"
            label={{
              value: 'target',
              position: 'right',
              fill: '#f5a623',
              fontSize: 10,
              fontFamily: 'JetBrains Mono',
            }}
          />
          <Line
            type="monotone"
            dataKey="mae"
            stroke="#f5a623"
            strokeWidth={2}
            dot={{ r: 3, fill: '#f5a623' }}
            name="MAE"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
