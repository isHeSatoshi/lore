import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Measurement = {
  complete: boolean;
  accuracy: number | null;
  questions_seen: number;
};

export default function AccuracyChart({
  chart,
  systems,
  flat,
}: {
  chart: Record<string, number>[];
  systems: Record<string, Measurement[]>;
  flat?: Measurement;
}) {
  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart
        data={chart}
        margin={{ top: 25, right: 25, left: 0, bottom: 20 }}
      >
        <CartesianGrid vertical={false} stroke="#e6e9df" />
        <XAxis
          type="number"
          dataKey="seen"
          domain={["dataMin", "dataMax"]}
          tickLine={false}
          label={{
            value: "Stream questions seen",
            position: "insideBottom",
            offset: -12,
          }}
        />
        <YAxis unit="%" domain={[0, 100]} axisLine={false} tickLine={false} />
        <Tooltip
          formatter={(value) =>
            `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`
          }
        />
        <Legend verticalAlign="top" />
        {["floor", "ceiling"].map((name) => {
          const p = systems[name]?.[0];
          return p?.complete && p.accuracy != null ? (
            <ReferenceLine
              key={name}
              y={p.accuracy}
              stroke={name === "floor" ? "#68745f" : "#7d6a3f"}
              strokeDasharray="5 5"
              label={{ value: name, position: "insideTopRight" }}
            />
          ) : null;
        })}
        <Line
          type="linear"
          dataKey="lore"
          name="Lore"
          stroke="#295f4d"
          strokeWidth={3}
          dot={{ r: 4 }}
          connectNulls={false}
        />
        <Line
          type="linear"
          dataKey="vector"
          name="Vector memory"
          stroke="#67628b"
          strokeWidth={2}
          dot={{ r: 4 }}
          connectNulls={false}
        />
        {flat?.complete && flat.accuracy != null && (
          <ReferenceDot
            x={flat.questions_seen}
            y={flat.accuracy}
            r={6}
            fill="#94543f"
            label="Flat"
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
