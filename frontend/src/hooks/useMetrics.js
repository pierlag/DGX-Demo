import { useEffect, useRef, useState } from "react";

// Subscribes to the live metrics WebSocket and returns the latest snapshot.
// Falls back to HTTP polling when the WebSocket cannot connect (e.g. Safari
// iOS through a DevTunnel, where the WS upgrade is often blocked).
export function useMetrics() {
  const [data, setData] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const pollRef = useRef(null);
  const wsOkRef = useRef(false);

  useEffect(() => {
    let stop = false;

    function startPolling() {
      if (stop || pollRef.current) return;
      const tick = async () => {
        try {
          const r = await fetch("/api/metrics/snapshot");
          if (!r.ok) throw new Error(String(r.status));
          const snap = await r.json();
          if (!stop) {
            setData(snap);
            setConnected(true);
          }
        } catch {
          if (!stop) setConnected(false);
        }
      };
      tick();
      pollRef.current = setInterval(tick, 2000);
    }

    function stopPolling() {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }

    function connect() {
      if (stop) return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      let ws;
      try {
        ws = new WebSocket(`${proto}://${location.host}/ws/metrics`);
      } catch {
        startPolling();
        return;
      }
      wsRef.current = ws;

      // If the WS does not open quickly, fall back to polling meanwhile.
      const openTimer = setTimeout(() => {
        if (!wsOkRef.current) startPolling();
      }, 3000);

      ws.onopen = () => {
        wsOkRef.current = true;
        clearTimeout(openTimer);
        stopPolling();
        setConnected(true);
      };
      ws.onmessage = (e) => {
        try {
          setData(JSON.parse(e.data));
        } catch {}
      };
      ws.onclose = () => {
        clearTimeout(openTimer);
        wsOkRef.current = false;
        setConnected(false);
        // Keep data flowing via polling, and keep retrying the WS.
        startPolling();
        if (!stop) setTimeout(connect, 1500);
      };
      ws.onerror = () => {
        startPolling();
        ws.close();
      };
    }

    connect();
    return () => {
      stop = true;
      stopPolling();
      wsRef.current?.close();
    };
  }, []);

  return { data, connected };
}
