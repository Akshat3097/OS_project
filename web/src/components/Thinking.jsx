// While the tutor works: a tiny Gantt bar whose blocks fill one after another.
export default function Thinking({ label = "Thinking" }) {
  return (
    <div className="thinking" role="status" aria-live="polite">
      <span className="thinking__bar" aria-hidden="true"><i /><i /><i /><i /></span>
      <span>{label}</span>
    </div>
  );
}
