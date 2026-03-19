import { LegalDocumentPage } from "../components/LegalDocumentPage";

export function TermsPage(): JSX.Element {
  return (
    <LegalDocumentPage
      title="Terms of Use"
      description="Terms of use for Rheonic beta users."
      path="/terms"
      markdownPath="/docs/terms.md"
    />
  );
}
