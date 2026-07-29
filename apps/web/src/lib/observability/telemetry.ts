type MetadataInput = {
  correlationId?: string;
  operation: string;
  routeTemplate?: string;
  method?: string;
  statusCode?: number;
  url?: string;
  headers?: string;
  query?: string;
};

export function metadataSignal(input: MetadataInput): Record<string, string | number> {
  if ("url" in input || "headers" in input || "query" in input) throw new Error("unsafe telemetry field");
  const values = {
    correlation_id: input.correlationId,
    operation: input.operation,
    route_template: input.routeTemplate,
    http_method: input.method,
    status_code: input.statusCode,
  };
  return Object.fromEntries(
    Object.entries(values).filter((entry): entry is [string, string | number] => entry[1] !== undefined),
  );
}
