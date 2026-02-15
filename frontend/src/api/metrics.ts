import type { Metrics } from "../types/metrics";
import type { ApiClient } from "./client";

export class MetricsApi {
  public constructor(private readonly client: ApiClient) {}

  public async fetchMetrics(): Promise<Metrics> {
    // TODO: Wire metrics endpoint path and response mapping.
    return this.client.get<Metrics>("/v1/metrics");
  }
}
