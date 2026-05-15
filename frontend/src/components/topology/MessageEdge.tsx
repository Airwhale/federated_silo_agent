type Props = {
  index: number;
  active?: boolean;
};

export function MessageEdge({ index, active = true }: Props) {
  const y = 34 + index * 24;
  return (
    <path
      d={`M 16 ${y} C 80 ${y - 18}, 132 ${y + 18}, 196 ${y}`}
      fill="none"
      stroke={active ? "#38bdf8" : "#475569"}
      strokeWidth="1.5"
      strokeDasharray={active ? "0" : "4 4"}
    />
  );
}
