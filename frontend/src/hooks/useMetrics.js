import { useEffect, useRef, useState } from "react";

// Subscribes to the live metrics WebSocket and returns the latest snapshot.
export function useMetrics() {
  const [data, setData] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    let stop = false;
    function connect() {
      if (stop) return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/metrics`);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onmessage = (e) => {
        try {
          setData(JSON.parse(e.data));
        } catch {}
      };
      ws.onclose = () => {
        setConnected(false);
        if (!stop) setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
    }
    connect();
    return () => {
      stop = true;
      wsRef.current?.close();
    };
  }, []);

  return { data, connected };
}
