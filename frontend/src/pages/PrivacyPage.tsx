import { PublicLayout } from "../components/PublicLayout";

export function PrivacyPage(): JSX.Element {
  return (
    <PublicLayout navAuthHref="/login" navAuthLabel="Sign in" shellClassName="public-shell-marketing" showDocsLink={false}>
      <section className="landing-marketing">
        <h1>Privacy</h1>
        <p>Coming soon.</p>
      </section>
    </PublicLayout>
  );
}
