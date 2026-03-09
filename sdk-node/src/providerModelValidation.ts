import { sdkNodeConfig } from "./config.js";

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

export function validateProviderModel(provider: string, model: string | null | undefined): void {
  const normalizedProvider = provider.trim().toLowerCase();
  if (!normalizedProvider) {
    throw new RHEONICValidationError(
      "RHEONIC: provider must be explicitly provided.",
      provider,
      String(model ?? ""),
      sdkNodeConfig.supportedProviders,
    );
  }

  if (!sdkNodeConfig.supportedProviders.includes(normalizedProvider as (typeof sdkNodeConfig.supportedProviders)[number])) {
    throw new RHEONICValidationError(
      `RHEONIC: unsupported provider: ${provider}`,
      provider,
      String(model ?? ""),
      sdkNodeConfig.supportedProviders,
    );
  }

  const normalizedModel = typeof model === "string" ? model.trim() : "";
  if (!normalizedModel) {
    throw new RHEONICValidationError(
      `RHEONIC: model must be explicitly provided for provider ${normalizedProvider}.`,
      normalizedProvider,
      String(model ?? ""),
      sdkNodeConfig.supportedProviders,
    );
  }
}
