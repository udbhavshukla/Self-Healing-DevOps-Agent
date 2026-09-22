interface Props {
  onStart: () => void;
  running: boolean;
  disabledReason?: string;
}

export default function StartWorkflowButton({
  onStart,
  running,
  disabledReason,
}: Props) {
  return (
    <div className="start-row">
      <button
        type="button"
        className="start-button"
        onClick={onStart}
        disabled={running}
        title={disabledReason}
      >
        {running ? "Running…" : "Start Workflow"}
      </button>
      {disabledReason !== undefined && (
        <span className="muted">{disabledReason}</span>
      )}
    </div>
  );
}
