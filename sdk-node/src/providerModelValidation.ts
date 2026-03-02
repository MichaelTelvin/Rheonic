export class RHEONICValidationError extends Error {
  public readonly provider: string;
  public readonly model: string;
  public readonly expectedProviders: readonly string[];

  public constructor(message: string, provider: string, model: string, expectedProviders: readonly string[]) {
    super(message);
    this.name = "RHEONICValidationError";
    this.provider = provider;
    this.model = model;
    this.expectedProviders = expectedProviders;
  }
}

const SUPPORTED_PROVIDERS = ["openai", "anthropic", "google"] as const;

export function validateProviderModel(provider: string, model: string | null | undefined): void {
  const normalizedProvider = provider.trim().toLowerCase();
  if (!normalizedProvider) {
    throw new RHEONICValidationError(
      "RHEONIC: provider must be explicitly provided.",
      provider,
      String(model ?? ""),
      SUPPORTED_PROVIDERS,
    );
  }

  if (!SUPPORTED_PROVIDERS.includes(normalizedProvider as (typeof SUPPORTED_PROVIDERS)[number])) {
    throw new RHEONICValidationError(
      `RHEONIC: unsupported provider: ${provider}`,
      provider,
      String(model ?? ""),
      SUPPORTED_PROVIDERS,
    );
  }

  const normalizedModel = typeof model === "string" ? model.trim() : "";
  if (!normalizedModel) {
    throw new RHEONICValidationError(
      `RHEONIC: model must be explicitly provided for provider ${normalizedProvider}.`,
      normalizedProvider,
      String(model ?? ""),
      SUPPORTED_PROVIDERS,
    );
  }
}
