import { LegalDocumentPage } from "../components/LegalDocumentPage";

export function PrivacyPage(): JSX.Element {
  return (
    <LegalDocumentPage
      title="Privacy Policy"
      description="Privacy policy for Rheonic beta users."
      path="/privacy"
      markdownPath="/docs/privacy.md"
    />
  );
}
