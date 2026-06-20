import { useEffect, useRef, useCallback, useState } from 'react'

const WS_BASE = import.meta.env.VITE_WS_URL ||
  (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
  window.location.host

export function useGameSocket(sessionId, handlers) {
  const ws = useRef(null)
  const handlersRef = useRef(handlers)
  const [connected, setConnected] = useState(false)
  const [engineReady, setEngineReady] = useState(false)
  const reconnectTimer = useRef(null)
  const mountedRef = useRef(true)

  // Keep handlers ref current without re-connecting
  useEffect(() => { handlersRef.current = handlers }, [handlers])

  const connect = useCallback(() => {
    if (!sessionId) return
    if (ws.current?.readyState === WebSocket.OPEN) return

    const url = `${WS_BASE}/ws/game/${sessionId}`
    const socket = new WebSocket(url)
    ws.current = socket

    socket.onopen = () => {
      if (!mountedRef.current) return
      setConnected(true)
      clearTimeout(reconnectTimer.current)
    }

    socket.onmessage = (ev) => {
      if (!mountedRef.current) return
      try {
        const msg = JSON.parse(ev.data)
        const handler = handlersRef.current[msg.type]
        if (handler) handler(msg)
        else if (handlersRef.current['*']) handlersRef.current['*'](msg)

        if (msg.type === 'connected') {
          setEngineReady(msg.engine_ready ?? false)
        }
      } catch (e) {
        console.error('WS parse error', e)
      }
    }

    socket.onclose = () => {
      if (!mountedRef.current) return
      setConnected(false)
      // Reconnect after 2s
      reconnectTimer.current = setTimeout(connect, 2000)
    }

    socket.onerror = (e) => console.error('WS error', e)
  }, [sessionId])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimer.current)
      ws.current?.close()
    }
  }, [connect])

  const send = useCallback((type, data = {}) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type, ...data }))
    }
  }, [])

  return { send, connected, engineReady }
}
