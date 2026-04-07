import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';
import { config } from '@/config';
import { useAuthStore } from '@/store/authStore';

type EventHandler = (data: unknown) => void;

/** Parsed WebSocket message from the backend ConnectionManager. */
interface WSMessage {
  type: string;
  timestamp?: string;
  data?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Singleton WebSocket manager — shared across all hook instances
// ---------------------------------------------------------------------------

type Listener = { type: string; handler: EventHandler };

let socket: WebSocket | null = null;
let listeners: Listener[] = [];
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 1000;
let pingInterval: ReturnType<typeof setInterval> | null = null;
let mountCount = 0;
const MAX_RECONNECT_DELAY = 30_000;

// Reactive connection state — avoids polling in consumers
let _connected = false;
let _connectionListeners = new Set<() => void>();
function _setConnected(v: boolean) {
  if (_connected !== v) {
    _connected = v;
    _connectionListeners.forEach((fn) => fn());
  }
}
function _subscribeConnection(cb: () => void) {
  _connectionListeners.add(cb);
  return () => { _connectionListeners.delete(cb); };
}
function _getConnected() { return _connected; }

function getWsUrl(username: string): string {
  return `${config.wsUrl}?username=${encodeURIComponent(username)}`;
}

function notifyListeners(msg: WSMessage) {
  for (const l of listeners) {
    if (l.type === msg.type) {
      try {
        l.handler(msg);
      } catch (err) {
        console.error(`[WS] listener error for "${msg.type}":`, err);
      }
    }
  }
}

function cleanup() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }
  if (socket) {
    // Remove handlers to avoid reconnect on intentional close
    socket.onclose = null;
    socket.onerror = null;
    socket.onmessage = null;
    // Close both OPEN and CONNECTING sockets to prevent leaked connections
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close();
    }
    socket = null;
  }
  reconnectDelay = 1000;
  _setConnected(false);
}

function connect(username: string) {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const url = getWsUrl(username);
  if (config.isDev) {
    console.log('[WS] Connecting to', url);
  }

  socket = new WebSocket(url);

  socket.onopen = () => {
    if (config.isDev) {
      console.log('[WS] Connected');
    }
    reconnectDelay = 1000; // reset backoff on successful connect
    _setConnected(true);

    // Heartbeat every 25s to keep connection alive through proxies
    if (pingInterval) clearInterval(pingInterval);
    pingInterval = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send('ping');
      }
    }, 25_000);
  };

  socket.onmessage = (event) => {
    try {
      const msg: WSMessage = JSON.parse(event.data);
      if (msg.type === 'pong') return; // ignore heartbeat responses
      notifyListeners(msg);
    } catch {
      if (config.isDev) {
        console.warn('[WS] Non-JSON message:', event.data);
      }
    }
  };

  socket.onclose = () => {
    if (config.isDev) {
      console.log(`[WS] Disconnected, reconnecting in ${reconnectDelay}ms`);
    }
    if (pingInterval) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
    socket = null;
    _setConnected(false);
    scheduleReconnect(username);
  };

  socket.onerror = (err) => {
    if (config.isDev) {
      console.error('[WS] Error:', err);
    }
    // onclose will fire after onerror, which handles reconnection
  };
}

function scheduleReconnect(username: string) {
  if (reconnectTimer) return;
  if (mountCount <= 0) return; // no active hook instances

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect(username);
  }, reconnectDelay);

  reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
}

// ---------------------------------------------------------------------------
// React hook
// ---------------------------------------------------------------------------

export const useWebSocket = () => {
  const username = useAuthStore((s) => s.username);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const shouldConnect = !config.isLocalMode && isAuthenticated && !!username;
  const usernameRef = useRef(username);
  usernameRef.current = username;

  // Manage connection lifecycle
  useEffect(() => {
    if (!shouldConnect || !username) return;

    mountCount++;
    connect(username);

    return () => {
      mountCount--;
      if (mountCount <= 0) {
        cleanup();
        mountCount = 0;
      }
    };
  }, [shouldConnect, username]);

  const subscribe = useCallback((eventType: string, handler: EventHandler) => {
    const entry: Listener = { type: eventType, handler };
    listeners.push(entry);
    return () => {
      listeners = listeners.filter((l) => l !== entry);
    };
  }, []);

  const send = useCallback((data: string | Record<string, unknown>) => {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }, []);

  const isConnected = useCallback(() => {
    return (socket?.readyState === WebSocket.OPEN) || false;
  }, []);

  // Reactive connection state — no polling needed
  const connected = useSyncExternalStore(_subscribeConnection, _getConnected);

  return {
    subscribe,
    send,
    isConnected,
    connected,
  };
};
