import { useState } from 'react'
import { ChevronDown } from 'lucide-react'

/**
 * Collapsible section with animated chevron
 */
export default function CollapsibleSection({
  title,
  icon: Icon,
  iconColor = 'text-gray-400',
  children,
  defaultOpen = true,
  className = ''
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className={`bg-gray-900 rounded-lg ${className}`}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full p-4 flex items-center justify-between text-left hover:bg-gray-800/50 rounded-lg transition-colors"
      >
        <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
          {Icon && <Icon className={`w-4 h-4 ${iconColor}`} />}
          {title}
        </h3>
        <ChevronDown
          className={`w-4 h-4 text-gray-500 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>
      <div className={`overflow-hidden transition-all duration-200 ${isOpen ? 'max-h-[1000px] opacity-100' : 'max-h-0 opacity-0'}`}>
        <div className="px-4 pb-4">
          {children}
        </div>
      </div>
    </div>
  )
}
