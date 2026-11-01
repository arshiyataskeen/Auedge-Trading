export default function LoadingCard({ label = 'Loading…' }: { label?: string }) {
  return (
    <div data-testid="loading-card" style={{ minHeight: 120 }}
      className="flex items-center justify-center rounded border border-line bg-panel text-[12px] text-muted">
      {label}
    </div>
  )
}
