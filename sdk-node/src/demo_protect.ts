import { createClient, instrumentAnthropic, instrumentGoogle, instrumentOpenAI, LLMTBGBlockedError } from "./index.js";

const backendBaseUrl = process.env.LLMTBG_BACKEND_URL ?? "http://localhost:8000";
const providerStubUrl = process.env.LLMTBG_PROVIDER_URL ?? "http://localhost:8099";

function printProviderStubHelp(): void {
    console.error(`Provider stub is unreachable at ${providerStubUrl}.`);
    console.error("Start it with `python3 tests/e2e/provider_stub.py` or set LLMTBG_PROVIDER_URL to a reachable endpoint.");
}

async function providerCount(): Promise<number> {
    const res = await fetch(`${providerStubUrl}/count`);
    if (!res.ok) {
        throw new Error(`provider_stub_count_failed:${res.status}`);
    }
    const payload = await res.json() as { count?: number };
    return Number(payload.count ?? 0);
}

async function resetProvider(): Promise<void> {
    const res = await fetch(`${providerStubUrl}/reset`, { method: "POST" });
    if (!res.ok) {
        throw new Error(`provider_stub_reset_failed:${res.status}`);
    }
}

async function callProviderStub(payload: unknown): Promise<void> {
    const res = await fetch(`${providerStubUrl}/call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        throw new Error(`provider_stub_call_failed:${res.status}`);
    }
}

async function main() {
    const ingestKey = process.env.LLMTBG_INGEST_KEY;
    if (!ingestKey) {
        console.error("LLMTBG_INGEST_KEY is required (create/copy a key from the dashboard).");
        process.exit(1);
    }
    const provider = (process.env.LLMTBG_PROVIDER ?? "").trim().toLowerCase();
    if (!provider) {
        console.error("LLMTBG_PROVIDER is required (openai | anthropic | google).");
        process.exit(1);
    }
    if (!["openai", "anthropic", "google"].includes(provider)) {
        console.error(`LLMTBG_PROVIDER is unsupported: ${provider}`);
        process.exit(1);
    }
    const model = (process.env.LLMTBG_MODEL ?? "").trim();
    if (!model) {
        console.error(`LLMTBG_MODEL is required for provider ${provider}.`);
        process.exit(1);
    }

    try {
        await resetProvider();
    } catch {
        printProviderStubHelp();
        process.exit(1);
    }

    const client = createClient({
        baseUrl: backendBaseUrl,
        ingestKey,
        protectEnabled: true,
        environment: process.env.LLMTBG_ENV ?? "dev",
        debug: process.env.LLMTBG_DEBUG === "1" || process.env.LLMTBG_DEBUG === "true",
        // keep it simple; we want immediate behavior for manual testing
        flushIntervalMs: 60_000,
    });

    // Fake provider clients that hit your local provider stub
    const openai = {
        chat: {
            completions: {
                create: async (payload: any) => {
                    await callProviderStub(payload);
                    return { model: payload.model, usage: { total_tokens: 10 } };
                },
            },
        },
    };
    const anthropic = {
        messages: {
            create: async (payload: any) => {
                await callProviderStub(payload);
                return {
                    model: payload.model,
                    usage: { input_tokens: 6, output_tokens: 4 },
                };
            },
        },
    };
    const googleModel = {
        model,
        generateContent: async (payload: any) => {
            const requestPayload = typeof payload === "string" ? { prompt: payload } : payload;
            await callProviderStub(requestPayload);
            return {
                response: {
                    usageMetadata: { totalTokenCount: 10 },
                },
            };
        },
    };

    instrumentOpenAI(openai as any, { client, feature: "manual-protect-demo" });
    instrumentAnthropic(anthropic as any, { client, feature: "manual-protect-demo" });
    instrumentGoogle(googleModel as any, { client, feature: "manual-protect-demo" });

    const before = await providerCount();

    const scenario = (process.env.LLMTBG_SCENARIO ?? "allow").toLowerCase();
    const maxTokens = Number(process.env.LLMTBG_MAX_TOKENS ?? (scenario === "block" ? 2000 : 128));
    const inputTokens = Number(process.env.LLMTBG_INPUT_TOKENS ?? 10);
    const openaiRequest = {
        model,
        messages: [
            {
                role: "user",
                content: `Protect demo request. scenario=${scenario}; input_tokens_hint=${inputTokens}`,
            },
        ],
        max_tokens: maxTokens,
    };
    const anthropicRequest = {
        model,
        messages: [{ role: "user", content: `Protect demo request. scenario=${scenario}` }],
        max_tokens: maxTokens,
    };
    const googleRequest = `Protect demo request. scenario=${scenario}`;
    console.log(`[DEMO] provider=${provider} model=${model} scenario=${scenario}`);
    console.log("[DEMO] provider scoping active: counters/incidents/decisions are isolated by provider");

    try {
        if (provider === "anthropic") {
            await (anthropic as any).messages.create(anthropicRequest);
        } else if (provider === "google") {
            await (googleModel as any).generateContent(googleRequest);
        } else {
            await (openai as any).chat.completions.create(openaiRequest);
        }
        console.log(`[OK] Provider call executed (provider=${provider}, scenario=${scenario}).`);
    } catch (err) {
        if (err instanceof LLMTBGBlockedError) {
            console.log(`[BLOCKED] LLMTBGBlockedError thrown (provider=${provider}, scenario=${scenario}).`);
        } else {
            printProviderStubHelp();
            console.error("[ERROR] Unexpected error:", err);
            process.exitCode = 1;
        }
    } finally {
        await client.flush();
        console.log("[DEMO] sdk delivery stats:", client.getStats());
        client.close();
    }

    const after = await providerCount();
    console.log({ provider_calls_delta: after - before, before, after });
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});
