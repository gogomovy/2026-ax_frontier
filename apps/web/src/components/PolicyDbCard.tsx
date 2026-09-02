import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function PolicyDbCard() {
  const { t } = useTranslation();
  return (
    <Link to="/policies" className="db-card" data-testid="knowledge-home-policy-card">
      <h2>{t("home.policyCard")}</h2>
      <p>{t("home.policyCardHint")}</p>
    </Link>
  );
}
