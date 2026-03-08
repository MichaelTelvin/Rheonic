import { PublicLayout } from "../components/PublicLayout";
import { Seo } from "../components/Seo";

export function TermsPage(): JSX.Element {
  return (
    <PublicLayout navAuthHref="/login" navAuthLabel="Sign in" shellClassName="public-shell-marketing" showDocsLink={false}>
      <Seo
        title="Terms of Use | Rheonic"
        description="Terms of use for Rheonic beta users."
        path="/terms"
      />
      <section className="landing-marketing">
        <div className="docs-article-shell">
          <article className="docs-article">
            <p className="docs-eyebrow">Legal</p>
            <h1>Terms of Use</h1>
            <p className="docs-lead">
              Last updated: March 8, 2026. These terms govern your use of the Rheonic beta service.
            </p>

            <h2>Beta service</h2>
            <p>
              Rheonic is provided for business evaluation and operational monitoring of LLM traffic. Beta features may
              change, break, or be removed without notice.
            </p>

            <h2>Authorized use</h2>
            <p>
              You may use the service only for lawful business purposes and only with systems and data you are
              authorized to monitor. You must keep your account credentials and project keys secure.
            </p>

            <h2>Restrictions</h2>
            <p>
              You may not misuse the service, interfere with its operation, attempt unauthorized access, reverse
              engineer non-public parts of the product except where law permits, or use Rheonic to process prohibited
              data without approval.
            </p>

            <h2>No guarantee</h2>
            <p>
              Protect decisions, alerts, incidents, and telemetry are provided on a best-effort basis. Rheonic does
              not guarantee prevention of outages, provider overages, or security incidents.
            </p>

            <h2>Customer responsibility</h2>
            <p>
              You remain responsible for your applications, provider accounts, prompt content, legal compliance, and
              production rollout decisions. Beta should be validated before production dependence.
            </p>

            <h2>Suspension and termination</h2>
            <p>
              We may suspend or terminate access if use creates security risk, violates these terms, or threatens the
              stability of the service.
            </p>

            <h2>Liability</h2>
            <p>
              To the maximum extent allowed by law, the beta service is provided &quot;as is&quot; without warranties,
              and Rheonic will not be liable for indirect, incidental, special, consequential, or lost-profit damages.
            </p>

            <h2>Contact</h2>
            <p>
              Questions about these terms can be sent to <a href="mailto:legal@rheonic.ai">legal@rheonic.ai</a>.
            </p>
          </article>
        </div>
      </section>
    </PublicLayout>
  );
}
