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
    // sr-only on a wrapping <div>, not the <table> itself: Tailwind's
    // sr-only relies on clip-path to hide content, which doesn't shrink an
    // element's own layout box the way it does for ordinary elements —
    // applied directly to a <table>, the table still lays out at its full
    // natural width/height (confirmed: 246px+ wide, contributing real
    // horizontal overflow on narrow viewports even though nothing is
    // visually painted). A <div> has no such special sizing behavior, so
    // wrapping it here keeps the table itself unconstrained (real rows/
    // columns, still genuinely present for a screen reader) while the
    // wrapper collapses to the expected 1x1px box.
    <div className="sr-only">
      <table>
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
    </div>
  );
}
