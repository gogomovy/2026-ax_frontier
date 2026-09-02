import { useTranslation } from "react-i18next";
import { DecisionDbCard } from "../components/DecisionDbCard";
import { PolicyDbCard } from "../components/PolicyDbCard";

export function KnowledgeHome() {
  const { t } = useTranslation();
  return (
    <section>
      <p className="page-kicker">{t("home.title")}</p>
      <h1>{t("home.title")}</h1>
      <div className="home-cards">
        <PolicyDbCard />
        <DecisionDbCard />
      </div>
    </section>
  );
}
