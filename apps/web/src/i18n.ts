import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import ko from "./locales/ko.json";

void i18n.use(initReactI18next).init({
  lng: "ko",
  fallbackLng: "ko",
  interpolation: { escapeValue: false },
  resources: {
    ko: { translation: ko },
    en: { translation: en },
  },
});

export default i18n;
