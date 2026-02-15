import type { Incident } from "../types/incident";
import type { ApiClient } from "./client";

export class IncidentsApi {
  public constructor(private readonly client: ApiClient) {}

  public async fetchIncidents(): Promise<Incident[]> {
    // TODO: Wire incidents endpoint path and response mapping.
    return this.client.get<Incident[]>("/v1/incidents");
  }
}
