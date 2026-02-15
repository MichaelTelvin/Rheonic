export class LLMTokenBurnGuardClient {
  public constructor(
    public readonly apiKey: string,
    public readonly baseUrl: string,
  ) {
    // TODO: Add HTTP transport configuration.
  }
}
