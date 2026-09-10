"use client";
import React from "react";
import { Camera, CameraOff } from "lucide-react";
import { Button } from "@/lib/ui";

export default function Scanner({ onScan }: { onScan: (text: string) => void }) {
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
      } catch {
        setErr("Camera unavailable — use the manual field or a demo-scan chip below.");
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
      <Button
        type="button"
        variant="secondary"
        size="sm"
        icon={on ? <CameraOff size={14} /> : <Camera size={14} />}
        onClick={() => (on ? stop() : (setErr(null), setOn(true)))}
      >
        {on ? "Stop camera" : "Open camera scanner"}
      </Button>
      <div
        id="pf-scanner-region"
        className="mt-3 overflow-hidden rounded-xl bg-sidebar"
        style={{ width: on ? 280 : 0, height: on ? 280 : 0 }}
      />
      {err && <p className="mt-2 text-[12px] font-medium text-warn">{err}</p>}
    </div>
  );
}
