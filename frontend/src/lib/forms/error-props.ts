// Wires a field to its own error message via aria-invalid/aria-describedby
// so a screen reader announces *why* a field is invalid (the message text),
// not just that it is. `fieldId` must match the `id` used on the <input>
// itself and pair with an `id={`${fieldId}-error`}` on the rendered error
// <p>. Returns undefined attributes (not `false`/omitted keys) when there's
// no error, matching react-hook-form's own error-presence semantics.
//
// Accepts `unknown` rather than react-hook-form's FieldError: generic form
// components (e.g. ProjectForm<T>) get back a Merge<FieldError, ...> type
// for each field that isn't structurally assignable to plain FieldError —
// only presence/absence is ever needed here, never the error's own shape.
export function errorProps(fieldId: string, error: unknown) {
  return {
    "aria-invalid": error ? (true as const) : undefined,
    "aria-describedby": error ? `${fieldId}-error` : undefined,
  };
}
