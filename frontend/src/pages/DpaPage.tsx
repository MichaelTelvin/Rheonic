import { PublicLayout } from "../components/PublicLayout";
import { Seo } from "../components/Seo";

export function DpaPage(): JSX.Element {
  return (
    <PublicLayout navAuthHref="/login" navAuthLabel="Sign in" shellClassName="public-shell-marketing" showDocsLink={false}>
      <Seo
        title="Data Processing Addendum | Rheonic"
        description="Data Processing Addendum for Rheonic beta users."
        path="/dpa"
      />
      <section className="landing-marketing">
        <div className="docs-article-shell">
          <article className="docs-article">
            <p className="docs-eyebrow">Legal</p>
            <h1>Data Processing Addendum</h1>
            <p className="docs-lead">
              Last updated: March 2026. This Data Processing Addendum is between the customer and Michael Telvin, an
              individual entrepreneur operating Rheonic.
            </p>

            <h2>Roles</h2>
            <p>
              Customer is the data controller. Rheonic acts as a data processor for service data processed on behalf
              of the Customer.
            </p>

            <h2>Scope</h2>
            <p>
              Rheonic processes data solely to provide the service, including monitoring LLM usage, detecting
              anomalies, and executing protect-mode actions.
            </p>

            <h2>Subprocessors</h2>
            <p>
              Rheonic uses subprocessors listed in the Privacy Policy. Rheonic remains responsible for subprocessors&apos;
              compliance with this DPA.
            </p>

            <h2>Data handling</h2>
            <p>
              Rheonic processes data according to Customer instructions via the service configuration and API usage.
            </p>

            <h2>Security</h2>
            <p>
              Rheonic implements reasonable technical and organizational measures to protect data, as described in the
              Privacy Policy.
            </p>

            <h2>Data subject rights</h2>
            <p>Rheonic will assist the Customer in responding to data subject requests where applicable.</p>

            <h2>Deletion</h2>
            <p>
              Customer may request deletion of account-related data by contacting{" "}
              <a href="mailto:privacy@rheonic.dev">privacy@rheonic.dev</a>. Data may also be deleted as part of beta
              system resets.
            </p>

            <h2>Changes</h2>
            <p>This DPA may be updated alongside the Privacy Policy as the service evolves.</p>

            <h2>Contact</h2>
            <p>
              <a href="mailto:privacy@rheonic.dev">privacy@rheonic.dev</a>
            </p>
          </article>
        </div>
      </section>
    </PublicLayout>
  );
}
