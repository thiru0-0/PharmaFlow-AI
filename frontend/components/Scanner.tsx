"use client";
import React from "react";

export default function Scanner({ onScan }: { onScan: (text: string) => void }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [on, setOn] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const instRef = React.useRef<any>(null);

  React.useEffect(() => {
    if (!on) return;
    let cancelled = false;
    (async () => {
      try {
        const { Html5Qrcode } = await import("html5-qrcode");
        if (cancelled) return;
        const inst = new Html5Qrcode("pf-scanner-region");
        instRef.current = inst;
        await inst.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: 220 },
          (text: string) => { onScan(text); stop(); },
          () => {}
        );
      } catch (e: any) {
        setErr("Camera unavailable — use the manual / demo scan below.");
        setOn(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [on]);

  function stop() {
    setOn(false);
    const inst = instRef.current;
    if (inst) { inst.stop().catch(() => {}).finally(() => inst.clear?.()); instRef.current = null; }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        {!on ? (
          <button className="btn secondary" onClick={() => { setErr(null); setOn(true); }}>Open camera scanner</button>
        ) : (
          <button className="btn secondary" onClick={stop}>Stop camera</button>
        )}
      </div>
      <div id="pf-scanner-region" ref={ref} style={{ width: on ? 280 : 0, height: on ? 280 : 0, overflow: "hidden", borderRadius: 8 }} />
      {err && <p style={{ color: "var(--warn)", fontSize: 13 }}>{err}</p>}
    </div>
  );
}
