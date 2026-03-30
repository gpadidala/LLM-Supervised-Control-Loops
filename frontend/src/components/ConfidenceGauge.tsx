interface ConfidenceGaugeProps {
  value: number // 0-1
  size?: number
  label?: string
}

export default function ConfidenceGauge({
  value,
  size = 160,
  label = 'Confidence',
}: ConfidenceGaugeProps) {
  const clampedValue = Math.max(0, Math.min(1, value))
  const percentage = Math.round(clampedValue * 100)

  // SVG parameters for semicircle
  const cx = size / 2
  const cy = size / 2 + 10
  const radius = size / 2 - 20
  const startAngle = Math.PI
  const endAngle = 0

  // Arc path helper
  const polarToCartesian = (angle: number) => ({
    x: cx + radius * Math.cos(angle),
    y: cy - radius * Math.sin(angle),
  })

  // Background arc (full semicircle)
  const bgStart = polarToCartesian(startAngle)
  const bgEnd = polarToCartesian(endAngle)
  const bgPath = `M ${bgStart.x} ${bgStart.y} A ${radius} ${radius} 0 0 1 ${bgEnd.x} ${bgEnd.y}`

  // Zone colors
  const zones = [
    { from: 0, to: 0.4, color: '#ef4444' },      // red
    { from: 0.4, to: 0.65, color: '#eab308' },    // yellow
    { from: 0.65, to: 0.85, color: '#86efac' },    // light green
    { from: 0.85, to: 1.0, color: '#22c55e' },     // bright green
  ]

  // Needle angle (PI = 0%, 0 = 100%)
  const needleAngle = Math.PI - clampedValue * Math.PI
  const needleEnd = {
    x: cx + (radius - 5) * Math.cos(needleAngle),
    y: cy - (radius - 5) * Math.sin(needleAngle),
  }

  // Get color for current value
  const getColor = (v: number) => {
    for (const zone of zones) {
      if (v >= zone.from && v < zone.to) return zone.color
    }
    return zones[zones.length - 1].color
  }

  const currentColor = getColor(clampedValue)

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size / 2 + 30} viewBox={`0 0 ${size} ${size / 2 + 30}`}>
        {/* Background arc */}
        <path
          d={bgPath}
          fill="none"
          stroke="#334155"
          strokeWidth={12}
          strokeLinecap="round"
        />

        {/* Zone arcs */}
        {zones.map((zone, i) => {
          const zoneStartAngle = Math.PI - zone.from * Math.PI
          const zoneEndAngle = Math.PI - zone.to * Math.PI
          const start = polarToCartesian(zoneStartAngle)
          const end = polarToCartesian(zoneEndAngle)
          const largeArc = zone.to - zone.from > 0.5 ? 1 : 0
          return (
            <path
              key={i}
              d={`M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArc} 1 ${end.x} ${end.y}`}
              fill="none"
              stroke={zone.color}
              strokeWidth={12}
              strokeLinecap="round"
              opacity={0.3}
            />
          )
        })}

        {/* Value arc */}
        {clampedValue > 0.01 && (() => {
          const valEnd = polarToCartesian(needleAngle)
          const largeArc = clampedValue > 0.5 ? 1 : 0
          return (
            <path
              d={`M ${bgStart.x} ${bgStart.y} A ${radius} ${radius} 0 ${largeArc} 1 ${valEnd.x} ${valEnd.y}`}
              fill="none"
              stroke={currentColor}
              strokeWidth={12}
              strokeLinecap="round"
            />
          )
        })()}

        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={needleEnd.x}
          y2={needleEnd.y}
          stroke="#e2e8f0"
          strokeWidth={2}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={4} fill="#e2e8f0" />

        {/* Value text */}
        <text
          x={cx}
          y={cy + 20}
          textAnchor="middle"
          fill={currentColor}
          fontSize={size / 6}
          fontWeight="bold"
        >
          {percentage}%
        </text>
      </svg>
      <span className="text-xs text-slate-400 -mt-1">{label}</span>
    </div>
  )
}
