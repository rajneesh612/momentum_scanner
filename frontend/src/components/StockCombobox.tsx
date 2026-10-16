import { useEffect, useRef, useState } from 'react'

import { ApiError, listStocks } from '../services/api'
import type { Stock } from '../types'

interface StockComboboxProps {
  id?: string
  value: string
  onSelect: (symbol: string) => void
  placeholder?: string
}

const DEBOUNCE_MS = 300
const PAGE_SIZE = 20

export default function StockCombobox({ id, value, onSelect, placeholder }: StockComboboxProps) {
  // null = not actively editing, so the input just displays `value`.
  // Once the user types, this holds their in-progress query instead.
  const [editingQuery, setEditingQuery] = useState<string | null>(null)
  const [isOpen, setIsOpen] = useState(false)
  const [results, setResults] = useState<Stock[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const displayedValue = editingQuery ?? value

  useEffect(() => {
    if (!isOpen) return

    setStatus('loading')
    setErrorMessage(null)
    const timeout = setTimeout(() => {
      listStocks({ q: displayedValue || undefined, limit: PAGE_SIZE })
        .then((response) => {
          setResults(response.items)
          setStatus('idle')
          setHighlightedIndex(0)
        })
        .catch((error) => {
          setResults([])
          setStatus('error')
          setErrorMessage(error instanceof ApiError ? error.message : 'Search failed.')
        })
    }, DEBOUNCE_MS)

    return () => clearTimeout(timeout)
  }, [displayedValue, isOpen])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setEditingQuery(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function selectStock(stock: Stock) {
    onSelect(stock.symbol)
    setEditingQuery(null)
    setIsOpen(false)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!isOpen) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const chosen = results[highlightedIndex]
      if (chosen) selectStock(chosen)
    } else if (e.key === 'Escape') {
      setIsOpen(false)
      setEditingQuery(null)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={isOpen}
        aria-autocomplete="list"
        autoComplete="off"
        value={displayedValue}
        placeholder={placeholder}
        onFocus={() => setIsOpen(true)}
        onChange={(e) => {
          setEditingQuery(e.target.value.toUpperCase())
          setIsOpen(true)
        }}
        onKeyDown={handleKeyDown}
        className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-slate-500"
      />

      {isOpen && (
        <div className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-slate-700 bg-slate-900 shadow-lg">
          {status === 'loading' && (
            <p className="px-3 py-2 text-sm text-slate-500">Searching…</p>
          )}
          {status === 'error' && (
            <p className="px-3 py-2 text-sm text-rose-400">{errorMessage}</p>
          )}
          {status === 'idle' && results.length === 0 && (
            <p className="px-3 py-2 text-sm text-slate-500">No matching stocks found.</p>
          )}
          {status === 'idle' &&
            results.map((stock, index) => (
              <button
                key={stock.symbol}
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  selectStock(stock)
                }}
                onMouseEnter={() => setHighlightedIndex(index)}
                className={`flex w-full items-baseline justify-between gap-3 px-3 py-2 text-left text-sm ${
                  index === highlightedIndex ? 'bg-slate-800' : ''
                }`}
              >
                <span className="truncate text-slate-200">{stock.name}</span>
                <span className="shrink-0 font-mono text-xs text-slate-400">{stock.symbol}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  )
}
