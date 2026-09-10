import AppShell from "@/components/AppShell";
import { RealtimeProvider } from "@/lib/realtime";

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <RealtimeProvider>
      <AppShell>{children}</AppShell>
    </RealtimeProvider>
  );
}
