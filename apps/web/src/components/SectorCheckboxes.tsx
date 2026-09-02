import { useTranslation } from "react-i18next";
import { SECTOR_IDS, type SectorId } from "../sectors";

type Props = {
  value: SectorId[];
  onChange: (next: SectorId[]) => void;
  testId: string;
};

export function SectorCheckboxes({ value, onChange, testId }: Props) {
  const { t } = useTranslation();

  return (
    <div className="sectors" data-testid={testId}>
      {SECTOR_IDS.map((id) => {
        const checked = value.includes(id);
        return (
          <label key={id}>
            <input
              type="checkbox"
              data-testid={`${testId}-${id}`}
              checked={checked}
              onChange={() => {
                onChange(checked ? value.filter((item) => item !== id) : [...value, id]);
              }}
            />{" "}
            {t(`sector.${id}`)}
          </label>
        );
      })}
    </div>
  );
}
