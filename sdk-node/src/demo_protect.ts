import { createClient, instrumentOpenAI, LLMTBGBlockedError } from "./index.js";

const backendBaseUrl = process.env.LLMTBG_BACKEND_URL ?? "http://localhost:8000";
const providerStubUrl = process.env.LLMTBG_PROVIDER_URL ?? "http://localhost:8099";

async function providerCount(): Promise<number> {
    const res = await fetch(`${providerStubUrl}/count`);
    const payload = await res.json() as { count?: number };
    return Number(payload.count ?? 0);
}

async function resetProvider(): Promise<void> {
    await fetch(`${providerStubUrl}/reset`, { method: "POST" });
}

async function main() {
    const ingestKey = process.env.LLMTBG_INGEST_KEY;
    if (!ingestKey) {
        console.error("LLMTBG_INGEST_KEY is required (create/copy a key from the dashboard).");
        process.exit(1);
    }

    await resetProvider();

    const client = createClient({
        baseUrl: backendBaseUrl,
        ingestKey,
        protectEnabled: true,
        environment: process.env.LLMTBG_ENV ?? "dev",
        debug: process.env.LLMTBG_DEBUG === "1" || process.env.LLMTBG_DEBUG === "true",
        // keep it simple; we want immediate behavior for manual testing
        flushIntervalMs: 60_000,
    });

    // Fake OpenAI client that hits your local provider stub
    const openai = {
        chat: {
            completions: {
                create: async (payload: any) => {
                    await fetch(`${providerStubUrl}/call`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload),
                    });
                    return { model: payload.model ?? "gpt-4o-mini", usage: { total_tokens: 10 } };
                },
            },
        },
    };

    instrumentOpenAI(openai as any, { client, feature: "manual-protect-demo" });

    const before = await providerCount();

    const scenario = (process.env.LLMTBG_SCENARIO ?? "allow").toLowerCase();
    const maxTokens = Number(process.env.LLMTBG_MAX_TOKENS ?? (scenario === "block" ? 2000 : 128));
    const inputTokens = Number(process.env.LLMTBG_INPUT_TOKENS ?? 10);
    const providerRequest = {
        model: "gpt-4o-mini",
        messages: [
            {
                role: "user",
                content: `Protect demo request. scenario=${scenario}; input_tokens_hint=${inputTokens}`,
            },
        ],
        max_tokens: maxTokens,
    };

    try {
        await (openai as any).chat.completions.create(providerRequest);
        console.log(`[OK] Provider call executed (scenario=${scenario}).`);
    } catch (err) {
        if (err instanceof LLMTBGBlockedError) {
            console.log(`[BLOCKED] LLMTBGBlockedError thrown (scenario=${scenario}).`);
        } else {
            console.error("[ERROR] Unexpected error:", err);
            process.exitCode = 1;
        }
    } finally {
        await client.flush();
        client.close();
    }

    const after = await providerCount();
    console.log({ provider_calls_delta: after - before, before, after });
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});
