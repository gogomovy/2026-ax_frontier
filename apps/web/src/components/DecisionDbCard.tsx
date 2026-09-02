import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function DecisionDbCard() {
  const { t } = useTranslation();
  return (
    <Link to="/decisions" className="db-card" data-testid="knowledge-home-decision-card">
      <h2>{t("home.decisionCard")}</h2>
      <p>{t("home.decisionCardHint")}</p>
    </Link>
  );
}
