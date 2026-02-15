export class OpenAIAdapter {
  public extractUsage(_response: unknown): Record<string, unknown> {
    // TODO: Parse OpenAI response usage schema.
    return {};
  }
}
