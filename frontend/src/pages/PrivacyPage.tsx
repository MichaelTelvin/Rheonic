import { PublicLayout } from "../components/PublicLayout";
import { Seo } from "../components/Seo";

export function PrivacyPage(): JSX.Element {
  return (
    <PublicLayout navAuthHref="/login" navAuthLabel="Sign in" shellClassName="public-shell-marketing" showDocsLink={false}>
      <Seo
        title="Privacy Policy | Rheonic"
        description="Privacy policy for Rheonic beta users."
        path="/privacy"
      />
      <section className="landing-marketing">
        <div className="docs-article-shell">
          <article className="docs-article">
            <p className="docs-eyebrow">Legal</p>
            <h1>Privacy Policy</h1>
            <p className="docs-lead">
              Last updated: March 8, 2026. This policy explains what data Rheonic collects during beta use, why we
              collect it, and how to request deletion or support.
            </p>

            <h2>What we collect</h2>
            <p>
              We collect account, project, and usage data needed to operate the service. This can include email
              address, authentication events, project names, API key metadata, alert settings, incident records, and
              telemetry sent through the Rheonic SDK or API.
            </p>

            <h2>How we use it</h2>
            <p>
              We use this data to authenticate users, deliver the dashboard, process telemetry, detect incidents,
              operate protect-mode decisions, troubleshoot failures, and improve the product during beta.
            </p>

            <h2>What you should not send</h2>
            <p>
              Do not send regulated or highly sensitive personal data into Rheonic during beta unless you have written
              approval from Rheonic and your own legal basis to do so. Beta environments should use test or minimized
              data wherever possible.
            </p>

            <h2>Retention</h2>
            <p>
              We retain account and operational records for as long as needed to run the service, investigate issues,
              and meet legitimate security and audit needs. Beta data may be deleted, reset, or truncated as we evolve
              the product.
            </p>

            <h2>Sharing and subprocessors</h2>
            <p>
              We use infrastructure and software service providers to host the application and operate core product
              functions. We do not sell personal data. We may disclose information when required for security,
              legal compliance, or to protect the service and its users.
            </p>

            <h2>Security</h2>
            <p>
              We use reasonable technical and organizational measures to protect service data, but no system can be
              guaranteed perfectly secure. You are responsible for protecting your own credentials, secrets, and any
              data you choose to send to the platform.
            </p>

            <h2>Your requests</h2>
            <p>
              To request access, correction, deletion, or export of account-related data, contact{" "}
              <a href="mailto:privacy@rheonic.ai">privacy@rheonic.ai</a>. For beta, we will handle requests manually.
            </p>

            <h2>Contact</h2>
            <p>
              Privacy questions can be sent to <a href="mailto:privacy@rheonic.ai">privacy@rheonic.ai</a>.
            </p>
          </article>
        </div>
      </section>
    </PublicLayout>
  );
}
