import { Feather } from "lucide-react";
import { Button } from "./ui/button";

export function Notice({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="notice" role="alert">
      <p>{message}</p>
      {onRetry && (
        <Button variant="secondary" size="small" onClick={onRetry}>
          重试
        </Button>
      )}
    </div>
  );
}

export function Loading({ label = "正在翻开故事…" }: { label?: string }) {
  return (
    <div className="loading-state" role="status">
      <span className="loading-glyph">
        <Feather size={27} />
      </span>
      <p>{label}</p>
    </div>
  );
}
