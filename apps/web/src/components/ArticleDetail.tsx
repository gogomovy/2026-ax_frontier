import { useTranslation } from "react-i18next";
import type { Article } from "../types/knowledge";

type Props = {
  article: Article;
  onConfirm: (id: string) => Promise<void>;
  onUnconfirm: (id: string) => Promise<void>;
};

export function ArticleDetail({ article, onConfirm, onUnconfirm }: Props) {
  const { t } = useTranslation();
  return (
    <article data-testid="article-detail">
      <h3>{article.title}</h3>
      {article.url ? (
        <p>
          <a href={article.url}>{article.url}</a>
        </p>
      ) : null}
      <p>{article.confirmed ? t("articles.confirmed") : t("articles.candidates")}</p>
      <div className="row-actions">
        {article.confirmed ? (
          <button
            type="button"
            className="ghost"
            data-testid="article-unconfirm-button"
            onClick={() => void onUnconfirm(article.id)}
          >
            {t("articles.unconfirm")}
          </button>
        ) : (
          <button
            type="button"
            className="primary"
            data-testid="article-confirm-button"
            onClick={() => void onConfirm(article.id)}
          >
            {t("articles.confirm")}
          </button>
        )}
      </div>
    </article>
  );
}
