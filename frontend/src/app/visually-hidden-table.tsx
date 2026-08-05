// Text alternative for a chart, carrying exactly the values the chart
// renders visually — screen-reader users get the same numbers, not a
// weaker summary. `sr-only` (visually hidden, still in the accessibility
// tree) rather than a toggle, since these are small enough tables that
// hiding them behind an extra interaction would just be friction.
interface VisuallyHiddenTableProps {
  caption: string;
  headers: string[];
  rows: (string | number)[][];
}

export function VisuallyHiddenTable({ caption, headers, rows }: VisuallyHiddenTableProps) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr>
          {headers.map((header) => (
            <th key={header} scope="col">
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, rowIndex) => (
          <tr key={rowIndex}>
            {row.map((cell, cellIndex) => (
              <td key={cellIndex}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
