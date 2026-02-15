import type { Policy } from "../types/policy";
import type { ApiClient } from "./client";

export class PolicyApi {
  public constructor(private readonly client: ApiClient) {}

  public async fetchPolicy(): Promise<Policy> {
    // TODO: Wire policy endpoint path and response mapping.
    return this.client.get<Policy>("/v1/policy");
  }
}
