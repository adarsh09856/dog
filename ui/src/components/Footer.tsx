export default function Footer() {
  return (
    <footer className="fixed bottom-0 left-0 right-0 bg-background/80 backdrop-blur-md border-t border-border/60 py-3 px-6 z-40">
      <div className="flex justify-between items-center text-xs text-muted-foreground max-w-7xl mx-auto">
        <span>Kodewaves Sovereign Voice AI Platform</span>
        <div className="flex items-center gap-4">
          <span>Self-Hosted &amp; Private</span>
          <span className="text-border">|</span>
          <span>Version 1.0.0</span>
        </div>
      </div>
    </footer>
  );
}
