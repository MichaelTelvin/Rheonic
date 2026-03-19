import { LegalDocumentPage } from "../components/LegalDocumentPage";

export function DpaPage(): JSX.Element {
  return (
    <LegalDocumentPage
      title="Data Processing Addendum"
      description="Data Processing Addendum for Rheonic beta users."
      path="/dpa"
      markdownPath="/docs/dpa.md"
    />
  );
}
