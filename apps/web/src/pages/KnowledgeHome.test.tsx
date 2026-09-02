import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import "../i18n";
import { KnowledgeHome } from "./KnowledgeHome";

describe("KnowledgeHome", () => {
  it("renders the two database cards", () => {
    render(
      <MemoryRouter>
        <KnowledgeHome />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("knowledge-home-policy-card")).toBeTruthy();
    expect(screen.getByTestId("knowledge-home-decision-card")).toBeTruthy();
  });
});
