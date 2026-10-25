// A compact data table. Numbers are right-aligned with tabular figures; the first column is the row label.

const isNum = (v) => typeof v === "number" || (typeof v === "string" && /^-?\d+(\.\d+)?%?$/.test(v.trim()));

export default function Table({ columns, rows, label, small = false }) {
  if (!rows || !rows.length) return null;
  return (
    <div className={`table-wrap${small ? " table-wrap--small" : ""}`}>
      {label && <div className="table-label">{label}</div>}
      <table className="data">
        <thead>
          <tr>{columns.map((c, i) => <th key={i} className={i > 0 && isNum(rows[0][i]) ? "num" : ""}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((v, j) => (
                <td key={j} className={j === 0 ? "rowhead" : isNum(v) ? "num" : ""}>{v === null || v === undefined ? "" : String(v)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
