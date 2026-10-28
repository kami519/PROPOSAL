import { ArrowDownToLine } from 'lucide-react'

export function BrandMark({ size = 17 }: { size?: number }) {
  return (
    <span className="brand-mark" aria-hidden="true">
      <ArrowDownToLine size={size} strokeWidth={2.4} />
    </span>
  )
}
